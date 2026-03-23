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


def _get_piscina_label():
    """Return the correct CaseVacanza pool label based on piscina_tipo in JSON."""
    dot = PROP.get("dotazioni", {})
    if not isinstance(dot, dict):
        return None
    tipo = dot.get("piscina_tipo", "")
    if not tipo:
        return None
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
    dot = PROP.get("dotazioni", {})
    if not isinstance(dot, dict):
        return []
    servizi = []
    for key, label in DOTAZIONI_MAP.items():
        if label and dot.get(key) is True:
            servizi.append(label)
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi()

SCREENSHOT_DIR = "screenshots"

LETTO_LABEL = {
    "matrimoniale": "Letto matrimoniale (ca. 140 x 200 cm)",
    "singolo": "Letto singolo (ca. 90 x 200 cm)",
    "divano_letto": "Divano letto singolo",
    "divano_letto_matrimoniale": "Divano letto matrimoniale",
    "francese": "Letto Queen-size (ca. 160 x 200 cm)",
    "king": "Letto King-size (ca. 180 x 200 cm)",
    "castello": "Letto a castello",
    "singoli_separati": "Letti singoli separati (2x ca. 90 x 200 cm)",
}

step_counter = 0
step_errors = []


def screenshot(page, name):
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
    path = f"{SCREENSHOT_DIR}/{name}.html"
    try:
        html = page.content()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  HTML salvato: {path}")
    except Exception as e:
        print(f"  [WARN] HTML save fallito ({name}): {e}")


def step_done(page, name):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    page.wait_for_timeout(400)
    screenshot(page, name)
    save_html(page, name)


