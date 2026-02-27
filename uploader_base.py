"""
uploader_base.py — Utilities condivise per tutti gli uploader portale.

Ogni uploader (casevacanza, booking, idealista, expedia, immobiliare)
importa da qui le funzioni comuni. Zero duplicazione.
"""

import json
import os
import tempfile
import urllib.request


# ---------------------------------------------------------------------------
# Caricamento dati proprietà
# ---------------------------------------------------------------------------

def load_property_data(default="Il_Faro_Badesi_DATI.json"):
    """Carica JSON proprietà da env PROPERTY_DATA o file default."""
    data_file = os.environ.get(
        "PROPERTY_DATA",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), default),
    )
    with open(data_file, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Screenshot e debug
# ---------------------------------------------------------------------------

class StepCounter:
    """Contatore globale per numerare screenshot progressivi."""
    def __init__(self):
        self.value = 0

    def next(self):
        self.value += 1
        return self.value


def screenshot(page, name, counter, screenshot_dir="screenshots"):
    """Salva screenshot full-page con contatore progressivo."""
    n = counter.next()
    path = f"{screenshot_dir}/step{n:02d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def save_html(page, name, screenshot_dir="screenshots"):
    """Salva HTML completo della pagina per debug."""
    path = f"{screenshot_dir}/{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  HTML salvato: {path}")


def wait(page, ms=5000):
    """Attesa tra step — wrapper Playwright."""
    page.wait_for_timeout(ms)


# ---------------------------------------------------------------------------
# Gestione step con try/except
# ---------------------------------------------------------------------------

def try_step(page, step_name, func, counter, screenshot_dir="screenshots"):
    """Esegue uno step con gestione errore. Screenshot + HTML su fallimento."""
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}", counter, screenshot_dir)
        save_html(page, f"errore_{step_name}", screenshot_dir)


# ---------------------------------------------------------------------------
# Foto placeholder per test
# ---------------------------------------------------------------------------

def download_placeholder_photos(count=5):
    """Scarica foto test da picsum.photos. Restituisce lista path."""
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
# Costruzione lista servizi da JSON
# ---------------------------------------------------------------------------

def build_services(dotazioni, mapping):
    """Costruisce la lista servizi attivi (true) dato JSON dotazioni + mappatura portale.

    Args:
        dotazioni: dict dal JSON proprietà (PROP["dotazioni"])
        mapping: dict {chiave_json: label_portale} specifico del portale

    Returns:
        lista di label da selezionare/spuntare sul portale
    """
    servizi = []
    for key, label in mapping.items():
        if dotazioni.get(key) is True:
            servizi.append(label)
    # Parcheggio: controlla flag diretto O stringa in altro_dotazioni
    if dotazioni.get("parcheggio_privato") is True or \
       "parcheggio" in (dotazioni.get("altro_dotazioni") or "").lower():
        if "Parcheggio" not in [s for s in servizi]:
            servizi.append("Parcheggio")
    return servizi


# ---------------------------------------------------------------------------
# Setup browser Playwright
# ---------------------------------------------------------------------------

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def create_browser_context(playwright, headless=True, locale="it-IT",
                           user_agent=None, stealth=False,
                           extra_args=None):
    """Crea browser + context Playwright con configurazione standard.

    Args:
        playwright: istanza sync_playwright
        headless: True per CI, False per interattivo
        locale: lingua browser
        user_agent: override user agent
        stealth: tenta di applicare playwright-stealth
        extra_args: argomenti aggiuntivi per il browser

    Returns:
        (browser, context, page)
    """
    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    if extra_args:
        launch_args.extend(extra_args)

    browser = playwright.chromium.launch(headless=headless, args=launch_args)
    context = browser.new_context(
        locale=locale,
        viewport={"width": 1366, "height": 768},
        user_agent=user_agent or DEFAULT_USER_AGENT,
        java_script_enabled=True,
    )
    page = context.new_page()

    if stealth:
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.")

    return browser, context, page
