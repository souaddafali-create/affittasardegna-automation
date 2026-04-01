"""
booking_extranet_fill.py — Compila le sezioni dell'Extranet Booking.com

Usa i cookie salvati da booking_uploader.py per accedere all'Extranet
e compilare automaticamente tutte le sezioni della proprietà dal JSON.

Uso:
    set BK_EMAIL=info@affittasardegna.it
    set PROPERTY_DATA=Bilo_Le_Calette_DATI.json
    python booking_extranet_fill.py

Prerequisito: aver già eseguito booking_uploader.py almeno una volta
(per avere booking_session.json con i cookie di sessione).
"""

import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_FILE = os.environ.get(
    "PROPERTY_DATA", os.path.join(os.path.dirname(__file__), "Bilo_Le_Calette_DATI.json")
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

# ID proprietà su Booking (impostato dopo login o passato come env var)
HOTEL_ID = os.environ.get("HOTEL_ID", "")

SESSION_FILE = os.path.join(os.path.dirname(__file__), "booking_session.json")
SCREENSHOT_DIR = "screenshots_extranet"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

step_counter = 0


def screenshot(page, name):
    global step_counter
    step_counter += 1
    path = os.path.join(SCREENSHOT_DIR, f"step{step_counter:02d}_{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def save_html(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  HTML: {path}")


def wait(page, ms=3000):
    page.wait_for_timeout(ms)


def click_save(page):
    """Clicca il bottone Salva nella pagina Extranet."""
    for label in ["Salva", "Save", "Salva modifiche", "Save changes"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Salvato ('{label}')")
                wait(page, 3000)
                return True
        except Exception:
            continue
    # Fallback: bottone submit
    try:
        btn = page.locator("button[type='submit'], input[type='submit']")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            print("  Salvato (submit)")
            wait(page, 3000)
            return True
    except Exception:
        pass
    print("  Bottone Salva non trovato")
    return False


def click_si_no(page, label_text, value_si):
    """Clicca Si o No per una riga con label_text."""
    try:
        row = page.locator(f"tr:has-text('{label_text}'), div:has-text('{label_text}')")
        if row.count() > 0:
            btn_text = "Sì" if value_si else "No"
            # Cerca il bottone Si/No nella riga
            btn = row.first.get_by_role("button", name=btn_text)
            if btn.count() == 0:
                btn = row.first.locator(f"text='{btn_text}'")
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  {label_text}: {btn_text}")
                return True
    except Exception:
        pass
    return False


def detect_hotel_id(page):
    """Rileva l'hotel_id dall'URL della pagina Extranet."""
    url = page.url
    if "hotel_id=" in url:
        import re
        match = re.search(r'hotel_id=(\d+)', url)
        if match:
            return match.group(1)
    return ""


# ---------------------------------------------------------------------------
# Sezioni Extranet
# ---------------------------------------------------------------------------

def fill_servizi_dotazioni(page, hotel_id):
    """Struttura > Servizi e dotazioni"""
    print("\n=== SERVIZI E DOTAZIONI ===")
    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/facilities.html?hotel_id={hotel_id}&lang=it"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "servizi_dotazioni")
    save_html(page, "servizi_dotazioni")

    dot = PROP["dotazioni"]

    # Mappa: label Booking → (chiave JSON, valore)
    servizi_map = {
        "Piscina": ("piscina", dot.get("piscina", False)),
        "Bar": (None, False),
        "Sauna": (None, False),
        "Giardino": (None, False),
        "Terrazza": ("terrazza", dot.get("terrazza", False)),
        "Camere non fumatori": (None, True),  # Sempre sì
        "Disponibilità di camere familiari": (None, True),
        "Vasca idromassaggio/Jacuzzi": (None, False),
        "Aria condizionata": ("aria_condizionata", dot.get("aria_condizionata", False)),
    }

    for label, (key, val) in servizi_map.items():
        try:
            # Cerca i bottoni Sì/No per questa riga
            text_el = page.get_by_text(label, exact=True)
            if text_el.count() > 0:
                parent = text_el.first.locator("xpath=ancestor::*[.//button or .//a[@role='button']][1]")
                if parent.count() > 0:
                    btn_label = "Sì" if val else "No"
                    btn = parent.get_by_role("button", name=btn_label)
                    if btn.count() == 0:
                        btn = parent.get_by_text(btn_label, exact=True)
                    if btn.count() > 0:
                        # Controlla se già selezionato (ha classe active/selected)
                        btn.first.click()
                        page.wait_for_timeout(500)
                        print(f"  {label}: {btn_label}")
        except Exception as e:
            print(f"  {label}: errore - {e}")

    # Pasti: tutto No (già impostato di solito)
    # Lingue parlate: aggiungi Italiano
    try:
        add_btn = page.get_by_text("Aggiungi", exact=True)
        if add_btn.count() > 0:
            add_btn.first.click()
            wait(page, 2000)
            # Cerca "Italiano" nel dropdown
            ita = page.get_by_text("Italiano", exact=True)
            if ita.count() > 0:
                ita.first.click()
                print("  Lingua: Italiano")
    except Exception:
        pass

    # Numero piani edificio
    try:
        piani = page.locator("input[type='number']").first
        if piani.is_visible() and not piani.input_value():
            piani.fill("2")
            print("  Piani edificio: 2")
    except Exception:
        pass

    # Scorri in fondo e salva
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    wait(page, 1000)
    click_save(page)
    screenshot(page, "servizi_salvato")


def fill_condizioni(page, hotel_id):
    """Struttura > Condizioni della struttura"""
    print("\n=== CONDIZIONI DELLA STRUTTURA ===")
    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/policies.html?hotel_id={hotel_id}&lang=it"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "condizioni")
    save_html(page, "condizioni")

    cond = PROP["condizioni"]

    # Clicca Modifica su "Informazioni sugli ospiti"
    modifica_btns = page.get_by_text("Modifica", exact=True)
    for i in range(modifica_btns.count()):
        try:
            btn = modifica_btns.nth(i)
            # Trova la sezione check-in/check-out
            parent_text = btn.locator("xpath=ancestor::*[contains(., 'check')]").first.inner_text()
            if "check" in parent_text.lower():
                btn.click()
                wait(page, 3000)
                break
        except Exception:
            continue

    screenshot(page, "condizioni_modifica")
    save_html(page, "condizioni_modifica")

    # Prova a compilare i campi visibili
    # Check-in
    for sel in ["select[name*='checkin'], input[name*='checkin']"]:
        try:
            f = page.locator(sel)
            if f.count() > 0 and f.first.is_visible():
                f.first.select_option(label="17:00")
                print("  Check-in: 17:00")
                break
        except Exception:
            pass

    # Check-out
    for sel in ["select[name*='checkout'], input[name*='checkout']"]:
        try:
            f = page.locator(sel)
            if f.count() > 0 and f.first.is_visible():
                f.first.select_option(label="10:00")
                print("  Check-out: 10:00")
                break
        except Exception:
            pass

    click_save(page)
    screenshot(page, "condizioni_salvate")


def fill_metratura_dotazioni(page, hotel_id):
    """Struttura > Metratura e dotazioni camere/alloggi"""
    print("\n=== METRATURA E DOTAZIONI ===")
    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/amenities.html?hotel_id={hotel_id}&lang=it"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "metratura")
    save_html(page, "metratura")

    dot = PROP["dotazioni"]

    # Dimensioni alloggio
    try:
        dim_field = page.locator("input[type='number']").first
        if dim_field.is_visible() and not dim_field.input_value():
            dim_field.fill("40")
            print("  Dimensioni: 40 mq")
    except Exception:
        pass

    # Mappa dotazioni alloggio
    dotazioni_si = {
        "Aria condizionata": dot.get("aria_condizionata", False),
        "Angolo cottura": dot.get("piano_cottura", False),
        "Doccia": True,  # bagno con doccia
        "Balcone": dot.get("terrazza", False),
        "Terrazza": dot.get("terrazza", False),
        "TV a schermo piatto": dot.get("tv", False),
        "Lavatrice": dot.get("lavatrice", False),
        "Lavastoviglie": dot.get("lavastoviglie", False),
        "Frigorifero": dot.get("frigo_congelatore", False),
        "Piano cottura": dot.get("piano_cottura", False),
        # Bagno
        "WC": True,
        "Carta igienica": True,
        "Asciugamani": True,
        # Media
        "TV": dot.get("tv", False),
    }

    # Per ogni dotazione, clicca Sì o No
    for label, val in dotazioni_si.items():
        btn_text = "Sì" if val else "No"
        try:
            text_el = page.get_by_text(label, exact=True)
            if text_el.count() > 0 and text_el.first.is_visible():
                parent = text_el.first.locator("xpath=ancestor::*[.//button][1]")
                if parent.count() > 0:
                    btn = parent.get_by_role("button", name=btn_text)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(300)
                        print(f"  {label}: {btn_text}")
        except Exception:
            pass

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    wait(page, 1000)
    click_save(page)
    screenshot(page, "metratura_salvata")


def fill_profilo(page, hotel_id):
    """Struttura > Il tuo profilo / Descrizioni"""
    print("\n=== PROFILO / DESCRIZIONE ===")
    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/profile.html?hotel_id={hotel_id}&lang=it"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "profilo")
    save_html(page, "profilo")

    desc = PROP["marketing"]["descrizione_lunga"]

    # Info sulla struttura (textarea)
    try:
        textareas = page.locator("textarea")
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            if ta.is_visible() and not ta.input_value():
                ta.fill(desc)
                print(f"  Descrizione compilata ({len(desc)} chars)")
                break
    except Exception:
        pass

    click_save(page)
    screenshot(page, "profilo_salvato")


def fill_gestione_camere(page, hotel_id):
    """Struttura > Gestione camere/alloggi"""
    print("\n=== GESTIONE CAMERE ===")
    url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/rooms.html?hotel_id={hotel_id}&lang=it"
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "gestione_camere")
    save_html(page, "gestione_camere")

    ident = PROP["identificativi"]

    # CIN
    try:
        cin_field = page.locator("input[name*='cin'], input[id*='cin']")
        if cin_field.count() > 0 and cin_field.first.is_visible():
            cin_field.first.fill(ident["cin"])
            print(f"  CIN: {ident['cin']}")
    except Exception:
        pass

    # CIR
    try:
        cir = ident.get("cir", "")
        if cir:
            cir_field = page.locator("input[name*='cir'], input[id*='cir']")
            if cir_field.count() > 0 and cir_field.first.is_visible():
                cir_field.first.fill(cir)
                print(f"  CIR: {cir}")
    except Exception:
        pass

    # Max ospiti
    try:
        ospiti = page.locator("input[name*='max_persons'], input[name*='occupancy']")
        if ospiti.count() > 0 and ospiti.first.is_visible():
            ospiti.first.fill(str(PROP["composizione"]["max_ospiti"]))
            print(f"  Max ospiti: {PROP['composizione']['max_ospiti']}")
    except Exception:
        pass

    screenshot(page, "gestione_camere_compilata")
    # Non salvare automaticamente — potrebbe servire intervento manuale
    print("  (Verifica nel browser prima di salvare)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    print(f"Proprietà: {PROP['identificativi']['nome_struttura']} (da {DATA_FILE})")

    EMAIL = os.environ.get("BK_EMAIL", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                   "--disable-blink-features=AutomationControlled"],
        )

        # Prova a caricare sessione salvata, altrimenti parti senza
        ctx_kwargs = dict(
            locale="it-IT",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            java_script_enabled=True,
        )
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE
            print(f"  Sessione caricata da {SESSION_FILE}")

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            # --- LOGIN ---
            hotel_id = HOTEL_ID

            if hotel_id:
                # Vai direttamente all'Extranet
                url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/home.html?hotel_id={hotel_id}&lang=it"
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                wait(page, 5000)
            else:
                page.goto("https://admin.booking.com/", wait_until="domcontentloaded", timeout=60_000)
                wait(page, 5000)

            screenshot(page, "extranet_iniziale")

            # Se siamo su una pagina di login, fai login manualmente
            if "sign-in" in page.url or "account.booking.com" in page.url or "Accedi" in page.content()[:3000]:
                print("\n=== LOGIN NECESSARIO ===")

                # Inserisci email se disponibile
                if EMAIL:
                    try:
                        email_sel = 'input[type="email"], input[name="loginname"], input[name="username"]'
                        e = page.locator(email_sel)
                        if e.count() > 0 and e.first.is_visible():
                            e.first.fill(EMAIL)
                            print(f"  Email inserita: {EMAIL}")
                            # Clicca Avanti/Submit
                            for btn_text in ["Avanti", "Next", "Accedi", "Sign in"]:
                                btn = page.get_by_role("button", name=btn_text)
                                if btn.count() > 0:
                                    btn.first.click()
                                    break
                            wait(page, 3000)
                    except Exception:
                        pass

                print("  Completa il login nel browser (password, OTP, ecc.)")
                input(">>> Premi INVIO quando sei nell'Extranet... ")
                wait(page, 3000)
                screenshot(page, "dopo_login")

                # Salva sessione
                context.storage_state(path=SESSION_FILE)
                print(f"  Sessione salvata: {SESSION_FILE}")

            # Rileva hotel_id se non fornito
            if not hotel_id:
                hotel_id = detect_hotel_id(page)
                if not hotel_id:
                    # Cerca nell'HTML
                    import re
                    match = re.search(r'hotel_id[=:][\s"]*(\d+)', page.content())
                    if match:
                        hotel_id = match.group(1)
                if not hotel_id:
                    hotel_id = input(">>> Hotel ID non trovato. Inseriscilo (es. 16088667): ").strip()

            print(f"  Hotel ID: {hotel_id}")
            print(f"  URL: {page.url}")

            # --- COMPILA SEZIONI ---
            for section_name, section_fn in [
                ("Servizi e dotazioni", fill_servizi_dotazioni),
                ("Metratura e dotazioni", fill_metratura_dotazioni),
                ("Condizioni della struttura", fill_condizioni),
                ("Profilo / Descrizione", fill_profilo),
                ("Gestione camere", fill_gestione_camere),
            ]:
                try:
                    section_fn(page, hotel_id)
                except Exception as e:
                    print(f"\n  ERRORE in {section_name}: {e}")
                    screenshot(page, f"errore_{section_name.replace(' ','_')}")
                    save_html(page, f"errore_{section_name.replace(' ','_')}")
                    input(f">>> '{section_name}' fallito. Completa nel browser, poi INVIO: ")

            # Salva sessione aggiornata
            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass

            print("\n=== COMPLETATO ===")
            print("  Controlla nel browser che tutto sia corretto.")
            print("  Controlla nel browser che tutto sia corretto.")

            # Salva sessione aggiornata
            context.storage_state(path=SESSION_FILE)

        except Exception as e:
            print(f"\n  ERRORE: {e}")
            try:
                screenshot(page, "errore")
                save_html(page, "errore")
            except Exception:
                pass
        finally:
            print("\n" + "=" * 50)
            print("  BROWSER APERTO — puoi verificare e correggere.")
            print("  Scrivi 'chiudi' per chiudere.")
            print("=" * 50)
            while True:
                resp = input(">>> ").strip().lower()
                if resp in ("chiudi", "close", "exit", "quit", "stop"):
                    break
                print("  Scrivi 'chiudi' per uscire.")
            browser.close()


if __name__ == "__main__":
    main()
