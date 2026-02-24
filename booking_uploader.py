#!/usr/bin/env python3
"""
Uploader automatico per Booking.com Extranet — inserimento proprietà via Playwright.

Il wizard di registrazione Booking.com è organizzato in più step:
  1. Tipo di proprietà  — apartment, house, villa, hotel, …
  2. Dettagli           — nome proprietà e descrizione
  3. Posizione          — indirizzo, città, CAP, paese
  4. Struttura          — bagni, ospiti max, superficie
  5. Tariffe            — prezzo per notte
  6. Check-in/out       — orari di arrivo e partenza
  7. Contatti           — email e telefono del gestore

Legge le credenziali da variabili d'ambiente:
    BK_EMAIL    — email dell'account Booking.com (partner/extranet)
    BK_PASSWORD — password dell'account Booking.com

Legge i dati delle proprietà da output/booking.csv (generato da
property_processor.py) oppure da un file CSV alternativo.

Uso:
    # Inserisce tutte le proprietà (browser visibile)
    python3 booking_uploader.py

    # Solo la prima proprietà del CSV (indice 0-based)
    python3 booking_uploader.py --indice 0

    # Usa il CSV di test con Appartamento Test Stintino
    python3 booking_uploader.py --csv output/booking_test.csv --indice 0

    # Browser invisibile (headless)
    python3 booking_uploader.py --headless

    # Stampa i dati senza aprire il browser
    python3 booking_uploader.py --dry-run

Variabili d'ambiente utili:
    BK_EMAIL         email account Booking.com Extranet
    BK_PASSWORD      password account Booking.com Extranet
    CHROMIUM_PATH    percorso binario Chromium (opzionale)
"""

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------

# Booking.com usa un sistema di autenticazione unificato su account.booking.com;
# dopo il login viene reindirizzato all'Extranet su admin.booking.com.
LOGIN_URL    = "https://account.booking.com/sign-in"
EXTRANET_URL = "https://admin.booking.com/"

# URL di registrazione nuova proprietà — Booking usa un wizard a più passi.
# Viene tentato prima il percorso canonico, poi i fallback.
NEW_PROPERTY_URLS = [
    "https://admin.booking.com/hotel/hoteladmin/overview/create/",
    "https://partner.booking.com/",
    "https://join.booking.com/",
]

# Cartella screenshot di debug/errore
SCREENSHOT_DIR = Path("screenshot_errori_bk")

# ---------------------------------------------------------------------------
# SELETTORI
# Centralizzati qui per facilitare aggiornamenti quando Booking cambia layout.
# Ogni voce usa selettori CSS / testo alternativi separati da virgola;
# Playwright seleziona il primo che trova.
# ---------------------------------------------------------------------------

