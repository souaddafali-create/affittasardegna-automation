import os
import re
import tempfile
import urllib.request

from playwright.sync_api import sync_playwright

EMAIL = os.environ["CASEVACANZA_EMAIL"]
PASSWORD = os.environ["CASEVACANZA_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DESCRIPTION = (
    "Bellissimo appartamento a due passi dalla spiaggia della Pelosa, "
    "una delle spiagge più belle e rinomate di tutta la Sardegna. "
    "Ideale per famiglie e coppie, con 2 camere da letto spaziose, "
    "un soggiorno luminoso e accogliente e tutti i comfort necessari "
    "per un soggiorno indimenticabile. La posizione è strategica per "
    "esplorare il nord della Sardegna: a pochi minuti troverete il "
    "Parco Nazionale dell'Asinara, raggiungibile in traghetto, e le "
    "magnifiche calette di Capo Falcone. L'appartamento dispone di "
    "aria condizionata, Wi-Fi veloce, parcheggio privato, lavatrice "
    "e forno. La zona è ricca di ristoranti tipici, negozi e servizi. "
    "Perfetto come base per escursioni, snorkeling e giornate di relax "
    "al mare con tutta la famiglia."
)

SCREENSHOT_DIR = "screenshots"

step_counter = 0


def screenshot(page, name):
    """Save a debug screenshot with incrementing step number."""
    global step_counter
    step_counter += 1
    path = f"{SCREENSHOT_DIR}/step{step_counter:02d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def wait(page, ms=5000):
    """Wait between steps — CaseVacanza is slow."""
    page.wait_for_timeout(ms)


def click_continua(page):
    """Click the 'Continua' button and wait."""
    page.get_by_text("Continua", exact=True).click()
    wait(page)


def click_plus(page, label_text, times=1):
    """Click the + button near a label N times.

    Finds the text label, goes up to the parent row/container,
    then clicks the last button (which is typically +).
    """
    for _ in range(times):
        container = page.get_by_text(label_text, exact=True).locator("..").locator("..")
        plus_btn = container.locator("button").last
        plus_btn.click()
        page.wait_for_timeout(500)


def download_placeholder_photos(count=5):
    """Download placeholder photos from picsum.photos."""
    paths = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(count):
        path = os.path.join(tmp_dir, f"photo_{i+1}.jpg")
        # Each request gets a random image
        urllib.request.urlretrieve(
            f"https://picsum.photos/800/600?random={i+1}", path
        )
        paths.append(path)
        print(f"  Foto scaricata: {path}")
    return paths


def login(page):
    page.goto("https://my.casevacanza.it")
    page.wait_for_selector("#username", timeout=30_000)
    page.locator("#username").fill(EMAIL)
    page.locator("#password").fill(PASSWORD)
    page.locator("#kc-login").click()
    page.wait_for_url("**/home**", timeout=30_000)
    print("Login effettuato.")


def dismiss_popups(page):
    """Close cookies popup and ReactModal overlay."""
    wait(page, 3000)

    # Cookies
    ok_btn = page.locator("button", has_text="Ok")
    if ok_btn.count() > 0:
        ok_btn.first.click()
        print("Popup cookies chiuso.")
        wait(page, 1000)

    # ReactModal
    modal_overlay = page.locator(".ReactModal__Overlay")
    if modal_overlay.count() > 0:
        close_btn = modal_overlay.locator("button").first
        if close_btn.count() > 0:
            close_btn.click()
        else:
            modal_overlay.click(position={"x": 10, "y": 10})
        wait(page, 1000)
        print("ReactModal chiuso.")


def navigate_to_add_property(page):
    """Navigate: Proprietà → Aggiungi una proprietà."""
    page.locator("a", has_text="Proprietà").first.click()
    wait(page)
    print("Navigato a Proprietà.")

    page.get_by_text("Aggiungi una proprietà").click()
    wait(page)
    print("Navigato a Aggiungi una proprietà.")


def insert_property(page):
    """Complete the full property insertion wizard."""
    photo_paths = download_placeholder_photos(5)

    # --- Step 1: Click "Proprietà a unità singola" ---
    print("Step 1: Proprietà a unità singola")
    page.get_by_text("Proprietà a unità singola").click()
    wait(page)
    screenshot(page, "tipo_proprietà")

    # --- Step 2: Seleziona "Appartamento" dal dropdown ---
    print("Step 2: Seleziona Appartamento")
    # Try <select> first, then custom dropdown
    select = page.locator("select")
    if select.count() > 0:
        select.first.select_option(label="Appartamento")
    else:
        page.get_by_text("Appartamento").click()
    wait(page)
    screenshot(page, "appartamento_selezionato")

    # --- Step 3: Click "Intero alloggio" ---
    print("Step 3: Intero alloggio")
    page.get_by_text("Intero alloggio").click()
    wait(page)
    screenshot(page, "intero_alloggio")

    # --- Step 4: Click "Continua" ---
    print("Step 4: Continua (tipo proprietà)")
    click_continua(page)
    screenshot(page, "dopo_tipo")

    # --- Step 5: Clicca "Inseriscilo manualmente" e diagnostica campi ---
    print("Step 5: Indirizzo — click 'Inseriscilo manualmente'")
    screenshot(page, "indirizzo_pagina_default")

    page.get_by_text("Inseriscilo manualmente").click()
    wait(page, 3000)
    screenshot(page, "indirizzo_campi_manuali")

    # Diagnostica: dump HTML e form elements dei campi manuali
    html = page.content()
    with open(f"{SCREENSHOT_DIR}/step05_campi_manuali.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML campi manuali salvato.")

    print("\n=== FORM ELEMENTS (campi manuali) ===")
    inputs = re.findall(r'<(?:input|select|textarea)[^>]*>', html)
    for inp in inputs:
        print(inp)
    print(f"=== TOTALE: {len(inputs)} elementi ===\n")

    print("=== INPUT NAME/ID ===")
    name_ids = re.findall(
        r'<(?:input|select|textarea)[^>]*(?:name|id)=["\']([^"\']+)["\'][^>]*>',
        html,
    )
    for ni in name_ids:
        print(f"  {ni}")

    print("\nDIAGNOSTICA COMPLETATA — controlla log e artifact per i selettori.")


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            login(page)
            dismiss_popups(page)
            navigate_to_add_property(page)
            screenshot(page, "pagina_iniziale")
            insert_property(page)
        finally:
            # Save final screenshot in case of failure
            try:
                screenshot(page, "final_state")
                with open(f"{SCREENSHOT_DIR}/final_state.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
