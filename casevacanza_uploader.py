#!/usr/bin/env python3
"""
Uploader automatico per CaseVacanza.it — inserimento proprietà via Playwright.

Legge le credenziali da variabili d'ambiente:
    CV_EMAIL    — email dell'account CaseVacanza.it
    CV_PASSWORD — password dell'account CaseVacanza.it

Legge i dati delle proprietà da output/casevacanza.csv (generato da
property_processor.py) e inserisce ciascuna proprietà tramite il form
web del portale.

Uso:
    # Inserisce tutte le proprietà (browser visibile)
    python3 casevacanza_uploader.py

    # Solo la seconda proprietà del CSV (indice 0-based)
    python3 casevacanza_uploader.py --indice 1

    # Browser invisibile (headless)
    python3 casevacanza_uploader.py --headless

    # Stampa i dati che verrebbero inseriti senza aprire il browser
    python3 casevacanza_uploader.py --dry-run

    # File CSV alternativo
    python3 casevacanza_uploader.py --csv output_test_nord/casevacanza.csv
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
# SELETTORI
# Tutti i selettori CSS / testo sono concentrati qui per poterli aggiornare
# rapidamente se il sito cambia layout.
# ---------------------------------------------------------------------------

SEL = {
    # --- Login ---
    "login_email":    'input[name="email"], input[type="email"]',
    "login_password": 'input[name="password"], input[type="password"]',
    "login_submit":   'button[type="submit"], input[type="submit"]',

    # --- Menu / navigazione ---
    # Link/bottone "Inserisci annuncio" nell'area proprietario
    "inserisci_annuncio": 'a:has-text("Inserisci"), a:has-text("Nuovo annuncio"), '
                          'a:has-text("Aggiungi proprietà"), button:has-text("Inserisci")',

    # --- Form inserimento proprietà ---
    "titolo":            'input[name="titolo"], input[name="title"], input[id*="titolo"]',
    "tipo_immobile":     'select[name="tipo"], select[name="tipologia"], select[id*="tipo"]',
    "descrizione_breve": 'textarea[name="descrizione_breve"], textarea[id*="breve"]',
    "descrizione":       'textarea[name="descrizione"], textarea[id*="descrizione"], '
                         'textarea[name="description"]',
    "prezzo_notte":      'input[name="prezzo_notte"], input[name="prezzo"], input[id*="prezzo"]',
    "prezzo_settimana":  'input[name="prezzo_settimana"], input[id*="settimana"]',
    "cauzione":          'input[name="cauzione"], input[id*="cauzione"]',
    "soggiorno_min":     'input[name="soggiorno_minimo"], input[name="min_stay"], '
                         'input[id*="soggiorno"]',
    "ospiti_max":        'input[name="ospiti"], input[name="ospiti_max"], '
                         'input[name="max_ospiti"], input[id*="ospiti"]',
    "camere":            'input[name="camere"], input[name="num_camere"], input[id*="camere"]',
    "bagni":             'input[name="bagni"], input[name="num_bagni"], input[id*="bagni"]',
    "superficie":        'input[name="superficie"], input[name="mq"], input[id*="mq"]',
    "indirizzo":         'input[name="indirizzo"], input[name="via"], input[id*="indirizzo"]',
    "localita":          'input[name="localita"], input[name="citta"], input[id*="localita"]',
    "cap":               'input[name="cap"], input[name="postal_code"], input[id*="cap"]',
    "provincia":         'select[name="provincia"], input[name="provincia"]',
    "disponibile_dal":   'input[name="disponibile_dal"], input[name="data_inizio"], '
                         'input[id*="dal"], input[type="date"]:first-of-type',
    "disponibile_al":    'input[name="disponibile_al"], input[name="data_fine"], '
                         'input[id*="al"]',
    "contatto_email":    'input[name="contatto_email"], input[name="email_contatto"]',
    "contatto_telefono": 'input[name="telefono"], input[name="contatto_telefono"]',

    # Pulsante salvataggio finale
    "salva": 'button[type="submit"]:has-text("Salva"), '
             'button[type="submit"]:has-text("Pubblica"), '
             'button[type="submit"]:has-text("Inserisci"), '
             'input[type="submit"]',
}

# URL del portale
BASE_URL    = "https://www.casevacanza.it"
LOGIN_URL   = f"{BASE_URL}/login"
ANNUNCI_URL = f"{BASE_URL}/proprietario/annunci"   # area gestione proprietario

# Cartella dove salvare gli screenshot in caso di errore
SCREENSHOT_DIR = Path("screenshot_errori")


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------

@dataclass
class Proprieta:
    titolo: str
    tipo_immobile: str
    descrizione_breve: str
    descrizione_completa: str
    lingua_annuncio: str
    prezzo_per_notte_eur: float
    prezzo_per_settimana_eur: float
    cauzione_eur: float
    soggiorno_minimo_notti: int
    numero_ospiti_max: int
    numero_camere: int
    numero_bagni: int
    superficie_mq: float
    indirizzo: str
    localita: str
    provincia: str
    regione: str
    cap: str
    nazione: str
    disponibile_dal: str
    disponibile_al: str
    contatto_email: str
    contatto_telefono: str


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
                titolo=riga["titolo_annuncio"],
                tipo_immobile=riga["tipo_immobile"],
                descrizione_breve=riga["descrizione_breve"],
                descrizione_completa=riga["descrizione_completa"],
                lingua_annuncio=riga["lingua_annuncio"],
                prezzo_per_notte_eur=float(riga["prezzo_per_notte_eur"]),
                prezzo_per_settimana_eur=float(riga["prezzo_per_settimana_eur"]),
                cauzione_eur=float(riga["cauzione_eur"]),
                soggiorno_minimo_notti=int(riga["soggiorno_minimo_notti"]),
                numero_ospiti_max=int(riga["numero_ospiti_max"]),
                numero_camere=int(riga["numero_camere"]),
                numero_bagni=int(riga["numero_bagni"]),
                superficie_mq=float(riga["superficie_mq"]),
                indirizzo=riga["indirizzo"],
                localita=riga["localita"],
                provincia=riga["provincia"],
                regione=riga["regione"],
                cap=riga["cap"],
                nazione=riga["nazione"],
                disponibile_dal=riga["disponibile_dal"],
                disponibile_al=riga["disponibile_al"],
                contatto_email=riga["contatto_email"],
                contatto_telefono=riga["contatto_telefono"],
            ))
    return risultati


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run(proprieta: list[Proprieta]) -> None:
    print(f"\n{'='*65}")
    print("DRY RUN — dati che verrebbero inseriti su CaseVacanza.it")
    print(f"{'='*65}")
    for i, p in enumerate(proprieta):
        print(f"\n[{i}] {p.titolo}")
        print(f"  Tipo          : {p.tipo_immobile}")
        print(f"  Localita      : {p.localita} ({p.provincia}) {p.cap}")
        print(f"  Indirizzo     : {p.indirizzo}")
        print(f"  Prezzo notte  : €{p.prezzo_per_notte_eur:.2f}")
        print(f"  Prezzo sett.  : €{p.prezzo_per_settimana_eur:.2f}")
        print(f"  Cauzione      : €{p.cauzione_eur:.2f}")
        print(f"  Ospiti max    : {p.numero_ospiti_max}  |  Camere: {p.numero_camere}  |  Bagni: {p.numero_bagni}")
        print(f"  Superficie    : {p.superficie_mq} m²")
        print(f"  Disponibile   : {p.disponibile_dal} → {p.disponibile_al}")
        print(f"  Soggiorno min : {p.soggiorno_minimo_notti} notti")
        print(f"  Desc. breve   : {p.descrizione_breve[:80]}…")
        print(f"  Contatto      : {p.contatto_email}  {p.contatto_telefono}")
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
        print(f"  [screenshot] Salvato: {path}")
    except Exception:
        pass


def _fill(page, selettore: str, valore: str, nome_campo: str) -> bool:
    """Riempie il primo elemento corrispondente al selettore. Ritorna True se trovato."""
    try:
        loc = page.locator(selettore).first
        loc.wait_for(state="visible", timeout=5_000)
        loc.clear()
        loc.fill(valore)
        return True
    except Exception:
        print(f"  [WARN] Campo non trovato: {nome_campo!r}  (selettore: {selettore[:60]})")
        return False


def _select(page, selettore: str, valore: str, nome_campo: str) -> bool:
    """Seleziona un'opzione da una <select> per testo visibile o valore."""
    try:
        loc = page.locator(selettore).first
        loc.wait_for(state="visible", timeout=5_000)
        # Prova prima per testo, poi per valore
        try:
            loc.select_option(label=valore)
        except Exception:
            loc.select_option(value=valore.lower())
        return True
    except Exception:
        print(f"  [WARN] Select non trovata: {nome_campo!r}  (selettore: {selettore[:60]})")
        return False