SEL = {
    # --- Login (account.booking.com) ---
    "login_email":    'input#loginname, input[name="loginname"], input[type="email"]',
    "login_password": 'input#password, input[name="password"], input[type="password"]',
    "login_submit":   'button[type="submit"], .bui-button--primary, '
                      'button:has-text("Sign in"), button:has-text("Accedi")',

    # --- Navigazione verso nuova proprietà ---
    "btn_nuova_proprieta": 'a:has-text("List your property"), a:has-text("Add property"), '
                           'a:has-text("Aggiungi proprietà"), button:has-text("List property"), '
                           'a[href*="create"], a[href*="register"], a[href*="join"]',

    # --- Step 1: Tipo di proprietà ---
    # Booking usa radio button o tile selezionabili per il tipo
    "tipo_apartment":  'input[type="radio"][value*="apartment"], '
                       'label:has-text("Apartment"), [data-value*="apartment"]',
    "tipo_villa":      'input[type="radio"][value*="villa"], '
                       'label:has-text("Villa"), [data-value*="villa"]',
    "tipo_house":      'input[type="radio"][value*="house"], '
                       'label:has-text("House"), [data-value*="house"]',
    "tipo_hotel":      'input[type="radio"][value*="hotel"], '
                       'label:has-text("Hotel"), [data-value*="hotel"]',
    # Selettore generico per <select> tipo proprietà (fallback)
    "tipo_select":     'select[name*="property_type"], select[name*="type"], '
                       'select[id*="property_type"]',

    # --- Step 2: Dettagli proprietà ---
    "nome_proprieta":  'input[name*="property_name"], input[name*="name"], '
                       'input[id*="property_name"], input[placeholder*="property name" i], '
                       'input[placeholder*="nome" i]',
    "descrizione":     'textarea[name*="description"], textarea[id*="description"], '
                       'textarea[name*="descrizione"], textarea[placeholder*="description" i]',

    # --- Step 3: Posizione ---
    "indirizzo":       'input[name*="address"], input[name*="street"], input[id*="address"], '
                       'input[placeholder*="address" i], input[placeholder*="indirizzo" i]',
    "citta":           'input[name*="city"], input[id*="city"], '
                       'input[placeholder*="city" i], input[placeholder*="città" i]',
    "cap":             'input[name*="postcode"], input[name*="postal"], input[name*="zip"], '
                       'input[id*="postcode"], input[placeholder*="postcode" i]',
    "paese":           'select[name*="country"], select[id*="country"], '
                       'input[name*="country"]',

    # --- Step 4: Struttura / capacità ---
    "ospiti_max":      'input[name*="max_guests"], input[name*="guests"], '
                       'input[id*="max_guests"], input[id*="guests"]',
    "bagni":           'input[name*="bathrooms"], input[id*="bathrooms"], '
                       'select[name*="bathrooms"]',
    "superficie":      'input[name*="size"], input[name*="sqm"], input[name*="surface"], '
                       'input[id*="size"], input[id*="sqm"]',

    # --- Step 5: Tariffe ---
    "prezzo_notte":    'input[name*="price"], input[name*="rate"], input[name*="amount"], '
                       'input[id*="price"], input[id*="rate"]',

    # --- Step 6: Check-in / Check-out ---
    "check_in":        'input[name*="check_in"], input[name*="checkin"], '
                       'select[name*="check_in"], input[id*="check_in"]',
    "check_out":       'input[name*="check_out"], input[name*="checkout"], '
                       'select[name*="check_out"], input[id*="check_out"]',

    # --- Step 7: Contatti ---
    "email_contatto":  'input[name*="contact_email"], input[name*="email"], '
                       'input[id*="contact_email"]',
    "telefono":        'input[name*="phone"], input[name*="telephone"], '
                       'input[id*="phone"], input[id*="telephone"]',

    # --- Pulsanti di navigazione ---
    "avanti":    'button:has-text("Next"), button:has-text("Continue"), '
                 'button:has-text("Avanti"), button:has-text("Continua"), '
                 'a:has-text("Next"), [data-action="next"]',
    "salva":     'button[type="submit"]:has-text("Save"), '
                 'button[type="submit"]:has-text("Submit"), '
                 'button[type="submit"]:has-text("Finish"), '
                 'button[type="submit"]:has-text("Complete"), '
                 'button:has-text("Salva"), button:has-text("Pubblica"), '
                 'input[type="submit"]',
}


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------

@dataclass
class Proprieta:
    property_name: str
    property_type: str
    description_it: str
    price_per_night_eur: float
    max_guests: int
    bathrooms: int
    size_sqm: float
    address_line1: str
    city: str
    postal_code: str
    country: str
    check_in_from: str
    check_out_until: str
    contact_email: str
    contact_phone: str


# ---------------------------------------------------------------------------
# Lettura CSV
# ---------------------------------------------------------------------------

