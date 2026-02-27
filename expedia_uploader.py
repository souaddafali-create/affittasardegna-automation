"""
expedia_uploader.py — Upload proprietà su Vrbo/Expedia con Playwright.

Wizard inserimento proprietà su Vrbo (Expedia) owner dashboard.

Env vars richieste:
    EXPEDIA_EMAIL    — email account Vrbo/Expedia
    EXPEDIA_PASSWORD — password account Vrbo/Expedia
    PROPERTY_DATA    — (opzionale) path al JSON proprietà

REGOLA: tutti i dati vengono dal JSON. Zero valori inventati.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

from uploader_base import (
    load_property_data, StepCounter, screenshot as _screenshot_base,
    save_html as _save_html_base, wait, try_step as _try_step_base,
    download_placeholder_photos, build_services, create_browser_context,
)
from portali.expedia_map import DOTAZIONI_MAP, DOTAZIONI_MAP_IT

# --- Configurazione ---
PROP = load_property_data()

EMAIL = os.environ["EXPEDIA_EMAIL"]
PASSWORD = os.environ["EXPEDIA_PASSWORD"]

INTERACTIVE = sys.stdin.isatty() or os.environ.get("INTERACTIVE", "") == "1"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots_expedia"
_counter = StepCounter()

SERVIZI_EN = build_services(PROP["dotazioni"], DOTAZIONI_MAP)
SERVIZI_IT = build_services(PROP["dotazioni"], DOTAZIONI_MAP_IT)


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
    """Login su Vrbo/Expedia owner dashboard."""
    print("Login Vrbo/Expedia...")
    page.goto("https://www.vrbo.com/login", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_page")

    # Cookie popup
    for btn_text in ["Accept", "Accept All", "Accetta", "Accetta tutti", "OK"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie popup chiuso ('{btn_text}')")
                wait(page, 1000)
                break
        except Exception:
            pass

    # Email
    for sel in ['input[name="email"]', 'input[type="email"]',
                 '#loginFormEmailInput', 'input[name="username"]']:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, EMAIL)
                print(f"  Email compilata ({sel})")
                break
        except Exception:
            continue

    # Click "Continue" / "Avanti" per arrivare al campo password
    for btn_text in ["Continue", "Next", "Avanti", "Continua"]:
        try:
            btn = page.get_by_role("button", name=btn_text)
            if btn.count() > 0:
                btn.first.click()
                wait(page, 3000)
                break
        except Exception:
            continue

    # Password
    for sel in ['input[name="password"]', 'input[type="password"]', '#password']:
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, PASSWORD)
                print(f"  Password compilata ({sel})")
                break
        except Exception:
            continue

    # Click login
    for btn_text in ["Sign in", "Log in", "Accedi", "Entra"]:
        try:
            btn = page.get_by_role("button", name=btn_text)
            if btn.count() > 0:
                btn.first.click()
                break
        except Exception:
            continue

    wait(page, 5000)

    # Gestione 2FA/CAPTCHA se interattivo
    if INTERACTIVE:
        html = page.content().lower()
        if any(kw in html for kw in ["verification", "verifica", "captcha", "confirm"]):
            input("\n>>> Completa verifica 2FA/CAPTCHA nel browser, poi premi INVIO... ")

    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")


# ---------------------------------------------------------------------------
# Navigazione
# ---------------------------------------------------------------------------

def navigate_to_add_property(page):
    """Naviga alla pagina di inserimento nuova proprietà."""
    page.goto("https://www.vrbo.com/list-your-property", timeout=60_000)
    wait(page, 3000)
    screenshot(page, "pagina_inserimento")
    print("Navigato a inserimento proprietà.")


# ---------------------------------------------------------------------------
# Wizard inserimento proprietà
# ---------------------------------------------------------------------------

def insert_property(page):
    """Completa il wizard di inserimento proprietà su Vrbo/Expedia."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    dot = PROP["dotazioni"]
    cond = PROP["condizioni"]
    mktg = PROP["marketing"]

    photo_paths = download_placeholder_photos(5)

    # --- Step 1: Tipo proprietà ---
    def do_step1():
        print("Step 1: Tipo proprietà")
        for text in ["Apartment", "Appartamento", "Flat", "Condo"]:
            try:
                el = page.get_by_text(text, exact=True)
                if el.count() > 0:
                    el.first.click()
                    print(f"  Selezionato: {text}")
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "tipo_proprieta")

    try_step(page, "step1_tipo", do_step1)

    # --- Step 2: Nome proprietà ---
    def do_step2():
        print("Step 2: Nome proprietà")
        nome = ident["nome_struttura"]
        for sel in ['input[name="propertyName"]', 'input[name="name"]',
                     'input[name="title"]', '#propertyName']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, nome)
                    print(f"  Nome: {nome}")
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "nome")

    try_step(page, "step2_nome", do_step2)

    # --- Step 3: Indirizzo ---
    def do_step3():
        print("Step 3: Indirizzo")
        indirizzo = ident["indirizzo"]
        comune = ident["comune"]
        cap = ident.get("cap", "")

        for sel in ['input[name="address"]', 'input[name="streetAddress"]',
                     'input[placeholder*="address"]', '#address']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, f"{indirizzo}, {comune}, {cap}")
                    wait(page, 2000)
                    try:
                        page.locator(".autocomplete-suggestion, .suggestion, li[role='option']").first.click()
                    except Exception:
                        page.keyboard.press("Enter")
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "indirizzo")

    try_step(page, "step3_indirizzo", do_step3)

    # --- Step 4: Ospiti / Camere / Bagni ---
    def do_step4():
        print("Step 4: Ospiti, camere, bagni")
        fields = {
            "guests": comp.get("max_ospiti", 4),
            "bedrooms": comp.get("camere", 1),
            "bathrooms": comp.get("bagni", 1),
        }
        for name, value in fields.items():
            for sel in [f'input[name="{name}"]', f'select[name="{name}"]',
                         f'input[name="num{name.title()}"]']:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        if loc.evaluate("el => el.tagName") == "SELECT":
                            loc.select_option(str(value))
                        else:
                            loc.fill(str(value))
                        print(f"  {name}: {value}")
                        break
                except Exception:
                    continue
        wait(page)
        screenshot(page, "composizione")

    try_step(page, "step4_composizione", do_step4)

    # --- Step 5: Letti ---
    def do_step5():
        print("Step 5: Configurazione letti")
        letti = comp.get("letti", [])
        letti_map = {
            "matrimoniale": ["Double bed", "Queen bed", "King bed",
                             "Letto matrimoniale"],
            "singolo": ["Single bed", "Twin bed", "Letto singolo"],
            "divano_letto": ["Sofa bed", "Divano letto"],
        }
        for letto in letti:
            tipo = letto["tipo"]
            labels = letti_map.get(tipo, [tipo])
            for label in labels:
                try:
                    el = page.get_by_label(label)
                    if el.count() > 0:
                        el.fill(str(letto["quantita"]))
                        print(f"  {label}: {letto['quantita']}")
                        break
                except Exception:
                    continue
        wait(page)
        screenshot(page, "letti")

    try_step(page, "step5_letti", do_step5)

    # --- Step 6: Servizi ---
    def do_step6():
        print("Step 6: Servizi e dotazioni")
        # Prova prima EN, poi fallback IT
        for servizio_en, servizio_it in zip(SERVIZI_EN, SERVIZI_IT):
            found = False
            for label in [servizio_en, servizio_it]:
                try:
                    cb = page.get_by_label(label, exact=True)
                    if cb.count() > 0 and not cb.is_checked():
                        cb.check()
                        print(f"  [OK] {label}")
                        found = True
                        break
                except Exception:
                    pass
                try:
                    el = page.get_by_text(label, exact=True)
                    if el.count() > 0:
                        el.first.click()
                        print(f"  [OK fallback] {label}")
                        found = True
                        break
                except Exception:
                    pass
            if not found:
                print(f"  [SKIP] {servizio_en} — non trovato")
        wait(page)
        screenshot(page, "servizi")

    try_step(page, "step6_servizi", do_step6)

    # --- Step 7: Foto ---
    def do_step7():
        print("Step 7: Upload foto")
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            file_input.first.set_input_files(photo_paths)
            print(f"  Caricate {len(photo_paths)} foto")
        else:
            print("  Input file non trovato")
        wait(page, 5000)
        screenshot(page, "foto")

    try_step(page, "step7_foto", do_step7)

    # --- Step 8: Descrizione ---
    def do_step8():
        print("Step 8: Descrizione")
        desc = mktg.get("descrizione_lunga", "")
        for sel in ['textarea[name="description"]', 'textarea[name="propertyDescription"]',
                     '#description', 'textarea']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, desc)
                    print("  Descrizione compilata")
                    break
            except Exception:
                continue
        wait(page)
        screenshot(page, "descrizione")

    try_step(page, "step8_descrizione", do_step8)

    # --- Step 9: Prezzo ---
    def do_step9():
        print("Step 9: Prezzo e cauzione")
        prezzo = cond.get("prezzo_notte")
        if prezzo:
            for sel in ['input[name="price"]', 'input[name="nightlyRate"]',
                         'input[name="baseRate"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, str(prezzo))
                        print(f"  Prezzo/notte: {prezzo}")
                        break
                except Exception:
                    continue

        cauzione = cond.get("cauzione_euro")
        if cauzione:
            for sel in ['input[name="deposit"]', 'input[name="securityDeposit"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, str(cauzione))
                        print(f"  Cauzione: {cauzione}")
                        break
                except Exception:
                    continue
        wait(page)
        screenshot(page, "prezzo")

    try_step(page, "step9_prezzo", do_step9)

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

    headless = not INTERACTIVE
    print("=" * 60)
    print("VRBO/EXPEDIA UPLOADER — Playwright")
    print(f"Browser: {'headless' if headless else 'visibile'} "
          f"(INTERACTIVE={INTERACTIVE})")
    print("=" * 60)

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
