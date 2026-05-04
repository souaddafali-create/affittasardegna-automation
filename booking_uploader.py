import json
import os
import platform
import random
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Modalità interattiva: TTY, INTERACTIVE=1, oppure Windows (locale).
# Su Windows è SEMPRE interattivo (browser visibile, OTP/CAPTCHA manuali).
# ---------------------------------------------------------------------------
INTERACTIVE = (
    sys.stdin.isatty()
    or os.environ.get("INTERACTIVE", "") == "1"
    or (platform.system() == "Windows" and os.environ.get("CI") is None)
)

# --- Carica dati proprietà dal file JSON ---
# Supporta: PROPERTY_DATA env, argomento CLI, o default Il_Faro_Badesi_DATI.json
if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
    DATA_FILE = sys.argv[1]
elif os.environ.get("PROPERTY_DATA"):
    DATA_FILE = os.environ["PROPERTY_DATA"]
else:
    DATA_FILE = os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json")

with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

print(f"Proprietà: {PROP['identificativi']['nome_struttura']} (da {DATA_FILE})")

# Credenziali opzionali con --skip-login
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


def click_continua(page):
    """Clicca il pulsante Continua/Continue/Avanti/Next."""
    for txt in ["Continua", "Continue", "Avanti", "Next"]:
        try:
            btn = page.get_by_text(txt, exact=True)
            if btn.count() > 0:
                btn.first.click()
                print(f"  Click: {txt}")
                return
        except Exception:
            continue
    print("  Pulsante Continua non trovato")


def try_step(page, step_name, func):
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"\n  *** ERRORE in {step_name}: {e} ***")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")
        if INTERACTIVE:
            input(f"\n>>> ERRORE in {step_name}. Guarda il browser, poi premi INVIO per continuare... ")


def download_photos_from_urls(urls, fallback_count=5):
    """Scarica foto dagli URL CDN (es. Krossbooking) in cartella temporanea.

    Se ``urls`` è vuoto/None, ritorna placeholder picsum come fallback.
    Ritorna la lista dei path locali scaricati con successo.
    """
    tmp_dir = tempfile.mkdtemp()
    paths = []

    if urls:
        for i, url in enumerate(urls):
            ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
            path = os.path.join(tmp_dir, f"photo_{i+1}{ext}")
            try:
                urllib.request.urlretrieve(url, path)
                paths.append(path)
                print(f"  Foto scaricata: {path} <- {url}")
            except Exception as e:
                print(f"  ATTENZIONE: download fallito per {url}: {e}")
        if paths:
            return paths
        print("  ATTENZIONE: nessuna foto scaricata dagli URL forniti, uso placeholder.")

    # Fallback: placeholder picsum
    print(f"  Genero {fallback_count} foto placeholder picsum...")
    for i in range(fallback_count):
        path = os.path.join(tmp_dir, f"placeholder_{i+1}.jpg")
        try:
            urllib.request.urlretrieve(
                f"https://picsum.photos/800/600?random={i+1}", path
            )
            paths.append(path)
            print(f"  Placeholder: {path}")
        except Exception as e:
            print(f"  ATTENZIONE: download placeholder fallito: {e}")
    return paths


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
# CAPTCHA e OTP — sempre con pausa manuale interattiva
# ---------------------------------------------------------------------------

def _page_has_captcha(page):
    """Rileva CAPTCHA reali. Evita falsi positivi da testo generico."""
    # Cerca iframe o elementi CAPTCHA specifici (reCAPTCHA, hCaptcha, Arkose)
    captcha_iframes = page.locator(
        "iframe[src*='captcha'], iframe[src*='recaptcha'], "
        "iframe[src*='hcaptcha'], iframe[src*='arkoselabs'], "
        "iframe[title*='captcha' i]"
    ).count()
    if captcha_iframes > 0:
        return True
    # Cerca div/elementi CAPTCHA noti
    captcha_els = page.locator(
        ".g-recaptcha, .h-captcha, #captcha, [data-captcha], "
        "[class*='captcha' i], #challenge"
    ).count()
    if captcha_els > 0:
        return True
    # Fallback testo — solo "captcha" (NON "human" che causa falsi positivi)
    html = page.content().lower()
    return "choose all" in html and "images" in html


def _page_has_otp(page):
    """Rileva se Booking sta chiedendo un codice di verifica email."""
    html = page.content().lower()
    otp_keywords = ["verification", "verifica", "codice", "code", "confirm", "pin"]
    has_keyword = any(kw in html for kw in otp_keywords)
    has_otp_input = page.locator(
        "input[name*='otp'], input[name*='code'], input[name*='pin'], "
        "input[name*='token'], input[type='tel'], "
        "input[autocomplete='one-time-code']"
    ).count() > 0
    return has_keyword and has_otp_input