def leggi_csv(percorso: str) -> list[Proprieta]:
    path = Path(percorso)
    if not path.exists():
        print(f"[ERRORE] File non trovato: {percorso}", file=sys.stderr)
        sys.exit(1)

    risultati = []
    with open(path, newline="", encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            risultati.append(Proprieta(
                property_name=riga["property_name"],
                property_type=riga["property_type"],
                description_it=riga["description_it"],
                price_per_night_eur=float(riga["price_per_night_eur"]),
                max_guests=int(riga["max_guests"]),
                bathrooms=int(riga["bathrooms"]),
                size_sqm=float(riga["size_sqm"]),
                address_line1=riga["address_line1"],
                city=riga["city"],
                postal_code=riga["postal_code"],
                country=riga["country"],
                check_in_from=riga["check_in_from"],
                check_out_until=riga["check_out_until"],
                contact_email=riga["contact_email"],
                contact_phone=riga["contact_phone"],
            ))
    return risultati


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run(proprieta: list[Proprieta]) -> None:
    print(f"\n{'='*65}")
    print("DRY RUN — dati che verrebbero inseriti su Booking.com Extranet")
    print(f"{'='*65}")
    for i, p in enumerate(proprieta):
        print(f"\n[{i}] {p.property_name}")
        print(f"  Tipo              : {p.property_type}")
        print(f"  Città / CAP       : {p.city} {p.postal_code}  ({p.country})")
        print(f"  Indirizzo         : {p.address_line1}")
        print(f"  Prezzo notte      : €{p.price_per_night_eur:.2f}")
        print(f"  Ospiti max        : {p.max_guests}  |  Bagni: {p.bathrooms}")
        print(f"  Superficie        : {p.size_sqm} m²")
        print(f"  Check-in          : {p.check_in_from}  |  Check-out: {p.check_out_until}")
        print(f"  Contatto          : {p.contact_email}  {p.contact_phone}")
        print(f"  Descrizione       : {p.description_it[:90]}…")
    print(f"\n{'='*65}\n")


# ---------------------------------------------------------------------------
# Helpers Playwright
# ---------------------------------------------------------------------------

def _screenshot(page, nome: str) -> None:
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"{ts}_{nome}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  [screenshot] {path.name}")
    except Exception:
        pass


def _fill(page, selettore: str, valore: str, nome: str, timeout: int = 5_000) -> bool:
    """Riempie il primo campo visibile che corrisponde al selettore."""
    try:
        loc = page.locator(selettore).first
        loc.wait_for(state="visible", timeout=timeout)
        loc.clear()
        loc.fill(str(valore))
        return True
    except Exception:
        print(f"  [warn] Campo non trovato: {nome!r}")
        return False


def _select(page, selettore: str, valore: str, nome: str, timeout: int = 5_000) -> bool:
    """Seleziona opzione in <select> per etichetta o valore."""
    try:
        loc = page.locator(selettore).first
        loc.wait_for(state="visible", timeout=timeout)
        try:
            loc.select_option(label=valore)
        except Exception:
            loc.select_option(value=valore.lower())
        return True
    except Exception:
        print(f"  [warn] Select non trovata: {nome!r}")
        return False


def _clicca_avanti(page) -> bool:
    """Clicca il pulsante 'Avanti'/'Next' del wizard se presente."""
    try:
        btn = page.locator(SEL["avanti"]).first
        if btn.count() and btn.is_visible(timeout=2_000):
            btn.click()
            page.wait_for_load_state("domcontentloaded")
            return True
    except Exception:
        pass
    return False


def _seleziona_tipo_proprieta(page, tipo: str) -> bool:
    """
    Seleziona il tipo di proprietà nel wizard Booking.com.
    Booking usa tile cliccabili o radio button per il tipo.
    """
    tipo_lower = tipo.lower()

    # Mappa i tipi del CSV ai selettori specifici di Booking.com
    mapping = {
        "apartment":    SEL["tipo_apartment"],
        "appartamento": SEL["tipo_apartment"],
        "villa":        SEL["tipo_villa"],
        "house":        SEL["tipo_house"],
        "casa":         SEL["tipo_house"],
        "hotel":        SEL["tipo_hotel"],
    }

    selettore = mapping.get(tipo_lower)
    if selettore:
        try:
            loc = page.locator(selettore).first
            if loc.count() and loc.is_visible(timeout=3_000):
                loc.click()
                print(f"  Tipo proprietà selezionato: {tipo!r}")
                return True
        except Exception:
            pass

    # Fallback: <select> generica
    return _select(page, SEL["tipo_select"], tipo, "tipo_proprieta")


# ---------------------------------------------------------------------------
# Logica principale Playwright
# ---------------------------------------------------------------------------

def login(page, email: str, password: str) -> None:
    print(f"  Navigazione a {LOGIN_URL} …")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle")
    except Exception:
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
    _screenshot(page, "01_login_page")

    _fill(page, SEL["login_email"],    email,    "login_email")
    _fill(page, SEL["login_password"], password, "login_password")

    page.locator(SEL["login_submit"]).first.click()
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        page.wait_for_load_state("domcontentloaded")
    _screenshot(page, "02_dopo_login")

    url_attuale = page.url.lower()
    if "sign-in" in url_attuale or "login" in url_attuale or "error" in url_attuale:
        print("[ERRORE] Login non riuscito. Controlla BK_EMAIL e BK_PASSWORD.", file=sys.stderr)
        sys.exit(1)
    print("  Login effettuato.")


