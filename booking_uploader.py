import json
import os
import random
import statistics
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

# Modalita interattiva: se il terminale e un TTY o se INTERACTIVE=1
INTERACTIVE = sys.stdin.isatty() or os.environ.get("INTERACTIVE", "") == "1"

# --- Carica dati proprieta dal file JSON ---
DATA_FILE = os.environ.get(
    "PROPERTY_DATA", os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json")
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

EMAIL = os.environ["BK_EMAIL"]
PASSWORD = os.environ["BK_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots_booking"
step_counter = 0


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def screenshot(page, name):
    global step_counter
    step_counter += 1
    path = f"{SCREENSHOT_DIR}/step{step_counter:02d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def save_html(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  HTML salvato: {path}")


def wait(page, ms=5000):
    page.wait_for_timeout(ms)


def human_type(page, selector, text):
    page.click(selector)
    time.sleep(random.uniform(0.3, 0.7))
    for char in text:
        page.keyboard.type(char, delay=random.randint(50, 150))
    time.sleep(random.uniform(0.2, 0.5))


def try_step(page, step_name, func):
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")


def click_continue(page):
    for txt in ["Continua", "Continue", "Avanti", "Next"]:
        try:
            btn = page.get_by_role("button", name=txt)
            if btn.count() > 0:
                btn.first.click()
                wait(page)
                return
        except Exception:
            continue
    # Fallback: button[type=submit]
    try:
        page.click('button[type="submit"]', timeout=5000)
        wait(page)
    except Exception:
        print("  Pulsante continua non trovato")


def download_placeholder_photos(count=5):
    paths = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(count):
        path = os.path.join(tmp_dir, f"photo_{i+1}.jpg")
        urllib.request.urlretrieve(
            f"https://picsum.photos/800/600?random={i+1}", path
        )
        paths.append(path)
        print(f"  Foto scaricata: {path}")
    return paths


def compute_price(cond):
    """Calcola prezzo notte dal JSON: prezzo_notte diretto o mediana listino."""
    prezzo = cond.get("prezzo_notte")
    if prezzo is not None:
        return int(prezzo)
    listino = cond.get("listino_prezzi", [])
    if listino:
        prezzi = [p["prezzo_notte"] for p in listino if p.get("prezzo_notte")]
        if prezzi:
            return int(statistics.median(prezzi))
    return None


# ---------------------------------------------------------------------------
# Booking Extranet: mappatura dotazioni
# REGOLA: spunta SOLO le dotazioni con valore true nel JSON.
# ---------------------------------------------------------------------------

DOTAZIONI_BOOKING = {
    "tv": "TV",
    "piano_cottura": "Piano cottura",
    "frigo_congelatore": "Frigorifero",
    "forno": "Forno",
    "microonde": "Microonde",
    "lavatrice": "Lavatrice",
    "lavastoviglie": "Lavastoviglie",
    "aria_condizionata": "Aria condizionata",
    "riscaldamento": "Riscaldamento",
    "internet_wifi": "WiFi",
    "phon": "Asciugacapelli",
    "ferro_stiro": "Ferro da stiro",
    "terrazza": "Terrazza",
    "giardino": "Giardino",
    "piscina": "Piscina",
    "arredi_esterno": "Mobili da esterno",
    "barbecue": "Barbecue",
    "culla": "Culla",
    "seggiolone": "Seggiolone",
    "animali_ammessi": "Animali domestici",
}


def _build_servizi_booking():
    dot = PROP["dotazioni"]
    servizi = []
    for key, label in DOTAZIONI_BOOKING.items():
        if dot.get(key) is True:
            servizi.append(label)
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi_booking()

# Mappa tipo letto JSON -> label Booking
LETTO_LABELS = {
    "matrimoniale": ["Letto matrimoniale"],
    "francese": ["Letto Queen-size"],
    "singolo": ["Letto singolo"],
    "divano_letto": ["Divano letto matrimoniale", "Divano letto"],
    "divano_letto_singolo": ["Divano letto singolo"],
    "king": ["Letto King-size"],
    "castello": ["Letto a castello"],
}


# ---------------------------------------------------------------------------
# Login Booking Extranet
# ---------------------------------------------------------------------------

def _wait_for_interactive(page, prompt_msg, check_done_fn, timeout_s=300):
    if INTERACTIVE:
        input(f"\n>>> {prompt_msg}\n>>> Premi INVIO quando hai finito... ")
    else:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if check_done_fn(page):
                return
            time.sleep(5)
        raise TimeoutError(f"Timeout ({timeout_s}s) in attesa di: {prompt_msg}")


def _page_has_captcha(page):
    html = page.content().lower()
    return "captcha" in html or "human" in html or "choose all" in html


def _page_has_otp(page):
    html = page.content().lower()
    otp_keywords = ["verification", "verifica", "codice", "code", "confirm", "pin"]
    has_keyword = any(kw in html for kw in otp_keywords)
    has_otp_input = page.locator(
        "input[name*='otp'], input[name*='code'], input[name*='pin'], "
        "input[name*='token'], input[type='tel'], "
        "input[autocomplete='one-time-code']"
    ).count() > 0
    return has_keyword and has_otp_input


def login(page):
    print("Login Booking Extranet...")
    if INTERACTIVE:
        print("  (modalita interattiva - browser visibile)")
    page.goto("https://account.booking.com/sign-in", wait_until="domcontentloaded", timeout=60_000)
    wait(page, 3000)
    screenshot(page, "login_page")
    save_html(page, "login_page")

    # Email
    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    page.wait_for_selector(email_sel, timeout=15_000)
    human_type(page, email_sel, EMAIL)
    wait(page, 1000)
    screenshot(page, "email_inserita")

    page.click('button[type="submit"]', timeout=10_000)
    wait(page, 5000)
    screenshot(page, "dopo_email")

    # CAPTCHA
    if _page_has_captcha(page):
        print("  *** CAPTCHA RILEVATO ***")
        screenshot(page, "captcha")
        save_html(page, "captcha")
        _wait_for_interactive(
            page, "CAPTCHA rilevato! Risolvilo nel browser.",
            lambda p: not _page_has_captcha(p),
        )
        print("  CAPTCHA superato.")
        wait(page, 3000)

    # OTP
    if _page_has_otp(page):
        print("  *** CODICE DI VERIFICA EMAIL RICHIESTO ***")
        screenshot(page, "otp_richiesto")
        save_html(page, "otp_pagina")
        if INTERACTIVE:
            code = input("\n>>> Inserisci il codice di verifica ricevuto via email: ").strip()
            otp_sel = (
                "input[name*='otp'], input[name*='code'], input[name*='pin'], "
                "input[name*='token'], input[type='tel'], "
                "input[autocomplete='one-time-code']"
            )
            page.locator(otp_sel).first.fill(code)
            wait(page, 1000)
            page.click('button[type="submit"]', timeout=10_000)
            wait(page, 5000)
            screenshot(page, "dopo_otp")
        else:
            raise RuntimeError(
                "Booking richiede un codice di verifica email. "
                "Eseguire lo script in locale con INTERACTIVE=1."
            )

    # Secondo CAPTCHA (post-OTP)
    if _page_has_captcha(page):
        print("  *** CAPTCHA post-OTP ***")
        _wait_for_interactive(
            page, "Secondo CAPTCHA! Risolvilo nel browser.",
            lambda p: not _page_has_captcha(p),
        )
        wait(page, 3000)

    # Password
    pw_sel = 'input[type="password"], input[name="password"], #password'
    try:
        page.wait_for_selector(pw_sel, timeout=15_000)
        human_type(page, pw_sel, PASSWORD)
        wait(page, 1000)
        screenshot(page, "password_inserita")
        page.click('button[type="submit"]', timeout=10_000)
        wait(page, 8000)
        screenshot(page, "dopo_login")
    except Exception:
        print("  Campo password non trovato - login senza password.")
        screenshot(page, "no_password")

    print(f"  URL dopo login: {page.url}")


# ---------------------------------------------------------------------------
# Navigazione a "Aggiungi nuova struttura"
# ---------------------------------------------------------------------------

def navigate_to_add_property(page):
    print("Navigazione a 'Aggiungi nuova struttura'...")
    page.goto("https://join.booking.com/", wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "join_page")
    save_html(page, "join_page")
    print(f"  URL: {page.url}")


# ---------------------------------------------------------------------------
# Step 0: Selezione categoria (Appartamento)
# ---------------------------------------------------------------------------

def select_category(page):
    """Clicca 'Appartamento' nella pagina di selezione categoria."""
    print("Selezione categoria: Appartamento")
    screenshot(page, "categoria_page")
    save_html(page, "categoria")

    # La pagina mostra 4 card: Appartamento, Case, Hotel, Strutture alternative
    # Ogni card ha un bottone "Iscrivi la tua struttura"
    # Clicca il primo (Appartamento)
    try:
        card = page.locator("text=Appartamento").first
        # Clicca il bottone "Iscrivi la tua struttura" dentro la card Appartamento
        btn = card.locator("xpath=ancestor::div[.//button or .//a]//a[contains(text(),'Iscrivi')]")
        if btn.count() > 0:
            btn.first.click()
        else:
            # Fallback: clicca il primo "Iscrivi la tua struttura"
            page.locator("text=Iscrivi la tua struttura").first.click()
        print("  Appartamento selezionato")
    except Exception:
        # Fallback: clicca direttamente il primo bottone Iscrivi
        try:
            page.locator("text=Iscrivi la tua struttura").first.click()
            print("  Appartamento selezionato (fallback)")
        except Exception as e:
            print(f"  ERRORE selezione categoria: {e}")
            if INTERACTIVE:
                input(">>> Seleziona 'Appartamento' manualmente, poi premi INVIO: ")

    wait(page)
    screenshot(page, "dopo_categoria")


# ---------------------------------------------------------------------------
# Wizard 13 step: Name -> Address -> ChannelManager -> Bedroom ->
#   Facilities -> Services -> Languages -> HouseRules -> HostProfile ->
#   Photos -> RequestToBook -> PaymentMode -> Price
# ---------------------------------------------------------------------------

def insert_property(page):
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    dot = PROP["dotazioni"]
    cond = PROP.get("condizioni", {})
    mktg = PROP.get("marketing", {})

    # ── Step 1: Name ──
    print("Step 1/13: Nome struttura")

    def do_name():
        screenshot(page, "name_page")
        save_html(page, "step01_name")

        for label in ["Nome della struttura", "Property name"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(ident["nome_struttura"])
                print(f"  Nome: {ident['nome_struttura']}")
                break
        else:
            field = page.locator(
                "input[name*='name'], input[name*='nome'], "
                "input[placeholder*='nome'], input[placeholder*='name']"
            )
            if field.count() > 0:
                field.first.fill(ident["nome_struttura"])
                print(f"  Nome (fallback): {ident['nome_struttura']}")

        wait(page, 1000)
        click_continue(page)
        screenshot(page, "after_name")

    try_step(page, "step01_name", do_name)

    # ── Step 2: Address ──
    print("Step 2/13: Indirizzo")

    def do_address():
        screenshot(page, "address_page")
        save_html(page, "step02_address")

        # Via
        for label in ["Indirizzo", "Street address"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(ident["indirizzo"])
                print(f"  Indirizzo: {ident['indirizzo']}")
                break
        else:
            field = page.locator("input[name*='address'], input[name*='street']")
            if field.count() > 0:
                field.first.fill(ident["indirizzo"])
        wait(page, 1000)

        # Citta
        for label in ["Citta", "City", "Comune"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(ident["comune"])
                print(f"  Citta: {ident['comune']}")
                break
        else:
            field = page.locator("input[name*='city'], input[name*='citta']")
            if field.count() > 0:
                field.first.fill(ident["comune"])
        wait(page, 1000)

        # CAP
        for label in ["CAP", "Codice postale", "Zip code", "Postal code"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(ident["cap"])
                print(f"  CAP: {ident['cap']}")
                break
        else:
            field = page.locator("input[name*='zip'], input[name*='postal'], input[name*='cap']")
            if field.count() > 0:
                field.first.fill(ident["cap"])
        wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_address")

    try_step(page, "step02_address", do_address)

    # ── Step 3: Channel Manager ──
    print("Step 3/13: Channel Manager (skip)")

    def do_channel_manager():
        screenshot(page, "channel_manager_page")
        save_html(page, "step03_channel_manager")

        # Cerca "No" / "Non uso un channel manager" / skip
        for txt in ["No", "Non uso un channel manager",
                     "I don't use a channel manager",
                     "No, I don't"]:
            try:
                btn = page.get_by_text(txt, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Channel Manager: skip ({txt})")
                    break
            except Exception:
                continue

        wait(page, 1000)
        click_continue(page)
        screenshot(page, "after_channel_manager")

    try_step(page, "step03_channel_manager", do_channel_manager)

    # ── Step 4: Bedroom ──
    print("Step 4/13: Configurazione camere e letti")

    def _click_bed_plus(partial_label, clicks):
        label_el = page.get_by_text(partial_label, exact=False)
        if label_el.count() == 0:
            return False
        try:
            plus = label_el.first.locator(
                "xpath=ancestor::*[.//button][1]//button[last()]"
            )
            if plus.is_visible():
                for _ in range(clicks):
                    plus.click()
                    page.wait_for_timeout(400)
                return True
        except Exception:
            pass
        try:
            plus = label_el.first.locator(
                "xpath=following::button[normalize-space()='+'][1]"
            )
            if plus.count() > 0 and plus.is_visible():
                for _ in range(clicks):
                    plus.click()
                    page.wait_for_timeout(400)
                return True
        except Exception:
            pass
        return False

    def do_bedroom():
        screenshot(page, "bedroom_page")
        save_html(page, "step04_bedroom")

        # Numero camere da letto
        for label in ["Camere da letto", "Bedrooms", "Numero di camere"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["camere"]))
                print(f"  Camere: {comp['camere']}")
                break
        wait(page, 1000)

        # Letti per tipo
        letti = comp.get("letti", [])
        for letto in letti:
            tipo = letto["tipo"]
            quantita = letto["quantita"]
            labels = LETTO_LABELS.get(tipo, [])
            if not labels:
                print(f"  Tipo letto sconosciuto: {tipo}, skip")
                continue
            found = False
            for label in labels:
                if _click_bed_plus(label, quantita):
                    print(f"  {label}: +{quantita}")
                    found = True
                    break
            if not found:
                for label in labels:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(str(quantita))
                        print(f"  {label}: {quantita} via fill")
                        found = True
                        break
            if not found:
                print(f"  Label non trovata per '{tipo}', skip")
            wait(page, 500)

        click_continue(page)
        screenshot(page, "after_bedroom")

    try_step(page, "step04_bedroom", do_bedroom)

    # ── Step 5: Facilities ──
    print("Step 5/13: Servizi e dotazioni")

    def do_facilities():
        screenshot(page, "facilities_page")
        save_html(page, "step05_facilities")

        # Bagni
        for label in ["Bagni", "Bathrooms", "Numero di bagni"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["bagni"]))
                print(f"  Bagni: {comp['bagni']}")
                break
        wait(page, 1000)

        # Metri quadri (se presente nel JSON)
        mq = comp.get("metri_quadri")
        if mq:
            for label in ["Dimensione", "Size", "Metri quadri", "Square meters"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(str(mq))
                    print(f"  Metri quadri: {mq}")
                    break
            wait(page, 1000)

        # Dotazioni - SOLO quelle con true nel JSON
        for servizio in SERVIZI:
            try:
                btn = page.get_by_text(servizio, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(500)
                    print(f"  Dotazione: {servizio}")
                else:
                    cb = page.locator(f"label:has-text('{servizio}')")
                    if cb.count() > 0:
                        cb.first.click()
                        page.wait_for_timeout(500)
                        print(f"  Dotazione (label): {servizio}")
                    else:
                        print(f"  Dotazione non trovata: {servizio}")
            except Exception as e:
                print(f"  Errore dotazione {servizio}: {e}")

        wait(page)
        click_continue(page)
        screenshot(page, "after_facilities")

    try_step(page, "step05_facilities", do_facilities)

    # ── Step 6: Services ──
    print("Step 6/13: Servizi extra (colazione, parcheggio)")

    def do_services():
        screenshot(page, "services_page")
        save_html(page, "step06_services")

        # Colazione: non offriamo colazione -> seleziona "No"
        for txt in ["No", "Non offriamo la colazione",
                     "No breakfast", "We don't offer breakfast"]:
            try:
                btn = page.get_by_text(txt, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Colazione: No")
                    break
            except Exception:
                continue
        wait(page, 1000)

        # Parcheggio dal JSON
        has_parking = dot.get("parcheggio_privato") is True or \
            "parcheggio" in (dot.get("altro_dotazioni") or "").lower()
        if has_parking:
            for txt in ["Si", "Yes", "Parcheggio disponibile",
                         "Parking available"]:
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        print("  Parcheggio: Si")
                        break
                except Exception:
                    continue
            wait(page, 1000)
            # Gratuito / incluso
            for txt in ["Gratuito", "Free", "Incluso"]:
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        print(f"  Parcheggio: {txt}")
                        break
                except Exception:
                    continue
        wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_services")

    try_step(page, "step06_services", do_services)

    # ── Step 7: Languages ──
    print("Step 7/13: Lingue parlate")

    def do_languages():
        screenshot(page, "languages_page")
        save_html(page, "step07_languages")

        # Seleziona Italiano (dovrebbe essere gia selezionato)
        for txt in ["Italiano", "Italian"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Lingua: {txt}")
                    break
            except Exception:
                continue
        wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_languages")

    try_step(page, "step07_languages", do_languages)

    # ── Step 8: House Rules ──
    print("Step 8/13: Regole della casa")

    def do_house_rules():
        screenshot(page, "house_rules_page")
        save_html(page, "step08_house_rules")

        # Check-in
        checkin = cond.get("check_in", "")
        if checkin:
            for label in ["Check-in", "Orario check-in", "Check-in from",
                          "Check-in dalle"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(checkin)
                    print(f"  Check-in: {checkin}")
                    break
            wait(page, 1000)

        # Check-out
        checkout = cond.get("check_out", "")
        if checkout:
            for label in ["Check-out", "Orario check-out", "Check-out until",
                          "Check-out entro"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(checkout)
                    print(f"  Check-out: {checkout}")
                    break
            wait(page, 1000)

        # Animali
        animali = dot.get("animali_ammessi", False)
        if animali:
            for txt in ["Si", "Yes", "Animali ammessi"]:
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        print("  Animali: ammessi")
                        break
                except Exception:
                    continue
        else:
            for txt in ["No", "Non ammessi", "No pets"]:
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        print("  Animali: non ammessi")
                        break
                except Exception:
                    continue
        wait(page, 1000)

        # Fumo: non fumare (dalle regole casa)
        regole = cond.get("regole_casa", "") or ""
        if "non fumare" in regole.lower() or "no smoking" in regole.lower():
            for txt in ["Non fumare", "No smoking", "Vietato fumare"]:
                try:
                    btn = page.get_by_text(txt, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        print("  Fumo: vietato")
                        break
                except Exception:
                    continue
        wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_house_rules")

    try_step(page, "step08_house_rules", do_house_rules)

    # ── Step 9: Host Profile ──
    print("Step 9/13: Profilo host (skip)")

    def do_host_profile():
        screenshot(page, "host_profile_page")
        save_html(page, "step09_host_profile")

        # Skip - non compilare nulla, solo continua
        click_continue(page)
        screenshot(page, "after_host_profile")

    try_step(page, "step09_host_profile", do_host_profile)

    # ── Step 10: Photos ──
    print("Step 10/13: Upload foto")

    def do_photos():
        screenshot(page, "photos_page")
        save_html(page, "step10_photos")

        photo_paths = download_placeholder_photos(5)
        uploaded = False

        for selector in ["input[type='file']", "input[accept*='image']"]:
            try:
                fi = page.locator(selector)
                if fi.count() > 0:
                    fi.set_input_files(photo_paths, timeout=10_000)
                    uploaded = True
                    print(f"  Upload via {selector}")
                    break
            except Exception as e:
                print(f"  Upload fallito ({selector}): {e}")

        if not uploaded:
            try:
                fi = page.locator("input[type='file']")
                if fi.count() > 0:
                    fi.evaluate("el => el.style.display = 'block'")
                    fi.set_input_files(photo_paths, timeout=10_000)
                    uploaded = True
                    print("  Upload via forced display")
            except Exception as e:
                print(f"  Forced upload fallito: {e}")

        if uploaded:
            wait(page, 10_000)
            screenshot(page, "photos_uploaded")
        else:
            print("  SKIP foto")

        click_continue(page)
        screenshot(page, "after_photos")

    try_step(page, "step10_photos", do_photos)

    # ── Step 11: Request to Book ──
    print("Step 11/13: Modalita prenotazione")

    def do_request_to_book():
        screenshot(page, "request_to_book_page")
        save_html(page, "step11_request_to_book")

        # Seleziona "Tutte le richieste" / "I'll review each request"
        # per avere controllo sulle prenotazioni
        for txt in ["tutte le richieste", "I'll review",
                     "Voglio approvare", "Request to book"]:
            try:
                btn = page.get_by_text(txt, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    print("  Prenotazione: approvazione manuale")
                    break
            except Exception:
                continue
        wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_request_to_book")

    try_step(page, "step11_request_to_book", do_request_to_book)

    # ── Step 12: Payment Mode ──
    print("Step 12/13: Modalita pagamento")

    def do_payment_mode():
        screenshot(page, "payment_mode_page")
        save_html(page, "step12_payment_mode")

        # Cauzione - solo se presente nel JSON
        cauzione_val = cond.get("cauzione_euro")
        if cauzione_val is not None:
            for label in ["Cauzione", "Deposit", "Damage deposit",
                          "Deposito cauzionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(str(cauzione_val))
                    print(f"  Cauzione: {cauzione_val} EUR")
                    break
            wait(page, 1000)

        click_continue(page)
        screenshot(page, "after_payment_mode")

    try_step(page, "step12_payment_mode", do_payment_mode)

    # ── Step 13: Price ──
    print("Step 13/13: Prezzo")

    def do_price():
        screenshot(page, "price_page")
        save_html(page, "step13_price")

        prezzo = compute_price(cond)
        if prezzo is not None:
            for label in ["Prezzo per notte", "Price per night", "Prezzo",
                          "Tariffa per notte", "Nightly rate"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(str(prezzo))
                    print(f"  Prezzo: {prezzo} EUR/notte")
                    break
            else:
                field = page.locator(
                    "input[name*='price'], input[name*='rate'], "
                    "input[name*='prezzo'], input[name*='tariffa']"
                )
                if field.count() > 0:
                    field.first.fill(str(prezzo))
                    print(f"  Prezzo (fallback): {prezzo} EUR/notte")
        else:
            print("  Prezzo non presente nel JSON - lascio vuoto")
        wait(page, 1000)

        # CIN
        cin = ident.get("cin", "")
        if cin:
            for label in ["CIN", "Codice Identificativo Nazionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cin)
                    print(f"  CIN: {cin}")
                    break
            else:
                field = page.locator(
                    "input[name*='cin'], input[name*='CIN'], "
                    "input[placeholder*='CIN']"
                )
                if field.count() > 0:
                    field.first.fill(cin)
                    print(f"  CIN (fallback): {cin}")
            wait(page, 1000)

        # CIR
        cir = ident.get("cir", "")
        if cir:
            for label in ["CIR", "Codice Identificativo Regionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cir)
                    print(f"  CIR: {cir}")
                    break
            wait(page, 1000)

        # NON cliccare submit finale - solo screenshot
        screenshot(page, "final_review")
        save_html(page, "step13_final")
        print("Wizard completato! NON inviato - verifica manuale.")

    try_step(page, "step13_price", do_price)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    headless = not INTERACTIVE
    print(f"Browser: {'headless' if headless else 'visibile'} "
          f"(INTERACTIVE={INTERACTIVE})")

    # Cartella per salvare la sessione del browser (cookie, localStorage)
    # Cosi al prossimo avvio il login e gia fatto
    session_dir = os.path.join(os.path.dirname(__file__), "browser_session")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            session_dir,
            headless=headless,
            locale="it-IT",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            java_script_enabled=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.")

        try:
            login(page)
            navigate_to_add_property(page)
            screenshot(page, "pagina_iniziale")
            select_category(page)
            insert_property(page)
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            context.close()


if __name__ == "__main__":
    main()
