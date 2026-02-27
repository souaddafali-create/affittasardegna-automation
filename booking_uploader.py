import os
import random
import sys
import time

from playwright.sync_api import sync_playwright

from uploader_base import (
    load_property_data, StepCounter, screenshot as _screenshot_base,
    save_html as _save_html_base, wait, try_step as _try_step_base,
    download_placeholder_photos, build_services, create_browser_context,
)

# Modalità interattiva: se il terminale è un TTY o se INTERACTIVE=1
INTERACTIVE = sys.stdin.isatty() or os.environ.get("INTERACTIVE", "") == "1"

# --- Carica dati proprietà dal file JSON ---
PROP = load_property_data()

EMAIL = os.environ["BK_EMAIL"]
PASSWORD = os.environ["BK_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots_booking"
_counter = StepCounter()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def screenshot(page, name):
    _screenshot_base(page, name, _counter, SCREENSHOT_DIR)


def save_html(page, name):
    _save_html_base(page, name, SCREENSHOT_DIR)


def human_type(page, selector, text):
    """Digita come un umano con pause random."""
    page.click(selector)
    time.sleep(random.uniform(0.3, 0.7))
    for char in text:
        page.keyboard.type(char, delay=random.randint(50, 150))
    time.sleep(random.uniform(0.2, 0.5))


def try_step(page, step_name, func):
    _try_step_base(page, step_name, func, _counter, SCREENSHOT_DIR)


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


SERVIZI = build_services(PROP["dotazioni"], DOTAZIONI_BOOKING)


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


def login(page):
    """Accesso a Booking Extranet con supporto OTP e CAPTCHA interattivi."""
    print("Login Booking Extranet...")
    if INTERACTIVE:
        print("  (modalità interattiva — il browser si aprirà visibile)")
    page.goto("https://account.booking.com/sign-in", wait_until="networkidle", timeout=30_000)
    wait(page, 3000)
    screenshot(page, "login_page")

    # ── Email ──
    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    page.wait_for_selector(email_sel, timeout=15_000)
    human_type(page, email_sel, EMAIL)
    wait(page, 1000)
    screenshot(page, "email_inserita")

    # Click continua
    page.click('button[type="submit"]', timeout=10_000)
    wait(page, 5000)
    screenshot(page, "dopo_email")

    # ── CAPTCHA ──
    if _page_has_captcha(page):
        print("  *** CAPTCHA RILEVATO ***")
        screenshot(page, "captcha")
        save_html(page, "captcha")
        _wait_for_interactive(
            page,
            "CAPTCHA rilevato! Risolvilo nel browser.",
            lambda p: not _page_has_captcha(p),
        )
        print("  CAPTCHA superato.")
        screenshot(page, "captcha_superato")
        wait(page, 3000)

    # ── Codice di verifica email (OTP) ──
    if _page_has_otp(page):
        print("  *** CODICE DI VERIFICA EMAIL RICHIESTO ***")
        screenshot(page, "otp_richiesto")
        save_html(page, "otp_pagina")

        if INTERACTIVE:
            code = input("\n>>> Inserisci il codice di verifica ricevuto via email: ").strip()
            # Trova il campo OTP e compila
            otp_sel = (
                "input[name*='otp'], input[name*='code'], input[name*='pin'], "
                "input[name*='token'], input[type='tel'], "
                "input[autocomplete='one-time-code']"
            )
            otp_field = page.locator(otp_sel).first
            otp_field.fill(code)
            wait(page, 1000)
            screenshot(page, "otp_inserito")

            # Submit OTP
            page.click('button[type="submit"]', timeout=10_000)
            wait(page, 5000)
            screenshot(page, "dopo_otp")
            print("  Codice di verifica inviato.")
        else:
            # In CI non possiamo chiedere input — fallisce
            raise RuntimeError(
                "Booking richiede un codice di verifica email. "
                "Eseguire lo script in locale con INTERACTIVE=1."
            )
    else:
        print("  Nessun OTP richiesto, procedo.")

    # ── Secondo CAPTCHA (possibile dopo OTP) ──
    if _page_has_captcha(page):
        print("  *** CAPTCHA RILEVATO (post-OTP) ***")
        screenshot(page, "captcha_post_otp")
        _wait_for_interactive(
            page,
            "Secondo CAPTCHA! Risolvilo nel browser.",
            lambda p: not _page_has_captcha(p),
        )
        wait(page, 3000)

    # ── Password ──
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
        # Alcuni flussi (es. magic link) saltano la password
        print("  Campo password non trovato — potrebbe essere login senza password.")
        screenshot(page, "no_password")

    print(f"  URL dopo login: {page.url}")


# ---------------------------------------------------------------------------
# Navigazione a "Aggiungi nuova struttura"
# ---------------------------------------------------------------------------

def navigate_to_add_property(page):
    """Navigate to 'List your property' on Booking Extranet."""
    print("Navigazione a 'Aggiungi nuova struttura'...")

    # Try the Extranet join/list-property URL
    page.goto("https://join.booking.com/", wait_until="networkidle", timeout=30_000)
    wait(page, 5000)
    screenshot(page, "join_page")
    save_html(page, "join_page")
    print(f"  URL: {page.url}")


# ---------------------------------------------------------------------------
# Inserimento proprietà su Booking Extranet
# ---------------------------------------------------------------------------

def insert_property(page):
    """Complete the Booking Extranet property insertion wizard."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    photo_paths = download_placeholder_photos(5)

    # --- Step 1: Seleziona tipo struttura ---
    print("Step 1: Tipo struttura — Appartamento")

    def do_step1():
        screenshot(page, "tipo_struttura_pagina")
        save_html(page, "step1_tipo")
        # Booking usa "Apartment" o "Appartamento" a seconda della lingua
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
        # Click continua/next
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "dopo_composizione")

    try_step(page, "step5_composizione", do_step5)

    # --- Step 6: Letti (dal JSON composizione.letti) ---
    print("Step 6: Configurazione letti")

    # Mappa tipo letto JSON → possibili label Booking (IT/EN)
    LETTO_LABELS_BOOKING = {
        "matrimoniale": ["Letto matrimoniale", "Double bed", "Letto alla francese"],
        "francese": ["Letto alla francese", "Queen bed"],
        "singolo": ["Letto singolo", "Single bed", "Letti singoli"],
        "divano_letto": ["Divano letto", "Sofa bed"],
    }

    def do_step6():
        screenshot(page, "letti_pagina")
        save_html(page, "step6_letti")

        letti = comp.get("letti", [])
        if not letti:
            print("  ATTENZIONE: nessun dato letti nel JSON, skip")

        for letto in letti:
            tipo = letto["tipo"]
            quantita = str(letto["quantita"])
            labels = LETTO_LABELS_BOOKING.get(tipo, [])
            if not labels:
                print(f"  Tipo letto sconosciuto: {tipo}, skip")
                continue
            found = False
            for label in labels:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(quantita)
                    print(f"  {label}: {quantita} (dal JSON)")
                    found = True
                    break
            if not found:
                print(f"  Label non trovata per tipo '{tipo}', skip")
            wait(page, 1000)

        # Continua
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "dopo_descrizione")

    try_step(page, "step9_descrizione", do_step9)

    # --- Step 10: Prezzo e condizioni (dal JSON, niente hardcoded) ---
    print("Step 10: Prezzo e condizioni")

    def do_step10():
        screenshot(page, "prezzo_pagina")
        save_html(page, "step10_prezzo")

        cond = PROP.get("condizioni", {})

        # Prezzo a notte — solo se presente nel JSON
        prezzo = cond.get("prezzo_notte")
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
        cauzione_val = cond.get("cauzione_euro")
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_text(txt, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
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

    # In locale (INTERACTIVE): browser visibile per OTP/CAPTCHA manuali
    # In CI: headless
    headless = not INTERACTIVE
    print(f"Browser: {'headless' if headless else 'visibile'} "
          f"(INTERACTIVE={INTERACTIVE})")

    with sync_playwright() as p:
        browser, context, page = create_browser_context(
            p, headless=headless, user_agent=USER_AGENT, stealth=True,
            extra_args=["--disable-blink-features=AutomationControlled"],
        )

        try:
            login(page)
            navigate_to_add_property(page)
            screenshot(page, "pagina_iniziale")
            insert_property(page)
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