# ---------------------------------------------------------------------------
# Logica principale Playwright
# ---------------------------------------------------------------------------

def login(page, email: str, password: str) -> None:
    print(f"  Navigazione a {LOGIN_URL} …")
    page.goto(LOGIN_URL, wait_until="networkidle")
    _screenshot(page, "01_login_page")

    _fill(page, SEL["login_email"], email, "login_email")
    _fill(page, SEL["login_password"], password, "login_password")

    page.locator(SEL["login_submit"]).first.click()
    page.wait_for_load_state("networkidle")
    _screenshot(page, "02_dopo_login")

    # Verifica login riuscito cercando elementi presenti solo se autenticati
    if "login" in page.url or "errore" in page.url.lower():
        _screenshot(page, "02_login_fallito")
        print("[ERRORE] Login non riuscito. Controlla CV_EMAIL e CV_PASSWORD.", file=sys.stderr)
        sys.exit(1)
    print("  Login effettuato.")


def vai_a_nuovo_annuncio(page) -> None:
    print(f"  Navigazione a {ANNUNCI_URL} …")
    page.goto(ANNUNCI_URL, wait_until="networkidle")
    _screenshot(page, "03_area_annunci")

    # Clicca "Inserisci nuovo annuncio"
    try:
        page.locator(SEL["inserisci_annuncio"]).first.click()
        page.wait_for_load_state("networkidle")
        _screenshot(page, "04_form_inserimento")
        print("  Form di inserimento aperto.")
    except Exception:
        # Fallback: prova navigazione diretta a URL tipici
        for url_tentativo in [
            f"{BASE_URL}/proprietario/annunci/nuovo",
            f"{BASE_URL}/inserisci-annuncio",
            f"{BASE_URL}/nuovo-annuncio",
        ]:
            print(f"  [fallback] Provo {url_tentativo}")
            page.goto(url_tentativo, wait_until="networkidle")
            if page.locator(SEL["titolo"]).count() > 0:
                break
        _screenshot(page, "04_form_inserimento_fallback")


