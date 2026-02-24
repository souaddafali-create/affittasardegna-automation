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
    """Click the + button near a label N times."""
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

    ok_btn = page.locator("button", has_text="Ok")
    if ok_btn.count() > 0:
        ok_btn.first.click()
        print("Popup cookies chiuso.")
        wait(page, 1000)

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

    # --- Step 5: Compila indirizzo (modalità manuale) ---
    print("Step 5: Indirizzo")
    page.get_by_text("Inseriscilo manualmente").click()
    wait(page, 3000)
    screenshot(page, "campi_manuali")

    # Paese: Italia è già selezionato di default
    # Compila i campi con selettori data-test
    page.locator('[data-test="stateOrProvince"]').fill("Sardegna")
    wait(page, 1000)
    page.locator('[data-test="city"]').fill("Stintino")
    wait(page, 1000)
    page.locator('[data-test="street"]').fill("Via Sassari")
    wait(page, 1000)
    page.locator('[data-test="houseNumberOrName"]').fill("10")
    wait(page, 1000)
    page.locator('[data-test="postalCode"]').fill("07040")
    wait(page, 1000)
    screenshot(page, "indirizzo_compilato")

    # --- Step 6: Continua (indirizzo) ---
    print("Step 6: Continua (indirizzo)")
    click_continua(page)
    screenshot(page, "dopo_indirizzo")

    # --- Step 7: Mappa — Continua senza modificare pin ---
    print("Step 7: Mappa — Continua")
    click_continua(page)
    screenshot(page, "dopo_mappa")

    # --- Step 8: DIAGNOSTICA ospiti e camere ---
    print("Step 8: DIAGNOSTICA ospiti e camere")
    screenshot(page, "ospiti_camere_pagina")

    html = page.content()
    with open(f"{SCREENSHOT_DIR}/step08_ospiti.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML pagina ospiti salvato.")

    # Dump tutti i data-test
    print("\n=== DATA-TEST ATTRIBUTES ===")
    dt_matches = re.findall(r'data-test="[^"]*"', html)
    for m in sorted(set(dt_matches)):
        print(f"  {m}")

    # Dump tutti i bottoni (primi 40)
    print("\n=== BUTTONS ===")
    buttons = re.findall(r'<button[^>]*>.*?</button>', html, re.DOTALL)
    for i, b in enumerate(buttons[:40]):
        print(f"  [{i}] {b[:300]}")
        print("  ---")

    # Contesto attorno a "ospiti" / "guest"
    print("\n=== CONTESTO 'ospiti'/'guest' ===")
    matches = re.findall(r'.{200}(?:ospiti|guest|Ospiti|Guest).{200}', html, re.IGNORECASE)
    for m in matches:
        print(m[:500])
        print("---")

    # Contesto attorno a "bedroom" / "camere"
    print("\n=== CONTESTO 'bedroom'/'camere' ===")
    matches = re.findall(r'.{200}(?:bedroom|camere|Bedroom|Camere).{200}', html, re.IGNORECASE)
    for m in matches:
        print(m[:500])
        print("---")

    # Tutti gli aria-label
    print("\n=== ARIA-LABEL ===")
    aria_matches = re.findall(r'aria-label="[^"]*"', html)
    for m in sorted(set(aria_matches)):
        print(f"  {m}")

    print("\nDIAGNOSTICA OSPITI COMPLETATA.")


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
            try:
                screenshot(page, "final_state")
                with open(f"{SCREENSHOT_DIR}/final_state.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
