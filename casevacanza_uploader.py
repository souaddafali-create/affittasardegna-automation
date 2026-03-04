import json
import os
import re
import tempfile
import urllib.request

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
LETTO_LABEL = {
    "matrimoniale": "Letto matrimoniale",
    "singolo": "Letto singolo",
    "divano_letto": "Divano letto",
    "francese": "Letto Queen-size",
    "king": "Letto King-size",
    "castello": "Letto a castello",
}

step_counter = 0
step_errors = []


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


def try_step(page, step_name, func, critical=False):
    """Execute a step wrapped in try/except. Dismiss overlays before,
    always capture state after (success or failure).

    If critical=True, re-raise the exception to stop the wizard
    (used for steps where continuing makes no sense if they fail)."""
    print(f"\n--- {step_name} ---")
    dismiss_overlay(page)
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        step_errors.append((step_name, str(e)))
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")
        if critical:
            raise


def click_save_and_verify(page, step_name):
    """Click save-button and verify the wizard actually advanced.
    Returns True if advanced, False if stuck on same page."""
    url_before = page.url
    heading_before = page.evaluate("""() => {
        const h = document.querySelector('h1, h2, h3, [data-test*="title"], [class*="heading"]');
        return h ? h.textContent.trim() : '';
    }""")

    page.locator('[data-test="save-button"]').click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    url_after = page.url
    heading_after = page.evaluate("""() => {
        const h = document.querySelector('h1, h2, h3, [data-test*="title"], [class*="heading"]');
        return h ? h.textContent.trim() : '';
    }""")

    advanced = (url_after != url_before) or (heading_after != heading_before)
    if not advanced:
        # Check for validation errors on the page
        errors = page.evaluate("""() => {
            const errEls = document.querySelectorAll(
                '[class*="error"], [class*="Error"], [role="alert"], .invalid-feedback'
            );
            return Array.from(errEls).map(e => e.textContent.trim()).filter(t => t).slice(0, 3);
        }""")
        if errors:
            print(f"  [WARN] Wizard NON avanzato — errori validazione: {errors}")
        else:
            print(f"  [WARN] Wizard potrebbe non essere avanzato (URL/heading invariati)")
    else:
        print(f"  Wizard avanzato: {step_name}")

    step_done(page, f"dopo_{step_name}")
    return advanced


def load_photo_paths():
    """Load photo paths from JSON (marketing.foto).
    If no valid photos, download 5 placeholders (1024x768)."""
    foto_json = PROP.get("marketing", {}).get("foto", [])
    if foto_json:
        json_dir = os.path.dirname(os.path.abspath(DATA_FILE))
        paths = []
        for f in foto_json:
            p = f if os.path.isabs(f) else os.path.join(json_dir, f)
            if os.path.isfile(p):
                paths.append(p)
                print(f"  Foto dal JSON: {p}")
            else:
                print(f"  [WARN] Foto non trovata: {p}")
        if paths:
            return paths
        print("  Nessuna foto valida nel JSON — scarico placeholder")

    # Fallback: generate 5 placeholder photos locally (min 768px width required by site)
    print("  Genero 5 foto placeholder locali (1024x768)...")
    paths = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(5):
        path = os.path.join(tmp_dir, f"photo_{i+1}.jpg")
        _generate_placeholder_jpeg(path, 1024, 768, color_index=i)
        paths.append(path)
        print(f"  Foto placeholder generata: {path}")
    return paths


def _generate_placeholder_jpeg(path, width, height, color_index=0):
    """Generate a solid-color JPEG placeholder image."""
    try:
        from PIL import Image
        colors = [(70, 130, 180), (60, 179, 113), (255, 165, 0),
                  (147, 112, 219), (220, 20, 60)]
        color = colors[color_index % len(colors)]
        img = Image.new("RGB", (width, height), color)
        img.save(path, "JPEG", quality=85)
    except ImportError:
        # Fallback: download from picsum if PIL not available
        urllib.request.urlretrieve(
            f"https://picsum.photos/{width}/{height}?random={color_index + 1}", path
        )