def compila_form(page, p: Proprieta) -> None:
    print(f"  Compilazione form: {p.titolo!r} …")

    _fill(page,   SEL["titolo"],            p.titolo,                     "titolo")
    _select(page, SEL["tipo_immobile"],     p.tipo_immobile,              "tipo_immobile")
    _fill(page,   SEL["descrizione_breve"], p.descrizione_breve,          "descrizione_breve")
    _fill(page,   SEL["descrizione"],       p.descrizione_completa,       "descrizione")
    _fill(page,   SEL["prezzo_notte"],      str(p.prezzo_per_notte_eur),  "prezzo_notte")
    _fill(page,   SEL["prezzo_settimana"],  str(p.prezzo_per_settimana_eur), "prezzo_settimana")
    _fill(page,   SEL["cauzione"],          str(p.cauzione_eur),          "cauzione")
    _fill(page,   SEL["soggiorno_min"],     str(p.soggiorno_minimo_notti), "soggiorno_min")
    _fill(page,   SEL["ospiti_max"],        str(p.numero_ospiti_max),     "ospiti_max")
    _fill(page,   SEL["camere"],            str(p.numero_camere),         "camere")
    _fill(page,   SEL["bagni"],             str(p.numero_bagni),          "bagni")
    _fill(page,   SEL["superficie"],        str(p.superficie_mq),         "superficie")
    _fill(page,   SEL["indirizzo"],         p.indirizzo,                  "indirizzo")
    _fill(page,   SEL["localita"],          p.localita,                   "localita")
    _fill(page,   SEL["cap"],               p.cap,                        "cap")
    _select(page, SEL["provincia"],         p.provincia,                  "provincia")
    _fill(page,   SEL["disponibile_dal"],   p.disponibile_dal,            "disponibile_dal")
    _fill(page,   SEL["disponibile_al"],    p.disponibile_al,             "disponibile_al")
    _fill(page,   SEL["contatto_email"],    p.contatto_email,             "contatto_email")
    _fill(page,   SEL["contatto_telefono"], p.contatto_telefono,          "contatto_telefono")

    _screenshot(page, f"05_form_compilato_{p.cap}")