def vai_a_nuova_proprieta(page) -> None:
    """Naviga al wizard di registrazione nuova proprietà."""
    print(f"  Navigazione all'Extranet: {EXTRANET_URL} …")
    try:
        page.goto(EXTRANET_URL, wait_until="networkidle", timeout=20_000)
    except Exception:
        page.goto(EXTRANET_URL, wait_until="domcontentloaded")
    _screenshot(page, "03_extranet_home")

    # Prova prima il link "List your property" / "Add property" nell'interfaccia
    try:
        btn = page.locator(SEL["btn_nuova_proprieta"]).first
        btn.wait_for(state="visible", timeout=4_000)
        btn.click()
        page.wait_for_load_state("networkidle")
        _screenshot(page, "04_wizard_inizio")
        print("  Wizard nuova proprietà aperto via bottone.")
        return
    except Exception:
        pass

    # Fallback: prova gli URL diretti del wizard
    for url in NEW_PROPERTY_URLS:
        print(f"  [fallback] Provo {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=15_000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded")

        # Controlla se siamo su una pagina del wizard
        if (page.locator(SEL["nome_proprieta"]).count() > 0 or
                page.locator(SEL["tipo_select"]).count() > 0 or
                page.locator(SEL["tipo_apartment"]).count() > 0):
            _screenshot(page, "04_wizard_inizio_fallback")
            print(f"  Wizard trovato: {url}")
            return

    _screenshot(page, "04_wizard_non_trovato")
    print("  [warn] Wizard non trovato — potrebbe essere già sulla pagina corretta.")


def _compila_tipo_e_nome(page, p: Proprieta) -> None:
    """Step 1-2: tipo di proprietà e nome."""
    _seleziona_tipo_proprieta(page, p.property_type)
    _fill(page, SEL["nome_proprieta"], p.property_name, "nome_proprieta")
    _fill(page, SEL["descrizione"],    p.description_it, "descrizione")


def _compila_posizione(page, p: Proprieta) -> None:
    """Step 3: posizione / indirizzo."""
    _fill(page,   SEL["indirizzo"], p.address_line1, "indirizzo")
    _fill(page,   SEL["citta"],     p.city,          "citta")
    _fill(page,   SEL["cap"],       p.postal_code,   "cap")
    _select(page, SEL["paese"],     p.country,       "paese")


def _compila_struttura(page, p: Proprieta) -> None:
    """Step 4: dettagli struttura."""
    _fill(page, SEL["ospiti_max"], str(p.max_guests), "ospiti_max")
    _fill(page, SEL["bagni"],      str(p.bathrooms),  "bagni")
    _fill(page, SEL["superficie"], str(p.size_sqm),   "superficie")


def _compila_tariffe(page, p: Proprieta) -> None:
    """Step 5: tariffe."""
    _fill(page, SEL["prezzo_notte"], str(p.price_per_night_eur), "prezzo_notte")


def _compila_checkin(page, p: Proprieta) -> None:
    """Step 6: orari check-in e check-out."""
    _fill(page, SEL["check_in"],  p.check_in_from,   "check_in")
    _fill(page, SEL["check_out"], p.check_out_until,  "check_out")


def _compila_contatti(page, p: Proprieta) -> None:
    """Step 7: contatti del gestore."""
    _fill(page, SEL["email_contatto"], p.contact_email, "email_contatto")
    _fill(page, SEL["telefono"],       p.contact_phone, "telefono")


def compila_form(page, p: Proprieta) -> None:
    """
    Compila il wizard multi-step di Booking.com.
    Dopo ogni sezione prova a cliccare 'Avanti'; se il wizard è su pagina
    singola, i campi sono tutti presenti e il click viene ignorato.
    """
    print(f"  Compilazione wizard: {p.property_name!r} …")

    _compila_tipo_e_nome(page, p)
    _clicca_avanti(page)

    _compila_posizione(page, p)
    _clicca_avanti(page)

    _compila_struttura(page, p)
    _clicca_avanti(page)

    _compila_tariffe(page, p)
    _clicca_avanti(page)

    _compila_checkin(page, p)
    _clicca_avanti(page)

    _compila_contatti(page, p)

    _screenshot(page, f"05_form_compilato_{p.postal_code}")


