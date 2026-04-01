"""
booking_explore.py — Esplorazione wizard Booking.com Extranet

Scopo: login su Booking, naviga al wizard "Inserisci il tuo immobile",
e cattura screenshot + HTML di OGNI schermata del wizard SENZA compilare.

Uso locale (Windows):
    set BK_EMAIL=info@affittasardegna.it
    set BK_PASSWORD=tua_password
    python booking_explore.py

Il browser si apre visibile. Per ogni step del wizard:
- Cattura screenshot PNG (full page)
- Salva HTML della pagina
- Mappa i selettori form trovati
- Clicca "Continua" / "Next" per passare allo step successivo
- Se necessario, chiede intervento manuale (CAPTCHA, OTP, compilare campi obbligatori)

Output: cartella booking_wizard_exploration/ con tutti gli screenshot e un
file BOOKING_WIZARD_MAP.json con la mappa di tutti gli step.
"""

import json
import os
import sys
import time
import random

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMAIL = os.environ.get("BK_EMAIL", "")
PASSWORD = os.environ.get("BK_PASSWORD", "")

if not EMAIL:
    print("ERRORE: variabile BK_EMAIL non impostata.")
    print("  set BK_EMAIL=tua@email.com")
    sys.exit(1)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

OUT_DIR = "booking_wizard_exploration"
step_counter = 0
wizard_map = []

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def screenshot(page, name):
    global step_counter
    step_counter += 1
    path = os.path.join(OUT_DIR, f"step{step_counter:02d}_{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 Screenshot: {path}")
    return path


def save_html(page, name):
    path = os.path.join(OUT_DIR, f"{name}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  📄 HTML: {path}")
    return path


def wait(page, ms=3000):
    page.wait_for_timeout(ms)


def human_type(page, selector, text):
    page.click(selector)
    time.sleep(random.uniform(0.3, 0.7))
    for char in text:
        page.keyboard.type(char, delay=random.randint(50, 150))
    time.sleep(random.uniform(0.2, 0.5))


def extract_form_elements(page):
    """Estrai tutti gli elementi form visibili nella pagina."""
    elements = []

    # Input fields
    for inp in page.locator("input:visible").all():
        try:
            elements.append({
                "tag": "input",
                "type": inp.get_attribute("type") or "text",
                "name": inp.get_attribute("name") or "",
                "id": inp.get_attribute("id") or "",
                "placeholder": inp.get_attribute("placeholder") or "",
                "aria_label": inp.get_attribute("aria-label") or "",
            })
        except Exception:
            pass

    # Select fields
    for sel in page.locator("select:visible").all():
        try:
            elements.append({
                "tag": "select",
                "name": sel.get_attribute("name") or "",
                "id": sel.get_attribute("id") or "",
            })
        except Exception:
            pass

    # Textarea
    for ta in page.locator("textarea:visible").all():
        try:
            elements.append({
                "tag": "textarea",
                "name": ta.get_attribute("name") or "",
                "id": ta.get_attribute("id") or "",
                "placeholder": ta.get_attribute("placeholder") or "",
            })
        except Exception:
            pass

    # Buttons
    for btn in page.locator("button:visible").all():
        try:
            elements.append({
                "tag": "button",
                "type": btn.get_attribute("type") or "",
                "text": btn.inner_text().strip()[:80],
            })
        except Exception:
            pass

    return elements


def map_wizard_step(page, step_name):
    """Cattura screenshot, HTML e form elements di uno step del wizard."""
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"  URL: {page.url}")
    print(f"{'='*60}")

    img_path = screenshot(page, step_name)
    html_path = save_html(page, step_name)
    elements = extract_form_elements(page)

    # Cerca heading/titolo della pagina
    title = ""
    for sel in ["h1", "h2", "[role='heading']"]:
        try:
            h = page.locator(sel).first
            if h.is_visible():
                title = h.inner_text().strip()[:120]
                break
        except Exception:
            pass

    step_info = {
        "step": step_counter,
        "name": step_name,
        "url": page.url,
        "title": title,
        "screenshot": img_path,
        "html": html_path,
        "form_elements": elements,
    }
    wizard_map.append(step_info)

    print(f"  Titolo: {title}")
    print(f"  Form elements trovati: {len(elements)}")
    for el in elements:
        print(f"    - {el['tag']}[{el.get('type','')}] name={el.get('name','')} "
              f"id={el.get('id','')} {el.get('text','')[:40]}")

    return step_info


