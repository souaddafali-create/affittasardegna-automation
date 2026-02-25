#!/usr/bin/env python3
"""
Esplorazione Booking.com Partner Hub — SOLO lettura, nessuna scrittura.

Questo script NON inserisce nulla. Naviga le pagine chiave del flusso
"aggiungi proprietà" di Booking.com e salva screenshot + HTML di ogni step
come artefatti per analizzare i selettori reali.

Step eseguiti:
  1. Apre https://account.booking.com/sign-in  → screenshot + HTML
  2. Inserisce credenziali e fa login           → screenshot + HTML
  3. Naviga alla pagina extranet / home         → screenshot + HTML
  4. Cerca e clicca "Aggiungi proprietà"        → screenshot + HTML
  5. STOP — stampa riepilogo di tutto trovato

Uso:
    export BK_EMAIL='tua@email.it'
    export BK_PASSWORD='tuapassword'
    python3 booking_explorer.py

Output:
    artefatti_booking/
        01_login_page.png
        01_login_page.html
        02_dopo_login.png
        02_dopo_login.html
        03_extranet_home.png
        03_extranet_home.html
        04_aggiungi_proprieta.png
        04_aggiungi_proprieta.html
        riepilogo.txt
"""

import os
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("artefatti_booking")

LOGIN_URL    = "https://account.booking.com/sign-in"
EXTRANET_URL = "https://admin.booking.com/"

# URL candidati per la pagina "aggiungi proprietà"
AGGIUNGI_URLS = [
    "https://admin.booking.com/hotel/hoteladmin/overview/create/",
    "https://partner.booking.com/",
    "https://join.booking.com/",
]

