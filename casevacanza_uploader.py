import os
from playwright.sync_api import sync_playwright

EMAIL = os.environ["CASEVACANZA_EMAIL"]
PASSWORD = os.environ["CASEVACANZA_PASSWORD"]


def login(page) -> None:
    page.goto("https://my.casevacanza.it")
    # The SPA redirects to a Keycloak login page; wait for the form to appear
    page.wait_for_selector("#username", timeout=15_000)
    page.locator("#username").fill(EMAIL)
    page.locator("#password").fill(PASSWORD)
    page.locator("#kc-login").click()
    page.wait_for_url("**/dashboard**", timeout=15_000)
    print("Login effettuato.")


def insert_property(page) -> None:
    page.get_by_role("link", name="Aggiungi proprietà").click()

    page.get_by_label("Nome proprietà").fill("Casa vacanze Sardegna")
    page.get_by_label("Indirizzo").fill("Via Sardegna 1, Cagliari")
    page.get_by_label("Descrizione").fill(
        "Splendida casa vacanze con vista mare in Sardegna."
    )
    page.get_by_label("Prezzo per notte").fill("120")

    page.get_by_role("button", name="Salva").click()
    page.wait_for_selector("text=Proprietà salvata", timeout=10_000)
    print("Proprietà inserita con successo.")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            login(page)
            insert_property(page)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