def _handle_captcha(page, label=""):
    """Controlla e gestisce CAPTCHA se presente — SEMPRE pausa manuale."""
    if not _page_has_captcha(page):
        return
    tag = f" ({label})" if label else ""
    print(f"\n  *** CAPTCHA RILEVATO{tag} ***")
    screenshot(page, f"captcha_{label or 'generic'}")
    save_html(page, f"captcha_{label or 'generic'}")
    if INTERACTIVE:
        input(f">>> CAPTCHA rilevato{tag}! Risolvilo nel browser, poi premi INVIO... ")
        print("  CAPTCHA superato.")
        screenshot(page, f"captcha_superato_{label or 'generic'}")
        wait(page, 3000)
    else:
        raise RuntimeError(f"CAPTCHA rilevato{tag}. Eseguire in locale con INTERACTIVE=1.")


def _handle_otp(page, label=""):
    """Controlla e gestisce OTP — SEMPRE pausa manuale."""
    if not _page_has_otp(page):
        return
    tag = f" ({label})" if label else ""
    print(f"\n  *** CODICE DI VERIFICA EMAIL RICHIESTO{tag} ***")
    screenshot(page, f"otp_richiesto_{label}")
    save_html(page, f"otp_pagina_{label}")
    if INTERACTIVE:
        input(">>> Inserisci il codice di verifica nel BROWSER, poi premi INVIO... ")
        print("  OTP completato.")
        wait(page, 5000)
        screenshot(page, f"dopo_otp_{label}")
    else:
        raise RuntimeError(
            "Booking richiede un codice di verifica email. "
            "Eseguire in locale con INTERACTIVE=1."
        )


