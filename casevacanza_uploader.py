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

    # --- Step 8: Ospiti e camere ---
    print("Step 8: Ospiti e camere")
    click_plus(page, "Ospiti", 3)
    click_plus(page, "Camere da letto", 1)
    click_plus(page, "Soggiorno", 1)
    click_plus(page, "Bagno", 1)
    wait(page)
    screenshot(page, "ospiti_camere")

    # --- Step 9: Continua (ospiti) ---
    print("Step 9: Continua (ospiti)")
    click_continua(page)
    screenshot(page, "dopo_ospiti")

    # --- Step 10: Configura letti ---
    print("Step 10: Configura letti")
    camera_sections = page.locator("[class*='camera'], [class*='room'], [class*='Camera']")
    if camera_sections.count() >= 2:
        cam1 = camera_sections.nth(0)
        mat_plus = cam1.get_by_text("Letto matrimoniale").locator("..").locator("..").locator("button").last
        if mat_plus.count() > 0:
            mat_plus.click()
        cam2 = camera_sections.nth(1)
        sin_plus = cam2.get_by_text("Letto singolo").locator("..").locator("..").locator("button").last
        if sin_plus.count() > 0:
            sin_plus.click()
            page.wait_for_timeout(500)
            sin_plus.click()
    else:
        click_plus(page, "Letto matrimoniale", 1)
        click_plus(page, "Letto singolo", 2)
    wait(page)
    screenshot(page, "letti_configurati")

    # --- Step 11: Continua (letti) ---
    print("Step 11: Continua (letti)")
    click_continua(page)
    screenshot(page, "dopo_letti")

    # --- Step 12: Upload 5 foto ---
    print("Step 12: Upload foto")
    file_input = page.locator("input[type='file']")
    file_input.set_input_files(photo_paths)
    wait(page, 10_000)
    screenshot(page, "foto_caricate")

    # --- Step 13: Continua (foto) ---
    print("Step 13: Continua (foto)")
    click_continua(page)
    screenshot(page, "dopo_foto")

    # --- Step 14: Seleziona servizi ---
    print("Step 14: Servizi")
    servizi = ["Aria condizionata", "Wi-Fi", "Parcheggio", "Lavatrice", "Forno"]
    for servizio in servizi:
        btn = page.get_by_text(servizio, exact=True)
        if btn.count() > 0:
            btn.first.click()
            page.wait_for_timeout(500)
            print(f"  Servizio selezionato: {servizio}")
    wait(page)
    screenshot(page, "servizi_selezionati")

    # --- Step 15: Continua (servizi) ---
    print("Step 15: Continua (servizi)")
    click_continua(page)
    screenshot(page, "dopo_servizi")

    # --- Step 16: Click "Li scrivo io" ---
    print("Step 16: Li scrivo io")
    page.get_by_text("Li scrivo io").click()
    wait(page)
    screenshot(page, "li_scrivo_io")

    # --- Step 17: Titolo e descrizione ---
    print("Step 17: Titolo e descrizione")
    titolo = "Appartamento Test Stintino - Vista Mare"

    titolo_field = page.get_by_label("Titolo")
    if titolo_field.count() > 0:
        titolo_field.fill(titolo)
    else:
        page.locator("input[name*='titolo'], input[name*='title'], input[placeholder*='Titolo']").first.fill(titolo)
    wait(page, 1000)

    desc_field = page.get_by_label("Descrizione")
    if desc_field.count() > 0:
        desc_field.fill(DESCRIPTION)
    else:
        page.locator("textarea").first.fill(DESCRIPTION)
    wait(page, 1000)
    screenshot(page, "titolo_descrizione")

    # --- Step 18: Continua (titolo/descrizione) ---
    print("Step 18: Continua (titolo/descrizione)")
    click_continua(page)
    screenshot(page, "dopo_titolo_desc")

    # --- Step 19: Prezzo ---
    print("Step 19: Prezzo")
    prezzo_field = page.get_by_label("Prezzo")
    if prezzo_field.count() > 0:
        prezzo_field.fill("120")
    else:
        page.locator("input[type='number'], input[name*='prezz'], input[name*='price']").first.fill("120")
    wait(page)
    screenshot(page, "prezzo")

    # --- Step 20: Continua (prezzo) ---
    print("Step 20: Continua (prezzo)")
    click_continua(page)
    screenshot(page, "dopo_prezzo")

    # --- Step 21: Impostazioni avanzate prezzi — skip, Continua ---
    print("Step 21: Skip impostazioni prezzi avanzate")
    click_continua(page)
    screenshot(page, "dopo_prezzi_avanzati")

    # --- Step 22: Calendario — lascia default, Continua ---
    print("Step 22: Calendario")
    click_continua(page)
    screenshot(page, "dopo_calendario")

    # --- Step 23: Requisiti regionali — lascia CIN/CIR vuoti, Continua ---
    print("Step 23: Requisiti regionali")
    click_continua(page)
    screenshot(page, "dopo_requisiti")

    # --- Step 24: Pagina finale — solo screenshot, NON inviare ---
    print("Step 24: Pagina finale — SOLO screenshot")
    wait(page)
    screenshot(page, "pagina_finale")
    with open(f"{SCREENSHOT_DIR}/pagina_finale.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("Flusso completato! NON inviato per la verifica.")


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