# Possibili selettori per il bottone "aggiungi/lista proprietà"
SEL_AGGIUNGI = (
    'a:has-text("List your property"), '
    'a:has-text("Add property"), '
    'a:has-text("Aggiungi proprietà"), '
    'a:has-text("Register a new property"), '
    'button:has-text("List property"), '
    'a[href*="create"], a[href*="register"], a[href*="join"]'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _salva(page, nome: str, log: list[str]) -> None:
    """Salva screenshot PNG e sorgente HTML nella cartella OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    png = OUTPUT_DIR / f"{nome}.png"
    try:
        page.screenshot(path=str(png), full_page=True)
        msg = f"  [screenshot] {png.name}"
        print(msg)
        log.append(msg)
    except Exception as e:
        print(f"  [warn] screenshot {nome} fallito: {e}")

    html_path = OUTPUT_DIR / f"{nome}.html"
    try:
        html = page.content()
        html_path.write_text(html, encoding="utf-8")
        msg = f"  [html]       {html_path.name}  ({len(html):,} bytes)"
        print(msg)
        log.append(msg)
    except Exception as e:
        print(f"  [warn] salvataggio HTML {nome} fallito: {e}")


def _goto(page, url: str, log: list[str]) -> bool:
    """Naviga verso url con fallback da networkidle a domcontentloaded."""
    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
        return True
    except Exception:
        pass
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        return True
    except Exception as e:
        msg = f"  [errore] Navigazione a {url} fallita: {e}"
        print(msg)
        log.append(msg)
        return False


def _wait_load(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=8_000)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Step 1 — Pagina di login
# ---------------------------------------------------------------------------

def step_login_page(page, log: list[str]) -> None:
    print(f"\n[STEP 1] Apro pagina login: {LOGIN_URL}")
    _goto(page, LOGIN_URL, log)
    _salva(page, "01_login_page", log)

    # Stampa info base sulla pagina
    try:
        title = page.title()
        url   = page.url
        msg = f"  [info] title={title!r}  url={url}"
        print(msg)
        log.append(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Step 2 — Login con credenziali
# ---------------------------------------------------------------------------

def step_login(page, email: str, password: str, log: list[str]) -> bool:
    print("\n[STEP 2] Inserisco credenziali e faccio login …")

    # Selettori multipli per compatibilità con variazioni del form
    campi_email = [
        'input#loginname',
        'input[name="loginname"]',
        'input[name="username"]',
        'input[type="email"]',
    ]
    campi_pwd = [
        'input#password',
        'input[name="password"]',
        'input[type="password"]',
    ]
    bottoni_submit = [
        'button[type="submit"]',
        '.bui-button--primary',
        'button:has-text("Sign in")',
        'button:has-text("Accedi")',
        'input[type="submit"]',
    ]

    # Compila email
    compilato_email = False
    for sel in campi_email:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=3_000):
                loc.clear()
                loc.fill(email)
                log.append(f"  [ok] email compilata con selettore: {sel}")
                compilato_email = True
                break
        except Exception:
            continue
    if not compilato_email:
        msg = "  [warn] campo email non trovato"
        print(msg); log.append(msg)

    # Compila password
    compilato_pwd = False
    for sel in campi_pwd:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=3_000):
                loc.clear()
                loc.fill(password)
                log.append(f"  [ok] password compilata con selettore: {sel}")
                compilato_pwd = True
                break
        except Exception:
            continue
    if not compilato_pwd:
        msg = "  [warn] campo password non trovato"
        print(msg); log.append(msg)

    # Clicca submit
    cliccato = False
    for sel in bottoni_submit:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=2_000):
                loc.click()
                log.append(f"  [ok] submit cliccato con selettore: {sel}")
                cliccato = True
                break
        except Exception:
            continue
    if not cliccato:
        msg = "  [warn] bottone submit non trovato"
        print(msg); log.append(msg)

    _wait_load(page)
    _salva(page, "02_dopo_login", log)

    url_attuale = page.url.lower()
    title = page.title()
    msg = f"  [info] dopo login → url={page.url!r}  title={title!r}"
    print(msg); log.append(msg)

    if "sign-in" in url_attuale or "login" in url_attuale:
        msg = "  [warn] Sembra ancora sulla pagina login — credenziali errate o 2FA richiesto"
        print(msg); log.append(msg)
        return False

    print("  [ok] Login effettuato.")
    return True


# ---------------------------------------------------------------------------
# Step 3 — Extranet home
# ---------------------------------------------------------------------------

def step_extranet_home(page, log: list[str]) -> None:
    print(f"\n[STEP 3] Navigo all'Extranet home: {EXTRANET_URL}")
    _goto(page, EXTRANET_URL, log)
    _salva(page, "03_extranet_home", log)

    url   = page.url
    title = page.title()
    msg = f"  [info] url={url!r}  title={title!r}"
    print(msg); log.append(msg)

    # Cerca link "List your property" o "Aggiungi proprietà"
    try:
        links = page.locator("a").all()
        trovati = []
        for lnk in links[:80]:  # primi 80 link
            try:
                testo = lnk.inner_text().strip()
                href  = lnk.get_attribute("href") or ""
                if testo and (
                    any(kw in testo.lower() for kw in
                        ("list", "add", "new", "aggiungi", "nuova", "register", "property", "proprietà"))
                    or any(kw in href.lower() for kw in ("create", "register", "new", "add"))
                ):
                    trovati.append(f"    LINK: {testo!r} → {href}")
            except Exception:
                continue
        if trovati:
            msg = "  [info] Link candidati per 'aggiungi proprietà':"
            print(msg); log.append(msg)
            for t in trovati:
                print(t); log.append(t)
        else:
            msg = "  [info] Nessun link candidato trovato nella home"
            print(msg); log.append(msg)
    except Exception as e:
        log.append(f"  [warn] scansione link fallita: {e}")


# ---------------------------------------------------------------------------
# Step 4 — Navigazione alla pagina "aggiungi proprietà"
# ---------------------------------------------------------------------------

def step_aggiungi_proprieta(page, log: list[str]) -> None:
    print("\n[STEP 4] Cerco pagina 'Aggiungi proprietà' …")

    # Prima prova il bottone in pagina
    try:
        btn = page.locator(SEL_AGGIUNGI).first
        if btn.count() and btn.is_visible(timeout=3_000):
            href = btn.get_attribute("href") or ""
            testo = btn.inner_text().strip()
            msg = f"  [ok] Bottone trovato: {testo!r} → {href}"
            print(msg); log.append(msg)
            btn.click()
            _wait_load(page)
            _salva(page, "04_aggiungi_proprieta", log)
            msg = f"  [info] url dopo click: {page.url!r}"
            print(msg); log.append(msg)
            _stampa_form_info(page, log)
            return
    except Exception:
        pass

    # Fallback: prova URL diretti
    for url in AGGIUNGI_URLS:
        print(f"  [fallback] Provo URL diretto: {url}")
        if _goto(page, url, log):
            _salva(page, f"04_aggiungi_{url.split('/')[2].replace('.', '_')}", log)
            url_att = page.url
            title   = page.title()
            msg = f"  [info] url={url_att!r}  title={title!r}"
            print(msg); log.append(msg)
            _stampa_form_info(page, log)
            # Se la pagina contiene un form o un wizard, ci siamo
            n_input = page.locator("input").count()
            n_select = page.locator("select").count()
            if n_input > 2 or n_select > 0:
                msg = f"  [ok] Pagina con form trovata — {n_input} input, {n_select} select"
                print(msg); log.append(msg)
                return

    msg = "  [warn] Pagina 'aggiungi proprietà' non raggiunta — verificare screenshot e HTML"
    print(msg); log.append(msg)


def _stampa_form_info(page, log: list[str]) -> None:
    """Analizza input e select presenti nella pagina e li stampa nel log."""
    try:
        inputs  = page.locator("input").all()
        selects = page.locator("select").all()
        buttons = page.locator("button").all()

        if inputs:
            log.append(f"  [form] {len(inputs)} input trovati:")
            for inp in inputs[:30]:
                try:
                    t    = inp.get_attribute("type") or "text"
                    name = inp.get_attribute("name") or ""
                    id_  = inp.get_attribute("id") or ""
                    ph   = inp.get_attribute("placeholder") or ""
                    msg  = f"    input type={t!r} name={name!r} id={id_!r} placeholder={ph!r}"
                    print(msg); log.append(msg)
                except Exception:
                    continue

        if selects:
            log.append(f"  [form] {len(selects)} select trovate:")
            for sel in selects[:20]:
                try:
                    name = sel.get_attribute("name") or ""
                    id_  = sel.get_attribute("id") or ""
                    msg  = f"    select name={name!r} id={id_!r}"
                    print(msg); log.append(msg)
                except Exception:
                    continue

        if buttons:
            log.append(f"  [form] {len(buttons)} bottoni trovati:")
            for btn in buttons[:20]:
                try:
                    t    = btn.get_attribute("type") or ""
                    testo = btn.inner_text().strip()[:60]
                    msg  = f"    button type={t!r} testo={testo!r}"
                    print(msg); log.append(msg)
                except Exception:
                    continue

    except Exception as e:
        log.append(f"  [warn] analisi form fallita: {e}")


# ---------------------------------------------------------------------------
# Salva riepilogo testo
# ---------------------------------------------------------------------------

def _salva_riepilogo(log: list[str]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / "riepilogo.txt"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linee = [f"Esplorazione Booking.com — {ts}", "=" * 60, ""] + log + [""]
    path.write_text("\n".join(linee), encoding="utf-8")
    print(f"\n  [riepilogo] Salvato: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    email    = os.environ.get("BK_EMAIL", "").strip()
    password = os.environ.get("BK_PASSWORD", "").strip()
    if not email or not password:
        print(
            "[ERRORE] Imposta BK_EMAIL e BK_PASSWORD:\n"
            "  export BK_EMAIL='tua@email.it'\n"
            "  export BK_PASSWORD='tuapassword'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[ERRORE] Playwright non installato:\n"
            "  pip install playwright\n"
            "  python3 -m playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    log: list[str] = []
    print(f"\n{'='*60}")
    print("ESPLORAZIONE BOOKING.COM PARTNER HUB")
    print(f"{'='*60}")
    print(f"Output artefatti: {OUTPUT_DIR.resolve()}/")
    print(f"Login URL: {LOGIN_URL}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            slow_mo=50,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.on("pageerror", lambda exc: log.append(f"[JS error] {exc}"))

        try:
            step_login_page(page, log)
            logged_in = step_login(page, email, password, log)
            if logged_in:
                step_extranet_home(page, log)
                step_aggiungi_proprieta(page, log)
            else:
                print("\n[WARN] Login non riuscito — screenshot salvati per analisi.")
        except Exception as exc:
            msg = f"[ERRORE CRITICO] {exc}"
            print(msg); log.append(msg)
        finally:
            context.close()
            browser.close()

    _salva_riepilogo(log)

    print(f"\n{'='*60}")
    print(f"Esplorazione completata. Artefatti in: {OUTPUT_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