def dismiss_overlay(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    for selector in [".react-modal-portal-v2", ".ReactModal__Overlay"]:
        try:
            modal = page.locator(selector)
            if modal.count() > 0 and modal.first.is_visible():
                close_btn = modal.locator("button").first
                if close_btn.count() > 0:
                    close_btn.click()
                    page.wait_for_timeout(200)
                    return
        except Exception:
            pass
    try:
        ok_btn = page.locator("button", has_text="Ok")
        if ok_btn.count() > 0 and ok_btn.first.is_visible():
            ok_btn.first.click()
            page.wait_for_timeout(200)
    except Exception:
        pass
    hidden = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll('.ReactModal__Overlay').forEach(el => {
            el.style.pointerEvents = 'none';
            el.style.zIndex = '-1';
            count++;
            el.querySelectorAll('*').forEach(child => {
                child.style.pointerEvents = 'none';
            });
        });
        return count;
    }""")
    if hidden:
        page.wait_for_timeout(200)


def dismiss_cookie(page):
    try:
        btn = page.locator('[data-test="accept-button"]:visible').first
        if btn.is_visible(timeout=2000):
            btn.click()
            page.wait_for_timeout(500)
            print("  Cookie banner chiuso")
    except Exception:
        pass


def try_step(page, step_name, func, critical=False):
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
    dismiss_overlay(page)
    url_before = page.url
    heading_before = page.evaluate("""() => {
        const h = document.querySelector('h1, h2, h3, [data-test*="title"], [class*="heading"]');
        return h ? h.textContent.trim() : '';
    }""")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(200)
    save_exists = page.evaluate("""() => {
        const btn = document.querySelector('[data-test="save-button"]');
        if (!btn) return 'not in DOM';
        const rect = btn.getBoundingClientRect();
        const style = window.getComputedStyle(btn);
        return `in DOM, display=${style.display}, text="${btn.textContent.trim()}"`;
    }""")
    print(f"  [DIAG] save-button: {save_exists}")
    try:
        save_btn = page.locator('[data-test="save-button"]')
        save_btn.scroll_into_view_if_needed(timeout=3000)
        save_btn.click(timeout=10000)
    except Exception:
        dismiss_overlay(page)
        try:
            page.locator('[data-test="save-button"]').click(force=True, timeout=5000)
        except Exception:
            clicked = False
            for btn_text in ["Continua", "Avanti", "Salva e continua", "Save", "Salva"]:
                try:
                    btn = page.get_by_role("button", name=btn_text)
                    if btn.count() > 0:
                        btn.first.scroll_into_view_if_needed()
                        btn.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                page.evaluate("""() => {
                    const selectors = ['[data-test="save-button"]','button[type="submit"]','button.bg-primary-normal-gradient'];
                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && btn.offsetParent !== null) { btn.scrollIntoView(); btn.click(); return sel; }
                    }
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.textContent.toLowerCase().trim();
                        if ((text.includes('continua') || text.includes('salva')) && btn.offsetParent !== null) {
                            btn.scrollIntoView(); btn.click(); return text;
                        }
                    }
                    return false;
                }""")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(200)
    url_after = page.url
    heading_after = page.evaluate("""() => {
        const h = document.querySelector('h1, h2, h3, [data-test*="title"], [class*="heading"]');
        return h ? h.textContent.trim() : '';
    }""")
    advanced = (url_after != url_before) or (heading_after != heading_before)
    if not advanced:
        print(f"  [WARN] Wizard potrebbe non essere avanzato")
    else:
        print(f"  Wizard avanzato: {step_name}")
    step_done(page, f"dopo_{step_name}")
    return advanced


def load_photo_paths():
    foto_json = PROP.get("marketing", {}).get("foto", [])
    if foto_json:
        json_dir = os.path.dirname(os.path.abspath(DATA_FILE))
        paths = []
        for f in foto_json:
            p = f if os.path.isabs(f) else os.path.join(json_dir, f)
            if os.path.isfile(p):
                paths.append(p)
        if paths:
            return paths
    print("  Genero 5 foto placeholder locali (1024x768)...")
    paths = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(5):
        path = os.path.join(tmp_dir, f"photo_{i+1}.jpg")
        _generate_placeholder_jpeg(path, 1024, 768, color_index=i)
        paths.append(path)
    return paths


def _generate_placeholder_jpeg(path, width, height, color_index=0):
    try:
        from PIL import Image
        colors = [(70, 130, 180), (60, 179, 113), (255, 165, 0), (147, 112, 219), (220, 20, 60)]
        color = colors[color_index % len(colors)]
        img = Image.new("RGB", (width, height), color)
        img.save(path, "JPEG", quality=85)
    except ImportError:
        urllib.request.urlretrieve(f"https://picsum.photos/{width}/{height}?random={color_index + 1}", path)


def calculate_base_price():
    prezzo_base = PROP.get("condizioni", {}).get("prezzo_base")
    if prezzo_base:
        return prezzo_base
    listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
    if listino:
        prezzi = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
        return prezzi[len(prezzi) // 2] if prezzi else None
    return PROP.get("condizioni", {}).get("prezzo_notte")


def consolidate_seasonal_prices():
    """Supporta sia dal/al che da/a come chiavi del listino."""
    listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
    if not listino:
        return []
    sog_bassa = PROP.get("condizioni", {}).get("soggiorno_minimo_bassa", {})
    default_min = sog_bassa.get("notti", 5)
    seasons = []
    current = None
    for entry in listino:
        prezzo = entry.get("prezzo_notte")
        if not prezzo:
            continue
        da = entry.get("dal") or entry.get("da", "")
        a = entry.get("al") or entry.get("a", "")
        if current and current["prezzo_notte"] == prezzo:
            current["a"] = a
        else:
            if current:
                seasons.append(current)
            current = {"da": da, "a": a, "prezzo_notte": prezzo, "notti_min": default_min}
    if current:
        seasons.append(current)
    return seasons


def _parse_date_it(date_str, year=2025):
    """Parse date ISO '2025-03-28' o italiano '28-mar'."""
    if not date_str:
        return ""
    if len(date_str) == 10 and date_str[4] == "-":
        return date_str
    mesi = {
        "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
        "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
    }
    parts = date_str.strip().split("-")
    day = int(parts[0])
    month = mesi.get(parts[1].lower(), 1)
    return f"{year}-{month:02d}-{day:02d}"


def fill_field(page, value, labels, css_selectors, field_name):
    if not value:
        return False
    val = str(value)
    filled = False
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
    if not filled:
        keywords = [l.lower() for l in labels]
        filled = page.evaluate("""({val, keywords}) => {
            const fields = document.querySelectorAll('input, textarea, select');
            for (const f of fields) {
                const container = f.closest('label') || f.closest('.form-group') || f.parentElement;
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
    if clicks <= 0:
        return True
    for click_idx in range(clicks):
        btn_info = page.evaluate("""(label) => {
            function findCounterRow(startEl) {
                let el = startEl;
                for (let depth = 0; depth < 10; depth++) {
                    if (!el) return null;
                    const buttons = el.querySelectorAll('button');
                    if (buttons.length >= 2) return {container: el, buttons: buttons};
                    el = el.parentElement;
                }
                return null;
            }
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
            while (walker.nextNode()) {
                const nodeText = walker.currentNode.textContent.trim();
                if (nodeText.toLowerCase() === label.toLowerCase()) {
                    const row = findCounterRow(walker.currentNode.parentElement);
                    if (row) {
                        const addBtn = row.buttons[row.buttons.length - 1];
                        const rect = addBtn.getBoundingClientRect();
                        return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                    }
                }
            }
            const labelLower = label.toLowerCase();
            const candidates = Array.from(document.querySelectorAll('div, span, label, p, h3, h4, li'))
                .filter(el => {
                    const t = el.textContent.trim().toLowerCase();
                    return t.includes(labelLower) && t.length < label.length * 4;
                }).sort((a, b) => a.textContent.length - b.textContent.length);
            for (const el of candidates) {
                const row = findCounterRow(el);
                if (row) {
                    const addBtn = row.buttons[row.buttons.length - 1];
                    const rect = addBtn.getBoundingClientRect();
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            }
            return {found: false};
        }""", label_text)
        if not btn_info.get("found"):
            print(f"  [WARN] {label_text}: + button non trovato")
            return False
        page.mouse.click(btn_info["x"], btn_info["y"])
        page.wait_for_timeout(250)
    print(f"  {label_text}: +{clicks} click completati")
    return True


def login(page):
    print("Login CaseVacanza.it...")
    page.goto("https://my.casevacanza.it", timeout=60_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)
    screenshot(page, "login_page")
    try:
        ok_btn = page.locator("button", has_text="Ok")
        if ok_btn.count() > 0 and ok_btn.first.is_visible():
            ok_btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass
    login_frame = page
    if len(page.frames) > 1:
        for frame in page.frames:
            try:
                if frame.locator("input[type='password']").count() > 0:
                    login_frame = frame
                    break
            except Exception:
                pass
    INPUT_SELECTOR = "#username, #email, input[name='username'], input[type='email'], input[type='text'], input[type='password']"
    try:
        login_frame.wait_for_selector(INPUT_SELECTOR, timeout=30_000)
    except Exception:
        raise RuntimeError("Campi login non trovati")
    page.wait_for_timeout(1000)
    email_field = None
    for sel in ["#username", "#email", "input[name='username']", "input[type='email']", "input[type='text']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            email_field = loc.first
            break
    if email_field is None:
        raise RuntimeError("Campo email non trovato")
    email_field.fill(EMAIL)
    pw_field = None
    for sel in ["#password", "input[name='password']", "input[type='password']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            pw_field = loc.first
            break
    if pw_field is None:
        raise RuntimeError("Campo password non trovato")
    pw_field.fill(PASSWORD)
    screenshot(page, "login_credenziali")
    login_btn = None
    for sel in ["#kc-login", "button[type='submit']", "input[type='submit']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            login_btn = loc.first
            break
    if login_btn is None:
        raise RuntimeError("Bottone login non trovato")
    login_btn.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)
    step_done(page, "dopo_login")
    print("Login effettuato.")


def navigate_to_add_property(page):
    print("Navigazione al wizard...")
    page.goto("https://my.casevacanza.it/listing/add-property", timeout=30_000)
    page.wait_for_load_state("domcontentloaded")
    dismiss_overlay(page)
    page.wait_for_timeout(1500)
    step_done(page, "pagina_iniziale")
    print("Pagina wizard raggiunta.")


def insert_property(page):
    photo_paths = load_photo_paths()
    comp = PROP["composizione"]
    ospiti = comp["max_ospiti"]
    camere = comp["camere"]
    bagni = comp["bagni"]

    def do_step1():
        dismiss_cookie(page)
        page.wait_for_timeout(500)
        single = page.locator('[data-test="single"]')
        if single.count() > 0:
            single.click(force=True)
        else:
            page.get_by_text("Proprietà a unità singola", exact=False).click()
        page.wait_for_load_state("domcontentloaded")
        step_done(page, "tipo_proprietà")

    try_step(page, "step1_unità_singola", do_step1, critical=True)

    tipo = PROP["identificativi"]["tipo_struttura"]

    def do_step2():
        select = page.locator("select")
        if select.count() > 0:
            try:
                select.first.select_option(label=tipo)
            except Exception:
                options = select.first.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))")
                for opt in options:
                    if tipo.lower() in opt["text"].lower():
                        select.first.select_option(value=opt["value"])
                        break
        else:
            page.get_by_text(tipo).click()
        step_done(page, "tipo_struttura_selezionato")

    try_step(page, "step2_tipo_struttura", do_step2, critical=True)

    def do_step3():
        page.get_by_text("Intero alloggio").click()
        step_done(page, "intero_alloggio")

    try_step(page, "step3_intero_alloggio", do_step3)
    click_save_and_verify(page, "tipo_proprietà")

    def do_step5():
        page.get_by_text("Inseriscilo manualmente").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(400)
        ident = PROP["identificativi"]
        addr_parts = ident["indirizzo"].rsplit(" ", 1)
        via = addr_parts[0] if len(addr_parts) > 1 else ident["indirizzo"]
        civico = addr_parts[1] if len(addr_parts) > 1 else ""
        page.locator('[data-test="stateOrProvince"]').fill(ident["regione"])
        page.wait_for_timeout(200)
        page.locator('[data-test="city"]').fill(ident["comune"])
        page.wait_for_timeout(200)
        page.locator('[data-test="street"]').fill(via)
        page.wait_for_timeout(200)
        page.locator('[data-test="houseNumberOrName"]').fill(civico)
        page.wait_for_timeout(200)
        page.locator('[data-test="postalCode"]').fill(ident["cap"])
        page.wait_for_timeout(200)
        step_done(page, "indirizzo_compilato")

    try_step(page, "step5_indirizzo", do_step5)
    click_save_and_verify(page, "indirizzo")

    def do_step7():
        page.locator('[data-test="save-button"]').click()
        page.wait_for_load_state("domcontentloaded")
        step_done(page, "dopo_mappa")

    try_step(page, "step7_mappa", do_step7)

    def do_step8():
        screenshot(page, "step8_BEFORE_clicks")
        dismiss_cookie(page)
        page.wait_for_timeout(500)
        add = page.locator('[data-test="counter-add-btn"]')
        guest_add = page.locator('[data-test="guest-count"] [data-test="counter-add-btn"]')
        for _ in range(max(0, ospiti - 1)):
            guest_add.click()
            page.wait_for_timeout(300)
        print(f"  Ospiti → {ospiti}")
        for _ in range(max(0, camere - 1)):
            add.nth(1).click()
            page.wait_for_timeout(300)
        print(f"  Camere → {camere}")
        for _ in range(max(0, bagni)):
            add.nth(3).click()
            page.wait_for_timeout(300)
        print(f"  Bagni → {bagni}")
        add.nth(4).click()
        page.wait_for_timeout(300)
        print("  Cucina → 1")
        try:
            bambini_cb = page.locator('[data-test="children-allowed"]')
            if bambini_cb.count() > 0 and not bambini_cb.is_checked():
                bambini_cb.check()
        except Exception:
            pass
        screenshot(page, "step8_AFTER_room_clicks")
        step_done(page, "ospiti_camere")

    try_step(page, "step8_ospiti_camere", do_step8)
    click_save_and_verify(page, "ospiti")

    def do_step10():
        dismiss_cookie(page)
        page.wait_for_timeout(500)
        letti = comp.get("letti", [])
        if not letti:
            print("  Nessun dato letti nel JSON, skip")
            step_done(page, "letti_skip")
            return
        screenshot(page, "step10_BEFORE_letti")
        LETTO_TESTO = {
            "matrimoniale": "Letto matrimoniale",
            "king": "Letto King-size",
            "queen": "Letto Queen-size",
            "singolo": "Letto singolo",
            "divano_letto": "Divano letto singolo",
            "divano_letto_matrimoniale": "Divano letto matrimoniale",
            "letto_a_castello": "Letto a castello",
        }

        def click_letto(label_parziale, quantita, camera_idx):
            if camera_idx > 0:
                try:
                    expand_btns = page.locator('[data-test="expand-room"]')
                    if expand_btns.count() > 0:
                        expand_btns.first.click()
                        page.wait_for_timeout(800)
                except Exception:
                    pass
            for _ in range(quantita):
                coords = page.evaluate("""(label) => {
                    const btns = document.querySelectorAll('[data-test="counter-add-btn"]');
                    for (const btn of btns) {
                        const gp = btn.parentElement && btn.parentElement.parentElement;
                        if (gp && gp.textContent.includes(label)) {
                            const r = btn.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) return {x: r.left + r.width/2, y: r.top + r.height/2};
                        }
                    }
                    return null;
                }""", label_parziale)
                if coords:
                    page.mouse.click(coords['x'], coords['y'])
                    page.wait_for_timeout(400)
                else:
                    print(f"    [WARN] '{label_parziale}' non trovato")
                    return
            print(f"    + {quantita}x {label_parziale}")

        for cam_idx, letto_entry in enumerate(letti[:camere]):
            tipo = letto_entry.get("tipo", "matrimoniale")
            qty = int(letto_entry.get("quantita", 1))
            label = LETTO_TESTO.get(tipo, tipo)
            click_letto(label, qty, cam_idx)
        for letto_entry in letti[camere:]:
            tipo = letto_entry.get("tipo", "")
            qty = int(letto_entry.get("quantita", 1))
            label = LETTO_TESTO.get(tipo, tipo)
            if tipo:
                click_letto(label, qty, 0)
        screenshot(page, "step10_AFTER_letti")
        step_done(page, "letti_configurati")

    try_step(page, "step10_letti", do_step10)
    click_save_and_verify(page, "letti")

    def do_step12():
        if not photo_paths:
            step_done(page, "foto_skip")
            return
        uploaded = False
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                btn = page.get_by_text("Carica foto")
                if btn.count() > 0:
                    btn.first.click()
            fc_info.value.set_files(photo_paths)
            uploaded = True
            print(f"  Upload {len(photo_paths)} foto via file chooser")
        except Exception as e:
            print(f"  File chooser fallito: {e}")
        if not uploaded:
            try:
                fi = page.locator("input[type='file']")
                if fi.count() > 0:
                    fi.set_input_files(photo_paths)
                    uploaded = True
            except Exception:
                pass
        if uploaded:
            page.wait_for_timeout(6000)
        step_done(page, "foto_caricate" if uploaded else "foto_skip")

    try_step(page, "step12_foto", do_step12)
    click_save_and_verify(page, "foto")

    def do_step14():
        try:
            tab = page.get_by_text("Tutti", exact=True)
            if tab.count() > 0:
                tab.first.click()
                page.wait_for_timeout(800)
        except Exception:
            pass
        for servizio in SERVIZI:
            selected = False
            for strategy in [
                lambda s: page.get_by_role("checkbox", name=s, exact=True),
                lambda s: page.get_by_role("checkbox", name=s, exact=False),
                lambda s: page.get_by_label(s, exact=True),
            ]:
                try:
                    cb = strategy(servizio)
                    if cb.count() > 0:
                        cb.first.check()
                        page.wait_for_timeout(200)
                        print(f"  [OK] {servizio}")
                        selected = True
                        break
                except Exception:
                    continue
            if not selected:
                try:
                    result = page.evaluate("""(label) => {
                        const checkboxes = document.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
                        for (const cb of checkboxes) {
                            const container = cb.closest('label') || cb.parentElement?.parentElement;
                            if ((container?.textContent || '').includes(label)) {
                                cb.click();
                                return true;
                            }
                        }
                        return false;
                    }""", servizio)
                    if result:
                        selected = True
                        print(f"  [OK] {servizio} (JS)")
                except Exception:
                    pass
            if not selected:
                print(f"  [MISS] {servizio}")
        step_done(page, "servizi_selezionati")

    try_step(page, "step14_servizi", do_step14)
    click_save_and_verify(page, "servizi")

    def do_step16():
        page.get_by_text("Li scrivo io").click()
        page.wait_for_load_state("domcontentloaded")
        step_done(page, "li_scrivo_io")

    try_step(page, "step16_li_scrivo_io", do_step16)

    def do_step17():
        titolo = PROP.get("marketing", {}).get("titolo") or PROP["identificativi"]["nome_struttura"]
        descrizione = PROP["marketing"]["descrizione_lunga"]
        titolo_field = page.get_by_label("Titolo")
        if titolo_field.count() > 0:
            titolo_field.fill(titolo)
        else:
            page.locator("input[name*='titolo'], input[name*='title'], input[placeholder*='Titolo']").first.fill(titolo)
        page.wait_for_timeout(200)
        desc_field = page.get_by_label("Descrizione")
        if desc_field.count() > 0:
            desc_field.fill(descrizione)
        else:
            page.locator("textarea").first.fill(descrizione)
        page.wait_for_timeout(200)
        step_done(page, "titolo_descrizione")

    try_step(page, "step17_titolo_desc", do_step17)
    click_save_and_verify(page, "titolo_desc")

    def do_step19():
        base_prezzo = calculate_base_price()
        cond = PROP["condizioni"]
        if base_prezzo is not None:
            prezzo_str = str(base_prezzo)
            filled = False
            try:
                page.get_by_text("Impostiamo il prezzo", exact=False).wait_for(timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(800)
            for ph in ["Prezzo per notte", "€ Prezzo per notte", "Prezzo", "notte"]:
                try:
                    f = page.get_by_placeholder(ph, exact=False)
                    if f.count() > 0:
                        f.first.scroll_into_view_if_needed()
                        f.first.click()
                        page.wait_for_timeout(200)
                        f.first.fill(prezzo_str)
                        filled = True
                        print(f"  Prezzo: {prezzo_str} EUR/notte")
                        break
                except Exception:
                    continue
            if not filled:
                try:
                    visible_inputs = page.locator("input:visible").all()
                    for inp in visible_inputs:
                        inp_type = inp.get_attribute("type") or "text"
                        if inp_type in ("text", "number", "tel", ""):
                            inp.fill(prezzo_str)
                            filled = True
                            print(f"  Prezzo: {prezzo_str} EUR/notte (visible input)")
                            break
                except Exception:
                    pass
            if not filled:
                print(f"  [WARN] Campo prezzo non trovato")

        def add_extra_cost(button_label, amount_text):
            if not amount_text:
                return
            match = re.search(r'(\d+)', str(amount_text))
            if not match:
                return
            amount = match.group(1)
            try:
                btn = page.get_by_text(button_label, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
                    for ph in ["Prezzo", "Costo", "Importo", "EUR", "€", "0"]:
                        try:
                            f = page.get_by_placeholder(ph, exact=False)
                            if f.count() > 0:
                                f.last.fill(amount)
                                break
                        except Exception:
                            continue
                    for confirm_text in ["Salva", "Conferma", "Aggiungi", "OK", "Ok"]:
                        try:
                            confirm = page.get_by_role("button", name=confirm_text)
                            if confirm.count() > 0 and confirm.last.is_visible():
                                confirm.last.click()
                                page.wait_for_timeout(1500)
                                print(f"  {button_label}: €{amount} aggiunto")
                                break
                        except Exception:
                            continue
                    dismiss_overlay(page)
            except Exception as e:
                print(f"  [WARN] Extra cost '{button_label}': {e}")

        add_extra_cost("Pulizia", cond.get("pulizia_finale"))
        add_extra_cost("Asciugamani", cond.get("asciugamani"))
        add_extra_cost("Biancheria da letto", cond.get("lenzuola"))

        try:
            modifica_btn = page.get_by_text("Modifica", exact=False)
            if modifica_btn.count() > 0 and modifica_btn.first.is_visible():
                modifica_btn.first.click()
                page.wait_for_timeout(1500)
                sog_bassa = cond.get("soggiorno_minimo_bassa", {})
                notti = str(sog_bassa.get("notti", ""))
                if notti:
                    fill_field(page, notti, ["Soggiorno minimo", "Notti minime", "Minimo"],
                               ["input[name*='soggiorno']", "select[name*='min']"], "Soggiorno minimo")
                check_in_raw = cond.get("check_in", "")
                if check_in_raw:
                    fill_field(page, check_in_raw, ["Check-in", "Check in"],
                               ["select[name*='check_in']", "select[name*='checkin']"], "Check-in")
                check_out_raw = cond.get("check_out", "")
                if check_out_raw:
                    fill_field(page, check_out_raw, ["Check-out", "Check out"],
                               ["select[name*='check_out']", "select[name*='checkout']"], "Check-out")
                for save_text in ["Salva", "Conferma", "Save", "OK"]:
                    try:
                        save_btn = page.get_by_role("button", name=save_text)
                        if save_btn.count() > 0 and save_btn.last.is_visible():
                            save_btn.last.click()
                            page.wait_for_timeout(800)
                            break
                    except Exception:
                        continue
                dismiss_overlay(page)
        except Exception as e:
            print(f"  [WARN] Impostazioni predefinite: {e}")

        step_done(page, "prezzo_e_condizioni")

    try_step(page, "step19_prezzo", do_step19)
    click_save_and_verify(page, "prezzo")

    # --- Step 20b: Aggiungi prezzi stagionali nel wizard ---
    def do_step20b():
        listino = PROP.get("condizioni", {}).get("listino_prezzi") or []
        if not listino:
            print("  Nessun listino prezzi — skip stagioni wizard")
            return

        # Consolida stagioni
        seasons = consolidate_seasonal_prices()
        print(f"  Stagioni da inserire nel wizard: {len(seasons)}")

        for i, season in enumerate(seasons):
            da = season["da"]
            a = season["a"]
            prezzo = str(season["prezzo_notte"])
            print(f"  Stagione {i+1}: {da} → {a} = €{prezzo}")

            # Clicca Aggiungi prezzo stagionale
            clicked = False
            for btn_text in ["Aggiungi prezzo stagionale", "Aggiungi stagione", "Aggiungi prezzo"]:
                try:
                    btn = page.get_by_text(btn_text, exact=False)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        page.wait_for_timeout(1000)
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                print(f"  [WARN] Bottone aggiungi stagione non trovato")
                continue

            # Compila date con date picker
            page.wait_for_timeout(500)

            # Data inizio — cerca dropdown/input Da
            try:
                da_input = page.locator("[data-test='season-start-date']")
                if da_input.count() == 0:
                    da_input = page.locator("input").filter(has_text="Da").first
                if da_input.count() == 0:
                    # Prendi il primo date input visibile
                    date_inputs = page.locator("input[type='date']")
                    if date_inputs.count() > 0:
                        date_inputs.first.fill(da)
                        print(f"    Data inizio: {da}")
            except Exception as e:
                print(f"    [WARN] Data inizio: {e}")

            # Data fine
            try:
                date_inputs = page.locator("input[type='date']")
                if date_inputs.count() > 1:
                    date_inputs.last.fill(a)
                    print(f"    Data fine: {a}")
            except Exception as e:
                print(f"    [WARN] Data fine: {e}")

            # Prezzo per notte
            try:
                for ph in ["Prezzo per notte", "Prezzo", "notte"]:
                    f = page.get_by_placeholder(ph, exact=False)
                    if f.count() > 0:
                        f.last.fill(prezzo)
                        print(f"    Prezzo: €{prezzo}")
                        break
                else:
                    # Fallback: input number visibile
                    num_inputs = page.locator("input[type='number']")
                    if num_inputs.count() > 0:
                        num_inputs.last.fill(prezzo)
                        print(f"    Prezzo: €{prezzo} (number input)")
            except Exception as e:
                print(f"    [WARN] Prezzo stagione: {e}")

            # Salva stagione
            page.wait_for_timeout(300)
            for save_text in ["Salva", "Conferma", "Aggiungi", "OK"]:
                try:
                    save_btn = page.get_by_role("button", name=save_text)
                    if save_btn.count() > 0 and save_btn.last.is_visible():
                        save_btn.last.click()
                        page.wait_for_timeout(1000)
                        print(f"    Stagione {i+1} salvata")
                        break
                except Exception:
                    continue

        step_done(page, "stagioni_wizard")

    try_step(page, "step20b_stagioni", do_step20b)

    def do_step26():
        ical_url = PROP.get("condizioni", {}).get("ical_url")
        if ical_url:
            for radio_text in ["Si, utilizzo altre piattaforme", "Sì, utilizzo altre piattaforme", "utilizzo altre piattaforme"]:
                try:
                    radio = page.get_by_text(radio_text, exact=False)
                    if radio.count() > 0:
                        radio.first.click()
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    continue
            for sel in ["input[type='url']", "input[name*='ical']", "input[type='text']"]:
                try:
                    f = page.locator(sel)
                    if f.count() > 0:
                        f.last.fill(ical_url)
                        break
                except Exception:
                    continue
        else:
            try:
                radio = page.get_by_text("No, gestisco solo le prenotazioni qui", exact=False)
                if radio.count() > 0:
                    radio.first.click()
                    page.wait_for_timeout(400)
            except Exception:
                pass
        step_done(page, "dopo_calendario")

    try_step(page, "step26_calendario", do_step26)
    click_save_and_verify(page, "calendario")

    def do_step27():
        cin = PROP.get("identificativi", {}).get("cin")
        cir = PROP.get("identificativi", {}).get("cir")
        if not cin and not cir:
            step_done(page, "dopo_requisiti_skip")
            return
        if cin:
            for ph in ["Inserisci il numero CIN", "CIN", "numero CIN"]:
                try:
                    f = page.get_by_placeholder(ph, exact=False)
                    if f.count() > 0:
                        f.first.fill(cin)
                        print(f"  CIN: {cin}")
                        break
                except Exception:
                    continue
        if cir:
            for ph in ["Inserisci il numero CIR", "CIR", "numero CIR"]:
                try:
                    f = page.get_by_placeholder(ph, exact=False)
                    if f.count() > 0:
                        f.first.fill(cir)
                        print(f"  CIR: {cir}")
                        break
                except Exception:
                    continue
        step_done(page, "dopo_requisiti")

    try_step(page, "step27_requisiti", do_step27)
    click_save_and_verify(page, "requisiti")

    print("\nStep 28: Pagina finale")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(400)
    step_done(page, "pagina_finale")
    print("Flusso completato!")


def add_seasonal_prices(page):
    seasons = consolidate_seasonal_prices()
    if not seasons:
        print("\nNessun listino prezzi — skip tariffe stagionali")
        return
    print(f"\nTARIFFE STAGIONALI: {len(seasons)} stagioni da inserire")
    for s in seasons:
        print(f"  {s['da']} → {s['a']}: €{s['prezzo_notte']}/notte")
    page.goto("https://my.casevacanza.it/listing/properties", timeout=30_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    step_done(page, "lista_proprietà")
    nome = PROP["identificativi"]["nome_struttura"]
    found = False
    try:
        link = page.get_by_text(nome, exact=False)
        if link.count() > 0:
            link.first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(800)
            found = True
    except Exception:
        pass
    if not found:
        print("  Proprietà non trovata — skip tariffe stagionali")
        step_done(page, "proprietà_non_trovata")
        return
    for tab_text in ["Tariffe e disponibilità", "Tariffe", "Prezzi"]:
        try:
            tab = page.get_by_text(tab_text, exact=False)
            if tab.count() > 0:
                tab.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(800)
                break
        except Exception:
            continue
    for i, season in enumerate(seasons):
        da_date = _parse_date_it(season["da"])
        a_date = _parse_date_it(season["a"])
        print(f"  Stagione {i+1}: {da_date} → {a_date} = €{season['prezzo_notte']}")
        for btn_text in ["Aggiungi prezzo stagionale", "Aggiungi stagione", "Aggiungi prezzo"]:
            try:
                btn = page.get_by_text(btn_text, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(800)
                    break
            except Exception:
                continue
        fill_field(page, da_date, ["Da", "Dal", "Data inizio"], [], f"Data inizio {i+1}")
        fill_field(page, a_date, ["A", "Al", "Data fine"], [], f"Data fine {i+1}")
        fill_field(page, str(season["prezzo_notte"]), ["Prezzo", "Prezzo a notte"], ["input[type='number']"], f"Prezzo {i+1}")
        for save_text in ["Salva", "Conferma", "Aggiungi", "OK"]:
            try:
                save_btn = page.get_by_role("button", name=save_text)
                if save_btn.count() > 0:
                    save_btn.first.click()
                    page.wait_for_timeout(800)
                    break
            except Exception:
                continue
    print(f"Tariffe stagionali completate")


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
            if PROP.get("condizioni", {}).get("listino_prezzi"):
                try:
                    add_seasonal_prices(page)
                except Exception as e:
                    print(f"\n[ERRORE] Tariffe stagionali: {e}")
                    step_errors.append(("tariffe_stagionali", str(e)))
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            if step_errors:
                print(f"\nERRORI: {len(step_errors)} step falliti:")
                for name, err in step_errors:
                    print(f"  - {name}: {err}")
            else:
                print("\nTutti gli step completati con successo!")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