def click_continue(page):
    """Cerca e clicca il pulsante Continua/Next. Ritorna True se trovato."""
    for label in ["Continua", "Continue", "Avanti", "Next", "Salva e continua",
                   "Save and continue", "Conferma", "Confirm"]:
        try:
            # Prima prova come button
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  ➡️  Cliccato: '{label}'")
                wait(page, 5000)
                return True
        except Exception:
            pass
        try:
            # Poi come link
            link = page.get_by_role("link", name=label)
            if link.count() > 0 and link.first.is_visible():
                link.first.click()
                print(f"  ➡️  Cliccato link: '{label}'")
                wait(page, 5000)
                return True
        except Exception:
            pass
        try:
            # Poi come testo generico
            el = page.get_by_text(label, exact=True)
            if el.count() > 0 and el.first.is_visible():
                el.first.click()
                print(f"  ➡️  Cliccato testo: '{label}'")
                wait(page, 5000)
                return True
        except Exception:
            pass
    return False


def dismiss_cookie_banner(page):
    for label in ["Accetto", "Accetta", "Accept", "Accept all", "Accetta tutto"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso ('{label}')")
                wait(page, 1000)
                return
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(page):
    print("\n=== LOGIN BOOKING ===")
    print("  Modalità INTERATTIVA — browser visibile")

    print("  Navigo alla pagina di login...")
    page.goto("https://account.booking.com/sign-in", wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_pagina")
    print(f"  URL: {page.url}")

    dismiss_cookie_banner(page)

    # Email
    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    try:
        page.wait_for_selector(email_sel, timeout=15_000)
        human_type(page, email_sel, EMAIL)
        wait(page, 1000)
        screenshot(page, "email_inserita")

        page.click('button[type="submit"]', timeout=10_000)
        wait(page, 5000)
        screenshot(page, "dopo_email")
    except Exception as e:
        print(f"  Errore inserimento email: {e}")
        screenshot(page, "errore_email")

    # Da qui il flusso Booking varia: OTP, CAPTCHA, password...
    # Chiediamo all'utente di completare il login manualmente
    print("\n" + "=" * 60)
    print("  COMPLETA IL LOGIN NEL BROWSER:")
    print("  1. Se appare un CAPTCHA → risolvilo")
    print("  2. Se chiede un codice email → inseriscilo nel browser")
    print("  3. Se chiede la password → inseriscila")
    print("  4. Continua fino a essere LOGGATO sulla homepage")
    print("=" * 60)
    input("\n>>> Premi INVIO quando sei loggato sulla homepage di Booking... ")

    wait(page, 2000)
    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")


# ---------------------------------------------------------------------------
# Navigazione al wizard
# ---------------------------------------------------------------------------

def navigate_to_wizard(page):
    """Clicca 'Inserisci il tuo immobile' e gestisce la nuova scheda."""
    print("\n=== NAVIGAZIONE AL WIZARD ===")

    dismiss_cookie_banner(page)
    screenshot(page, "homepage_loggato")

    # "Inserisci il tuo immobile" apre una nuova scheda (target=_blank)
    new_page = None

    for label in [
        "Inserisci il tuo immobile",
        "List your property",
        "Registra la tua struttura",
    ]:
        try:
            link = page.get_by_role("link", name=label)
            if link.count() > 0:
                try:
                    with page.context.expect_page(timeout=10_000) as new_page_info:
                        link.first.click()
                    new_page = new_page_info.value
                    print(f"  Cliccato: '{label}' → nuova scheda")
                except Exception:
                    link.first.click()
                    print(f"  Cliccato: '{label}' (stessa scheda)")
                break
        except Exception:
            continue

    if new_page is None and "join.booking.com" not in page.url:
        print("  Link non trovato, navigo direttamente a join.booking.com...")
        page.goto("https://join.booking.com/", wait_until="domcontentloaded", timeout=60_000)

    wizard_page = new_page if new_page else page
    wizard_page.wait_for_load_state("networkidle", timeout=15_000)
    wait(wizard_page, 3000)
    dismiss_cookie_banner(wizard_page)
    screenshot(wizard_page, "landing_page")
    save_html(wizard_page, "landing_page")
    print(f"  URL landing: {wizard_page.url}")

    # Clicca "Get started now" sulla landing page
    if "join.booking.com" in wizard_page.url:
        for label in [
            "Get started now",
            "Inizia ora",
            "Inizia subito",
            "Comincia ora",
            "Continue your registration",
            "Continua la registrazione",
        ]:
            try:
                # Prova come link (potrebbe aprire nuova scheda)
                btn = wizard_page.get_by_role("link", name=label)
                if btn.count() > 0 and btn.first.is_visible():
                    try:
                        with wizard_page.context.expect_page(timeout=10_000) as new_info:
                            btn.first.click()
                        wizard_page = new_info.value
                        print(f"  Cliccato: '{label}' → nuova scheda")
                    except Exception:
                        btn.first.click()
                        print(f"  Cliccato: '{label}'")
                    break
            except Exception:
                pass
            try:
                btn = wizard_page.get_by_role("button", name=label)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    print(f"  Cliccato button: '{label}'")
                    break
            except Exception:
                pass
            try:
                btn = wizard_page.get_by_text(label, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    print(f"  Cliccato testo: '{label}'")
                    break
            except Exception:
                continue

        wait(wizard_page, 8000)

    wizard_page.wait_for_load_state("networkidle", timeout=15_000)
    screenshot(wizard_page, "wizard_start")
    save_html(wizard_page, "wizard_start")
    print(f"  URL wizard: {wizard_page.url}")

    return wizard_page


# ---------------------------------------------------------------------------
# Esplorazione wizard step-by-step
# ---------------------------------------------------------------------------

def explore_wizard(page):
    """Naviga il wizard step-by-step, catturando tutto senza compilare."""
    print("\n=== ESPLORAZIONE WIZARD ===")
    print("  Per ogni step: screenshot + HTML + mappa form")
    print("  Se il wizard richiede campi obbligatori per andare avanti,")
    print("  compila il minimo nel browser e premi INVIO.\n")

    max_steps = 20
    prev_url = ""

    for i in range(1, max_steps + 1):
        current_url = page.url
        map_wizard_step(page, f"wizard_step_{i:02d}")

        # Prova a cliccare Continua
        if click_continue(page):
            wait(page, 3000)
            new_url = page.url

            # Se l'URL non è cambiato, potrebbe esserci un errore di validazione
            if new_url == current_url:
                # Controlla se ci sono errori visibili
                errors = page.locator("[class*='error']:visible, [role='alert']:visible").all()
                if errors:
                    print(f"\n  ⚠️  ERRORE DI VALIDAZIONE RILEVATO (step {i})")
                    for err in errors[:3]:
                        try:
                            print(f"     {err.inner_text().strip()[:100]}")
                        except Exception:
                            pass

                print(f"\n  ⏸️  L'URL non è cambiato — probabilmente servono campi obbligatori.")
                print(f"     Compila il minimo necessario nel BROWSER, poi premi INVIO.")
                print(f"     (oppure scrivi 'skip' per saltare questo step,")
                print(f"      o 'stop' per terminare l'esplorazione)")
                resp = input("\n>>> Premi INVIO quando fatto, 'skip' o 'stop': ").strip().lower()
                if resp == "stop":
                    print("  Esplorazione interrotta dall'utente.")
                    break
                if resp == "skip":
                    print("  Step saltato.")
                    continue

                # Dopo l'intervento manuale, riprova Continua
                wait(page, 2000)
                screenshot(page, f"wizard_step_{i:02d}_dopo_manuale")
                click_continue(page)
                wait(page, 3000)

        else:
            # Nessun pulsante Continua trovato
            print(f"\n  ⚠️  Pulsante Continua/Next NON trovato (step {i})")
            print(f"     Potrebbe essere l'ultimo step, o serve intervento.")
            print(f"     Se c'è un pulsante diverso, cliccalo nel browser.")
            resp = input("\n>>> Premi INVIO per continuare, o 'stop' per terminare: ").strip().lower()
            if resp == "stop":
                break

        # Controlla se siamo usciti dal wizard
        final_url = page.url
        if final_url == prev_url and final_url == current_url:
            print("  URL invariato per 2 iterazioni, possibile loop.")
            resp = input(">>> Continuare? (invio=si, stop=no): ").strip().lower()
            if resp == "stop":
                break

        prev_url = current_url

    # Screenshot finale
    print("\n=== FINE ESPLORAZIONE ===")
    screenshot(page, "wizard_fine")
    save_html(page, "wizard_fine")


# ---------------------------------------------------------------------------
# Salva mappa wizard
# ---------------------------------------------------------------------------

def save_wizard_map():
    path = os.path.join(OUT_DIR, "BOOKING_WIZARD_MAP.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wizard_map, f, indent=2, ensure_ascii=False)
    print(f"\n  Mappa wizard salvata: {path}")
    print(f"  Totale step mappati: {len(wizard_map)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Output directory: {OUT_DIR}/")
    print(f"Email: {EMAIL}")
    print("Browser: VISIBILE (modalità interattiva)\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
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

        # Stealth opzionale
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.\n")

        try:
            login(page)
            wizard_page = navigate_to_wizard(page)
            explore_wizard(wizard_page)
        except Exception as e:
            print(f"\n  ERRORE FATALE: {e}")
            try:
                screenshot(page, "errore_fatale")
                save_html(page, "errore_fatale")
            except Exception:
                pass
        finally:
            save_wizard_map()
            print("\n  Premi INVIO per chiudere il browser...")
            input()
            browser.close()

    print("Fatto!")


if __name__ == "__main__":
    main()
