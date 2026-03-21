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

# --- Verifica dati letti dal JSON ---
print(f"=== DATI LETTI DAL JSON ({DATA_FILE}) ===")
print(f"Nome: {PROP['identificativi']['nome_struttura']}")
print(f"Tipo: {PROP['identificativi']['tipo_struttura']}")
print(f"Indirizzo: {PROP['identificativi']['indirizzo']}")
print(f"Comune: {PROP['identificativi']['comune']}")
print(f"Max ospiti: {PROP['composizione']['max_ospiti']}")
print(f"Camere: {PROP['composizione']['camere']}")
print(f"Bagni: {PROP['composizione']['bagni']}")
print(f"Posti letto: {PROP['composizione']['posti_letto']}")
print(f"Letti: {PROP['composizione'].get('letti', [])}")
print(f"===================================")

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

    # 4) Neutralize blocking overlays via JS — ONLY pointer-events:none
    #    NEVER use display:none because it can hide the save-button too!
    hidden = page.evaluate("""() => {
        let count = 0;
        // Only target the overlay backdrop, NOT the content or portal
        document.querySelectorAll(
            '.ReactModal__Overlay'
        ).forEach(el => {
            el.style.pointerEvents = 'none';
            el.style.zIndex = '-1';
            count++;
            // Also neutralize children that might intercept clicks
            el.querySelectorAll('*').forEach(child => {
                child.style.pointerEvents = 'none';
            });
        });
        return count;
    }""")
    if hidden:
        print(f"  Nascosti {hidden} overlay via JS (pointer-events:none + zIndex:-1)")
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
    # Dismiss any modal/overlay that might block the save button
    dismiss_overlay(page)

    url_before = page.url
    heading_before = page.evaluate("""() => {
        const h = document.querySelector('h1, h2, h3, [data-test*="title"], [class*="heading"]');
        return h ? h.textContent.trim() : '';
    }""")

    # Scroll to bottom to make save button visible
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)

    # Diagnostic: check if save-button exists in DOM
    save_exists = page.evaluate("""() => {
        const btn = document.querySelector('[data-test="save-button"]');
        if (!btn) return 'not in DOM';
        const rect = btn.getBoundingClientRect();
        const style = window.getComputedStyle(btn);
        return `in DOM, display=${style.display}, visibility=${style.visibility}, `
             + `opacity=${style.opacity}, rect=${JSON.stringify(rect)}, `
             + `disabled=${btn.disabled}, text="${btn.textContent.trim()}"`;
    }""")
    print(f"  [DIAG] save-button: {save_exists}")

    try:
        save_btn = page.locator('[data-test="save-button"]')
        save_btn.scroll_into_view_if_needed(timeout=3000)
        save_btn.click(timeout=10000)
    except Exception:
        print(f"  [WARN] Click save-button fallito — provo fallback")
        dismiss_overlay(page)
        try:
            page.locator('[data-test="save-button"]').click(force=True, timeout=5000)
        except Exception:
            # Fallback: try "Continua" button (visible at bottom of page)
            print(f"  [WARN] save-button non trovato — provo 'Continua'")
            clicked = False
            for btn_text in ["Continua", "Avanti", "Salva e continua", "Save", "Salva"]:
                try:
                    btn = page.get_by_role("button", name=btn_text)
                    if btn.count() > 0:
                        btn.first.scroll_into_view_if_needed()
                        btn.first.click()
                        clicked = True
                        print(f"  Click fallback su '{btn_text}'")
                        break
                except Exception:
                    continue
            if not clicked:
                # Last resort: JS click on any submit/save button
                js_clicked = page.evaluate("""() => {
                    // Try multiple selectors
                    const selectors = [
                        '[data-test="save-button"]',
                        'button[type="submit"]',
                        'button.bg-primary-normal-gradient',
                        'button[class*="save"]',
                        'button[class*="continue"]',
                        'button[class*="primary"]'
                    ];
                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && btn.offsetParent !== null) {
                            btn.scrollIntoView();
                            btn.click();
                            return sel;
                        }
                    }
                    // Try any visible button with save/continue text
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.textContent.toLowerCase().trim();
                        if ((text.includes('continua') || text.includes('salva') || text.includes('avanti'))
                            && btn.offsetParent !== null) {
                            btn.scrollIntoView();
                            btn.click();
                            return `text:"${btn.textContent.trim()}"`;
                        }
                    }
                    return false;
                }""")
                if js_clicked:
                    print(f"  Click JS fallback: {js_clicked}")
                else:
                    print(f"  [WARN] Nessun bottone save/continua trovato!")
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

    Strategy:
    1. JS finds the label element, walks up to the counter row container,
       identifies the LAST button (the "+" button), and returns its bounding box.
    2. Playwright clicks at the center of that bounding box using page.mouse.click().
       Real mouse events at real coordinates → React always responds.
    3. Re-locates the button each iteration (React may re-render after each click).
    """
    if clicks <= 0:
        return True

    for click_idx in range(clicks):
        # --- Locate the "+" button's bounding box via JS ---
        btn_info = page.evaluate("""(label) => {
            // Helper: given a starting element, walk up to find a row with >=2 buttons
            function findCounterRow(startEl) {
                let el = startEl;
                for (let depth = 0; depth < 10; depth++) {
                    if (!el) return null;
                    const buttons = el.querySelectorAll('button');
                    if (buttons.length >= 2) {
                        return {container: el, buttons: buttons};
                    }
                    el = el.parentElement;
                }
                return null;
            }

            // Strategy A: exact text node match
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            while (walker.nextNode()) {
                const nodeText = walker.currentNode.textContent.trim();
                if (nodeText.toLowerCase() === label.toLowerCase()) {
                    const row = findCounterRow(walker.currentNode.parentElement);
                    if (row) {
                        const addBtn = row.buttons[row.buttons.length - 1];
                        const rect = addBtn.getBoundingClientRect();
                        return {
                            found: true, method: 'exact',
                            x: rect.x + rect.width / 2,
                            y: rect.y + rect.height / 2,
                            w: rect.width, h: rect.height,
                            btnText: addBtn.textContent.trim(),
                            btnCount: row.buttons.length
                        };
                    }
                }
            }

            // Strategy B: element textContent includes label (shorter elements first)
            const labelLower = label.toLowerCase();
            const candidates = Array.from(
                document.querySelectorAll('div, span, label, p, h3, h4, li')
            ).filter(el => {
                const t = el.textContent.trim().toLowerCase();
                return t.includes(labelLower) && t.length < label.length * 4;
            }).sort((a, b) => a.textContent.length - b.textContent.length);

            for (const el of candidates) {
                const row = findCounterRow(el);
                if (row) {
                    const addBtn = row.buttons[row.buttons.length - 1];
                    const rect = addBtn.getBoundingClientRect();
                    return {
                        found: true, method: 'includes',
                        x: rect.x + rect.width / 2,
                        y: rect.y + rect.height / 2,
                        w: rect.width, h: rect.height,
                        btnText: addBtn.textContent.trim(),
                        btnCount: row.buttons.length
                    };
                }
            }

            // Strategy C: find ALL counter rows on the page and return diagnostic info
            const allButtons = document.querySelectorAll('button');
            const rows = [];
            const seen = new Set();
            for (const btn of allButtons) {
                let container = btn.parentElement;
                for (let d = 0; d < 5; d++) {
                    if (!container || seen.has(container)) break;
                    const siblings = container.querySelectorAll('button');
                    if (siblings.length >= 2 && siblings.length <= 4) {
                        seen.add(container);
                        // Get nearby text
                        const text = container.textContent.trim().substring(0, 80);
                        rows.push({text, btnCount: siblings.length});
                        break;
                    }
                    container = container.parentElement;
                }
            }

            return {found: false, counterRows: rows};
        }""", label_text)

        if not btn_info.get("found"):
            diag = btn_info.get("counterRows", [])
            print(f"  [WARN] {label_text}: + button non trovato (click {click_idx+1}/{clicks})")
            if diag and click_idx == 0:
                print(f"  [DIAG] Counter rows trovate sulla pagina:")
                for row in diag:
                    print(f"    - [{row['btnCount']} btn] {row['text']}")
            return False

        # --- Click at the exact coordinates using Playwright mouse ---
        x, y = btn_info["x"], btn_info["y"]
        page.mouse.click(x, y)
        page.wait_for_timeout(400)

        if click_idx == 0:
            method = btn_info.get("method", "?")
            btn_text = btn_info.get("btnText", "?")
            print(f"  {label_text}: clicking at ({x:.0f}, {y:.0f}), "
                  f"btn='{btn_text}', method={method}")

    print(f"  {label_text}: +{clicks} click completati")
    return True



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
    """Navigate to add-property wizard, or resume an incomplete property if one exists."""
    print("Controllo proprietà incomplete...")

    # First check if there's an incomplete property to resume
    page.goto("https://my.casevacanza.it/listing/properties", timeout=30_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)

    property_name = PROP.get("marketing", {}).get("titolo", "")
    # Look for "Da completare" / "Completa e pubblica" button for this property
    try:
        # Find property cards with "Da completare" status
        incomplete_cards = page.locator("text=Da completare")
        if incomplete_cards.count() > 0:
            print(f"  Trovate {incomplete_cards.count()} proprietà incomplete")

            # Try to find one matching our property name
            if property_name:
                matching = page.locator(f"text={property_name}")
                if matching.count() > 0:
                    # Find the "Completa e pubblica" button near this property
                    # Navigate up to the card container, then find the button
                    complete_btn = page.get_by_role("link", name="Completa e pubblica")
                    if complete_btn.count() == 0:
                        complete_btn = page.get_by_text("Completa e pubblica", exact=False)

                    if complete_btn.count() > 0:
                        # Click the first matching one
                        complete_btn.first.click()
                        page.wait_for_load_state("domcontentloaded")
                        page.wait_for_timeout(3000)
                        print(f"  Ripresa proprietà incompleta: {property_name}")
                        dismiss_overlay(page)
                        step_done(page, "ripresa_proprietà")
                        return
    except Exception as e:
        print(f"  [WARN] Controllo proprietà incomplete fallito: {e}")

    # No incomplete property found — create new
    print("Nessuna proprietà incompleta trovata — creo nuova")
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
    """Complete the full property insertion wizard.
    Handles both new properties and resuming incomplete ones."""
    photo_paths = load_photo_paths()

    # Detect if we're resuming (page is NOT on add-property start)
    current_url = page.url
    is_resuming = "add-property" not in current_url or "/edit/" in current_url or "/price" in current_url or "/calendar" in current_url
    if is_resuming:
        print(f"  Riprendo proprietà da: {current_url}")
        # Detect current wizard step from URL or page content
        page_text = page.evaluate("() => document.body?.innerText?.substring(0, 500) || ''")
        print(f"  Contenuto pagina: {page_text[:200]}...")

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

    # When resuming, step1 is not critical (we're past it already)
    try_step(page, "step1_unità_singola", do_step1, critical=not is_resuming)

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
        # Screenshot BEFORE any interaction
        save_html(page, "step8_BEFORE_clicks")
        screenshot(page, "step8_BEFORE_clicks")

        # --- OSPITI: use proven data-test scoped selector ---
        ospiti_btn = page.locator(
            '[data-test="guest-count"] [data-test="counter-add-btn"]')
        if ospiti_btn.count() > 0:
            for _ in range(comp["max_ospiti"] - 1):
                ospiti_btn.click()
                page.wait_for_timeout(300)
            print(f"  Ospiti: {comp['max_ospiti']}")
        else:
            # Fallback: coordinate click on ospiti counter
            click_room_counter(page, "Ospiti", comp["max_ospiti"] - 1)

        # Bambini ammessi checkbox
        try:
            bambini_cb = page.locator('[data-test="children-allowed"]')
            if bambini_cb.count() > 0 and not bambini_cb.is_checked():
                bambini_cb.check()
                print("  Bambini ammessi: checked")
        except Exception:
            pass

        # Animali domestici ammessi
        if PROP.get("dotazioni", {}).get("animali_ammessi"):
            try:
                animali_cb = page.get_by_text("Animali domestici ammessi", exact=False)
                if animali_cb.count() > 0:
                    animali_cb.first.click()
                    print("  Animali domestici: checked")
            except Exception:
                pass

        # Wait for DOM to settle after ospiti changes
        page.wait_for_timeout(1500)

        # --- ROOM COUNTERS: coordinate-based clicks ---
        # Camera da letto: default=1, need (camere - 1) extra clicks
        bedroom_extra = comp["camere"] - 1
        if bedroom_extra > 0:
            click_room_counter(page, "Camera da letto", bedroom_extra)

        # Soggiorno: skip (default 0 is fine for most properties)

        # Bagno: default=1 on CaseVacanza, need (bagni - 1) extra clicks
        bagno_extra = comp["bagni"] - 1
        if bagno_extra > 0:
            click_room_counter(page, "Bagno", bagno_extra)

        # Cucina: default=0, need 1 click
        click_room_counter(page, "Cucina", 1)

        # Take screenshot AFTER all clicks to verify
        screenshot(page, "step8_AFTER_room_clicks")

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
            filled = False

            # Wait for the price page to fully load
            try:
                page.get_by_text("Impostiamo il prezzo", exact=False).wait_for(timeout=8000)
                print("  Pagina prezzo caricata")
            except Exception:
                print("  [WARN] Heading 'Impostiamo il prezzo' non trovato, continuo comunque")
            page.wait_for_timeout(2000)

            # Diagnostic: log all input elements on the page
            diag = page.evaluate("""() => {
                const inputs = document.querySelectorAll('input');
                return Array.from(inputs).map(inp => ({
                    type: inp.type,
                    name: inp.name,
                    placeholder: inp.placeholder,
                    id: inp.id,
                    visible: inp.offsetParent !== null,
                    value: inp.value
                }));
            }""")
            print(f"  [DIAG] Input trovati sulla pagina: {diag}")

            # Strategy 0: get_by_placeholder — try with and without € symbol
            for ph in ["Prezzo per notte", "€ Prezzo per notte", "Prezzo", "notte"]:
                try:
                    f = page.get_by_placeholder(ph, exact=False)
                    if f.count() > 0:
                        f.first.scroll_into_view_if_needed()
                        f.first.click()
                        page.wait_for_timeout(500)
                        f.first.fill(prezzo_str)
                        filled = True
                        print(f"  Prezzo: {prezzo_str} EUR/notte (placeholder '{ph}')")
                        break
                except Exception:
                    continue

            # Strategy 1: label "Prezzo per notte"
            if not filled:
                for lbl in ["Prezzo per notte", "Prezzo", "Price per night", "Price"]:
                    try:
                        f = page.get_by_label(lbl, exact=False)
                        if f.count() > 0:
                            f.first.scroll_into_view_if_needed()
                            f.first.click()
                            page.wait_for_timeout(500)
                            f.first.fill(prezzo_str)
                            filled = True
                            print(f"  Prezzo: {prezzo_str} EUR/notte (label '{lbl}')")
                            break
                    except Exception:
                        continue

            # Strategy 2: CSS placeholder attribute (including € prefix)
            if not filled:
                try:
                    f = page.locator(
                        "input[placeholder*='Prezzo'], input[placeholder*='prezzo'], "
                        "input[placeholder*='notte'], input[placeholder*='€']"
                    )
                    if f.count() > 0:
                        f.first.scroll_into_view_if_needed()
                        f.first.click()
                        page.wait_for_timeout(500)
                        f.first.fill(prezzo_str)
                        filled = True
                        print(f"  Prezzo: {prezzo_str} EUR/notte (CSS placeholder)")
                except Exception:
                    pass

            # Strategy 3: CSS selectors — number input or name containing price
            if not filled:
                try:
                    f = page.locator(
                        "input[type='number'], input[name*='prezz'], input[name*='price'], "
                        "input[name*='rate'], input[name*='tariff']"
                    )
                    if f.count() > 0:
                        f.first.scroll_into_view_if_needed()
                        f.first.click()
                        page.wait_for_timeout(500)
                        f.first.fill(prezzo_str)
                        filled = True
                        print(f"  Prezzo: {prezzo_str} EUR/notte (CSS)")
                except Exception:
                    pass

            # Strategy 4: find ANY visible text input on this page
            # On the price page there is typically only one input field
            if not filled:
                try:
                    visible_inputs = page.locator("input:visible").all()
                    for inp in visible_inputs:
                        inp_type = inp.get_attribute("type") or "text"
                        if inp_type in ("text", "number", "tel", ""):
                            inp.scroll_into_view_if_needed()
                            inp.click()
                            page.wait_for_timeout(500)
                            inp.fill(prezzo_str)
                            filled = True
                            print(f"  Prezzo: {prezzo_str} EUR/notte (visible input type={inp_type})")
                            break
                except Exception as e:
                    print(f"  [WARN] Strategy 4 (visible input) fallita: {e}")

            # Strategy 5: JS — find input near "Prezzo" or "notte" text
            if not filled:
                filled = page.evaluate("""(val) => {
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        // Walk up to find a container with "prezzo" text
                        let container = inp;
                        for (let i = 0; i < 5; i++) {
                            container = container.parentElement;
                            if (!container) break;
                            const text = container.textContent.toLowerCase();
                            if (text.includes('prezzo') && text.includes('notte')) {
                                inp.focus();
                                const nativeSet = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                nativeSet.call(inp, val);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                inp.dispatchEvent(new Event('blur', {bubbles: true}));
                                return true;
                            }
                        }
                    }
                    return false;
                }""", prezzo_str)
                if filled:
                    print(f"  Prezzo: {prezzo_str} EUR/notte (JS)")

            # Strategy 6: JS — last resort, any empty visible input
            if not filled:
                filled = page.evaluate("""(val) => {
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        if (inp.offsetParent === null) continue;  // skip hidden
                        const t = inp.type || 'text';
                        if (['text','number','tel',''].includes(t) && !inp.value) {
                            inp.focus();
                            const nativeSet = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            nativeSet.call(inp, val);
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                            inp.dispatchEvent(new Event('blur', {bubbles: true}));
                            return true;
                        }
                    }
                    return false;
                }""", prezzo_str)
                if filled:
                    print(f"  Prezzo: {prezzo_str} EUR/notte (JS any empty input)")

            if not filled:
                print(f"  [WARN] Campo prezzo non trovato — {prezzo_str} EUR/notte")
            else:
                # Verify the value actually stuck
                page.wait_for_timeout(500)
                screenshot(page, "prezzo_filled")
        else:
            print("  Prezzo non presente nel JSON — lascio vuoto")

        # --- COSTI EXTRA: Pulizia, Asciugamani, Biancheria da letto ---
        # These are "+" buttons on the same page as prezzo.
        # Clicking opens a form to set the cost amount.
        cond = PROP["condizioni"]
        screenshot(page, "prezzo_before_extras")

        # Helper: click a cost-extra button and fill the amount
        def add_extra_cost(button_label, amount_text):
            """Click a 'Label +' button on the tariffe page, fill the cost form."""
            if not amount_text:
                return
            # Extract numeric amount from text like "250 EUR a soggiorno obbligatoria"
            import re as _re
            match = _re.search(r'(\d+)', str(amount_text))
            if not match:
                print(f"  [WARN] Nessun importo numerico in '{amount_text}' per {button_label}")
                return
            amount = match.group(1)

            try:
                # Find the button with label text — try multiple strategies
                btn_clicked = False

                # Strategy A: role=button with name
                try:
                    btn = page.get_by_role("button", name=button_label)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        btn_clicked = True
                except Exception:
                    pass

                # Strategy B: get_by_text
                if not btn_clicked:
                    try:
                        btn = page.get_by_text(button_label, exact=False)
                        if btn.count() > 0:
                            btn.first.click()
                            btn_clicked = True
                    except Exception:
                        pass

                # Strategy C: locator with button/a containing text
                if not btn_clicked:
                    try:
                        btn = page.locator(f"button:has-text('{button_label}'), a:has-text('{button_label}'), [role='button']:has-text('{button_label}')")
                        if btn.count() > 0:
                            btn.first.click()
                            btn_clicked = True
                    except Exception:
                        pass

                if not btn_clicked:
                    print(f"  [WARN] Bottone '{button_label}' non trovato sulla pagina")
                    return

                page.wait_for_timeout(2000)
                print(f"  Cliccato '{button_label}' — apro form costo extra")
                screenshot(page, f"extra_cost_{button_label.lower().replace(' ', '_')}")

                # Look for the price input that appeared
                filled = False

                # Try get_by_placeholder
                for ph in ["Prezzo", "Costo", "Importo", "EUR", "€", "0"]:
                    try:
                        f = page.get_by_placeholder(ph, exact=False)
                        if f.count() > 0:
                            f.last.click()
                            page.wait_for_timeout(300)
                            f.last.fill(amount)
                            filled = True
                            print(f"  {button_label}: €{amount} (placeholder '{ph}')")
                            break
                    except Exception:
                        continue

                # Try label-based
                if not filled:
                    for lbl in ["Prezzo", "Costo", "Importo", "Price", "Amount"]:
                        try:
                            f = page.get_by_label(lbl)
                            if f.count() > 0:
                                f.last.click()
                                page.wait_for_timeout(300)
                                f.last.fill(amount)
                                filled = True
                                print(f"  {button_label}: €{amount} (label '{lbl}')")
                                break
                        except Exception:
                            continue

                # Fallback: find input[type=number] or input[inputmode=numeric]
                if not filled:
                    try:
                        inputs = page.locator("input[type='number'], input[inputmode='numeric'], input[inputmode='decimal']")
                        if inputs.count() > 0:
                            inputs.last.click()
                            page.wait_for_timeout(300)
                            inputs.last.fill(amount)
                            filled = True
                            print(f"  {button_label}: €{amount} (input number)")
                    except Exception:
                        pass

                # Last fallback: JS — find visible input with € nearby
                if not filled:
                    filled = page.evaluate("""(amount) => {
                        const inputs = document.querySelectorAll('input');
                        for (const inp of inputs) {
                            if (inp.offsetParent === null) continue; // skip hidden
                            const rect = inp.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;
                            const container = inp.closest('form') || inp.closest('[class*="modal"]')
                                || inp.closest('[class*="Modal"]') || inp.parentElement?.parentElement;
                            if (container) {
                                const nativeSet = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value').set;
                                nativeSet.call(inp, amount);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                        return false;
                    }""", amount)
                    if filled:
                        print(f"  {button_label}: €{amount} (JS)")

                if not filled:
                    print(f"  [WARN] Campo importo per '{button_label}' non trovato")

                # Confirm/save the extra cost
                page.wait_for_timeout(500)
                for confirm_text in ["Salva", "Conferma", "Aggiungi", "OK", "Ok", "Save"]:
                    try:
                        confirm = page.get_by_role("button", name=confirm_text)
                        if confirm.count() > 0 and confirm.last.is_visible():
                            confirm.last.click()
                            page.wait_for_timeout(1500)
                            print(f"  Confermato {button_label} ('{confirm_text}')")
                            break
                    except Exception:
                        continue

                # Dismiss any overlay that remains after confirming
                dismiss_overlay(page)

            except Exception as e:
                print(f"  [WARN] Extra cost '{button_label}' fallito: {e}")

        # Add Pulizia
        add_extra_cost("Pulizia", cond.get("pulizia_finale"))

        # Add Asciugamani
        add_extra_cost("Asciugamani", cond.get("asciugamani"))

        # Add Biancheria da letto (use lenzuola from JSON)
        add_extra_cost("Biancheria da letto", cond.get("lenzuola"))

        screenshot(page, "prezzo_after_extras")

        # --- IMPOSTAZIONI PREDEFINITE: click "Modifica" to change defaults ---
        # Soggiorno minimo, check-in/out are in "Impostazioni predefinite" section
        try:
            # Find "Modifica" link/button near "Impostazioni predefinite"
            modifica_btn = None
            for sel in [
                page.get_by_role("link", name="Modifica"),
                page.get_by_role("button", name="Modifica"),
                page.get_by_text("Modifica", exact=False),
            ]:
                try:
                    if sel.count() > 0 and sel.first.is_visible():
                        modifica_btn = sel.first
                        break
                except Exception:
                    continue

            if modifica_btn:
                modifica_btn.click()
                page.wait_for_timeout(3000)
                print("  Cliccato 'Modifica' impostazioni predefinite")
                screenshot(page, "impostazioni_predefinite_aperte")

                # Soggiorno minimo — the modal likely has select/input for min nights
                sog_bassa = cond.get("soggiorno_minimo_bassa", {})
                sog_alta = cond.get("soggiorno_minimo_alta", {})
                notti = str(sog_bassa.get("notti", sog_alta.get("notti", "")))
                if notti:
                    # Try fill_field first
                    filled_sog = fill_field(
                        page, notti,
                        ["Soggiorno minimo", "Notti minime", "Minimum stay",
                         "Lunghezza del soggiorno", "Minimo"],
                        ["input[name*='soggiorno']", "input[name*='minim']",
                         "input[name*='stay']", "select[name*='soggiorno']",
                         "select[name*='min']", "input[name*='night']"],
                        "Soggiorno minimo"
                    )
                    # Fallback: JS in modal context
                    if not filled_sog:
                        filled_sog = page.evaluate("""(notti) => {
                            // Look for inputs/selects inside modal or overlay
                            const modal = document.querySelector('.ReactModal__Content')
                                || document.querySelector('[class*="modal"]')
                                || document.querySelector('[role="dialog"]');
                            if (!modal) return false;
                            const fields = modal.querySelectorAll('input, select');
                            for (const f of fields) {
                                const container = f.closest('label') || f.parentElement;
                                const text = (container?.textContent || '').toLowerCase();
                                if (text.includes('soggiorno') || text.includes('minim') || text.includes('nott')) {
                                    if (f.tagName === 'SELECT') {
                                        for (const opt of f.options) {
                                            if (opt.value === notti || opt.text.includes(notti)) {
                                                f.value = opt.value;
                                                f.dispatchEvent(new Event('change', {bubbles: true}));
                                                return true;
                                            }
                                        }
                                    } else {
                                        const nativeSet = Object.getOwnPropertyDescriptor(
                                            window.HTMLInputElement.prototype, 'value').set;
                                        nativeSet.call(f, notti);
                                        f.dispatchEvent(new Event('input', {bubbles: true}));
                                        f.dispatchEvent(new Event('change', {bubbles: true}));
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }""", notti)
                        if filled_sog:
                            print(f"  Soggiorno minimo: {notti} (JS modal)")

                # Check-in — extract start hour from "17:00 - 21:00"
                check_in_raw = cond.get("check_in", "")
                if check_in_raw:
                    fill_field(
                        page, check_in_raw,
                        ["Check-in", "Check in", "Orario arrivo", "Arrivo"],
                        ["input[name*='check_in']", "input[name*='checkin']",
                         "select[name*='check_in']", "select[name*='checkin']",
                         "select[name*='arrival']"],
                        "Check-in"
                    )

                # Check-out
                check_out_raw = cond.get("check_out", "")
                if check_out_raw:
                    fill_field(
                        page, check_out_raw,
                        ["Check-out", "Check out", "Orario partenza", "Partenza"],
                        ["input[name*='check_out']", "input[name*='checkout']",
                         "select[name*='check_out']", "select[name*='checkout']",
                         "select[name*='departure']"],
                        "Check-out"
                    )

                screenshot(page, "impostazioni_predefinite_compilate")

                # Save impostazioni predefinite — try multiple strategies
                saved = False
                for save_text in ["Salva", "Conferma", "Save", "OK", "Applica"]:
                    try:
                        save_btn = page.get_by_role("button", name=save_text)
                        if save_btn.count() > 0 and save_btn.last.is_visible():
                            save_btn.last.click()
                            page.wait_for_timeout(2000)
                            print(f"  Impostazioni predefinite salvate ('{save_text}')")
                            saved = True
                            break
                    except Exception:
                        continue

                # If save button not found, try submit type button in modal
                if not saved:
                    try:
                        submit = page.locator("[type='submit'], button[form]")
                        if submit.count() > 0 and submit.last.is_visible():
                            submit.last.click()
                            page.wait_for_timeout(2000)
                            saved = True
                            print("  Impostazioni predefinite salvate (submit)")
                    except Exception:
                        pass

                # Always dismiss overlay after modal interaction
                dismiss_overlay(page)
                page.wait_for_timeout(1000)

            else:
                print("  [INFO] Bottone 'Modifica' non trovato — impostazioni predefinite skip")
        except Exception as e:
            print(f"  [WARN] Impostazioni predefinite fallite: {e}")
            dismiss_overlay(page)

        step_done(page, "prezzo_e_condizioni")

    try_step(page, "step19_prezzo", do_step19)

    # --- Step 20: Continua (prezzo/tariffe page) ---
    print("Step 20: Continua (prezzo)")
    click_save_and_verify(page, "prezzo")

    # --- Step 26: Calendario (iCal import) ---
    print("Step 26: Calendario")

    def do_step26():
        screenshot(page, "calendario_before")
        ical_url = PROP.get("condizioni", {}).get("ical_url")
        if ical_url:
            # Step 1: Click radio "Sì, utilizzo altre piattaforme o un calendario personale"
            radio_clicked = False
            for radio_text in [
                "Si, utilizzo altre piattaforme o un calendario personale",
                "Sì, utilizzo altre piattaforme o un calendario personale",
                "utilizzo altre piattaforme o un calendario personale",
                "utilizzo altre piattaforme",
                "Si, utilizzo altre piattaforme",
                "Sì, utilizzo altre piattaforme",
                "Sì",
                "Si,",
            ]:
                try:
                    radio = page.get_by_text(radio_text, exact=False)
                    if radio.count() > 0:
                        radio.first.click()
                        page.wait_for_timeout(2000)
                        radio_clicked = True
                        print(f"  Radio selezionato: '{radio_text}'")
                        break
                except Exception:
                    continue

            # Fallback: click radio input directly
            if not radio_clicked:
                try:
                    radios = page.locator("input[type='radio']")
                    if radios.count() > 0:
                        radios.first.click()
                        page.wait_for_timeout(2000)
                        radio_clicked = True
                        print("  Radio selezionato (primo radio input)")
                except Exception:
                    pass

            if not radio_clicked:
                print("  [WARN] Radio 'Sì utilizzo altre piattaforme' non trovato")

            screenshot(page, "calendario_after_radio")

            # Step 2: Find URL input field and paste iCal URL
            url_filled = False
            for sel in [
                "input[type='url']", "input[name*='ical']", "input[name*='url']",
                "input[placeholder*='http']", "input[placeholder*='ical']",
                "input[placeholder*='URL']", "input[placeholder*='url']",
                "input[type='text']",
            ]:
                try:
                    f = page.locator(sel)
                    if f.count() > 0:
                        f.last.fill(ical_url)
                        url_filled = True
                        print(f"  iCal URL inserito: {ical_url}")
                        break
                except Exception:
                    continue

            if not url_filled:
                print(f"  [WARN] Campo URL iCal non trovato — URL: {ical_url}")

            # Step 3: Confirm import
            if url_filled:
                for confirm_text in ["Importa", "Sincronizza", "Salva", "Conferma",
                                     "Aggiungi", "OK", "Import", "Save"]:
                    try:
                        confirm = page.get_by_role("button", name=confirm_text)
                        if confirm.count() > 0 and confirm.first.is_visible():
                            confirm.first.click()
                            page.wait_for_timeout(2000)
                            print(f"  Confermato import iCal ('{confirm_text}')")
                            break
                    except Exception:
                        continue
        else:
            # No iCal: select "No, gestisco solo le prenotazioni qui"
            for no_text in [
                "No, gestisco solo le prenotazioni qui",
                "No,",
            ]:
                try:
                    radio = page.get_by_text(no_text, exact=False)
                    if radio.count() > 0:
                        radio.first.click()
                        page.wait_for_timeout(1000)
                        print(f"  Selezionato: '{no_text}'")
                        break
                except Exception:
                    continue

        step_done(page, "dopo_calendario")

    try_step(page, "step26_calendario", do_step26)

    # Advance past calendario page
    print("Continua (calendario)")
    click_save_and_verify(page, "calendario")

    # --- Step 27: Requisiti regionali — CIN/CIR ---
    print("Step 27: Requisiti regionali (CIN/CIR)")

    def do_step27():
        screenshot(page, "requisiti_before")
        cin = PROP.get("identificativi", {}).get("cin")
        cir = PROP.get("identificativi", {}).get("cir")

        if not cin and not cir:
            print("  CIN e CIR non presenti nel JSON — skip")
            step_done(page, "dopo_requisiti_skip")
            return

        # --- CIN ---
        if cin:
            filled_cin = False

            # Strategy 0: get_by_placeholder (most reliable — matches visible placeholder)
            for ph in ["Inserisci il numero CIN", "CIN", "numero CIN"]:
                try:
                    cin_field = page.get_by_placeholder(ph, exact=False)
                    if cin_field.count() > 0:
                        cin_field.first.click()
                        page.wait_for_timeout(300)
                        cin_field.first.fill(cin)
                        filled_cin = True
                        print(f"  CIN compilato: {cin} (placeholder '{ph}')")
                        break
                except Exception:
                    continue

            # Strategy 1: CSS placeholder attribute
            if not filled_cin:
                try:
                    cin_field = page.locator("input[placeholder*='CIN']")
                    if cin_field.count() > 0:
                        cin_field.first.click()
                        page.wait_for_timeout(300)
                        cin_field.first.fill(cin)
                        filled_cin = True
                        print(f"  CIN compilato: {cin} (CSS placeholder)")
                except Exception:
                    pass

            # Strategy 2: label
            if not filled_cin:
                try:
                    cin_field = page.get_by_label("CIN", exact=False)
                    if cin_field.count() > 0:
                        cin_field.first.click()
                        page.wait_for_timeout(300)
                        cin_field.first.fill(cin)
                        filled_cin = True
                        print(f"  CIN compilato (label): {cin}")
                except Exception:
                    pass

            # Strategy 3: JS — find first input inside a section containing "CIN" heading
            if not filled_cin:
                filled_cin = page.evaluate("""(val) => {
                    // Find headings/paragraphs mentioning CIN (Nazionale)
                    const allEls = document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,strong,b,span,div');
                    for (const el of allEls) {
                        const t = el.textContent || '';
                        if (t.includes('Nazionale') && t.includes('CIN') && !t.includes('CIR')) {
                            // Look for the nearest input after this heading
                            let sibling = el.nextElementSibling;
                            for (let i = 0; i < 10 && sibling; i++) {
                                const inp = sibling.querySelector('input') || (sibling.tagName === 'INPUT' ? sibling : null);
                                if (inp) {
                                    const nativeSet = Object.getOwnPropertyDescriptor(
                                        window.HTMLInputElement.prototype, 'value').set;
                                    nativeSet.call(inp, val);
                                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                sibling = sibling.nextElementSibling;
                            }
                        }
                    }
                    // Fallback: check parent hierarchy but only 3 levels
                    const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                    for (const inp of inputs) {
                        let container = inp.parentElement;
                        for (let i = 0; i < 3; i++) {
                            if (!container) break;
                            const text = container.textContent;
                            if (text.includes('CIN') && text.includes('Nazionale')) {
                                const nativeSet = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value').set;
                                nativeSet.call(inp, val);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                            container = container.parentElement;
                        }
                    }
                    return false;
                }""", cin)
                if filled_cin:
                    print(f"  CIN compilato (JS): {cin}")

            # Strategy 4: first text input on page
            if not filled_cin:
                try:
                    text_inputs = page.locator("input[type='text'], input:not([type])")
                    if text_inputs.count() > 0:
                        text_inputs.first.click()
                        page.wait_for_timeout(300)
                        text_inputs.first.fill(cin)
                        filled_cin = True
                        print(f"  CIN compilato (primo input): {cin}")
                except Exception:
                    pass

            if not filled_cin:
                print(f"  [WARN] Campo CIN non trovato — {cin}")

        # --- CIR ---
        if cir:
            filled_cir = False

            # Strategy 0: get_by_placeholder (most reliable)
            for ph in ["Inserisci il numero CIR", "CIR", "numero CIR"]:
                try:
                    cir_field = page.get_by_placeholder(ph, exact=False)
                    if cir_field.count() > 0:
                        cir_field.first.click()
                        page.wait_for_timeout(300)
                        cir_field.first.fill(cir)
                        filled_cir = True
                        print(f"  CIR compilato: {cir} (placeholder '{ph}')")
                        break
                except Exception:
                    continue

            # Strategy 1: CSS placeholder attribute
            if not filled_cir:
                try:
                    cir_field = page.locator("input[placeholder*='CIR']")
                    if cir_field.count() > 0:
                        cir_field.first.click()
                        page.wait_for_timeout(300)
                        cir_field.first.fill(cir)
                        filled_cir = True
                        print(f"  CIR compilato: {cir} (CSS placeholder)")
                except Exception:
                    pass

            # Strategy 2: label
            if not filled_cir:
                try:
                    cir_field = page.get_by_label("CIR", exact=False)
                    if cir_field.count() > 0:
                        cir_field.first.click()
                        page.wait_for_timeout(300)
                        cir_field.first.fill(cir)
                        filled_cir = True
                        print(f"  CIR compilato (label): {cir}")
                except Exception:
                    pass

            # Strategy 3: JS — find input inside section with "Regionale" and "CIR"
            if not filled_cir:
                filled_cir = page.evaluate("""(val) => {
                    const allEls = document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,strong,b,span,div');
                    for (const el of allEls) {
                        const t = el.textContent || '';
                        if (t.includes('Regionale') && t.includes('CIR')) {
                            let sibling = el.nextElementSibling;
                            for (let i = 0; i < 10 && sibling; i++) {
                                const inp = sibling.querySelector('input') || (sibling.tagName === 'INPUT' ? sibling : null);
                                if (inp) {
                                    const nativeSet = Object.getOwnPropertyDescriptor(
                                        window.HTMLInputElement.prototype, 'value').set;
                                    nativeSet.call(inp, val);
                                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                sibling = sibling.nextElementSibling;
                            }
                        }
                    }
                    // Fallback: parent hierarchy 3 levels
                    const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                    for (const inp of inputs) {
                        let container = inp.parentElement;
                        for (let i = 0; i < 3; i++) {
                            if (!container) break;
                            const text = container.textContent;
                            if (text.includes('CIR') && text.includes('Regionale')) {
                                const nativeSet = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value').set;
                                nativeSet.call(inp, val);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                            container = container.parentElement;
                        }
                    }
                    return false;
                }""", cir)
                if filled_cir:
                    print(f"  CIR compilato (JS): {cir}")

            # Strategy 4: second text input on page (first is CIN)
            if not filled_cir:
                try:
                    text_inputs = page.locator("input[type='text'], input:not([type])")
                    if text_inputs.count() > 1:
                        text_inputs.nth(1).click()
                        page.wait_for_timeout(300)
                        text_inputs.nth(1).fill(cir)
                        filled_cir = True
                        print(f"  CIR compilato (secondo input): {cir}")
                except Exception:
                    pass

            if not filled_cir:
                print(f"  [WARN] Campo CIR non trovato — {cir}")

        step_done(page, "dopo_requisiti")

    try_step(page, "step27_requisiti", do_step27)

    # Advance past requisiti page
    print("Continua (requisiti)")
    click_save_and_verify(page, "requisiti")

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
