import json
import os
import re

from playwright.sync_api import sync_playwright

# --- Carica dati proprietà dal file JSON ---
DATA_FILE = os.environ.get(
    "PROPERTY_DATA", os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json")
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

EMAIL = os.environ["CASEVACANZA_EMAIL"]
PASSWORD = os.environ["CASEVACANZA_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Mappatura dotazioni JSON → label esatte CaseVacanza.it
# REGOLA: spunta SOLO le dotazioni con valore true nel JSON.
#         Se false o assente, NON spuntare. Zero eccezioni.
# ---------------------------------------------------------------------------


def _get_piscina_label():
    """Return the correct CaseVacanza pool label based on piscina_tipo in JSON."""
    tipo = PROP.get("dotazioni", {}).get("piscina_tipo", "")
    if "privata" in tipo.lower():
        return "Piscina (privata)"
    return "Piscina (in comune)"


DOTAZIONI_MAP = {
    "tv": "TV",
    "piano_cottura": "Piano cottura",
    "frigo_congelatore": "Frigorifero",
    "forno": "Forno",
    "microonde": "Microonde",
    "lavatrice": "Lavatrice (privata)",
    "lavastoviglie": "Lavastoviglie",
    "aria_condizionata": "Aria condizionata",
    "riscaldamento": "Riscaldamento",
    "internet_wifi": "WiFi",
    "phon": "Asciugacapelli",
    "ferro_stiro": "Ferro da stiro",
    "terrazza": "Terrazza",
    "giardino": "Giardino",
    "piscina": _get_piscina_label(),
    "arredi_esterno": "Arredi da esterno",
    "barbecue": "Griglia per barbecue",
    "culla": "Culla",
    "seggiolone": "Seggiolone",
    "animali_ammessi": "Animali ammessi",
}


def _build_servizi():
    """Restituisce la lista dei servizi attivi (true) da selezionare su CaseVacanza.
    Legge SOLO dal JSON — se un servizio è false, NON viene incluso."""
    dot = PROP["dotazioni"]
    servizi = []
    for key, label in DOTAZIONI_MAP.items():
        if dot.get(key) is True:
            servizi.append(label)
    # Parcheggio: controlla flag diretto O la stringa in altro_dotazioni
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi()

SCREENSHOT_DIR = "screenshots"

# Mappa tipo letto JSON → indice bottone CaseVacanza
# CaseVacanza ordina: 0=Divano letto, 1=Matrimoniale, 2=Francese, 3=Singolo
LETTO_INDEX = {
    "matrimoniale": 1,
    "francese": 2,
    "singolo": 3,
    "divano_letto": 0,
}

step_counter = 0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def screenshot(page, name):
    """Save a debug screenshot with incrementing step number."""
    global step_counter
    step_counter += 1
    path = f"{SCREENSHOT_DIR}/step{step_counter:02d}_{name}.png"
    try:
        page.wait_for_load_state("load", timeout=10_000)
        page.screenshot(path=path, full_page=True)
        print(f"  Screenshot: {path}")
    except Exception as e:
        print(f"  [WARN] Screenshot fallita ({name}): {e}")


def save_html(page, name):
    """Save full HTML of current page for debugging."""
    path = f"{SCREENSHOT_DIR}/{name}.html"
    try:
        html = page.content()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML salvato: {path}")
    except Exception as e:
        print(f"  [WARN] HTML save fallito ({name}): {e}")


def step_done(page, name):
    """Standard post-step: wait for DOM ready, take screenshot + HTML."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    page.wait_for_timeout(1000)
    screenshot(page, name)
    save_html(page, name)


def dismiss_overlay(page):
    """Close any modal/overlay: Escape, button clicks, then JS hide."""
    # 1) Press Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # 2) Try close buttons inside known modal containers
    for selector in [".react-modal-portal-v2", ".ReactModal__Overlay"]:
        try:
            modal = page.locator(selector)
            if modal.count() > 0 and modal.first.is_visible():
                close_btn = modal.locator("button").first
                if close_btn.count() > 0:
                    close_btn.click()
                    page.wait_for_timeout(500)
                    print(f"  Modal chiuso ({selector} -> button)")
                    return
        except Exception:
            pass

    # 3) Ok button
    try:
        ok_btn = page.locator("button", has_text="Ok")
        if ok_btn.count() > 0 and ok_btn.first.is_visible():
            ok_btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    # 4) Hide (NOT remove!) blocking overlays via JS — removing breaks React
    hidden = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll(
            '.react-modal-portal-v2, .ReactModal__Overlay'
        ).forEach(el => {
            el.style.display = 'none';
            el.style.pointerEvents = 'none';
            count++;
        });
        return count;
    }""")
    if hidden:
        print(f"  Nascosti {hidden} overlay via JS (display:none)")
        page.wait_for_timeout(500)


def try_step(page, step_name, func):
    """Execute a step wrapped in try/except. Dismiss overlays before,
    always capture state after (success or failure)."""
    print(f"\n--- {step_name} ---")
    dismiss_overlay(page)
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")


def load_photo_paths():
    """Load photo paths from JSON (marketing.foto).
    If no valid photos found, return empty list (NO placeholder download)."""
    foto_json = PROP.get("marketing", {}).get("foto", [])
    if not foto_json:
        print("  Nessuna foto nel JSON — skip upload foto")
        return []
    json_dir = os.path.dirname(os.path.abspath(DATA_FILE))
    paths = []
    for f in foto_json:
        p = f if os.path.isabs(f) else os.path.join(json_dir, f)
        if os.path.isfile(p):
            paths.append(p)
            print(f"  Foto dal JSON: {p}")
        else:
            print(f"  [WARN] Foto non trovata: {p}")
    return paths


def calculate_base_price():
    """Calculate base nightly price: median of listino_prezzi,
    or prezzo_notte, or None."""
    listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
    if listino:
        prezzi = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
        return prezzi[len(prezzi) // 2] if prezzi else None
    return PROP.get("condizioni", {}).get("prezzo_notte")


def fill_field(page, value, labels, css_selectors, field_name):
    """Fill a form field using 3-level strategy: label → CSS → JS.
    Returns True if field was filled, False otherwise.
    Does NOT fill if value is None or empty string."""
    if not value:
        return False
    val = str(value)
    filled = False

    # Strategy 1: Playwright label
    for lbl in labels:
        try:
            f = page.get_by_label(lbl)
            if f.count() > 0:
                tag = f.first.evaluate("el => el.tagName")
                if tag == "SELECT":
                    try:
                        f.first.select_option(label=val)
                    except Exception:
                        f.first.select_option(value=val)
                else:
                    f.first.fill(val)
                filled = True
                print(f"  {field_name}: {val} (label '{lbl}')")
                break
        except Exception:
            continue

    # Strategy 2: CSS selectors
    if not filled:
        for sel in css_selectors:
            try:
                f = page.locator(sel)
                if f.count() > 0:
                    tag = f.first.evaluate("el => el.tagName")
                    if tag == "SELECT":
                        try:
                            f.first.select_option(label=val)
                        except Exception:
                            f.first.select_option(value=val)
                    else:
                        f.first.fill(val)
                    filled = True
                    print(f"  {field_name}: {val} (CSS '{sel}')")
                    break
            except Exception:
                continue

    # Strategy 3: JS — find input whose container text matches keywords
    if not filled:
        keywords = [l.lower() for l in labels]
        filled = page.evaluate("""({val, keywords}) => {
            const fields = document.querySelectorAll('input, textarea, select');
            for (const f of fields) {
                const container = f.closest('label') || f.closest('.form-group')
                    || f.closest('[class*="field"]') || f.parentElement;
                const text = (container?.textContent || '').toLowerCase();
                if (keywords.some(k => text.includes(k))) {
                    if (f.tagName === 'SELECT') {
                        for (const opt of f.options) {
                            if (opt.value === val || opt.text.includes(val)) {
                                f.value = opt.value;
                                f.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                    } else {
                        f.value = val;
                        f.dispatchEvent(new Event('input', {bubbles: true}));
                        return true;
                    }
                }
            }
            return false;
        }""", {"val": val, "keywords": keywords})
        if filled:
            print(f"  {field_name}: {val} (JS)")

    if not filled:
        print(f"  [WARN] {field_name} non trovato — {val}")
    return filled


def click_counter_by_label(page, label, times):
    """Find a counter widget associated with a text label and click + N times.
    Uses text-based search with JS walk-up to find nearest counter-add-btn."""
    if times <= 0:
        return
    for _ in range(times):
        clicked = page.evaluate("""(label) => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.trim().includes(label)) {
                    let el = node.parentElement;
                    for (let i = 0; i < 10 && el; i++) {
                        const btn = el.querySelector('[data-test="counter-add-btn"]');
                        if (btn) { btn.click(); return true; }
                        el = el.parentElement;
                    }
                }
            }
            return false;
        }""", label)
        if not clicked:
            print(f"  [WARN] Counter per '{label}' non trovato")
            return
        page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Login and navigation
# ---------------------------------------------------------------------------


def login(page):
    """Login su CaseVacanza.it via Keycloak SSO."""
    print("Login CaseVacanza.it...")
    page.goto("https://my.casevacanza.it", timeout=60_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    page.wait_for_timeout(2000)  # Extra wait for Keycloak redirect to settle
    screenshot(page, "login_page")

    # Close cookie popup if present
    try:
        ok_btn = page.locator("button", has_text="Ok")
        if ok_btn.count() > 0 and ok_btn.first.is_visible():
            ok_btn.first.click()
            page.wait_for_timeout(1000)
            print("  Popup cookie chiuso")
    except Exception:
        pass

    # Keycloak login form
    page.fill("#username", EMAIL)
    page.fill("#password", PASSWORD)
    screenshot(page, "login_credenziali")
    page.click("#kc-login")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    step_done(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")
    print("Login effettuato.")


def navigate_to_add_property(page):
    """Navigate directly to the add-property wizard URL."""
    print("Navigazione a add-property...")
    page.goto("https://my.casevacanza.it/listing/add-property", timeout=30_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)

    # Dismiss any modal (cookie popup, ReactModal, etc.)
    dismiss_overlay(page)
    page.wait_for_timeout(3000)  # Let React SPA fully render wizard components

    step_done(page, "pagina_iniziale")
    print("Pagina wizard raggiunta.")


# ---------------------------------------------------------------------------
# Wizard step functions
# ---------------------------------------------------------------------------


def insert_property(page):
    """Complete the full property insertion wizard."""
    photo_paths = load_photo_paths()

    # --- Step 1: Click [data-test="single"] (Proprietà a unità singola) ---
    print("Step 1: Proprietà a unità singola")
    dismiss_overlay(page)
    page.wait_for_timeout(2000)  # Let React finish rendering wizard
    page.locator('[data-test="single"]').click(force=True)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    step_done(page, "tipo_proprietà")

    # --- Step 2: Seleziona tipo struttura dal dropdown ---
    tipo = PROP["identificativi"]["tipo_struttura"]
    print(f"Step 2: Seleziona {tipo}")

    def do_step2():
        select = page.locator("select")
        if select.count() > 0:
            select.first.select_option(label=tipo)
        else:
            page.get_by_text(tipo).click()
        step_done(page, "appartamento_selezionato")

    try_step(page, "step2_tipo_struttura", do_step2)

    # --- Step 3: Click "Intero alloggio" ---
    print("Step 3: Intero alloggio")

    def do_step3():
        page.get_by_text("Intero alloggio").click()
        step_done(page, "intero_alloggio")

    try_step(page, "step3_intero_alloggio", do_step3)

    # --- Step 4: Continua (tipo proprietà) ---
    print("Step 4: Continua (tipo proprietà)")
    page.locator('[data-test="save-button"]').click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    step_done(page, "dopo_tipo")

    # --- Step 5: Compila indirizzo (modalità manuale) ---
    print("Step 5: Indirizzo")

    def do_step5():
        page.get_by_text("Inseriscilo manualmente").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        ident = PROP["identificativi"]
        addr_parts = ident["indirizzo"].rsplit(" ", 1)
        via = addr_parts[0] if len(addr_parts) > 1 else ident["indirizzo"]
        civico = addr_parts[1] if len(addr_parts) > 1 else ""

        page.locator('[data-test="stateOrProvince"]').fill(ident["regione"])
        page.wait_for_timeout(500)
        page.locator('[data-test="city"]').fill(ident["comune"])
        page.wait_for_timeout(500)
        page.locator('[data-test="street"]').fill(via)
        page.wait_for_timeout(500)
        page.locator('[data-test="houseNumberOrName"]').fill(civico)
        page.wait_for_timeout(500)
        page.locator('[data-test="postalCode"]').fill(ident["cap"])
        page.wait_for_timeout(500)
        step_done(page, "indirizzo_compilato")

    try_step(page, "step5_indirizzo", do_step5)

    # --- Step 6: Continua (indirizzo) ---
    print("Step 6: Continua (indirizzo)")
    page.locator('[data-test="save-button"]').click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    step_done(page, "dopo_indirizzo")

    # --- Step 7: Mappa — Imposta coordinate GPS se presenti nel JSON ---
    print("Step 7: Mappa")

    def do_step7():
        coords = PROP.get("identificativi", {}).get("coordinate")
        if coords and coords.get("latitudine") and coords.get("longitudine"):
            lat = coords["latitudine"]
            lng = coords["longitudine"]
            moved = page.evaluate("""({lat, lng}) => {
                // Strategy 1: hidden lat/lng input fields
                const latFields = document.querySelectorAll(
                    'input[name*="lat"], input[name*="latitude"]'
                );
                const lngFields = document.querySelectorAll(
                    'input[name*="lng"], input[name*="lon"], input[name*="longitude"]'
                );
                if (latFields.length > 0 && lngFields.length > 0) {
                    latFields[0].value = lat;
                    latFields[0].dispatchEvent(new Event('input', {bubbles: true}));
                    lngFields[0].value = lng;
                    lngFields[0].dispatchEvent(new Event('input', {bubbles: true}));
                    return 'hidden-inputs';
                }
                // Strategy 2: Google Maps
                if (window.google && window.google.maps) {
                    const mapEls = document.querySelectorAll('[class*="map"], [id*="map"]');
                    for (const el of mapEls) {
                        if (el.__gm_map && el.__gm_map.setCenter) {
                            const pos = new google.maps.LatLng(lat, lng);
                            el.__gm_map.setCenter(pos);
                            return 'google-maps';
                        }
                    }
                }
                // Strategy 3: Leaflet
                if (window.L) {
                    const containers = document.querySelectorAll('.leaflet-container');
                    for (const c of containers) {
                        if (c._leaflet_map) {
                            c._leaflet_map.setView([lat, lng], 15);
                            c._leaflet_map.eachLayer(function(layer) {
                                if (layer.setLatLng) layer.setLatLng([lat, lng]);
                            });
                            return 'leaflet';
                        }
                    }
                }
                return null;
            }""", {"lat": lat, "lng": lng})
            if moved:
                print(f"  Coordinate impostate ({lat}, {lng}) via {moved}")
            else:
                print(f"  [WARN] Coordinate ({lat}, {lng}) nel JSON ma mappa non manipolabile")
        else:
            print("  Nessuna coordinata nel JSON — skip posizionamento mappa")

        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_mappa")

    try_step(page, "step7_mappa", do_step7)

    # --- Step 8: Ospiti e camere ---
    comp = PROP["composizione"]
    print(f"Step 8: Ospiti e camere ({comp['max_ospiti']} ospiti, "
          f"{comp['camere']} cam, {comp['bagni']} bagni)")

    def do_step8():
        # Guest count — [data-test="guest-count"] works, default is 1
        for _ in range(comp["max_ospiti"] - 1):
            page.locator('[data-test="guest-count"] [data-test="counter-add-btn"]').click()
            page.wait_for_timeout(300)

        # Bedrooms — try data-test first, fallback to text-based
        bedroom_filled = False
        try:
            loc = page.locator('[data-test="bedroom"] [data-test="counter-add-btn"]')
            if loc.count() > 0:
                for _ in range(comp["camere"] - 1):
                    loc.click()
                    page.wait_for_timeout(300)
                bedroom_filled = True
                print(f"  Camere: {comp['camere']} (data-test)")
        except Exception:
            pass

        if not bedroom_filled:
            click_counter_by_label(page, "Camera da letto", comp["camere"] - 1)
            if comp["camere"] > 1:
                print(f"  Camere: {comp['camere']} (text-based)")

        # Bathrooms — try data-test first, fallback to text-based
        bathroom_filled = False
        try:
            loc = page.locator('[data-test="bath_room"] [data-test="counter-add-btn"]')
            if loc.count() > 0:
                for _ in range(comp["bagni"]):
                    loc.click()
                    page.wait_for_timeout(300)
                bathroom_filled = True
                print(f"  Bagni: {comp['bagni']} (data-test)")
        except Exception:
            pass

        if not bathroom_filled:
            click_counter_by_label(page, "Bagno", comp["bagni"])
            print(f"  Bagni: {comp['bagni']} (text-based)")

        step_done(page, "ospiti_camere")

    try_step(page, "step8_ospiti_camere", do_step8)

    # --- Step 9: Continua (ospiti) ---
    print("Step 9: Continua (ospiti)")

    def do_step9():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_ospiti")

    try_step(page, "step9_continua_ospiti", do_step9)

    # --- Step 10: Configura letti (dal JSON composizione.letti) ---
    print("Step 10: Configura letti")

    def do_step10():
        add_btns = page.locator('[data-test="counter-add-btn"]')
        count = add_btns.count()
        print(f"  Trovati {count} counter-add-btn")

        letti = comp.get("letti", [])
        if not letti:
            print("  ATTENZIONE: nessun dato letti nel JSON, skip")
        for letto in letti:
            tipo_letto = letto["tipo"]
            quantita = letto["quantita"]
            idx = LETTO_INDEX.get(tipo_letto)
            if idx is None:
                print(f"  Tipo letto sconosciuto: {tipo_letto}, skip")
                continue
            if idx >= count:
                print(f"  Indice {idx} fuori range ({count} bottoni), skip {tipo_letto}")
                continue
            for _ in range(quantita):
                add_btns.nth(idx).click()
                page.wait_for_timeout(300)
            print(f"  {tipo_letto}: +{quantita} (indice {idx})")

        step_done(page, "letti_configurati")

    try_step(page, "step10_letti", do_step10)

    # --- Step 11: Continua (letti) ---
    print("Step 11: Continua (letti)")

    def do_step11():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_letti")

    try_step(page, "step11_continua_letti", do_step11)

    # --- Step 12: Upload foto ---
    print("Step 12: Upload foto")

    def do_step12():
        if not photo_paths:
            print("  Nessuna foto valida — skip upload")
            step_done(page, "foto_skip")
            return

        uploaded = False
        # Strategy 1: standard input[type="file"]
        try:
            fi = page.locator("input[type='file']")
            if fi.count() > 0:
                fi.set_input_files(photo_paths)
                uploaded = True
                print(f"  Upload {len(photo_paths)} foto via input[type='file']")
        except Exception as e:
            print(f"  Strategy 1 fallita: {e}")

        # Strategy 2: input[accept*="image"]
        if not uploaded:
            try:
                fi = page.locator("input[accept*='image']")
                if fi.count() > 0:
                    fi.set_input_files(photo_paths)
                    uploaded = True
                    print(f"  Upload via input[accept*='image']")
            except Exception as e:
                print(f"  Strategy 2 fallita: {e}")

        # Strategy 3: force display on hidden input
        if not uploaded:
            try:
                fi = page.locator("input[type='file']")
                if fi.count() > 0:
                    fi.evaluate("el => el.style.display = 'block'")
                    fi.set_input_files(photo_paths)
                    uploaded = True
                    print("  Upload via forced display input[type='file']")
            except Exception as e:
                print(f"  Strategy 3 fallita: {e}")

        if uploaded:
            page.wait_for_timeout(10_000)
        else:
            print("  SKIP foto: nessuna strategia ha funzionato")

        step_done(page, "foto_caricate" if uploaded else "foto_skip")

    try_step(page, "step12_foto", do_step12)

    # --- Step 13: Continua (foto) ---
    print("Step 13: Continua (foto)")

    def do_step13():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_foto")

    try_step(page, "step13_continua_foto", do_step13)

    # --- Step 14: Seleziona servizi (SOLO quelli true nel JSON) ---
    print("Step 14: Servizi")
    print(f"  Servizi da selezionare dal JSON: {SERVIZI}")

    def do_step14():
        # Click "Tutti" tab to show all services
        for tab_label in ["Tutti", "tutti", "All", "all"]:
            try:
                tab = page.get_by_role("tab", name=tab_label)
                if tab.count() > 0:
                    tab.first.click()
                    page.wait_for_timeout(2000)
                    print(f"  Tab '{tab_label}' cliccata")
                    break
            except Exception:
                pass
        else:
            try:
                tab = page.get_by_text("Tutti", exact=True)
                if tab.count() > 0:
                    tab.first.click()
                    page.wait_for_timeout(2000)
                    print("  Tab 'Tutti' cliccata (text fallback)")
            except Exception as e:
                print(f"  [WARN] Tab 'Tutti' non trovata: {e}")

        # Select each service with progressive strategies
        for servizio in SERVIZI:
            selected = False

            # Strategy 1: get_by_role("checkbox")
            if not selected:
                try:
                    cb = page.get_by_role("checkbox", name=servizio, exact=True)
                    if cb.count() > 0:
                        cb.first.check()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (role=checkbox exact)")
                        selected = True
                except Exception:
                    pass

            if not selected:
                try:
                    cb = page.get_by_role("checkbox", name=servizio, exact=False)
                    if cb.count() > 0:
                        cb.first.check()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (role=checkbox partial)")
                        selected = True
                except Exception:
                    pass

            # Strategy 2: get_by_label
            if not selected:
                try:
                    cb = page.get_by_label(servizio, exact=True)
                    if cb.count() > 0:
                        cb.first.check()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (get_by_label)")
                        selected = True
                except Exception:
                    pass

            # Strategy 3: JS — find checkbox in container with matching text
            if not selected:
                try:
                    result = page.evaluate("""(label) => {
                        const checkboxes = document.querySelectorAll(
                            'input[type="checkbox"], [role="checkbox"], [role="switch"]'
                        );
                        for (const cb of checkboxes) {
                            const container = cb.closest('label')
                                || cb.closest('[data-test]')
                                || cb.parentElement?.parentElement?.parentElement
                                || cb.parentElement?.parentElement
                                || cb.parentElement;
                            const text = (container?.textContent || '').trim();
                            if (text.includes(label)) {
                                const isInput = cb.tagName === 'INPUT';
                                if (isInput && !cb.checked) {
                                    cb.click();
                                } else if (!isInput && cb.getAttribute('aria-checked') !== 'true') {
                                    cb.click();
                                }
                                return {found: true, text: text.substring(0, 60)};
                            }
                        }
                        return {found: false};
                    }""", servizio)
                    if result.get("found"):
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (JS checkbox)")
                        selected = True
                except Exception as e:
                    print(f"  [WARN] {servizio} JS: {e}")

            # Strategy 4: Click text directly
            if not selected:
                try:
                    el = page.get_by_text(servizio, exact=True)
                    if el.count() > 0:
                        el.first.click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (click text)")
                        selected = True
                except Exception:
                    pass

            if not selected:
                print(f"  [MISS] {servizio} — non trovato sulla pagina")

        step_done(page, "servizi_selezionati")

    try_step(page, "step14_servizi", do_step14)

    # --- Step 15: Continua (servizi) ---
    print("Step 15: Continua (servizi)")

    def do_step15():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_servizi")

    try_step(page, "step15_continua_servizi", do_step15)

    # --- Step 16: Click "Li scrivo io" ---
    print("Step 16: Li scrivo io")

    def do_step16():
        page.get_by_text("Li scrivo io").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "li_scrivo_io")

    try_step(page, "step16_li_scrivo_io", do_step16)

    # --- Step 17: Titolo e descrizione ---
    print("Step 17: Titolo e descrizione")

    def do_step17():
        titolo = PROP.get("marketing", {}).get("titolo") or PROP["identificativi"]["nome_struttura"]
        descrizione = PROP["marketing"]["descrizione_lunga"]

        titolo_field = page.get_by_label("Titolo")
        if titolo_field.count() > 0:
            titolo_field.fill(titolo)
        else:
            page.locator(
                "input[name*='titolo'], input[name*='title'], input[placeholder*='Titolo']"
            ).first.fill(titolo)
        page.wait_for_timeout(500)

        desc_field = page.get_by_label("Descrizione")
        if desc_field.count() > 0:
            desc_field.fill(descrizione)
        else:
            page.locator("textarea").first.fill(descrizione)
        page.wait_for_timeout(500)

        step_done(page, "titolo_descrizione")

    try_step(page, "step17_titolo_desc", do_step17)

    # --- Step 18: Continua (titolo/descrizione) ---
    print("Step 18: Continua (titolo/descrizione)")

    def do_step18():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_titolo_desc")

    try_step(page, "step18_continua_titolo", do_step18)

    # --- Step 19: Prezzo ---
    print("Step 19: Prezzo")

    def do_step19():
        base_prezzo = calculate_base_price()
        if base_prezzo is not None:
            prezzo_str = str(base_prezzo)
            prezzo_field = page.get_by_label("Prezzo")
            if prezzo_field.count() > 0:
                prezzo_field.fill(prezzo_str)
            else:
                page.locator(
                    "input[type='number'], input[name*='prezz'], input[name*='price']"
                ).first.fill(prezzo_str)
            print(f"  Prezzo base: {prezzo_str} EUR/notte")
        else:
            print("  Prezzo non presente nel JSON — lascio vuoto")

        step_done(page, "prezzo")

    try_step(page, "step19_prezzo", do_step19)

    # --- Step 20: Continua (prezzo) ---
    print("Step 20: Continua (prezzo)")

    def do_step20():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_prezzo")

    try_step(page, "step20_continua_prezzo", do_step20)

    # --- Step 21: Cauzione ---
    print("Step 21: Cauzione")

    def do_step21():
        cauzione_val = PROP.get("condizioni", {}).get("cauzione_euro")
        if cauzione_val is None:
            print("  Cauzione non presente nel JSON — skip")
            page.locator('[data-test="save-button"]').click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1000)
            step_done(page, "dopo_cauzione_skip")
            return
        cauzione = str(cauzione_val)

        filled = False
        # Strategy 1: label Playwright
        for lbl in ["Cauzione", "Deposito cauzionale", "Deposito", "Deposit"]:
            try:
                f = page.get_by_label(lbl)
                if f.count() > 0:
                    f.first.fill(cauzione)
                    filled = True
                    print(f"  Cauzione: {cauzione} EUR (label '{lbl}')")
                    break
            except Exception:
                continue

        # Strategy 2: CSS selectors
        if not filled:
            for sel in [
                "input[name*='cauzione']", "input[name*='deposit']",
                "select[name*='cauzione']", "select[name*='deposit']",
            ]:
                try:
                    f = page.locator(sel)
                    if f.count() > 0:
                        tag = f.first.evaluate("el => el.tagName")
                        if tag == "SELECT":
                            f.first.select_option(value=cauzione)
                        else:
                            f.first.fill(cauzione)
                        filled = True
                        print(f"  Cauzione: {cauzione} EUR (CSS '{sel}')")
                        break
                except Exception:
                    continue

        # Strategy 3: JS
        if not filled:
            filled = page.evaluate("""(val) => {
                const inputs = document.querySelectorAll('input, select');
                for (const inp of inputs) {
                    const container = inp.closest('label') || inp.closest('.form-group')
                        || inp.closest('[class*="field"]') || inp.parentElement;
                    const text = (container?.textContent || '').toLowerCase();
                    if (text.includes('cauzione') || text.includes('deposito')
                        || text.includes('deposit')) {
                        if (inp.tagName === 'SELECT') {
                            for (const opt of inp.options) {
                                if (opt.value === val || opt.text.includes(val)) {
                                    inp.value = opt.value;
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                            }
                        } else {
                            inp.value = val;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            return true;
                        }
                    }
                }
                return false;
            }""", cauzione)
            if filled:
                print(f"  Cauzione: {cauzione} EUR (JS)")

        if not filled:
            print(f"  [WARN] Campo cauzione non trovato — {cauzione} EUR da inserire manualmente")

        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_cauzione")

    try_step(page, "step21_cauzione", do_step21)

    # --- Step 22: Pulizie, biancheria, soggiorno minimo ---
    print("Step 22: Condizioni — pulizie, biancheria, soggiorno minimo")

    def do_step22():
        cond = PROP["condizioni"]

        # Pulizia finale
        fill_field(
            page,
            cond.get("pulizia_finale", ""),
            ["Pulizia finale", "Pulizie", "Cleaning", "Pulizia"],
            ["input[name*='puliz']", "textarea[name*='puliz']",
             "input[name*='clean']", "textarea[name*='clean']"],
            "Pulizia finale"
        )

        # Asciugamani
        fill_field(
            page,
            cond.get("asciugamani", ""),
            ["Asciugamani", "Towels"],
            ["input[name*='asciugam']", "textarea[name*='asciugam']"],
            "Asciugamani"
        )

        # Lenzuola
        fill_field(
            page,
            cond.get("lenzuola", ""),
            ["Lenzuola", "Bed linen", "Sheets"],
            ["input[name*='lenzuol']", "textarea[name*='lenzuol']"],
            "Lenzuola"
        )

        # Biancheria (legacy, per retrocompatibilità con Il Faro)
        fill_field(
            page,
            cond.get("biancheria", ""),
            ["Biancheria", "Linen", "Biancheria da letto"],
            ["input[name*='bianch']", "textarea[name*='bianch']"],
            "Biancheria"
        )

        # Soggiorno minimo — usa il valore più basso tra i periodi
        sog_bassa = cond.get("soggiorno_minimo_bassa", {})
        sog_alta = cond.get("soggiorno_minimo_alta", {})
        notti = str(sog_bassa.get("notti", sog_alta.get("notti", "")))
        if notti:
            fill_field(
                page,
                notti,
                ["Soggiorno minimo", "Notti minime", "Minimum stay"],
                ["input[name*='soggiorno']", "input[name*='minim']",
                 "input[name*='stay']", "select[name*='soggiorno']"],
                "Soggiorno minimo"
            )

        step_done(page, "condizioni_compilate")

    try_step(page, "step22_condizioni", do_step22)

    # --- Step 23: Continua (condizioni) ---
    print("Step 23: Continua (condizioni)")

    def do_step23():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_condizioni")

    try_step(page, "step23_continua_condizioni", do_step23)

    # --- Step 24: Regole check-in / check-out ---
    print("Step 24: Regole — check-in, check-out, regole casa")

    def do_step24():
        cond = PROP["condizioni"]

        fill_field(
            page,
            cond.get("check_in", ""),
            ["Check-in", "Check in", "Orario arrivo", "Arrivo"],
            ["input[name*='check_in']", "input[name*='checkin']",
             "select[name*='check_in']", "select[name*='checkin']"],
            "Check-in"
        )

        fill_field(
            page,
            cond.get("check_out", ""),
            ["Check-out", "Check out", "Orario partenza", "Partenza"],
            ["input[name*='check_out']", "input[name*='checkout']",
             "select[name*='check_out']", "select[name*='checkout']"],
            "Check-out"
        )

        fill_field(
            page,
            cond.get("regole_casa", ""),
            ["Regole", "Regole della casa", "House rules", "Regolamento"],
            ["textarea[name*='regol']", "textarea[name*='rule']",
             "textarea[name*='house']"],
            "Regole casa"
        )

        step_done(page, "regole_compilate")

    try_step(page, "step24_regole", do_step24)

    # --- Step 25: Continua (regole) ---
    print("Step 25: Continua (regole)")

    def do_step25():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_regole")

    try_step(page, "step25_continua_regole", do_step25)

    # --- Step 26: Calendario (iCal import) ---
    print("Step 26: Calendario")

    def do_step26():
        ical_url = PROP.get("condizioni", {}).get("ical_url")
        if ical_url:
            imported = False
            for btn_text in ["Importa", "Sincronizza", "iCal", "Import", "Sync",
                             "Importa calendario", "Collega calendario"]:
                try:
                    btn = page.get_by_text(btn_text)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.wait_for_timeout(1000)
                        print(f"  Cliccato '{btn_text}' sulla pagina calendario")

                        url_field = page.locator(
                            "input[type='url'], input[name*='ical'], input[name*='url'], "
                            "input[placeholder*='http'], input[placeholder*='ical'], "
                            "input[placeholder*='URL']"
                        )
                        if url_field.count() > 0:
                            url_field.first.fill(ical_url)
                            print(f"  iCal URL inserito: {ical_url}")
                            for confirm_text in ["Importa", "Salva", "Conferma", "OK",
                                                 "Import", "Save"]:
                                try:
                                    confirm = page.get_by_role("button", name=confirm_text)
                                    if confirm.count() > 0:
                                        confirm.first.click()
                                        page.wait_for_load_state("domcontentloaded")
                                        page.wait_for_timeout(1000)
                                        print(f"  Confermato import iCal ({confirm_text})")
                                        imported = True
                                        break
                                except Exception:
                                    continue
                        if imported:
                            break
                except Exception:
                    continue

            if not imported:
                print(f"  [WARN] iCal URL nel JSON ({ical_url}) ma import non trovato")
                print("  L'URL iCal dovrà essere inserito manualmente post-creazione")
        else:
            print("  Nessun iCal URL nel JSON — skip import calendario")

        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_calendario")

    try_step(page, "step26_calendario", do_step26)

    # --- Step 27: Requisiti regionali — CIN ---
    print("Step 27: Requisiti regionali (CIN)")

    def do_step27():
        cin = PROP.get("identificativi", {}).get("cin")
        if not cin:
            print("  CIN non presente nel JSON — skip")
            page.locator('[data-test="save-button"]').click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1000)
            step_done(page, "dopo_requisiti_skip")
            return

        filled = False
        try:
            cin_field = page.get_by_label("CIN")
            if cin_field.count() > 0:
                cin_field.fill(cin)
                filled = True
                print(f"  CIN compilato (label): {cin}")
        except Exception:
            pass

        if not filled:
            try:
                cin_field = page.locator(
                    "input[name*='cin'], input[name*='CIN'], "
                    "input[placeholder*='CIN']"
                )
                if cin_field.count() > 0:
                    cin_field.first.fill(cin)
                    filled = True
                    print(f"  CIN compilato (CSS): {cin}")
            except Exception:
                pass

        if not filled:
            # Last resort: use get_by_text to find nearby input
            try:
                text_inputs = page.locator("input[type='text']")
                if text_inputs.count() > 0:
                    text_inputs.first.fill(cin)
                    filled = True
                    print(f"  CIN compilato (primo input text): {cin}")
            except Exception:
                pass

        if not filled:
            print(f"  [WARN] Campo CIN non trovato — {cin}")

        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "dopo_requisiti")

    try_step(page, "step27_requisiti", do_step27)

    # --- Step 28: Pagina finale — solo screenshot, NON inviare ---
    print("\nStep 28: Pagina finale — SOLO screenshot")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1000)
    step_done(page, "pagina_finale")
    print("Flusso completato! NON inviato per la verifica.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.set_default_timeout(30_000)
        try:
            login(page)
            navigate_to_add_property(page)
            insert_property(page)
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
