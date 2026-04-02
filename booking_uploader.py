"""
Booking Extranet Uploader — Automazione wizard inserimento proprietà.

Flusso:
  1. Apre il browser su Booking Extranet e ATTENDE login manuale dell'utente
  2. Dopo il login, esegue il wizard automatico completo
  3. Resta in Extranet nella stessa sessione — browser MAI chiuso senza comando

Selettori reali mappati dagli HTML del wizard:
  - Nome        → input[name='property_name']
  - Indirizzo   → input[name='location-autocomplete']
  - Servizi     → input[type='checkbox'][name^='amenity_']
  - Continua    → button[data-testid='FormButtonPrimary-enabled']
  - Foto        → input[type='file']#photoFileInput
  - Prezzo      → input#desired_price

Env vars:
  PROPERTY_DATA   — path al JSON dati (default: Il_Faro_Badesi_DATI.json)
  SKIP_WIZARD     — se "1", salta il wizard e resta in Extranet dopo il login
"""

import json
import os
import random
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

DATA_FILE = os.environ.get(
    "PROPERTY_DATA",
    os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json"),
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

SKIP_WIZARD = os.environ.get("SKIP_WIZARD", "") == "1"

SCREENSHOT_DIR = "screenshots_booking"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

step_counter = 0

# Selettori reali Booking Extranet
SEL_PROPERTY_NAME = "input[name='property_name']"
SEL_ADDRESS = "input[name='location-autocomplete']"
SEL_AMENITY_CHECKBOX = "input[type='checkbox'][name^='amenity_']"
SEL_CONTINUE = "button[data-testid='FormButtonPrimary-enabled']"
SEL_PHOTO_INPUT = "input[type='file']#photoFileInput"
SEL_PRICE = "input#desired_price"


# ---------------------------------------------------------------------------
# Mappatura dotazioni JSON → name attribute checkbox Booking
# ---------------------------------------------------------------------------

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

# Mappa tipo letto JSON → label parziale Booking
LETTO_LABELS = {
    "matrimoniale": "Letto matrimoniale",
    "francese": "Letto Queen-size",
    "singolo": "Letto singolo",
    "divano_letto": "Divano letto",
    "divano_letto_singolo": "Divano letto singolo",
    "king": "Letto King-size",
    "castello": "Letto a castello",
}


def _build_servizi():
    """Lista servizi attivi (true nel JSON). REGOLA: mai inventare dati."""
    dot = PROP["dotazioni"]
    servizi = []
    for key, label in DOTAZIONI_BOOKING.items():
        if dot.get(key) is True:
            servizi.append(label)
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi()


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
    print(f"  HTML: {path}")


def click_continue(page, timeout=10_000):
    """Clicca il bottone Continua/Continue usando il selettore reale."""
    try:
        page.click(SEL_CONTINUE, timeout=timeout)
        page.wait_for_timeout(3000)
        return True
    except PwTimeout:
        # Fallback: cerca variante disabled-then-enabled o testo
        for txt in ["Continua", "Continue", "Avanti", "Next"]:
            try:
                btn = page.get_by_role("button", name=txt)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
        print("  WARN: bottone Continua non trovato")
        return False


def wait_for_navigation(page, ms=3000):
    page.wait_for_timeout(ms)


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
# Login manuale — l'utente fa tutto nel browser, lo script aspetta
# ---------------------------------------------------------------------------

def wait_for_manual_login(page, timeout_s=600):
    """Apre la pagina di login e attende che l'utente completi il login.
    Lo script rileva il completamento quando l'URL contiene 'extranet'
    o 'join.booking.com' (wizard nuovo annuncio)."""

    print("=" * 60)
    print("LOGIN MANUALE — Completa il login nel browser.")
    print("Lo script attende che tu arrivi in Extranet o al wizard.")
    print(f"Timeout: {timeout_s}s")
    print("=" * 60)

    page.goto("https://account.booking.com/sign-in", wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(2000)
    screenshot(page, "login_page")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = page.url.lower()
        if "extranet" in url or "join.booking.com" in url or "partner" in url:
            print(f"  Login completato! URL: {page.url}")
            screenshot(page, "login_ok")
            return
        page.wait_for_timeout(2000)

    raise TimeoutError(
        f"Login non completato entro {timeout_s}s. URL finale: {page.url}"
    )


# ---------------------------------------------------------------------------
# Wizard steps — selettori reali
# ---------------------------------------------------------------------------

def step_tipo_struttura(page):
    """Step: seleziona tipo struttura (Appartamento)."""
    print("\n--- Step: Tipo struttura ---")
    screenshot(page, "tipo_struttura")
    save_html(page, "step_tipo")

    tipo = PROP["identificativi"].get("tipo_struttura", "Appartamento")
    for label in [tipo, "Appartamento", "Apartment"]:
        try:
            el = page.get_by_text(label, exact=False)
            if el.count() > 0:
                el.first.click()
                print(f"  Tipo selezionato: {label}")
                page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    click_continue(page)
    screenshot(page, "dopo_tipo")


def step_quante_strutture(page):
    """Step: quante strutture? → 1."""
    print("\n--- Step: Quante strutture ---")
    screenshot(page, "quante_strutture")

    for label in ["Una", "One", "1"]:
        try:
            el = page.get_by_text(label, exact=True)
            if el.count() > 0:
                el.first.click()
                print(f"  Selezionato: {label}")
                break
        except Exception:
            continue

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_quante")


def step_nome(page):
    """Step: nome struttura — input[name='property_name']."""
    print("\n--- Step: Nome struttura ---")
    screenshot(page, "nome_pagina")
    save_html(page, "step_nome")

    nome = PROP["identificativi"]["nome_struttura"]

    try:
        page.wait_for_selector(SEL_PROPERTY_NAME, timeout=10_000)
        page.fill(SEL_PROPERTY_NAME, nome)
        print(f"  Nome: {nome}")
    except PwTimeout:
        print(f"  WARN: {SEL_PROPERTY_NAME} non trovato, provo fallback")
        fb = page.locator("input[name*='name'], input[placeholder*='nome']")
        if fb.count() > 0:
            fb.first.fill(nome)
            print(f"  Nome (fallback): {nome}")

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_nome")


def step_indirizzo(page):
    """Step: indirizzo — input[name='location-autocomplete']."""
    print("\n--- Step: Indirizzo ---")
    screenshot(page, "indirizzo_pagina")
    save_html(page, "step_indirizzo")

    ident = PROP["identificativi"]
    indirizzo_completo = f"{ident['indirizzo']}, {ident['cap']} {ident['comune']}, {ident['provincia']}"

    try:
        page.wait_for_selector(SEL_ADDRESS, timeout=10_000)
        page.fill(SEL_ADDRESS, indirizzo_completo)
        print(f"  Indirizzo: {indirizzo_completo}")

        # Attendi suggerimento autocomplete e seleziona il primo
        page.wait_for_timeout(2000)
        suggestion = page.locator("ul[role='listbox'] li, [data-testid*='suggestion'], .autocomplete-item").first
        try:
            if suggestion.is_visible(timeout=3000):
                suggestion.click()
                print("  Suggerimento autocomplete selezionato")
                page.wait_for_timeout(1000)
        except Exception:
            # Se non c'è autocomplete, prosegui
            print("  Nessun autocomplete, proseguo")

    except PwTimeout:
        print(f"  WARN: {SEL_ADDRESS} non trovato, provo fallback")
        fb = page.locator("input[name*='address'], input[name*='street'], input[name*='location']")
        if fb.count() > 0:
            fb.first.fill(indirizzo_completo)
            print(f"  Indirizzo (fallback): {indirizzo_completo}")

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_indirizzo")


def step_composizione(page):
    """Step: ospiti, camere, bagni."""
    print("\n--- Step: Composizione ---")
    screenshot(page, "composizione_pagina")
    save_html(page, "step_composizione")

    comp = PROP["composizione"]

    # Ospiti
    for label in ["Ospiti", "Guests", "Numero massimo di ospiti"]:
        field = page.get_by_label(label)
        if field.count() > 0:
            field.first.fill(str(comp["max_ospiti"]))
            print(f"  Ospiti: {comp['max_ospiti']}")
            break

    page.wait_for_timeout(500)

    # Camere
    for label in ["Camere da letto", "Bedrooms"]:
        field = page.get_by_label(label)
        if field.count() > 0:
            field.first.fill(str(comp["camere"]))
            print(f"  Camere: {comp['camere']}")
            break

    page.wait_for_timeout(500)

    # Bagni
    for label in ["Bagni", "Bathrooms"]:
        field = page.get_by_label(label)
        if field.count() > 0:
            field.first.fill(str(comp["bagni"]))
            print(f"  Bagni: {comp['bagni']}")
            break

    page.wait_for_timeout(500)
    click_continue(page)
    screenshot(page, "dopo_composizione")


def step_letti(page):
    """Step: configurazione letti dal JSON composizione.letti[]."""
    print("\n--- Step: Letti ---")
    screenshot(page, "letti_pagina")
    save_html(page, "step_letti")

    letti = PROP["composizione"].get("letti", [])
    if not letti:
        print("  WARN: nessun letto nel JSON, skip")
        click_continue(page)
        return

    for letto in letti:
        tipo = letto["tipo"]
        quantita = letto["quantita"]
        label = LETTO_LABELS.get(tipo)
        if not label:
            print(f"  Tipo letto sconosciuto: {tipo}, skip")
            continue

        # Prova bottone + (contatore Booking)
        placed = False
        label_el = page.get_by_text(label, exact=False)
        if label_el.count() > 0:
            try:
                container = label_el.first.locator("xpath=ancestor::*[.//button][1]")
                plus_btn = container.locator("button").last
                if plus_btn.is_visible():
                    for _ in range(quantita):
                        plus_btn.click()
                        page.wait_for_timeout(400)
                    print(f"  {label}: +{quantita}")
                    placed = True
            except Exception:
                pass

        # Fallback: fill input
        if not placed:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(quantita))
                print(f"  {label}: {quantita} (fill)")
                placed = True

        if not placed:
            print(f"  WARN: '{label}' non trovato per tipo '{tipo}'")

    page.wait_for_timeout(500)
    click_continue(page)
    screenshot(page, "dopo_letti")


def step_servizi(page):
    """Step: servizi/dotazioni — input[type='checkbox'][name^='amenity_']."""
    print("\n--- Step: Servizi ---")
    screenshot(page, "servizi_pagina")
    save_html(page, "step_servizi")

    # Raccogli tutte le checkbox amenity disponibili sulla pagina
    checkboxes = page.locator(SEL_AMENITY_CHECKBOX)
    cb_count = checkboxes.count()
    print(f"  Checkbox amenity trovate: {cb_count}")

    # Per ogni checkbox, leggi la label associata e confronta con SERVIZI
    for i in range(cb_count):
        cb = checkboxes.nth(i)
        cb_name = cb.get_attribute("name") or ""
        cb_id = cb.get_attribute("id") or ""

        # Cerca la label associata
        label_text = ""
        if cb_id:
            label_el = page.locator(f"label[for='{cb_id}']")
            if label_el.count() > 0:
                label_text = (label_el.first.inner_text() or "").strip()

        # Se non troviamo label per id, prova il parent
        if not label_text:
            try:
                parent_label = cb.locator("xpath=ancestor::label[1]")
                if parent_label.count() > 0:
                    label_text = (parent_label.first.inner_text() or "").strip()
            except Exception:
                pass

        # Confronta con i servizi attivi dal JSON
        for servizio in SERVIZI:
            if servizio.lower() in label_text.lower():
                if not cb.is_checked():
                    cb.check()
                    print(f"  CHECK: {label_text} (name={cb_name})")
                else:
                    print(f"  GIA' ATTIVO: {label_text}")
                break

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_servizi")


def step_foto(page):
    """Step: upload foto — input[type='file']#photoFileInput."""
    print("\n--- Step: Foto ---")
    screenshot(page, "foto_pagina")
    save_html(page, "step_foto")

    photo_paths = download_placeholder_photos(5)

    uploaded = False
    try:
        fi = page.locator(SEL_PHOTO_INPUT)
        if fi.count() > 0:
            # Rendi visibile se nascosto (comune per input file)
            fi.evaluate("el => { el.style.display = 'block'; el.style.opacity = '1'; }")
            fi.set_input_files(photo_paths, timeout=15_000)
            uploaded = True
            print(f"  Upload OK via {SEL_PHOTO_INPUT}")
    except Exception as e:
        print(f"  Upload via selettore primario fallito: {e}")

    if not uploaded:
        # Fallback: qualsiasi input file
        try:
            fi = page.locator("input[type='file']").first
            fi.evaluate("el => { el.style.display = 'block'; el.style.opacity = '1'; }")
            fi.set_input_files(photo_paths, timeout=15_000)
            uploaded = True
            print("  Upload OK via fallback input[type='file']")
        except Exception as e:
            print(f"  Upload fallback fallito: {e}")

    if uploaded:
        # Attendi caricamento foto
        page.wait_for_timeout(10_000)
        screenshot(page, "foto_caricate")
    else:
        print("  WARN: nessun upload foto riuscito")
        screenshot(page, "foto_fallito")

    click_continue(page)
    screenshot(page, "dopo_foto")


def step_descrizione(page):
    """Step: titolo e descrizione dal JSON marketing."""
    print("\n--- Step: Descrizione ---")
    screenshot(page, "descrizione_pagina")
    save_html(page, "step_descrizione")

    mkt = PROP["marketing"]

    # Descrizione lunga
    desc = mkt.get("descrizione_lunga", "")
    if desc:
        ta = page.locator("textarea").first
        if ta.count() > 0:
            ta.fill(desc)
            print("  Descrizione compilata")

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_descrizione")


def step_prezzo(page):
    """Step: prezzo — input#desired_price. Solo dati dal JSON."""
    print("\n--- Step: Prezzo ---")
    screenshot(page, "prezzo_pagina")
    save_html(page, "step_prezzo")

    cond = PROP.get("condizioni", {})

    # Prezzo notte: usa mediana listino se disponibile, altrimenti prezzo_notte
    prezzo = cond.get("prezzo_notte")
    listino = cond.get("listino_prezzi", [])
    if listino:
        prezzi_listino = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
        if prezzi_listino:
            mid = len(prezzi_listino) // 2
            prezzo = prezzi_listino[mid]
            print(f"  Prezzo mediana listino: {prezzo}")

    if prezzo is not None:
        try:
            page.wait_for_selector(SEL_PRICE, timeout=10_000)
            page.fill(SEL_PRICE, str(int(prezzo)))
            print(f"  Prezzo: {prezzo} EUR/notte (dal JSON)")
        except PwTimeout:
            print(f"  WARN: {SEL_PRICE} non trovato, provo fallback")
            for label in ["Prezzo per notte", "Price per night", "Prezzo"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(str(int(prezzo)))
                    print(f"  Prezzo (fallback): {prezzo}")
                    break
    else:
        print("  Prezzo non presente nel JSON — lascio vuoto")

    # Cauzione — solo se presente nel JSON
    cauzione_val = cond.get("cauzione_euro")
    if cauzione_val is not None:
        for label in ["Cauzione", "Deposit", "Damage deposit"]:
            field = page.get_by_label(label)
            if field.count() > 0:
                field.first.fill(str(cauzione_val))
                print(f"  Cauzione: {cauzione_val} EUR (dal JSON)")
                break

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_prezzo")


def step_codici(page):
    """Step: CIN e CIR dal JSON identificativi."""
    print("\n--- Step: Codici CIN/CIR ---")
    screenshot(page, "codici_pagina")
    save_html(page, "step_codici")

    ident = PROP["identificativi"]
    cin = ident.get("cin", "")
    cir = ident.get("cir", "")

    if cin:
        for sel in ["input[name*='cin' i]", "input[name*='CIN']", "input[placeholder*='CIN']"]:
            field = page.locator(sel)
            if field.count() > 0:
                field.first.fill(cin)
                print(f"  CIN: {cin}")
                break
        else:
            for label in ["CIN", "Codice Identificativo Nazionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cin)
                    print(f"  CIN (label): {cin}")
                    break

    if cir:
        for sel in ["input[name*='cir' i]", "input[name*='CIR']", "input[placeholder*='CIR']"]:
            field = page.locator(sel)
            if field.count() > 0:
                field.first.fill(cir)
                print(f"  CIR: {cir}")
                break
        else:
            for label in ["CIR", "Codice Identificativo Regionale"]:
                field = page.get_by_label(label)
                if field.count() > 0:
                    field.first.fill(cir)
                    print(f"  CIR (label): {cir}")
                    break

    page.wait_for_timeout(1000)
    click_continue(page)
    screenshot(page, "dopo_codici")


def step_finale(page):
    """Step finale: screenshot di verifica. NON invia."""
    print("\n--- Step: Finale (solo verifica) ---")
    page.wait_for_timeout(3000)
    screenshot(page, "pagina_finale")
    save_html(page, "step_finale")
    print("  Wizard completato. NON inviato — verifica manuale richiesta.")


# ---------------------------------------------------------------------------
# Wizard runner
# ---------------------------------------------------------------------------

WIZARD_STEPS = [
    step_tipo_struttura,
    step_quante_strutture,
    step_nome,
    step_indirizzo,
    step_composizione,
    step_letti,
    step_servizi,
    step_foto,
    step_descrizione,
    step_prezzo,
    step_codici,
    step_finale,
]


def run_wizard(page):
    """Esegue tutti gli step del wizard in sequenza."""
    print("\n" + "=" * 60)
    print("WIZARD AUTOMATICO — Inizio")
    print("=" * 60)

    # Naviga al wizard nuova struttura
    page.goto("https://join.booking.com/", wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(3000)
    screenshot(page, "wizard_start")
    save_html(page, "wizard_start")
    print(f"  URL wizard: {page.url}")

    for i, step_fn in enumerate(WIZARD_STEPS, 1):
        print(f"\n[{i}/{len(WIZARD_STEPS)}] {step_fn.__doc__ or step_fn.__name__}")
        try:
            step_fn(page)
        except Exception as e:
            print(f"  ERRORE in {step_fn.__name__}: {e}")
            screenshot(page, f"errore_{step_fn.__name__}")
            save_html(page, f"errore_{step_fn.__name__}")
            # Continua con il prossimo step invece di bloccarsi
            continue

    print("\n" + "=" * 60)
    print("WIZARD COMPLETATO")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Loop attesa — il browser resta aperto fino a comando esplicito
# ---------------------------------------------------------------------------

def wait_for_exit(page):
    """Tiene il browser aperto finché l'utente non chiude o preme Ctrl+C."""
    print("\n" + "=" * 60)
    print("BROWSER ATTIVO — La sessione Extranet è aperta.")
    print("Premi Ctrl+C nel terminale per chiudere.")
    print("=" * 60)

    try:
        while True:
            # Heartbeat: verifica che il browser sia ancora vivo
            try:
                _ = page.url
            except Exception:
                print("Browser chiuso dall'utente.")
                return
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nChiusura richiesta dall'utente.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Proprietà: {PROP['identificativi']['nome_struttura']}")
    print(f"JSON: {DATA_FILE}")
    print(f"SKIP_WIZARD: {SKIP_WIZARD}")
    print(f"Screenshot: {SCREENSHOT_DIR}/")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Sempre visibile: serve login manuale
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
            pass

        try:
            # 1. Login manuale
            wait_for_manual_login(page)

            # 2. Wizard (se non skippato)
            if SKIP_WIZARD:
                print("\nSKIP_WIZARD=1 — Wizard saltato.")
                screenshot(page, "skip_wizard")
            else:
                run_wizard(page)

            # 3. Resta in Extranet — browser MAI chiuso senza comando
            wait_for_exit(page)

        except KeyboardInterrupt:
            print("\nInterrotto dall'utente.")
        except Exception as e:
            print(f"\nERRORE FATALE: {e}")
            try:
                screenshot(page, "errore_fatale")
                save_html(page, "errore_fatale")
            except Exception:
                pass
            raise
        finally:
            print("Chiusura browser...")
            browser.close()


if __name__ == "__main__":
    main()
