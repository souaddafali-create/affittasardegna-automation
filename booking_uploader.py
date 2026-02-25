#!/usr/bin/env python3
"""
Booking.com Partner Hub — Esplorazione sito reale (STEP 1).

Questo script NON inserisce nulla. Naviga le pagine chiave del flusso
di inserimento proprietà su Booking.com e salva screenshot + HTML di ogni
step come artefatti, per identificare i selettori reali.

Step eseguiti:
  1. Apre https://account.booking.com/sign-in  → screenshot + HTML
  2. Inserisce BK_EMAIL e BK_PASSWORD, fa login → screenshot + HTML
  3. Naviga a admin.booking.com (extranet home) → screenshot + HTML
  4. Cerca e raggiunge la pagina "Aggiungi proprietà" → screenshot + HTML
     Stampa tutti i campi form trovati (input/select/button con name/id/placeholder)
  5. STOP — nessuna compilazione

Output in:  artefatti_booking/
  01_login_page.png / .html
  02_dopo_login.png / .html
  03_extranet_home.png / .html
  04_aggiungi_proprieta.png / .html
  riepilogo.txt

Credenziali da variabili d'ambiente:
  BK_EMAIL    — email account Booking.com Partner Hub
  BK_PASSWORD — password account Booking.com Partner Hub

Uso:
  export BK_EMAIL='tua@email.it'
  export BK_PASSWORD='tuapassword'
  python3 booking_uploader.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_DIR   = Path("artefatti_booking")
LOGIN_URL    = "https://account.booking.com/sign-in"
EXTRANET_URL = "https://admin.booking.com/"

# URL candidati per la pagina "aggiungi proprietà" (provati in ordine)
AGGIUNGI_URLS = [
    "https://admin.booking.com/hotel/hoteladmin/overview/create/",
    "https://partner.booking.com/",
    "https://join.booking.com/",
]

# Selettori per trovare il link "Aggiungi / List property" in pagina
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

def _salva(page, nome: str, log: list) -> None:
    """Salva screenshot PNG e HTML nella OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        png = OUTPUT_DIR / f"{nome}.png"
        page.screenshot(path=str(png), full_page=True)
        _log(log, f"[screenshot] {png.name}")
    except Exception as e:
        _log(log, f"[warn] screenshot {nome} fallito: {e}")

    try:
        html_path = OUTPUT_DIR / f"{nome}.html"
        html = page.content()
        html_path.write_text(html, encoding="utf-8")
        _log(log, f"[html]       {html_path.name}  ({len(html):,} bytes)")
    except Exception as e:
        _log(log, f"[warn] HTML {nome} fallito: {e}")


def _log(log: list, msg: str) -> None:
    print(f"  {msg}")
    log.append(msg)


def _goto(page, url: str, log: list) -> bool:
    """Naviga verso url con doppio fallback; non crasha mai."""
    try:
        page.goto(url, wait_until="networkidle", timeout=20_000)
        return True
    except Exception:
        pass
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        return True
    except Exception as e:
        _log(log, f"[errore] Navigazione a {url} fallita: {e}")
        return False


def _wait(page) -> None:
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