def salva_proprieta(page, p: Proprieta) -> bool:
    """Clicca il pulsante di salvataggio/invio finale e verifica il risultato."""
    try:
        page.locator(SEL["salva"]).first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            page.wait_for_load_state("domcontentloaded")
        _screenshot(page, f"06_dopo_salvataggio_{p.postal_code}")

        body = page.locator("body").inner_text().lower()
        if any(kw in body for kw in ("saved", "submitted", "success", "complete",
                                     "salvato", "salvata", "completato", "grazie",
                                     "thank you", "confirmed", "registration")):
            print(f"  [OK] Proprietà inserita: {p.property_name!r}")
            return True
        if any(kw in body for kw in ("error", "errore", "required", "obbligatorio",
                                     "invalid", "non valido")):
            print(f"  [warn] Possibile errore validazione per: {p.property_name!r}")
            _screenshot(page, f"06_errore_validazione_{p.postal_code}")
            return False
        print(f"  [OK?] Invio completato per: {p.property_name!r} (verificare su Extranet)")
        return True
    except Exception as exc:
        print(f"  [ERRORE] Impossibile cliccare 'Salva': {exc}", file=sys.stderr)
        _screenshot(page, f"06_salva_fallito_{p.postal_code}")
        return False


def inserisci_proprieta(page, p: Proprieta) -> bool:
    try:
        vai_a_nuova_proprieta(page)
        compila_form(page, p)
        return salva_proprieta(page, p)
    except Exception as exc:
        print(f"  [ERRORE] {p.property_name!r}: {exc}", file=sys.stderr)
        _screenshot(page, f"errore_generico_{p.postal_code}")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inserisce proprietà su Booking.com Extranet a partire da un CSV."
    )
    parser.add_argument(
        "--csv",
        default="output/booking.csv",
        help="Path del file CSV (default: output/booking.csv)",
    )
    parser.add_argument(
        "--indice",
        type=int,
        default=None,
        help="Indice 0-based della singola proprietà da caricare (default: tutte)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Esegui il browser in modalità headless (senza finestra grafica)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra i dati senza aprire il browser",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=2.0,
        help="Secondi di pausa tra una proprietà e la successiva (default: 2.0)",
    )
    args = parser.parse_args()

    tutte = leggi_csv(args.csv)
    if not tutte:
        print("[ERRORE] Nessuna proprietà trovata nel CSV.", file=sys.stderr)
        sys.exit(1)

    da_caricare = [tutte[args.indice]] if args.indice is not None else tutte
    print(f"\nProprietà da caricare: {len(da_caricare)} su {len(tutte)} totali.")

    if args.dry_run:
        dry_run(da_caricare)
        return

    email    = os.environ.get("BK_EMAIL", "").strip()
    password = os.environ.get("BK_PASSWORD", "").strip()
    if not email or not password:
        print(
            "[ERRORE] Imposta le variabili d'ambiente BK_EMAIL e BK_PASSWORD:\n"
            "  export BK_EMAIL='tua@email.it'\n"
            "  export BK_PASSWORD='tuapassword'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[ERRORE] Playwright non installato. Esegui:\n"
            "  pip install playwright\n"
            "  python3 -m playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    chromium_path = os.environ.get("CHROMIUM_PATH") or None
    ok = 0
    ko = 0

    with sync_playwright() as pw:
        launch_kwargs: dict = dict(
            headless=args.headless,
            slow_mo=80,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        if chromium_path:
            launch_kwargs["executable_path"] = chromium_path

        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.on("pageerror", lambda exc: print(f"  [JS error] {exc}"))

        try:
            login(page, email, password)

            for i, p in enumerate(da_caricare):
                print(f"\n[{i+1}/{len(da_caricare)}] Inserimento: {p.property_name!r}")
                if inserisci_proprieta(page, p):
                    ok += 1
                else:
                    ko += 1
                if i < len(da_caricare) - 1:
                    time.sleep(args.pausa)
        finally:
            context.close()
            browser.close()

    print(f"\n{'='*55}")
    print(f"Risultato: {ok} inserite con successo, {ko} fallite.")
    if ko > 0:
        print(f"Screenshot errori in: {SCREENSHOT_DIR}/")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
