import os
from playwright.sync_api import sync_playwright

EMAIL = os.environ["CASEVACANZA_EMAIL"]
PASSWORD = os.environ["CASEVACANZA_PASSWORD"]


def login(page) -> None:
    page.goto("https://my.casevacanza.it")
    # The SPA redirects to a Keycloak login page; wait for the form to appear
    page.wait_for_selector("#username", timeout=30_000)
    page.locator("#username").fill(EMAIL)
    page.locator("#password").fill(PASSWORD)
    page.locator("#kc-login").click()
    page.wait_for_url("**/home**", timeout=30_000)
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


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            login(page)
            page.wait_for_timeout(3_000)

            # Chiudi popup cookies cliccando "Ok"
            ok_btn = page.locator("button", has_text="Ok")
            if ok_btn.count() > 0:
                ok_btn.first.click()
                print("Popup cookies chiuso.")
                page.wait_for_timeout(1_000)

            # Clicca su "Proprietà" nel menu in alto
            page.locator("a", has_text="Proprietà").first.click()
            page.wait_for_timeout(3_000)
            print("Navigato a Proprietà.")

            # Debug: screenshot + HTML della pagina Proprietà
            page.screenshot(path="home_after_login.png", full_page=True)
            print("Screenshot salvato: home_after_login.png")
            html = page.content()
            with open("home_after_login.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("HTML salvato: home_after_login.html")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