def step_01_login_page(page, log: list) -> None:
    print(f"\n[STEP 1] Login page: {LOGIN_URL}")
    _goto(page, LOGIN_URL, log)
    _salva(page, "01_login_page", log)
    try:
        _log(log, f"[info] title={page.title()!r}  url={page.url!r}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Step 2 — Login con credenziali reali
# ---------------------------------------------------------------------------

def step_02_login(page, email: str, password: str, log: list) -> bool:
    print("\n[STEP 2] Login con credenziali …")

    # Selettori email (in ordine di priorità)
    for sel in [
        'input#loginname',
        'input[name="loginname"]',
        'input[name="username"]',
        'input[type="email"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=3_000):
                loc.clear()
                loc.fill(email)
                _log(log, f"[ok] email → selettore: {sel}")
                break
        except Exception:
            continue
    else:
        _log(log, "[warn] campo email non trovato")

    # Selettori password
    for sel in [
        'input#password',
        'input[name="password"]',
        'input[type="password"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=3_000):
                loc.clear()
                loc.fill(password)
                _log(log, f"[ok] password → selettore: {sel}")
                break
        except Exception:
            continue
    else:
        _log(log, "[warn] campo password non trovato")

    # Submit
    for sel in [
        'button[type="submit"]',
        '.bui-button--primary',
        'button:has-text("Sign in")',
        'button:has-text("Accedi")',
        'input[type="submit"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=2_000):
                loc.click()
                _log(log, f"[ok] submit → selettore: {sel}")
                break
        except Exception:
            continue
    else:
        _log(log, "[warn] bottone submit non trovato")

    _wait(page)
    _salva(page, "02_dopo_login", log)
    _log(log, f"[info] title={page.title()!r}  url={page.url!r}")

    if any(kw in page.url.lower() for kw in ("sign-in", "login", "signin")):
        _log(log, "[warn] ancora sulla pagina login — credenziali errate o 2FA attivo")
        return False

    _log(log, "[ok] login effettuato")
    return True


# ---------------------------------------------------------------------------
# Step 3 — Extranet home
# ---------------------------------------------------------------------------

def step_03_extranet_home(page, log: list) -> None:
    print(f"\n[STEP 3] Extranet home: {EXTRANET_URL}")
    _goto(page, EXTRANET_URL, log)
    _salva(page, "03_extranet_home", log)
    _log(log, f"[info] title={page.title()!r}  url={page.url!r}")

    # Scansiona link candidati per "aggiungi proprietà"
    try:
        trovati = []
        for lnk in page.locator("a").all()[:100]:
            try:
                testo = lnk.inner_text().strip()
                href  = lnk.get_attribute("href") or ""
                if testo and (
                    any(k in testo.lower() for k in
                        ("list", "add", "new", "aggiungi", "nuova", "register", "property", "proprietà"))
                    or any(k in href.lower() for k in ("create", "register", "new", "add"))
                ):
                    trovati.append(f"LINK: {testo!r} → {href}")
            except Exception:
                continue
        if trovati:
            _log(log, f"[info] {len(trovati)} link candidati trovati:")
            for t in trovati:
                _log(log, f"  {t}")
        else:
            _log(log, "[info] nessun link candidato trovato nella home")
    except Exception as e:
        _log(log, f"[warn] scansione link fallita: {e}")


# ---------------------------------------------------------------------------
# Step 4 — Pagina "Aggiungi proprietà" + dump campi form
# ---------------------------------------------------------------------------

def step_04_aggiungi_proprieta(page, log: list) -> None:
    print("\n[STEP 4] Cerco pagina 'Aggiungi proprietà' …")

    # Prima prova il bottone in pagina
    try:
        btn = page.locator(SEL_AGGIUNGI).first
        if btn.count() and btn.is_visible(timeout=3_000):
            testo = btn.inner_text().strip()
            href  = btn.get_attribute("href") or ""
            _log(log, f"[ok] bottone trovato: {testo!r} → {href}")
            btn.click()
            _wait(page)
            _salva(page, "04_aggiungi_proprieta", log)
            _log(log, f"[info] url={page.url!r}  title={page.title()!r}")
            _dump_form(page, log)
            return
    except Exception:
        pass

    # Fallback: URL diretti
    for url in AGGIUNGI_URLS:
        print(f"  [fallback] {url}")
        if _goto(page, url, log):
            safe_name = "04_" + url.split("/")[2].replace(".", "_")
            _salva(page, safe_name, log)
            _log(log, f"[info] url={page.url!r}  title={page.title()!r}")
            _dump_form(page, log)
            n_input  = page.locator("input").count()
            n_select = page.locator("select").count()
            if n_input > 2 or n_select > 0:
                _log(log, f"[ok] form trovato — {n_input} input, {n_select} select")
                return

    _log(log, "[warn] pagina 'aggiungi proprietà' non raggiunta — vedere screenshot")


def _dump_form(page, log: list) -> None:
    """Stampa nel log tutti i campi form presenti nella pagina."""
    try:
        inputs = page.locator("input").all()
        if inputs:
            _log(log, f"[form] {len(inputs)} input trovati:")
            for el in inputs[:40]:
                try:
                    t  = el.get_attribute("type") or "text"
                    n  = el.get_attribute("name") or ""
                    i  = el.get_attribute("id") or ""
                    ph = el.get_attribute("placeholder") or ""
                    _log(log, f"  input  type={t!r}  name={n!r}  id={i!r}  placeholder={ph!r}")
                except Exception:
                    continue
    except Exception as e:
        _log(log, f"[warn] dump input fallito: {e}")

    try:
        selects = page.locator("select").all()
        if selects:
            _log(log, f"[form] {len(selects)} select trovate:")
            for el in selects[:20]:
                try:
                    n = el.get_attribute("name") or ""
                    i = el.get_attribute("id") or ""
                    _log(log, f"  select name={n!r}  id={i!r}")
                except Exception:
                    continue
    except Exception as e:
        _log(log, f"[warn] dump select fallito: {e}")

    try:
        buttons = page.locator("button").all()
        if buttons:
            _log(log, f"[form] {len(buttons)} bottoni trovati:")
            for el in buttons[:20]:
                try:
                    t     = el.get_attribute("type") or ""
                    testo = el.inner_text().strip()[:80]
                    _log(log, f"  button type={t!r}  testo={testo!r}")
                except Exception:
                    continue
    except Exception as e:
        _log(log, f"[warn] dump button fallito: {e}")


# ---------------------------------------------------------------------------
# Riepilogo finale
# ---------------------------------------------------------------------------

def _salva_riepilogo(log: list) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / "riepilogo.txt"
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(
        f"Esplorazione Booking.com — {ts}\n" + "=" * 60 + "\n\n" +
        "\n".join(log) + "\n",
        encoding="utf-8",
    )
    print(f"\n  [riepilogo] {path}")


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

    log: list = []
    print("\n" + "=" * 60)
    print("BOOKING.COM — ESPLORAZIONE SITO REALE")
    print("=" * 60)

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
            step_01_login_page(page, log)
            ok = step_02_login(page, email, password, log)
            if ok:
                step_03_extranet_home(page, log)
                step_04_aggiungi_proprieta(page, log)
            else:
                print("\n[WARN] Login non riuscito — screenshot salvati per analisi.")
        except Exception as e:
            msg = f"[ERRORE CRITICO] {e}"
            print(msg)
            log.append(msg)
        finally:
            context.close()
            browser.close()

    _salva_riepilogo(log)
    print(f"\n{'='*60}")
    print(f"Artefatti salvati in: {OUTPUT_DIR.resolve()}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