def _dismiss_cookie_banner(page):
    """Chiude il banner cookie se presente."""
    for label in ["Accept", "Accetta", "Decline", "Rifiuta"]:
        try:
            btn = page.get_by_text(label, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso ('{label}')")
                wait(page, 1000)
                return
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Login Booking — riscritto da zero
# ---------------------------------------------------------------------------

def login(page):
    """Accesso a Booking.com — ogni passaggio ha try/except con pausa manuale.

    Se qualcosa fallisce, lo script NON crasha: fa screenshot e chiede
    all'utente di intervenire manualmente nel browser.
    """
    print("\n=== LOGIN BOOKING ===")
    if INTERACTIVE:
        print("  Modalità INTERATTIVA — browser visibile")

    # ── Pagina di login ──
    print("  Navigo alla pagina di login...")
    page.goto("https://account.booking.com/sign-in",
              wait_until="domcontentloaded", timeout=120_000)
    wait(page, 5000)
    screenshot(page, "login_pagina")
    print(f"  URL: {page.url}")

    # ── Cookie banner ──
    _dismiss_cookie_banner(page)

    # ── CAPTCHA pre-email ──
    _handle_captcha(page, "pre_email")

    # ── Email ──
    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    try:
        page.wait_for_selector(email_sel, timeout=30_000)
        human_type(page, email_sel, EMAIL)
        wait(page, 1000)
        screenshot(page, "email_inserita")

        # Click submit
        page.click('button[type="submit"]', timeout=120_000)
        wait(page, 5000)
        screenshot(page, "dopo_email")
    except Exception as e:
        print(f"  Campo email non trovato: {e}")
        screenshot(page, "email_non_trovata")
        save_html(page, "email_non_trovata")
        if INTERACTIVE:
            input("\n>>> Campo email non trovato. Inserisci email e clicca Continua nel browser, poi premi INVIO... ")
            screenshot(page, "dopo_email_manuale")
        else:
            raise

    # ── CAPTCHA post-email ──
    _handle_captcha(page, "post_email")

    # ── OTP (codice verifica email) ──
    _handle_otp(page, "pre_password")

    # ── CAPTCHA post-OTP ──
    _handle_captcha(page, "post_otp")

    # ── Password ──
    pw_sel = 'input[type="password"], input[name="password"], #password'
    try:
        page.wait_for_selector(pw_sel, timeout=30_000)
        human_type(page, pw_sel, PASSWORD)
        wait(page, 1000)
        screenshot(page, "password_inserita")

        page.click('button[type="submit"]', timeout=120_000)
        wait(page, 8000)
        screenshot(page, "dopo_login")
    except Exception:
        print("  Campo password non trovato.")
        screenshot(page, "no_password")
        if INTERACTIVE:
            input("\n>>> Password non trovata. Inserisci la password nel browser e fai login, poi premi INVIO... ")
            screenshot(page, "dopo_password_manuale")

    # ── CAPTCHA/OTP post-password ──
    _handle_captcha(page, "post_password")
    _handle_otp(page, "post_password")

    # ── Cookie banner (può riapparire) ──
    _dismiss_cookie_banner(page)

    print(f"  URL dopo login: {page.url}")
    screenshot(page, "login_completato")

    # ── Verifica finale: sei loggato? ──
    if INTERACTIVE:
        input("\n>>> Login completato? Se non sei loggato, fai login manualmente nel browser, poi premi INVIO... ")
        screenshot(page, "dopo_verifica_login")

    print("  Login completato.\n")


# ---------------------------------------------------------------------------
# Navigazione a Extranet — riscritto da zero
# ---------------------------------------------------------------------------

def navigate_to_add_property(page):
    """Dopo il login, naviga alla pagina di registrazione nuova struttura.

    Problema noto: admin.booking.com fa redirect a booking.com/index (sito
    clienti) perché l'account non ha ancora strutture. Quindi:
    1. Prima prova a cliccare "List your property" nella pagina corrente
    2. Se non funziona, vai diretto a join.booking.com/sign-in
    NON andare su admin.booking.com — fa solo redirect inutile.
    """
    print("=== NAVIGAZIONE A REGISTRAZIONE STRUTTURA ===")
    screenshot(page, "pre_navigazione")
    print(f"  URL attuale: {page.url}")

    # ── Step 1: Cerca "List your property" / "Registra la tua struttura" ──
    # nella pagina corrente (booking.com/index dopo login)
    print("  Cerco link 'List your property' nella pagina corrente...")
    for label in [
        "List your property",
        "Registra il tuo immobile",
        "Registra la tua struttura",
        "Aggiungi nuova struttura",
        "Metti in affitto",
        "Add a new property",
        "Register your property",
    ]:
        try:
            link = page.get_by_text(label, exact=False)
            if link.count() > 0 and link.first.is_visible():
                link.first.click()
                print(f"  Click: '{label}'")
                wait(page, 8000)
                _dismiss_cookie_banner(page)
                _handle_captcha(page, "dopo_registra")
                screenshot(page, "dopo_registra_struttura")
                print(f"  URL: {page.url}")

                if INTERACTIVE:
                    input("\n>>> Sei sulla pagina di registrazione? Premi INVIO per continuare... ")
                    screenshot(page, "dopo_pausa_registrazione")
                return
        except Exception:
            continue

    # ── Step 2: Fallback — vai diretto a join.booking.com ──
    print("  Link non trovato nella pagina, vado diretto a join.booking.com...")
    page.goto("https://join.booking.com/",
              wait_until="domcontentloaded", timeout=120_000)
    wait(page, 8000)
    _dismiss_cookie_banner(page)
    _handle_captcha(page, "join_page")
    screenshot(page, "join_page")
    save_html(page, "join_page")
    print(f"  URL: {page.url}")

    if INTERACTIVE:
        input("\n>>> Sei sulla pagina di registrazione struttura? Premi INVIO per continuare... ")


# ---------------------------------------------------------------------------
# Inserimento proprietà su Booking Extranet
# ---------------------------------------------------------------------------

def insert_property(page):
    """Complete the Booking Extranet property insertion wizard."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    foto_urls = PROP.get("marketing", {}).get("foto_urls", []) or PROP.get("foto_urls", [])
    photo_paths = download_photos_from_urls(foto_urls, fallback_count=5)

    # --- Step 1: Seleziona tipo struttura ---
    print("\nStep 1: Tipo struttura — Appartamento")

    def do_step1():
        screenshot(page, "tipo_struttura_pagina")
        save_html(page, "step1_tipo")
        for label in ["Appartamento", "Apartment", "Appartamenti"]:
            try:
                btn = page.get_by_text(label, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    print(f"  Tipo selezionato: {label}")
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "tipo_selezionato")

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
        click_continua(page)
        wait(page)
        screenshot(page, "dopo_numero")

    try_step(page, "step2_numero", do_step2)

    # --- Step 3: Nome struttura ---
    print("Step 3: Nome struttura")

    def do_step3():
        screenshot(page, "nome_pagina")
        save_html(page, "step3_nome")
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
        click_continua(page)
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
        click_continua(page)
        wait(page)
        screenshot(page, "dopo_indirizzo")

    try_step(page, "step4_indirizzo", do_step4)

    # --- Step 5: Composizione (ospiti, camere, bagni) ---
    print("Step 5: Composizione")

    def do_step5():
        screenshot(page, "composizione_pagina")
        save_html(page, "step5_composizione")

        for label in ["Ospiti", "Guests", "Numero massimo di ospiti"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["max_ospiti"]))
                print(f"  Ospiti: {comp['max_ospiti']}")
                break

        wait(page, 1000)

        for label in ["Camere da letto", "Bedrooms"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["camere"]))
                print(f"  Camere: {comp['camere']}")
                break

        wait(page, 1000)

        for label in ["Bagni", "Bathrooms"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(comp["bagni"]))
                print(f"  Bagni: {comp['bagni']}")
                break

        wait(page, 1000)
        click_continua(page)
        wait(page)
        screenshot(page, "dopo_composizione")

    try_step(page, "step5_composizione", do_step5)

    # --- Step 6: Letti (dal JSON composizione.letti) ---
    print("Step 6: Configurazione letti")

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

        click_continua(page)
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
        click_continua(page)
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

        click_continua(page)
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
        click_continua(page)
        wait(page)
        screenshot(page, "dopo_descrizione")

    try_step(page, "step9_descrizione", do_step9)

    # --- Step 10: Prezzo e condizioni (dal JSON) ---
    print("Step 10: Prezzo e condizioni")

    def do_step10():
        screenshot(page, "prezzo_pagina")
        save_html(page, "step10_prezzo")

        cond = PROP.get("condizioni", {})

        # Prezzo a notte — solo se presente nel JSON
        prezzo = cond.get("prezzo_notte") or cond.get("prezzo_base")
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

        # Cauzione — solo se presente nel JSON
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
        click_continua(page)
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

        if cir:
            for label in ["CIR", "Codice Identificativo Regionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cir)
                    print(f"  CIR: {cir}")
                    break

        wait(page, 1000)
        click_continua(page)
        wait(page)
        screenshot(page, "dopo_codici")

    try_step(page, "step11_codici", do_step11)

    # --- Step 12: Pagina finale — solo screenshot, NON inviare ---
    print("Step 12: Pagina finale — SOLO screenshot")

    def do_step12():
        wait(page)
        screenshot(page, "pagina_finale")
        save_html(page, "step12_finale")
        print("  Flusso Booking completato! NON inviato — solo verifica.")

    try_step(page, "step12_finale", do_step12)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # --skip-login: apre il browser su booking.com, tu fai login manualmente,
    # poi lo script continua con navigazione e wizard.
    skip_login = "--skip-login" in sys.argv

    # SEMPRE browser visibile in modalità interattiva (Windows locale)
    headless = not INTERACTIVE
    print(f"\nBrowser: {'headless' if headless else 'VISIBILE'} "
          f"(INTERACTIVE={INTERACTIVE})")
    if skip_login:
        print("  Modalità --skip-login: fai login tu nel browser.")

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
        ]
        if platform.system() != "Windows":
            launch_args.append("--no-sandbox")
            launch_args.append("--disable-dev-shm-usage")

        browser = p.chromium.launch(
            headless=headless,
            slow_mo=300 if INTERACTIVE else 0,
            args=launch_args,
        )
        context = browser.new_context(
            locale="it-IT",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            java_script_enabled=True,
        )
        page = context.new_page()

        # Stealth opzionale
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.")

        try:
            if skip_login:
                # Apri booking.com e lascia fare login all'utente
                page.goto("https://www.booking.com/",
                          wait_until="domcontentloaded", timeout=120_000)
                wait(page, 3000)
                _dismiss_cookie_banner(page)
                screenshot(page, "skip_login_pagina")
                input("\n>>> Fai login nel browser (email, CAPTCHA, OTP, password).\n"
                      ">>> Quando sei loggato e vedi la homepage, premi INVIO... ")
                screenshot(page, "dopo_login_manuale")
                print(f"  URL dopo login manuale: {page.url}")
            else:
                login(page)

            navigate_to_add_property(page)
            screenshot(page, "pagina_iniziale_wizard")
            insert_property(page)
        except Exception as e:
            print(f"\n*** ERRORE FATALE: {e} ***")
            try:
                screenshot(page, "errore_finale")
                save_html(page, "errore_finale")
            except Exception:
                pass
            if INTERACTIVE:
                input("\n>>> ERRORE. Guarda il browser, poi premi INVIO per chiudere... ")
            raise
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            if INTERACTIVE:
                input("\n>>> Completato! Controlla il browser, poi premi INVIO per chiudere... ")
            browser.close()


if __name__ == "__main__":
    main()
