"""
idealista_uploader.py — Upload proprietà su Idealista.it con Playwright.

Wizard inserimento annuncio affitto breve nell'area professionisti Idealista.

Env vars richieste:
    IDEALISTA_EMAIL    — email account Idealista
    IDEALISTA_PASSWORD — password account Idealista
    PROPERTY_DATA      — (opzionale) path al JSON proprietà

REGOLA: tutti i dati vengono dal JSON. Zero valori inventati.
"""

import os

from playwright.sync_api import sync_playwright

from uploader_base import (
    load_property_data, StepCounter, screenshot as _screenshot_base,
    save_html as _save_html_base, wait, try_step as _try_step_base,
    download_placeholder_photos, build_services, create_browser_context,
)
from portali.idealista_map import DOTAZIONI_MAP

# --- Configurazione ---
PROP = load_property_data()

EMAIL = os.environ["IDEALISTA_EMAIL"]
PASSWORD = os.environ["IDEALISTA_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots_idealista"
_counter = StepCounter()

SERVIZI = build_services(PROP["dotazioni"], DOTAZIONI_MAP)


def screenshot(page, name):
    _screenshot_base(page, name, _counter, SCREENSHOT_DIR)


def save_html(page, name):
    _save_html_base(page, name, SCREENSHOT_DIR)


def try_step(page, step_name, func):
    _try_step_base(page, step_name, func, _counter, SCREENSHOT_DIR)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(page):
    """Login su Idealista.it."""
    print("Login Idealista.it...")
    page.goto("https://www.idealista.it/login", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_page")

    # Chiudi popup cookie
    for btn_text in ["Accetta", "Accetta tutti", "Accept", "OK", "Accetto"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie popup chiuso ('{btn_text}')")
                wait(page, 1000)
                break
        except Exception:
            pass

    # Compila form login
    selectors_email = [
        'input[name="email"]', 'input[type="email"]',
        '#email', 'input[name="username"]',
    ]
    for sel in selectors_email:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, EMAIL)
                print(f"  Email compilata ({sel})")
                break
        except Exception:
            continue

    selectors_pwd = [
        'input[name="password"]', 'input[type="password"]', '#password',
    ]
    for sel in selectors_pwd:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, PASSWORD)
                print(f"  Password compilata ({sel})")
                break
        except Exception:
            continue

    # Click login button
    for btn_text in ["Accedi", "Log in", "Entra", "Accesso"]:
        try:
            btn = page.get_by_role("button", name=btn_text)
            if btn.count() > 0:
                btn.first.click()
                print(f"  Cliccato '{btn_text}'")
                break
        except Exception:
            continue

    wait(page, 5000)
    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")


# ---------------------------------------------------------------------------
# Navigazione a inserimento annuncio
# ---------------------------------------------------------------------------

def navigate_to_add_property(page):
    """Naviga alla pagina di inserimento nuovo annuncio."""
    page.goto("https://www.idealista.it/inserisci-annuncio/", timeout=60_000)
    wait(page, 3000)
    screenshot(page, "pagina_inserimento")
    print("Navigato a inserimento annuncio.")


# ---------------------------------------------------------------------------
# Wizard inserimento proprietà
# ---------------------------------------------------------------------------

def insert_property(page):
    """Completa il wizard di inserimento proprietà su Idealista."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    dot = PROP["dotazioni"]
    cond = PROP["condizioni"]
    mktg = PROP["marketing"]

    photo_paths = download_placeholder_photos(5)

    # --- Step 1: Tipo operazione → Affitto ---
    def do_step1():
        print("Step 1: Tipo operazione - Affitto")
        for text in ["Affitto", "Affittare", "In affitto"]:
            try:
                btn = page.get_by_text(text, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "tipo_operazione")

    try_step(page, "step1_tipo_operazione", do_step1)

    # --- Step 2: Tipo immobile ---
    def do_step2():
        print("Step 2: Tipo immobile")
        tipo = ident.get("tipo_struttura", "Appartamento")
        for text in [tipo, "Appartamento", "Flat"]:
            try:
                btn = page.get_by_text(text, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "tipo_immobile")

    try_step(page, "step2_tipo_immobile", do_step2)

    # --- Step 3: Indirizzo ---
    def do_step3():
        print("Step 3: Indirizzo")
        indirizzo = ident["indirizzo"]
        comune = ident["comune"]
        cap = ident.get("cap", "")

        # Campo indirizzo
        for sel in ['input[name="address"]', 'input[placeholder*="indirizzo"]',
                     'input[placeholder*="address"]', '#address']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, f"{indirizzo}, {comune}")
                    wait(page, 2000)
                    # Seleziona il primo suggerimento autocomplete
                    try:
                        page.locator(".autocomplete-suggestion, .suggestion, li[role='option']").first.click()
                    except Exception:
                        page.keyboard.press("Enter")
                    break
            except Exception:
                continue

        # CAP
        for sel in ['input[name="zipcode"]', 'input[name="postalCode"]',
                     'input[placeholder*="CAP"]']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, cap)
                    break
            except Exception:
                continue

        wait(page)
        screenshot(page, "indirizzo")

    try_step(page, "step3_indirizzo", do_step3)

    # --- Step 4: Composizione ---
    def do_step4():
        print("Step 4: Composizione")
        # Camere
        for sel in ['input[name="rooms"]', 'select[name="rooms"]',
                     'input[name="bedrooms"]']:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    if loc.evaluate("el => el.tagName") == "SELECT":
                        loc.select_option(str(comp.get("camere", 1)))
                    else:
                        loc.fill(str(comp.get("camere", 1)))
                    break
            except Exception:
                continue

        # Bagni
        for sel in ['input[name="bathrooms"]', 'select[name="bathrooms"]']:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    if loc.evaluate("el => el.tagName") == "SELECT":
                        loc.select_option(str(comp.get("bagni", 1)))
                    else:
                        loc.fill(str(comp.get("bagni", 1)))
                    break
            except Exception:
                continue

        # Superficie
        if comp.get("metri_quadri"):
            for sel in ['input[name="size"]', 'input[name="area"]',
                         'input[name="surface"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, str(comp["metri_quadri"]))
                        break
                except Exception:
                    continue

        # Piano
        if ident.get("piano"):
            for sel in ['input[name="floor"]', 'select[name="floor"]']:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        if loc.evaluate("el => el.tagName") == "SELECT":
                            loc.select_option(ident["piano"])
                        else:
                            loc.fill(ident["piano"])
                        break
                except Exception:
                    continue

        wait(page)
        screenshot(page, "composizione")

    try_step(page, "step4_composizione", do_step4)

    # --- Step 5: Titolo e descrizione ---
    def do_step5():
        print("Step 5: Titolo e descrizione")
        titolo = mktg.get("descrizione_breve", ident["nome_struttura"])
        desc = mktg.get("descrizione_lunga", "")

        for sel in ['input[name="title"]', 'input[name="adTitle"]',
                     '#title', 'input[placeholder*="titolo"]']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, titolo)
                    break
            except Exception:
                continue

        for sel in ['textarea[name="description"]', 'textarea[name="adDescription"]',
                     '#description', 'textarea']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, desc)
                    break
            except Exception:
                continue

        wait(page)
        screenshot(page, "titolo_descrizione")

    try_step(page, "step5_titolo_descrizione", do_step5)

    # --- Step 6: Prezzo ---
    def do_step6():
        print("Step 6: Prezzo")
        prezzo = cond.get("prezzo_notte")
        if prezzo:
            for sel in ['input[name="price"]', 'input[name="rent"]',
                         '#price', 'input[type="number"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, str(prezzo))
                        break
                except Exception:
                    continue

        # Cauzione
        cauzione = cond.get("cauzione_euro")
        if cauzione:
            for sel in ['input[name="deposit"]', 'input[name="cauzione"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, str(cauzione))
                        break
                except Exception:
                    continue

        wait(page)
        screenshot(page, "prezzo")

    try_step(page, "step6_prezzo", do_step6)

    # --- Step 7: Servizi/dotazioni ---
    def do_step7():
        print("Step 7: Servizi e dotazioni")
        print(f"  Servizi da selezionare: {SERVIZI}")
        for servizio in SERVIZI:
            try:
                cb = page.get_by_label(servizio, exact=True)
                if cb.count() > 0 and not cb.is_checked():
                    cb.check()
                    print(f"  [OK] {servizio}")
                    continue
            except Exception:
                pass
            # Fallback: testo visibile
            try:
                el = page.get_by_text(servizio, exact=True)
                if el.count() > 0:
                    el.first.click()
                    print(f"  [OK fallback] {servizio}")
                    continue
            except Exception:
                pass
            print(f"  [SKIP] {servizio} — non trovato")
        wait(page)
        screenshot(page, "servizi")

    try_step(page, "step7_servizi", do_step7)

    # --- Step 8: Foto ---
    def do_step8():
        print("Step 8: Upload foto")
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            file_input.first.set_input_files(photo_paths)
            print(f"  Caricate {len(photo_paths)} foto")
        else:
            print("  Input file non trovato")
        wait(page, 5000)
        screenshot(page, "foto")

    try_step(page, "step8_foto", do_step8)

    # --- Step 9: CIN ---
    def do_step9():
        print("Step 9: CIN / CIR")
        cin = ident.get("cin", "")
        if cin:
            for sel in ['input[name="cin"]', 'input[placeholder*="CIN"]',
                         'input[name="touristCode"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, cin)
                        print(f"  CIN: {cin}")
                        break
                except Exception:
                    continue
        wait(page)
        screenshot(page, "cin")

    try_step(page, "step9_cin", do_step9)

    # --- Step 10: Riepilogo finale — NO INVIO ---
    def do_step10():
        print("Step 10: Riepilogo finale")
        screenshot(page, "riepilogo_finale")
        save_html(page, "riepilogo_finale")
        print("  STOP: NON invio l'annuncio. Verifica manuale necessaria.")

    try_step(page, "step10_riepilogo", do_step10)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print("=" * 60)
    print("IDEALISTA.IT UPLOADER — Playwright")
    print("=" * 60)

    with sync_playwright() as p:
        browser, context, page = create_browser_context(
            p, headless=True, user_agent=USER_AGENT,
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
