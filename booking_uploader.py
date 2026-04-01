import json
import os
import random
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

# Modalità interattiva: se il terminale è un TTY o se INTERACTIVE=1
INTERACTIVE = sys.stdin.isatty() or os.environ.get("INTERACTIVE", "") == "1"

# --- Carica dati proprietà dal file JSON ---
DATA_FILE = os.environ.get(
    "PROPERTY_DATA", os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json")
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

EMAIL = os.environ.get("BK_EMAIL", "")
PASSWORD = os.environ.get("BK_PASSWORD", "")

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
    """Digita come un umano con pause random."""
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


# ---------------------------------------------------------------------------
# Booking Extranet: mappatura dotazioni
# REGOLA: spunta SOLO le dotazioni con valore true nel JSON.
#         Se false o assente, NON spuntare. Zero eccezioni.
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
    """Restituisce la lista dei servizi attivi (true) da selezionare su Booking.
    Legge SOLO dal JSON — se un servizio è false, NON viene incluso."""
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


# ---------------------------------------------------------------------------
# Login Booking Extranet
# ---------------------------------------------------------------------------

def _wait_for_interactive(page, prompt_msg, check_done_fn, timeout_s=300):
    """Pausa interattiva: chiede input da terminale oppure aspetta che l'utente
    agisca direttamente sul browser (modalità headless=False).

    - Se INTERACTIVE: mostra un prompt e attende INVIO.
    - Altrimenti (CI): attende fino a ``timeout_s`` che ``check_done_fn(page)``
      restituisca True (polling ogni 5s), poi fallisce.
    """
    if INTERACTIVE:
        input(f"\n>>> {prompt_msg}\n>>> Premi INVIO quando hai finito... ")
    else:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if check_done_fn(page):
                return
            time.sleep(5)
        raise TimeoutError(f"Timeout ({timeout_s}s) in attesa di: {prompt_msg}")


def _has_password_field(page):
    """Restituisce True se nella pagina c'è un campo password visibile."""
    return page.locator('input[type="password"]:visible').count() > 0


def _page_has_captcha(page):
    html = page.content().lower()
    return "captcha" in html or "human" in html or "choose all" in html


def _page_has_otp(page):
    """Rileva se Booking sta chiedendo un codice di verifica email.
    Più restrittivo per evitare falsi positivi sulla homepage."""
    url = page.url.lower()

    # Se siamo sulla homepage di Booking, NON è un OTP
    if "booking.com/index" in url or url.rstrip("/").endswith("booking.com"):
        return False

    # Controlla che siamo su una pagina di autenticazione
    auth_urls = ["account.booking.com", "sign-in", "verify", "auth"]
    if not any(u in url for u in auth_urls):
        return False

    html = page.content().lower()
    otp_keywords = ["verification code", "codice di verifica", "enter the code",
                     "inserisci il codice", "sent you a code", "inviato un codice"]
    has_keyword = any(kw in html for kw in otp_keywords)
    has_otp_input = page.locator(
        "input[name*='otp'], input[name*='code'], input[name*='pin'], "
        "input[name*='token'], input[autocomplete='one-time-code']"
    ).count() > 0
    return has_keyword and has_otp_input


def _dismiss_cookie_banner(page):
    """Chiude il banner cookie se presente."""
    for label in ["Accetto", "Accetta", "Accept", "Accept all"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso ('{label}')")
                wait(page, 1000)
                return
        except Exception:
            continue


def _click_continue(page):
    """Clicca il pulsante Continua/Next nel wizard Booking.
    Prova: data-testid, automation_id, ruolo button, testo."""
    # Selettori specifici Booking
    for sel in [
        "button[data-testid*='continue']",
        "button[data-testid*='next']",
        "button[data-testid*='submit']",
        "[id*='automation_id'][id*='continue']",
        "[id*='automation_id'][id*='next']",
    ]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cliccato continua: {sel}")
                return True
        except Exception:
            continue

    # Fallback testo
    for txt in ["Continua", "Continue", "Avanti", "Next",
                 "Salva e continua", "Save and continue"]:
        try:
            btn = page.get_by_role("button", name=txt)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cliccato: '{txt}'")
                return True
        except Exception:
            continue

    print("  Pulsante Continua non trovato")
    return False


def login_and_navigate(page):
    """Login su Booking e naviga fino al wizard di inserimento proprietà.

    Il login di Booking cambia spesso (CAPTCHA, OTP, password, magic link).
    In modalità interattiva: inserisce l'email, poi chiede all'utente di
    completare il login manualmente nel browser. Più robusto e affidabile.

    Returns the page where the wizard starts (potrebbe essere una nuova scheda).
    """
    print("=== LOGIN BOOKING ===")

    # -- Fase 1: Apri pagina login e inserisci email --
    page.goto("https://account.booking.com/sign-in",
              wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    _dismiss_cookie_banner(page)
    screenshot(page, "login_page")

    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    try:
        page.wait_for_selector(email_sel, timeout=15_000)
        human_type(page, email_sel, EMAIL)
        wait(page, 1000)
        page.click('button[type="submit"]', timeout=10_000)
        wait(page, 3000)
        screenshot(page, "dopo_email")
        print(f"  Email inserita: {EMAIL}")
    except Exception as e:
        print(f"  Errore inserimento email: {e}")

    # -- Fase 2: L'utente completa il login manualmente --
    if INTERACTIVE:
        print("\n" + "=" * 60)
        print("  COMPLETA IL LOGIN NEL BROWSER:")
        print("  - CAPTCHA → risolvilo")
        print("  - Codice email → inseriscilo")
        print("  - Password → inseriscila")
        print("  Continua fino a essere LOGGATO.")
        print("=" * 60)
        input("\n>>> Premi INVIO quando sei loggato... ")
    else:
        # In CI: prova il flusso automatico password
        pw_sel = 'input[type="password"]'
        try:
            page.wait_for_selector(pw_sel, timeout=15_000)
            human_type(page, pw_sel, PASSWORD)
            page.click('button[type="submit"]', timeout=10_000)
            wait(page, 8000)
        except Exception:
            raise RuntimeError("Login automatico fallito. Eseguire in locale con INTERACTIVE=1.")

    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")

    # -- Fase 3: Naviga al wizard "Inserisci il tuo immobile" --
    print("\nNavigazione al wizard...")
    _dismiss_cookie_banner(page)

    # "Inserisci il tuo immobile" apre una NUOVA SCHEDA (target=_blank)
    new_page = None
    for label in ["Inserisci il tuo immobile", "List your property"]:
        try:
            link = page.get_by_role("link", name=label)
            if link.count() > 0:
                with page.context.expect_page(timeout=15_000) as new_page_info:
                    link.first.click()
                new_page = new_page_info.value
                print(f"  Cliccato: '{label}' → nuova scheda")
                break
        except Exception:
            try:
                link = page.get_by_role("link", name=label)
                if link.count() > 0:
                    link.first.click()
                    print(f"  Cliccato: '{label}' (stessa scheda)")
                    break
            except Exception:
                continue

    wizard_page = new_page if new_page else page

    # Se non siamo ancora sul wizard, naviga direttamente
    if "join.booking.com" not in wizard_page.url:
        print("  Navigo direttamente a join.booking.com...")
        wizard_page.goto("https://join.booking.com/",
                         wait_until="domcontentloaded", timeout=60_000)

    wait(wizard_page, 5000)
    _dismiss_cookie_banner(wizard_page)
    screenshot(wizard_page, "landing_join")
    print(f"  URL landing: {wizard_page.url}")

    # Landing page join.booking.com: clicca "Get started" con ID reale
    if "become-a-host" not in wizard_page.url:
        try:
            # Selettore reale dalla pagina: id="getStarted"
            gs_btn = wizard_page.locator("#getStarted, [data-testid='getStarted']")
            if gs_btn.count() > 0:
                gs_btn.first.click()
                print("  Cliccato #getStarted")
            else:
                # Fallback testo
                for label in ["Get started now", "Inizia ora", "Inizia subito"]:
                    btn = wizard_page.get_by_role("button", name=label)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        print(f"  Cliccato: '{label}'")
                        break
                    btn = wizard_page.get_by_role("link", name=label)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        print(f"  Cliccato link: '{label}'")
                        break
        except Exception as e:
            print(f"  Errore Get Started: {e}")
        wait(wizard_page, 5000)

    screenshot(wizard_page, "wizard_start")
    save_html(wizard_page, "wizard_start")
    print(f"  URL wizard: {wizard_page.url}")
    return wizard_page


# ---------------------------------------------------------------------------
# Inserimento proprietà su Booking Extranet
# ---------------------------------------------------------------------------

def insert_property(page):
    """Complete the Booking Extranet property insertion wizard."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    photo_paths = download_placeholder_photos(5)

    # --- Step 1: Seleziona tipo struttura (category.html) ---
    # Selettori reali dal DOM:
    #   Container: #automation_id_screen_container_Category
    #   Appartamento btn: #automation_id_choose_category_apt_btn
    #   Quick Start btn: #automation_id_choose_category_quick_start_btn
    #   Hotel btn: #automation_id_choose_category_hotel_btn
    print("Step 1: Tipo struttura — Appartamento")

    def do_step1():
        _dismiss_cookie_banner(page)
        wait(page, 3000)
        screenshot(page, "tipo_struttura_pagina")
        save_html(page, "step1_tipo")

        # Clicca il bottone "Iscrivi la tua struttura" nella card Appartamento
        apt_btn = page.locator("#automation_id_choose_category_apt_btn")
        if apt_btn.count() > 0 and apt_btn.is_visible():
            apt_btn.click()
            print("  Cliccato #automation_id_choose_category_apt_btn")
        else:
            # Fallback: data-testid
            apt_btn = page.locator("[data-testid='category_card_container_apt'] button")
            if apt_btn.count() > 0:
                apt_btn.first.click()
                print("  Cliccato via data-testid apt")
            else:
                # Fallback: primo bottone "Iscrivi la tua struttura"
                btn = page.locator("[data-testid='category-card-btn']")
                if btn.count() > 0:
                    btn.first.click()
                    print("  Cliccato primo category-card-btn")
                elif INTERACTIVE:
                    input(">>> Clicca 'Iscrivi la tua struttura' sotto Appartamento, poi INVIO... ")
                else:
                    raise RuntimeError("Bottone categoria Appartamento non trovato")

        wait(page, 8000)
        screenshot(page, "dopo_categoria")
        save_html(page, "dopo_categoria")

    try_step(page, "step1_tipo", do_step1)

    # --- Step 2: Quante strutture stai inserendo? → 1 ---
    print("Step 2: Numero strutture")

    def do_step2():
        for label in ["Una", "One", "1"]:
            try:
                btn = page.get_by_text(label, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Selezionato: {label}")
                    break
            except Exception:
                continue
        wait(page)
        # Click continua/next
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_numero")

    try_step(page, "step2_numero", do_step2)

    # --- Step 3: Nome struttura ---
    print("Step 3: Nome struttura")

    def do_step3():
        screenshot(page, "nome_pagina")
        save_html(page, "step3_nome")
        # Prova diversi selettori per il campo nome
        nome_field = page.get_by_label("Nome della struttura")
        if nome_field.count() == 0:
            nome_field = page.get_by_label("Property name")
        if nome_field.count() == 0:
            nome_field = page.locator(
                "input[name*='name'], input[name*='nome'], "
                "input[placeholder*='nome'], input[placeholder*='name']"
            )
        if nome_field.count() > 0:
            nome_field.first.fill(ident["nome_struttura"])
            print(f"  Nome: {ident['nome_struttura']}")
        else:
            print("  Campo nome non trovato")
        wait(page)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_nome")

    try_step(page, "step3_nome", do_step3)

    # --- Step 4: Indirizzo ---
    print("Step 4: Indirizzo")

    def do_step4():
        screenshot(page, "indirizzo_pagina")
        save_html(page, "step4_indirizzo")

        # Indirizzo
        addr_field = page.get_by_label("Indirizzo")
        if addr_field.count() == 0:
            addr_field = page.get_by_label("Street address")
        if addr_field.count() == 0:
            addr_field = page.locator("input[name*='address'], input[name*='street']")
        if addr_field.count() > 0:
            addr_field.first.fill(ident["indirizzo"])
            print(f"  Indirizzo: {ident['indirizzo']}")

        wait(page, 1000)

        # Città
        city_field = page.get_by_label("Città")
        if city_field.count() == 0:
            city_field = page.get_by_label("City")
        if city_field.count() == 0:
            city_field = page.locator("input[name*='city'], input[name*='citta']")
        if city_field.count() > 0:
            city_field.first.fill(ident["comune"])
            print(f"  Città: {ident['comune']}")

        wait(page, 1000)

        # CAP
        cap_field = page.get_by_label("CAP")
        if cap_field.count() == 0:
            cap_field = page.get_by_label("Zip code")
        if cap_field.count() == 0:
            cap_field = page.get_by_label("Codice postale")
        if cap_field.count() == 0:
            cap_field = page.locator("input[name*='zip'], input[name*='postal']")
        if cap_field.count() > 0:
            cap_field.first.fill(ident["cap"])
            print(f"  CAP: {ident['cap']}")

        wait(page, 1000)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_indirizzo")

    try_step(page, "step4_indirizzo", do_step4)

    # --- Step 5: Composizione (ospiti, camere, bagni) ---
    print("Step 5: Composizione")

    def do_step5():
        screenshot(page, "composizione_pagina")
        save_html(page, "step5_composizione")

        # Ospiti
        for label in ["Ospiti", "Guests", "Numero massimo di ospiti"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["max_ospiti"]))
                print(f"  Ospiti: {comp['max_ospiti']}")
                break

        wait(page, 1000)

        # Camere da letto
        for label in ["Camere da letto", "Bedrooms"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["camere"]))
                print(f"  Camere: {comp['camere']}")
                break

        wait(page, 1000)

        # Bagni
        for label in ["Bagni", "Bathrooms"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["bagni"]))
                print(f"  Bagni: {comp['bagni']}")
                break

        wait(page, 1000)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_composizione")

    try_step(page, "step5_composizione", do_step5)

    # --- Step 6: Letti (dal JSON composizione.letti) ---
    print("Step 6: Configurazione letti")

    # Mappa tipo letto JSON → label parziale su Booking (match parziale)
    # Le label complete sono es. "Letto matrimoniale (ca. 140 x 200 cm)"
    LETTO_LABELS_BOOKING = {
        "matrimoniale": ["Letto matrimoniale"],
        "francese": ["Letto Queen-size"],
        "singolo": ["Letto singolo"],
        "divano_letto": ["Divano letto matrimoniale", "Divano letto singolo"],
        "divano_letto_singolo": ["Divano letto singolo"],
        "king": ["Letto King-size"],
        "castello": ["Letto a castello"],
    }

    def _click_bed_plus(partial_label, clicks):
        """Clicca il pulsante '+' N volte per un tipo letto su Booking.
        Booking usa contatori +/- per ogni tipo letto, non campi di testo."""
        # Trova il testo del letto nella pagina
        label_el = page.get_by_text(partial_label, exact=False)
        if label_el.count() == 0:
            return False

        # Risali al container riga che contiene i pulsanti +/-
        # Il '+' è tipicamente l'ultimo button nella riga
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

        # Fallback: cerca il primo '+' button che segue il label nel DOM
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

    def do_step6():
        screenshot(page, "letti_pagina")
        save_html(page, "step6_letti")

        letti = comp.get("letti", [])
        if not letti:
            print("  ATTENZIONE: nessun dato letti nel JSON, skip")

        for letto in letti:
            tipo = letto["tipo"]
            quantita = letto["quantita"]
            labels = LETTO_LABELS_BOOKING.get(tipo, [])
            if not labels:
                print(f"  Tipo letto sconosciuto: {tipo}, skip")
                continue
            found = False
            for label in labels:
                if _click_bed_plus(label, quantita):
                    print(f"  {label}: +{quantita} (dal JSON)")
                    found = True
                    break
            if not found:
                # Fallback: prova fill() su input con label
                for label in labels:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(str(quantita))
                        print(f"  {label}: {quantita} via fill (dal JSON)")
                        found = True
                        break
            if not found:
                print(f"  Label non trovata per tipo '{tipo}', skip")
            wait(page, 500)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_letti")

    try_step(page, "step6_letti", do_step6)

    # --- Step 7: Servizi/Dotazioni ---
    print("Step 7: Servizi e dotazioni")

    def do_step7():
        screenshot(page, "servizi_pagina")
        save_html(page, "step7_servizi")

        for servizio in SERVIZI:
            try:
                btn = page.get_by_text(servizio, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(500)
                    print(f"  Servizio selezionato: {servizio}")
                else:
                    # Prova con checkbox/label
                    cb = page.locator(f"label:has-text('{servizio}')")
                    if cb.count() > 0:
                        cb.first.click()
                        page.wait_for_timeout(500)
                        print(f"  Servizio selezionato (label): {servizio}")
                    else:
                        print(f"  Servizio non trovato: {servizio}")
            except Exception as e:
                print(f"  Errore servizio {servizio}: {e}")

        wait(page)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_servizi")

    try_step(page, "step7_servizi", do_step7)

    # --- Step 8: Foto ---
    print("Step 8: Upload foto")

    def do_step8():
        screenshot(page, "foto_pagina")
        save_html(page, "step8_foto")

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
            screenshot(page, "foto_caricate")
        else:
            print("  SKIP foto")
            screenshot(page, "foto_skip")

        # Continua
        _click_continue(page)
        wait(page)

    try_step(page, "step8_foto", do_step8)

    # --- Step 9: Descrizione ---
    print("Step 9: Descrizione")

    def do_step9():
        screenshot(page, "descrizione_pagina")
        save_html(page, "step9_descrizione")

        desc = PROP["marketing"]["descrizione_lunga"]
        desc_field = page.locator("textarea").first
        if desc_field.count() > 0:
            desc_field.fill(desc)
            print("  Descrizione compilata")
        else:
            print("  Campo descrizione non trovato")

        wait(page, 1000)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_descrizione")

    try_step(page, "step9_descrizione", do_step9)

    # --- Step 10: Prezzo e condizioni (dal JSON, niente hardcoded) ---
    print("Step 10: Prezzo e condizioni")

    def do_step10():
        screenshot(page, "prezzo_pagina")
        save_html(page, "step10_prezzo")

        cond = PROP.get("condizioni", {})

        # Prezzo a notte — dal JSON (prezzo_notte diretto, oppure mediana del listino)
        prezzo = cond.get("prezzo_notte")
        if prezzo is None:
            # Calcola mediana dal listino_prezzi se disponibile
            listino = cond.get("listino_prezzi", [])
            if listino:
                prezzi_listino = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
                if prezzi_listino:
                    mid = len(prezzi_listino) // 2
                    prezzo = prezzi_listino[mid]
                    print(f"  Prezzo calcolato (mediana listino): {prezzo}")
        if prezzo is not None:
            prezzo_str = str(prezzo)
            for label in ["Prezzo per notte", "Price per night", "Prezzo"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(prezzo_str)
                    print(f"  Prezzo: {prezzo_str} EUR/notte (dal JSON)")
                    break
        else:
            print("  Prezzo non presente nel JSON — lascio vuoto")

        wait(page, 1000)

        # Cauzione — solo se presente nel JSON (supporta sia cauzione_euro che cauzione)
        cauzione_val = cond.get("cauzione_euro") or cond.get("cauzione")
        if cauzione_val is not None:
            cauzione = str(cauzione_val)
            for label in ["Cauzione", "Deposit", "Damage deposit"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cauzione)
                    print(f"  Cauzione: {cauzione} EUR (dal JSON)")
                    break
        else:
            print("  Cauzione non presente nel JSON — lascio vuoto")

        wait(page, 1000)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_prezzo")

    try_step(page, "step10_prezzo", do_step10)

    # --- Step 11: Codici identificativi (CIN/CIR) ---
    print("Step 11: Codici identificativi (CIN/CIR)")

    def do_step11():
        screenshot(page, "codici_pagina")
        save_html(page, "step11_codici")

        cin = ident["cin"]
        cir = ident.get("cir", "")

        # CIN
        for label in ["CIN", "Codice Identificativo Nazionale"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(cin)
                print(f"  CIN: {cin}")
                break
        else:
            cin_field = page.locator(
                "input[name*='cin'], input[name*='CIN'], input[placeholder*='CIN']"
            )
            if cin_field.count() > 0:
                cin_field.first.fill(cin)
                print(f"  CIN (fallback): {cin}")

        wait(page, 1000)

        # CIR
        if cir:
            for label in ["CIR", "Codice Identificativo Regionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cir)
                    print(f"  CIR: {cir}")
                    break

        wait(page, 1000)

        # Continua
        _click_continue(page)
        wait(page)
        screenshot(page, "dopo_codici")

    try_step(page, "step11_codici", do_step11)

    # --- Step 12: Pagina finale — solo screenshot, NON inviare ---
    print("Step 12: Pagina finale — SOLO screenshot")

    def do_step12():
        wait(page)
        screenshot(page, "pagina_finale")
        save_html(page, "step12_finale")
        print("Flusso Booking completato! NON inviato per la verifica.")

    try_step(page, "step12_finale", do_step12)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print(f"Proprietà: {PROP['identificativi']['nome_struttura']} (da {DATA_FILE})")

    # In locale (INTERACTIVE): browser visibile per OTP/CAPTCHA manuali
    # In CI: headless
    headless = not INTERACTIVE
    print(f"Browser: {'VISIBILE' if not headless else 'headless'} "
          f"(INTERACTIVE={INTERACTIVE})")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            locale="it-IT",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            java_script_enabled=True,
        )
        page = context.new_page()

        # Stealth opzionale (se playwright-stealth è installato)
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.")

        try:
            wizard_page = login_and_navigate(page)
            screenshot(wizard_page, "pagina_iniziale")
            insert_property(wizard_page)
        finally:
            if INTERACTIVE:
                input("\n>>> Completato! Controlla il browser, poi premi INVIO per chiudere... ")
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