def calculate_base_price():
    """Calculate base nightly price: median of listino_prezzi,
    or prezzo_notte, or None."""
    listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
    if listino:
        prezzi = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
        return prezzi[len(prezzi) // 2] if prezzi else None
    return PROP.get("condizioni", {}).get("prezzo_notte")


def consolidate_seasonal_prices():
    """Consolidate weekly listino_prezzi entries into contiguous seasons
    with the same price. Returns list of {da, a, prezzo_notte, notti_min}.
    Example: 4 weeks at €137 become one season 28-mar → 25-apr at €137."""
    listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
    if not listino:
        return []

    # Get min-stay details for matching periods
    sog_dettaglio = PROP.get("condizioni", {}).get("soggiorno_minimo_dettaglio", [])
    sog_bassa = PROP.get("condizioni", {}).get("soggiorno_minimo_bassa", {})
    default_min = sog_bassa.get("notti", 5)

    def get_min_stay(da_str):
        """Find the min-stay for a given start date from soggiorno_minimo_dettaglio."""
        for sog in sog_dettaglio:
            if sog.get("da") == da_str:
                return sog.get("notti", default_min)
        return default_min

    # Consolidate: merge adjacent entries with same price
    seasons = []
    current = None
    for entry in listino:
        prezzo = entry.get("prezzo_notte")
        if not prezzo:
            continue
        if current and current["prezzo_notte"] == prezzo:
            # Extend current season
            current["a"] = entry["a"]
        else:
            # Start new season
            if current:
                seasons.append(current)
            current = {
                "da": entry["da"],
                "a": entry["a"],
                "prezzo_notte": prezzo,
                "notti_min": get_min_stay(entry["da"]),
            }
    if current:
        seasons.append(current)

    return seasons


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


def click_room_counter(page, label_text, clicks):
    """Click the + button N times for a counter row identified by label text.

    Room/bed counters on CaseVacanza do NOT have data-test attributes.
    This function uses JS to find the row by label text, walk up the DOM
    to find the container with [-] and [+] buttons, and click + N times.
    """
    if clicks <= 0:
        return True

    result = page.evaluate("""({label, n}) => {
        // Strategy: find elements containing the label text,
        // then walk up to find a container with at least 2 buttons (- and +)
        const allElements = document.querySelectorAll('div, span, label, p, h3, h4');
        for (const el of allElements) {
            const text = el.textContent.trim();
            if (!text.includes(label)) continue;

            // Skip if this element contains too much text (it's a parent container)
            if (text.length > label.length * 3) continue;

            // Walk up the DOM to find a container with buttons
            let container = el;
            for (let i = 0; i < 6; i++) {
                const buttons = container.querySelectorAll('button');
                if (buttons.length >= 2) {
                    // Found container with - and + buttons
                    // The + button is the last one in the row
                    const addBtn = buttons[buttons.length - 1];
                    for (let j = 0; j < n; j++) {
                        addBtn.click();
                    }
                    return {
                        found: true,
                        label: label,
                        btnText: addBtn.textContent.trim(),
                        clicks: n
                    };
                }
                if (!container.parentElement) break;
                container = container.parentElement;
            }
        }
        return {found: false, label: label};
    }""", {"label": label_text, "n": clicks})

    if result.get("found"):
        page.wait_for_timeout(500)
        print(f"  {label_text}: +{clicks} (JS row-based, btn='{result.get('btnText', '?')}')")
        return True
    else:
        print(f"  [WARN] {label_text}: bottone + non trovato sulla pagina")
        return False



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

    def do_step1():
        # Try data-test first, then text fallback
        single = page.locator('[data-test="single"]')
        if single.count() > 0:
            single.click(force=True)
        else:
            page.get_by_text("Proprietà a unità singola", exact=False).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        step_done(page, "tipo_proprietà")

    try_step(page, "step1_unità_singola", do_step1, critical=True)

    # --- Step 2: Seleziona tipo struttura dal dropdown ---
    tipo = PROP["identificativi"]["tipo_struttura"]
    print(f"Step 2: Seleziona {tipo}")

    def do_step2():
        select = page.locator("select")
        if select.count() > 0:
            try:
                select.first.select_option(label=tipo)
            except Exception:
                # Prova con value se label non corrisponde
                options = select.first.evaluate("""el => {
                    return Array.from(el.options).map(o => ({value: o.value, text: o.text}));
                }""")
                print(f"  Opzioni dropdown: {options}")
                # Cerca match parziale
                for opt in options:
                    if tipo.lower() in opt["text"].lower():
                        select.first.select_option(value=opt["value"])
                        print(f"  Selezionato '{opt['text']}' (match parziale)")
                        break
                else:
                    print(f"  [WARN] '{tipo}' non trovato nel dropdown, opzioni: {[o['text'] for o in options]}")
        else:
            page.get_by_text(tipo).click()
        step_done(page, "tipo_struttura_selezionato")

    try_step(page, "step2_tipo_struttura", do_step2, critical=True)

    # --- Step 3: Click "Intero alloggio" ---
    print("Step 3: Intero alloggio")

    def do_step3():
        page.get_by_text("Intero alloggio").click()
        step_done(page, "intero_alloggio")

    try_step(page, "step3_intero_alloggio", do_step3)

    # --- Step 4: Continua (tipo proprietà) ---
    print("Step 4: Continua (tipo proprietà)")
    click_save_and_verify(page, "tipo_proprietà")

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
    click_save_and_verify(page, "indirizzo")

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
        print(f"  Ospiti: {comp['max_ospiti']}")

        # Room counters — these do NOT have data-test attributes!
        # Use click_room_counter() which finds buttons by label text via JS

        # Bedrooms — default is 1, need (camere - 1) clicks
        bedroom_target = comp["camere"] - 1
        if bedroom_target > 0:
            click_room_counter(page, "Camera da letto", bedroom_target)
            print(f"  Camere target: {comp['camere']}")

        # Bathrooms — default is 0
        bath_target = comp["bagni"]
        if bath_target > 0:
            click_room_counter(page, "Bagno", bath_target)
            print(f"  Bagni target: {comp['bagni']}")

        step_done(page, "ospiti_camere")

    try_step(page, "step8_ospiti_camere", do_step8)

    # --- Step 9: Continua (ospiti) ---
    print("Step 9: Continua (ospiti)")
    click_save_and_verify(page, "ospiti")

    # --- Step 10: Configura letti (dal JSON composizione.letti) ---
    print("Step 10: Configura letti")

    def do_step10():
        letti = comp.get("letti", [])
        if not letti:
            print("  ATTENZIONE: nessun dato letti nel JSON, skip")
            step_done(page, "letti_configurati")
            return

        for letto in letti:
            tipo = letto["tipo"]
            qty = letto["quantita"]
            label = LETTO_LABEL.get(tipo)
            if not label:
                print(f"  [WARN] Tipo letto sconosciuto: {tipo}, skip")
                continue

            # Bed counters also don't have data-test — use click_room_counter
            click_room_counter(page, label, qty)

        step_done(page, "letti_configurati")

    try_step(page, "step10_letti", do_step10)

    # --- Step 11: Continua (letti) ---
    print("Step 11: Continua (letti)")
    click_save_and_verify(page, "letti")

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
    click_save_and_verify(page, "foto")

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
    click_save_and_verify(page, "servizi")

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
    click_save_and_verify(page, "titolo_desc")

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
    click_save_and_verify(page, "prezzo")

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
    click_save_and_verify(page, "condizioni")

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
    click_save_and_verify(page, "regole")

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
# Post-wizard: Seasonal pricing
# ---------------------------------------------------------------------------


def _parse_date_it(date_str, year=2025):
    """Parse Italian short date like '28-mar' into 'YYYY-MM-DD' string."""
    mesi = {
        "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
        "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
    }
    parts = date_str.strip().split("-")
    day = int(parts[0])
    month = mesi.get(parts[1].lower(), 1)
    return f"{year}-{month:02d}-{day:02d}"


def add_seasonal_prices(page):
    """Navigate to the property dashboard and add seasonal prices.

    This runs AFTER the wizard completes and the property exists.
    It goes to the property's 'Tariffe e disponibilità' tab and
    adds each consolidated seasonal price period.
    """
    seasons = consolidate_seasonal_prices()
    if not seasons:
        print("\nNessun listino prezzi nel JSON — skip tariffe stagionali")
        return

    print(f"\n{'='*60}")
    print(f"TARIFFE STAGIONALI: {len(seasons)} stagioni da inserire")
    print("=" * 60)
    for s in seasons:
        print(f"  {s['da']} → {s['a']}: €{s['prezzo_notte']}/notte (min {s['notti_min']} notti)")

    # Navigate to the property list to find the newly created property
    print("\nNavigazione alla lista proprietà...")
    page.goto("https://my.casevacanza.it/listing/properties", timeout=30_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)
    step_done(page, "lista_proprietà")

    # Find and click the property name to go to its dashboard
    nome = PROP["identificativi"]["nome_struttura"]
    print(f"Cerco proprietà '{nome}'...")

    found = False
    # Strategy 1: click exact property name link
    try:
        link = page.get_by_text(nome, exact=False)
        if link.count() > 0:
            link.first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            found = True
            print(f"  Proprietà trovata e aperta: {nome}")
    except Exception as e:
        print(f"  [WARN] Click nome proprietà fallito: {e}")

    # Strategy 2: click the first property card/link (if just created, it should be first)
    if not found:
        try:
            prop_link = page.locator("a[href*='/listing/properties/']").first
            if prop_link.count() > 0:
                prop_link.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                found = True
                print("  Aperta prima proprietà dalla lista")
        except Exception as e:
            print(f"  [WARN] Fallback prima proprietà fallito: {e}")

    if not found:
        print("  [ERRORE] Proprietà non trovata nella lista — skip tariffe stagionali")
        step_done(page, "proprietà_non_trovata")
        return

    step_done(page, "dashboard_proprietà")

    # Navigate to "Tariffe e disponibilità" tab
    print("Navigazione tab 'Tariffe e disponibilità'...")
    tab_found = False
    for tab_text in ["Tariffe e disponibilità", "Tariffe", "Prezzi", "Rates"]:
        try:
            tab = page.get_by_text(tab_text, exact=False)
            if tab.count() > 0:
                tab.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                tab_found = True
                print(f"  Tab '{tab_text}' aperta")
                break
        except Exception:
            continue

    # Strategy 2: click tab via href/data attribute
    if not tab_found:
        try:
            tab_link = page.locator(
                "a[href*='rate'], a[href*='tariff'], a[href*='price'], "
                "[data-test*='rate'], [data-test*='tariff']"
            )
            if tab_link.count() > 0:
                tab_link.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                tab_found = True
                print("  Tab tariffe aperta (CSS fallback)")
        except Exception as e:
            print(f"  [WARN] Tab tariffe CSS fallback fallito: {e}")

    if not tab_found:
        print("  [ERRORE] Tab 'Tariffe e disponibilità' non trovata — skip")
        step_done(page, "tab_tariffe_non_trovata")
        return

    step_done(page, "tab_tariffe")

    # Add each seasonal price
    for i, season in enumerate(seasons):
        print(f"\nStagione {i+1}/{len(seasons)}: "
              f"{season['da']} → {season['a']} = €{season['prezzo_notte']}")

        # Click "Aggiungi prezzo stagionale"
        add_clicked = False
        for btn_text in ["Aggiungi prezzo stagionale", "Aggiungi stagione",
                         "Aggiungi prezzo", "Add seasonal price", "Add season"]:
            try:
                btn = page.get_by_text(btn_text, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(2000)
                    add_clicked = True
                    print(f"  Cliccato '{btn_text}'")
                    break
            except Exception:
                continue

        if not add_clicked:
            # Try button/link with "aggiungi" + any price-related text
            try:
                btn = page.locator(
                    "button:has-text('Aggiungi'), a:has-text('Aggiungi')"
                ).last
                if btn.count() > 0:
                    btn.click()
                    page.wait_for_timeout(2000)
                    add_clicked = True
                    print("  Cliccato bottone 'Aggiungi' (fallback)")
            except Exception:
                pass

        if not add_clicked:
            print(f"  [ERRORE] Bottone 'Aggiungi prezzo stagionale' non trovato — skip")
            continue

        # Fill the seasonal price form
        # Date fields: "da" and "a" (from/to)
        da_date = _parse_date_it(season["da"])
        a_date = _parse_date_it(season["a"])

        # Fill start date
        fill_field(
            page, da_date,
            ["Da", "Dal", "Data inizio", "Inizio", "From", "Start"],
            ["input[name*='start'], input[name*='from'], input[name*='da']",
             "input[type='date']:first-of-type"],
            f"Data inizio stagione {i+1}"
        )

        # Fill end date
        fill_field(
            page, a_date,
            ["A", "Al", "Data fine", "Fine", "To", "End"],
            ["input[name*='end'], input[name*='to'], input[name*='a']",
             "input[type='date']:last-of-type"],
            f"Data fine stagione {i+1}"
        )

        # Fill price
        prezzo_str = str(season["prezzo_notte"])
        fill_field(
            page, prezzo_str,
            ["Prezzo", "Prezzo a notte", "Price", "Nightly rate"],
            ["input[name*='prezz'], input[name*='price'], input[name*='rate']",
             "input[type='number']"],
            f"Prezzo stagione {i+1}"
        )

        # Fill min stay if available
        notti_min = str(season.get("notti_min", ""))
        if notti_min:
            fill_field(
                page, notti_min,
                ["Soggiorno minimo", "Min", "Notti minime", "Minimum stay"],
                ["input[name*='min'], select[name*='min']"],
                f"Soggiorno min stagione {i+1}"
            )

        # Save/confirm the seasonal price
        saved = False
        for save_text in ["Salva", "Conferma", "Aggiungi", "Save", "OK", "Ok"]:
            try:
                save_btn = page.get_by_role("button", name=save_text)
                if save_btn.count() > 0:
                    save_btn.first.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)
                    saved = True
                    print(f"  Salvata stagione {i+1} ('{save_text}')")
                    break
            except Exception:
                continue

        if not saved:
            # Try data-test save button
            try:
                save_btn = page.locator('[data-test="save-button"]')
                if save_btn.count() > 0:
                    save_btn.first.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)
                    saved = True
                    print(f"  Salvata stagione {i+1} (data-test save)")
            except Exception:
                pass

        if not saved:
            print(f"  [WARN] Salvataggio stagione {i+1} non confermato")

        step_done(page, f"stagione_{i+1}")

    print(f"\nTariffe stagionali completate: {len(seasons)} stagioni processate")
    step_done(page, "tariffe_stagionali_completate")


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

            # Post-wizard: add seasonal prices if listino_prezzi exists
            if PROP.get("condizioni", {}).get("listino_prezzi"):
                print("\n" + "=" * 60)
                print("WIZARD COMPLETATO — Avvio inserimento tariffe stagionali")
                print("=" * 60)
                try:
                    add_seasonal_prices(page)
                except Exception as e:
                    print(f"\n[ERRORE] Tariffe stagionali fallite: {e}")
                    step_errors.append(("tariffe_stagionali", str(e)))
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            # Error summary
            if step_errors:
                print("\n" + "=" * 60)
                print(f"RIEPILOGO ERRORI: {len(step_errors)} step falliti:")
                for name, err in step_errors:
                    print(f"  - {name}: {err}")
                print("=" * 60)
            else:
                print("\nTutti gli step completati con successo!")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
