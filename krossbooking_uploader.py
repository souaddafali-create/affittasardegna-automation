#!/usr/bin/env python3
"""
Uploader automatico per KrossBooking PMS — inserimento proprietà via Playwright.

KrossBooking è un PMS (Property Management System) italiano per affitti
brevi. Il form di inserimento è organizzato in più tab/sezioni:
  1. Dati Generali  — nome, tipo, capacità, orari, politica cancellazione
  2. Ubicazione     — indirizzo, città, provincia, CAP
  3. Descrizione    — testo descrittivo della proprietà
  4. Tariffe        — prezzo notte, settimanale, cauzione, pulizie
  5. Disponibilità  — date min/max e soggiorno minimo
  6. Contatti       — email e telefono del gestore

Legge le credenziali da variabili d'ambiente:
    KB_EMAIL    — email dell'account KrossBooking
    KB_PASSWORD — password dell'account KrossBooking

Legge i dati delle proprietà da output/krossbooking.csv (generato da
property_processor.py con esporta_krossbooking()).

Uso:
    # Inserisce tutte le proprietà (browser visibile)
    python3 krossbooking_uploader.py

    # Solo la prima proprietà del CSV (indice 0-based)
    python3 krossbooking_uploader.py --indice 0

    # Browser invisibile
    python3 krossbooking_uploader.py --headless

    # Stampa i dati senza aprire il browser
    python3 krossbooking_uploader.py --dry-run

    # File CSV alternativo
    python3 krossbooking_uploader.py --csv output_test_nord/krossbooking.csv

Variabili d'ambiente utili:
    KB_EMAIL         email account KrossBooking
    KB_PASSWORD      password account KrossBooking
    CHROMIUM_PATH    percorso binario Chromium (solo se versione playwright
                     non corrisponde a quella installata nel sistema)
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

BASE_URL   = "https://app.krossbooking.com"
LOGIN_URL  = f"{BASE_URL}/login"
# URL dell'area gestione strutture nell'interfaccia KrossBooking
STRUTTURE_URL    = f"{BASE_URL}/strutture"
NUOVA_STRUTTURA  = f"{BASE_URL}/strutture/nuova"

# Cartella screenshot di debug/errore
SCREENSHOT_DIR = Path("screenshot_errori_kb")

# ---------------------------------------------------------------------------
# SELETTORI
# Centralizzati qui per facilitare l'aggiornamento quando il sito cambia.
# Ogni voce è una stringa di selettori CSS alternativi separati da virgola
# (Playwright li risolve nell'ordine, usa il primo che trova).
# ---------------------------------------------------------------------------

SEL = {
    # --- Login ---
    "login_email":    'input[name="email"], input[type="email"], input[id*="email"]',
    "login_password": 'input[name="password"], input[type="password"], input[id*="password"]',
    "login_submit":   'button[type="submit"], input[type="submit"], button:has-text("Accedi"), '
                      'button:has-text("Login"), button:has-text("Entra")',

    # --- Navigazione verso nuova struttura ---
    # Bottone / link per aggiungere una nuova struttura nell'area gestione
    "btn_nuova_struttura": 'a:has-text("Nuova struttura"), a:has-text("Aggiungi struttura"), '
                           'button:has-text("Nuova struttura"), button:has-text("Aggiungi"), '
                           'a[href*="nuova"], a[href*="new"]',

    # --- Tab/sezioni del form multi-step ---
    # KrossBooking usa tab cliccabili (se il form è su una sola pagina,
    # questi selettori vengono ignorati silenziosamente).
    "tab_dati_generali":  '[data-tab="generale"], a:has-text("Dati Generali"), '
                          'li:has-text("Generale"), .tab:has-text("Generale")',
    "tab_ubicazione":     '[data-tab="ubicazione"], a:has-text("Ubicazione"), '
                          'li:has-text("Ubicazione"), .tab:has-text("Ubicazione")',
    "tab_descrizione":    '[data-tab="descrizione"], a:has-text("Descrizione"), '
                          'li:has-text("Descrizione"), .tab:has-text("Descrizione")',
    "tab_tariffe":        '[data-tab="tariffe"], a:has-text("Tariffe"), '
                          'li:has-text("Tariffe"), .tab:has-text("Tariffe")',
    "tab_disponibilita":  '[data-tab="disponibilita"], a:has-text("Disponibilità"), '
                          'li:has-text("Disponibilità"), .tab:has-text("Disponibilità")',
    "tab_contatti":       '[data-tab="contatti"], a:has-text("Contatti"), '
                          'li:has-text("Contatti"), .tab:has-text("Contatti")',

    # --- Sezione 1: Dati Generali ---
    "codice_struttura":       'input[name="codice"], input[name="codice_struttura"], '
                              'input[id*="codice"]',
    "nome_proprieta":         'input[name="nome"], input[name="nome_struttura"], '
                              'input[name="title"], input[id*="nome"]',
    "tipo_struttura":         'select[name="tipo"], select[name="tipo_struttura"], '
                              'select[id*="tipo"]',
    "max_ospiti":             'input[name="max_ospiti"], input[name="ospiti"], '
                              'input[name="capacita"], input[id*="ospiti"]',
    "num_letti":              'input[name="letti"], input[name="num_letti"], '
                              'input[name="posti_letto"], input[id*="letti"]',
    "num_bagni":              'input[name="bagni"], input[name="num_bagni"], '
                              'input[id*="bagni"]',
    "superficie":             'input[name="superficie"], input[name="mq"], '
                              'input[id*="superficie"], input[id*="mq"]',
    "check_in_ore":           'input[name="check_in"], input[name="ora_checkin"], '
                              'input[name="checkin_time"], input[id*="check_in"]',
    "check_out_ore":          'input[name="check_out"], input[name="ora_checkout"], '
                              'input[name="checkout_time"], input[id*="check_out"]',
    "politica_cancellazione": 'select[name="politica_cancellazione"], '
                              'select[name="cancellation_policy"], '
                              'select[id*="politica"]',

    # --- Sezione 2: Ubicazione ---
    "indirizzo":   'input[name="indirizzo"], input[name="via"], input[name="address"], '
                   'input[id*="indirizzo"]',
    "citta":       'input[name="citta"], input[name="city"], input[id*="citta"]',
    "provincia":   'select[name="provincia"], input[name="provincia"], input[id*="provincia"]',
    "cap":         'input[name="cap"], input[name="postal_code"], input[id*="cap"]',
    "nazione":     'select[name="nazione"], select[name="country"], input[name="nazione"]',

    # --- Sezione 3: Descrizione ---
    "descrizione": 'textarea[name="descrizione"], textarea[name="description"], '
                   'textarea[id*="descrizione"]',

    # --- Sezione 4: Tariffe ---
    "prezzo_base_notte":    'input[name="prezzo_notte"], input[name="prezzo_base"], '
                            'input[name="tariffa_notte"], input[id*="prezzo"]',
    "tariffa_settimanale":  'input[name="prezzo_settimana"], input[name="tariffa_settimanale"], '
                            'input[id*="settimana"]',
    "deposito_cauzionale":  'input[name="cauzione"], input[name="deposito"], '
                            'input[id*="cauzione"], input[id*="deposito"]',
    "tariffa_pulizie":      'input[name="pulizie"], input[name="tariffa_pulizie"], '
                            'input[id*="pulizie"]',

    # --- Sezione 5: Disponibilità ---
    "disponibile_dal":   'input[name="disponibile_dal"], input[name="data_inizio"], '
                         'input[name="available_from"], input[id*="dal"]',
    "disponibile_al":    'input[name="disponibile_al"], input[name="data_fine"], '
                         'input[name="available_to"], input[id*="al"]',
    "soggiorno_minimo":  'input[name="soggiorno_minimo"], input[name="min_stay"], '
                         'input[id*="soggiorno"]',

    # --- Sezione 6: Contatti ---
    "email_contatto":    'input[name="email_contatto"], input[name="contatto_email"], '
                         'input[name="contact_email"], input[id*="email"]',
    "telefono_contatto": 'input[name="telefono"], input[name="contatto_telefono"], '
                         'input[name="phone"], input[id*="telefono"]',

    # --- Salvataggio ---
    "salva":    'button[type="submit"]:has-text("Salva"), '
                'button[type="submit"]:has-text("Pubblica"), '
                'button[type="submit"]:has-text("Crea struttura"), '
                'button[type="submit"]:has-text("Inserisci"), '
                'button:has-text("Salva e pubblica"), '
                'input[type="submit"]',
    # Pulsante "Avanti" nei form wizard multi-step
    "avanti":   'button:has-text("Avanti"), button:has-text("Prossimo"), '
                'button:has-text("Next"), a:has-text("Avanti")',
}


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------

@dataclass
class Struttura:
    codice_struttura: str
    nome_proprieta: str
    tipo_struttura: str
    descrizione: str
    max_ospiti: int
    num_letti: int
    num_bagni: int
    superficie_mq: float
    check_in_ore: str
    check_out_ore: str
    soggiorno_minimo: int
    prezzo_base_notte: float
    tariffa_settimanale: float
    deposito_cauzionale: float
    tariffa_pulizie: float
    politica_cancellazione: str
    indirizzo: str
    citta: str
    provincia: str
    cap: str
    nazione: str
    disponibile_dal: str
    disponibile_al: str
    email_contatto: str
    telefono_contatto: str


# ---------------------------------------------------------------------------
# Lettura CSV
# ---------------------------------------------------------------------------

def leggi_csv(percorso: str) -> list[Struttura]:
    path = Path(percorso)
    if not path.exists():
        print(f"[ERRORE] File non trovato: {percorso}", file=sys.stderr)
        sys.exit(1)

    risultati = []
    with open(path, newline="", encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            risultati.append(Struttura(
                codice_struttura=riga["codice_struttura"],
                nome_proprieta=riga["nome_proprieta"],
                tipo_struttura=riga["tipo_struttura"],
                descrizione=riga["descrizione"],
                max_ospiti=int(riga["max_ospiti"]),
                num_letti=int(riga["num_letti"]),
                num_bagni=int(riga["num_bagni"]),
                superficie_mq=float(riga["superficie_mq"]),
                check_in_ore=riga["check_in_ore"],
                check_out_ore=riga["check_out_ore"],
                soggiorno_minimo=int(riga["soggiorno_minimo"]),
                prezzo_base_notte=float(riga["prezzo_base_notte"]),
                tariffa_settimanale=float(riga["tariffa_settimanale"]),
                deposito_cauzionale=float(riga["deposito_cauzionale"]),
                tariffa_pulizie=float(riga["tariffa_pulizie"]),
                politica_cancellazione=riga["politica_cancellazione"],
                indirizzo=riga["indirizzo"],
                citta=riga["citta"],
                provincia=riga["provincia"],
                cap=riga["cap"],
                nazione=riga["nazione"],
                disponibile_dal=riga["disponibile_dal"],
                disponibile_al=riga["disponibile_al"],
                email_contatto=riga["email_contatto"],
                telefono_contatto=riga["telefono_contatto"],
            ))
    return risultati


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run(strutture: list[Struttura]) -> None:
    print(f"\n{'='*68}")
    print("DRY RUN — dati che verrebbero inseriti su KrossBooking")
    print(f"{'='*68}")
    for i, s in enumerate(strutture):
        print(f"\n[{i}] {s.nome_proprieta}  ({s.codice_struttura})")
        print(f"  Tipo              : {s.tipo_struttura}")
        print(f"  Capacità          : {s.max_ospiti} ospiti  |  letti: {s.num_letti}  |  bagni: {s.num_bagni}")
        print(f"  Superficie        : {s.superficie_mq} m²")
        print(f"  Orari             : check-in {s.check_in_ore}  /  check-out {s.check_out_ore}")
        print(f"  Soggiorno min.    : {s.soggiorno_minimo} notti")
        print(f"  Politica canc.    : {s.politica_cancellazione}")
        print(f"  Prezzo notte      : €{s.prezzo_base_notte:.2f}")
        print(f"  Tariffa sett.     : €{s.tariffa_settimanale:.2f}")
        print(f"  Deposito cauz.    : €{s.deposito_cauzionale:.2f}")
        print(f"  Tariffa pulizie   : €{s.tariffa_pulizie:.2f}")
        print(f"  Ubicazione        : {s.indirizzo}, {s.citta} ({s.provincia}) {s.cap}")
        print(f"  Disponibile       : {s.disponibile_dal} → {s.disponibile_al}")
        print(f"  Contatto          : {s.email_contatto}  {s.telefono_contatto}")
        print(f"  Descrizione       : {s.descrizione[:90]}…")
    print(f"\n{'='*68}\n")


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


def _clicca_tab(page, selettore: str, nome_tab: str) -> bool:
    """Clicca su un tab del form multi-step (ignora silenziosamente se non trovato)."""
    try:
        loc = page.locator(selettore).first
        if loc.count() and loc.is_visible(timeout=2_000):
            loc.click()
            page.wait_for_load_state("domcontentloaded")
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Logica principale Playwright
# ---------------------------------------------------------------------------

def login(page, email: str, password: str) -> None:
    print(f"  Navigazione a {LOGIN_URL} …")
    page.goto(LOGIN_URL, wait_until="networkidle")
    _screenshot(page, "01_login_page")

    _fill(page, SEL["login_email"],    email,    "login_email")
    _fill(page, SEL["login_password"], password, "login_password")
    page.locator(SEL["login_submit"]).first.click()
    page.wait_for_load_state("networkidle")
    _screenshot(page, "02_dopo_login")

    if "login" in page.url.lower():
        print("[ERRORE] Login non riuscito. Controlla KB_EMAIL e KB_PASSWORD.", file=sys.stderr)
        sys.exit(1)
    print("  Login effettuato.")


def vai_a_nuova_struttura(page) -> None:
    """Naviga al form di inserimento nuova struttura."""
    print(f"  Navigazione a {STRUTTURE_URL} …")
    page.goto(STRUTTURE_URL, wait_until="networkidle")
    _screenshot(page, "03_lista_strutture")

    # Prova prima il pulsante "Nuova struttura" nell'interfaccia
    try:
        btn = page.locator(SEL["btn_nuova_struttura"]).first
        btn.wait_for(state="visible", timeout=4_000)
        btn.click()
        page.wait_for_load_state("networkidle")
        _screenshot(page, "04_form_nuova_struttura")
        print("  Form nuova struttura aperto via bottone.")
        return
    except Exception:
        pass

    # Fallback: URL diretto
    for url in [NUOVA_STRUTTURA,
                f"{BASE_URL}/struttura/nuova",
                f"{BASE_URL}/properties/new",
                f"{BASE_URL}/property/new"]:
        print(f"  [fallback] Provo {url}")
        page.goto(url, wait_until="networkidle")
        if page.locator(SEL["nome_proprieta"]).count() > 0:
            _screenshot(page, "04_form_nuova_struttura_fallback")
            print(f"  Form trovato: {url}")
            return

    _screenshot(page, "04_form_non_trovato")
    print("  [warn] Form nuova struttura non trovato — potrebbe essere già nella pagina corretta.")


def _compila_dati_generali(page, s: Struttura) -> None:
    """Tab 1 — Dati generali della struttura."""
    _clicca_tab(page, SEL["tab_dati_generali"], "Dati Generali")

    _fill(page,   SEL["codice_struttura"],       s.codice_struttura,        "codice_struttura")
    _fill(page,   SEL["nome_proprieta"],         s.nome_proprieta,          "nome_proprieta")
    _select(page, SEL["tipo_struttura"],         s.tipo_struttura,          "tipo_struttura")
    _fill(page,   SEL["max_ospiti"],             str(s.max_ospiti),         "max_ospiti")
    _fill(page,   SEL["num_letti"],              str(s.num_letti),          "num_letti")
    _fill(page,   SEL["num_bagni"],              str(s.num_bagni),          "num_bagni")
    _fill(page,   SEL["superficie"],             str(s.superficie_mq),      "superficie_mq")
    _fill(page,   SEL["check_in_ore"],           s.check_in_ore,            "check_in_ore")
    _fill(page,   SEL["check_out_ore"],          s.check_out_ore,           "check_out_ore")
    _select(page, SEL["politica_cancellazione"], s.politica_cancellazione,  "politica_cancellazione")


def _compila_ubicazione(page, s: Struttura) -> None:
    """Tab 2 — Ubicazione."""
    _clicca_tab(page, SEL["tab_ubicazione"], "Ubicazione")

    _fill(page,   SEL["indirizzo"], s.indirizzo, "indirizzo")
    _fill(page,   SEL["citta"],     s.citta,     "citta")
    _select(page, SEL["provincia"], s.provincia, "provincia")
    _fill(page,   SEL["cap"],       s.cap,       "cap")
    _select(page, SEL["nazione"],   s.nazione,   "nazione")


def _compila_descrizione(page, s: Struttura) -> None:
    """Tab 3 — Descrizione testuale."""
    _clicca_tab(page, SEL["tab_descrizione"], "Descrizione")

    _fill(page, SEL["descrizione"], s.descrizione, "descrizione")


def _compila_tariffe(page, s: Struttura) -> None:
    """Tab 4 — Tariffe."""
    _clicca_tab(page, SEL["tab_tariffe"], "Tariffe")

    _fill(page, SEL["prezzo_base_notte"],   str(s.prezzo_base_notte),   "prezzo_base_notte")
    _fill(page, SEL["tariffa_settimanale"], str(s.tariffa_settimanale), "tariffa_settimanale")
    _fill(page, SEL["deposito_cauzionale"], str(s.deposito_cauzionale), "deposito_cauzionale")
    _fill(page, SEL["tariffa_pulizie"],     str(s.tariffa_pulizie),     "tariffa_pulizie")


def _compila_disponibilita(page, s: Struttura) -> None:
    """Tab 5 — Disponibilità."""
    _clicca_tab(page, SEL["tab_disponibilita"], "Disponibilità")

    _fill(page, SEL["disponibile_dal"],  s.disponibile_dal,        "disponibile_dal")
    _fill(page, SEL["disponibile_al"],   s.disponibile_al,         "disponibile_al")
    _fill(page, SEL["soggiorno_minimo"], str(s.soggiorno_minimo),  "soggiorno_minimo")


def _compila_contatti(page, s: Struttura) -> None:
    """Tab 6 — Contatti."""
    _clicca_tab(page, SEL["tab_contatti"], "Contatti")

    _fill(page, SEL["email_contatto"],    s.email_contatto,    "email_contatto")
    _fill(page, SEL["telefono_contatto"], s.telefono_contatto, "telefono_contatto")


def compila_form(page, s: Struttura) -> None:
    print(f"  Compilazione form: {s.nome_proprieta!r} …")

    _compila_dati_generali(page, s)
    _compila_ubicazione(page, s)
    _compila_descrizione(page, s)
    _compila_tariffe(page, s)
    _compila_disponibilita(page, s)
    _compila_contatti(page, s)

    _screenshot(page, f"05_form_compilato_{s.cap}")


def salva_struttura(page, s: Struttura) -> bool:
    """Clicca il bottone di salvataggio e verifica il risultato."""
    try:
        page.locator(SEL["salva"]).first.click()
        page.wait_for_load_state("networkidle")
        _screenshot(page, f"06_dopo_salvataggio_{s.cap}")

        body = page.locator("body").inner_text().lower()
        if any(kw in body for kw in ("salvata", "salvato", "creata", "inserita",
                                     "successo", "success", "pubblicata", "grazie")):
            print(f"  [OK] Struttura inserita: {s.nome_proprieta!r}")
            return True
        if any(kw in body for kw in ("errore", "error", "obbligatorio", "required",
                                     "campo mancante")):
            print(f"  [warn] Possibile errore validazione per: {s.nome_proprieta!r}")
            _screenshot(page, f"06_errore_validazione_{s.cap}")
            return False
        print(f"  [OK?] Salvataggio inviato per: {s.nome_proprieta!r} (verificare su KrossBooking)")
        return True
    except Exception as exc:
        print(f"  [ERRORE] Impossibile cliccare 'Salva': {exc}", file=sys.stderr)
        _screenshot(page, f"06_salva_fallito_{s.cap}")
        return False


def inserisci_struttura(page, s: Struttura) -> bool:
    try:
        vai_a_nuova_struttura(page)
        compila_form(page, s)
        return salva_struttura(page, s)
    except Exception as exc:
        print(f"  [ERRORE] {s.nome_proprieta!r}: {exc}", file=sys.stderr)
        _screenshot(page, f"errore_generico_{s.cap}")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inserisce strutture su KrossBooking PMS a partire da un CSV."
    )
    parser.add_argument(
        "--csv",
        default="output/krossbooking.csv",
        help="Path del file CSV (default: output/krossbooking.csv)",
    )
    parser.add_argument(
        "--indice",
        type=int,
        default=None,
        help="Indice 0-based della singola struttura da caricare (default: tutte)",
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
        help="Secondi di pausa tra una struttura e la successiva (default: 2.0)",
    )
    args = parser.parse_args()

    tutte = leggi_csv(args.csv)
    if not tutte:
        print("[ERRORE] Nessuna struttura trovata nel CSV.", file=sys.stderr)
        sys.exit(1)

    da_caricare = [tutte[args.indice]] if args.indice is not None else tutte
    print(f"\nStrutture da caricare: {len(da_caricare)} su {len(tutte)} totali.")

    if args.dry_run:
        dry_run(da_caricare)
        return

    email    = os.environ.get("KB_EMAIL", "").strip()
    password = os.environ.get("KB_PASSWORD", "").strip()
    if not email or not password:
        print(
            "[ERRORE] Imposta le variabili d'ambiente KB_EMAIL e KB_PASSWORD:\n"
            "  export KB_EMAIL='tua@email.it'\n"
            "  export KB_PASSWORD='tuapassword'",
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

            for i, s in enumerate(da_caricare):
                print(f"\n[{i+1}/{len(da_caricare)}] Inserimento: {s.nome_proprieta!r}")
                if inserisci_struttura(page, s):
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