def salva_annuncio(page, p: Proprieta) -> bool:
    try:
        page.locator(SEL["salva"]).first.click()
        page.wait_for_load_state("networkidle")
        _screenshot(page, f"06_dopo_salvataggio_{p.cap}")

        # Controlla presenza di messaggi di conferma / errore comuni
        body = page.locator("body").inner_text()
        if any(kw in body.lower() for kw in ("salvato", "pubblicato", "inserito", "successo", "grazie")):
            print(f"  [OK] Proprietà inserita: {p.titolo!r}")
            return True
        if any(kw in body.lower() for kw in ("errore", "error", "obbligatorio", "required")):
            print(f"  [WARN] Possibile errore dopo il salvataggio per: {p.titolo!r}")
            _screenshot(page, f"06_errore_form_{p.cap}")
            return False
        # Pagina cambiata senza messaggi espliciti → probabilmente ok
        print(f"  [OK?] Salvataggio inviato per: {p.titolo!r} (verificare manualmente)")
        return True
    except Exception as exc:
        print(f"  [ERRORE] Impossibile cliccare 'Salva': {exc}", file=sys.stderr)
        _screenshot(page, f"06_salva_fallito_{p.cap}")
        return False


def inserisci_proprieta(page, p: Proprieta) -> bool:
    try:
        vai_a_nuovo_annuncio(page)
        compila_form(page, p)
        return salva_annuncio(page, p)
    except Exception as exc:
        print(f"  [ERRORE] {p.titolo!r}: {exc}", file=sys.stderr)
        _screenshot(page, f"errore_generico_{p.cap}")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inserisce proprietà su CaseVacanza.it a partire da un CSV."
    )
    parser.add_argument(
        "--csv",
        default="output/casevacanza.csv",
        help="Path del file CSV (default: output/casevacanza.csv)",
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
        default=1.5,
        help="Secondi di pausa tra un annuncio e il successivo (default: 1.5)",
    )
    args = parser.parse_args()

    # Leggi CSV
    tutte = leggi_csv(args.csv)
    if not tutte:
        print("[ERRORE] Nessuna proprietà trovata nel CSV.", file=sys.stderr)
        sys.exit(1)

    # Filtra per indice se richiesto
    da_caricare = [tutte[args.indice]] if args.indice is not None else tutte
    print(f"\nProprietà da caricare: {len(da_caricare)} su {len(tutte)} totali.")

    # Dry run: niente browser
    if args.dry_run:
        dry_run(da_caricare)
        return

    # Credenziali da variabili d'ambiente
    email = os.environ.get("CV_EMAIL", "").strip()
    password = os.environ.get("CV_PASSWORD", "").strip()
    if not email or not password:
        print(
            "[ERRORE] Imposta le variabili d'ambiente CV_EMAIL e CV_PASSWORD:\n"
            "  export CV_EMAIL='tua@email.it'\n"
            "  export CV_PASSWORD='tuapassword'",
            file=sys.stderr,
        )
        sys.exit(1)

    # Importa Playwright solo se non siamo in dry-run
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[ERRORE] Playwright non installato. Esegui:\n"
            "  pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    ok = 0
    ko = 0

    # Percorso del binario Chromium (rilevato automaticamente da Playwright;
    # se la versione pip non corrisponde ai browser scaricati dal CLI di sistema,
    # imposta la variabile d'ambiente CHROMIUM_PATH per sovrascriverlo).
    chromium_path = os.environ.get("CHROMIUM_PATH") or None

    with sync_playwright() as pw:
        launch_kwargs: dict = dict(
            headless=args.headless,
            slow_mo=80,           # rallentamento leggero per stabilità
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

        # Intercetta errori JavaScript per il debug
        page.on("pageerror", lambda exc: print(f"  [JS error] {exc}"))

        try:
            login(page, email, password)

            for i, p in enumerate(da_caricare):
                print(f"\n[{i+1}/{len(da_caricare)}] Inserimento: {p.titolo!r}")
                if inserisci_proprieta(page, p):
                    ok += 1
                else:
                    ko += 1
                if i < len(da_caricare) - 1:
                    time.sleep(args.pausa)

        finally:
            context.close()
            browser.close()

    print(f"\n{'='*50}")
    print(f"Risultato: {ok} inseriti con successo, {ko} falliti.")
    if ko > 0:
        print(f"Gli screenshot degli errori sono in: {SCREENSHOT_DIR}/")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
