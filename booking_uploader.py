import json
import os
import random
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

# --- Carica dati proprietà dal file JSON ---
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
# ---------------------------------------------------------------------------

# Mappa dotazioni JSON → checkbox label Booking Extranet
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
    servizi = [label for key, label in DOTAZIONI_BOOKING.items() if dot.get(key)]
    if dot.get("parcheggio_privato") or "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi_booking()


# ---------------------------------------------------------------------------
# Login Booking Extranet
# ---------------------------------------------------------------------------

def login(page):
    """Accesso a Booking Extranet."""
    print("Login Booking Extranet...")
    page.goto("https://account.booking.com/sign-in", wait_until="networkidle", timeout=30_000)
    wait(page, 3000)
    screenshot(page, "login_page")

    # Email
    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    page.wait_for_selector(email_sel, timeout=15_000)
    human_type(page, email_sel, EMAIL)
    wait(page, 1000)
    screenshot(page, "email_inserita")

    # Click continua
    page.click('button[type="submit"]', timeout=10_000)
    wait(page, 5000)
    screenshot(page, "dopo_email")

    # Check CAPTCHA
    html = page.content().lower()
    if "captcha" in html or "human" in html or "choose all" in html:
        print("  *** CAPTCHA RILEVATO — intervento manuale necessario ***")
        screenshot(page, "captcha")
        save_html(page, "captcha")

    # Password
    pw_sel = 'input[type="password"], input[name="password"], #password'
    page.wait_for_selector(pw_sel, timeout=15_000)
    human_type(page, pw_sel, PASSWORD)
    wait(page, 1000)
    screenshot(page, "password_inserita")

    page.click('button[type="submit"]', timeout=10_000)
    wait(page, 8000)
    screenshot(page, "dopo_login")
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

    # --- Step 6: Letti ---
    print("Step 6: Configurazione letti")

    def do_step6():
        screenshot(page, "letti_pagina")
        save_html(page, "step6_letti")

        # Booking chiede tipo e numero letti per camera
        # Proviamo con letto matrimoniale + singoli
        for label in ["Letto matrimoniale", "Double bed", "Letto alla francese"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill("1")
                print(f"  {label}: 1")
                break

        wait(page, 1000)

        for label in ["Letto singolo", "Single bed", "Letti singoli"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill("2")
                print(f"  {label}: 2")
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

    # --- Step 10: Prezzo e condizioni ---
    print("Step 10: Prezzo e condizioni")

    def do_step10():
        screenshot(page, "prezzo_pagina")
        save_html(page, "step10_prezzo")

        # Prezzo a notte (placeholder — da configurare)
        for label in ["Prezzo per notte", "Price per night", "Prezzo"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill("120")
                print("  Prezzo: 120 EUR/notte")
                break

        wait(page, 1000)

        # Cauzione
        cauzione = str(PROP["condizioni"]["cauzione_euro"])
        for label in ["Cauzione", "Deposit", "Damage deposit"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(cauzione)
                print(f"  Cauzione: {cauzione} EUR")
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

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
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
