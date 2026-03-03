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

DESCRIPTION = PROP["marketing"]["descrizione_lunga"]

# ---------------------------------------------------------------------------
# Mappatura dotazioni JSON → label esatte CaseVacanza.it
# REGOLA: spunta SOLO le dotazioni con valore true nel JSON.
#         Se false o assente, NON spuntare. Zero eccezioni.
#
# Le label devono corrispondere ESATTAMENTE a quelle sulla pagina
# "Servizi popolari" di CaseVacanza.it. Alcune hanno specificazioni
# tra parentesi (es. "Lavatrice (privata)", "Piscina (in comune)").
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

step_counter = 0


def screenshot(page, name):
    """Save a debug screenshot with incrementing step number."""
    global step_counter
    step_counter += 1
    path = f"{SCREENSHOT_DIR}/step{step_counter:02d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def save_html(page, name):
    """Save full HTML of current page for debugging."""
    path = f"{SCREENSHOT_DIR}/{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  HTML salvato: {path}")


def wait(page, ms=5000):
    """Wait between steps — CaseVacanza is slow."""
    page.wait_for_timeout(ms)


def click_save(page):
    """Click the save/continue button (data-test='save-button') and wait."""
    page.locator('[data-test="save-button"]').click()
    wait(page)


def load_photo_paths():
    """Load photo paths from JSON (marketing.foto) or download placeholders."""
    foto_json = PROP.get("marketing", {}).get("foto", [])
    if foto_json:
        # Resolve paths relative to the JSON file location
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

    # Fallback: placeholder photos
    paths = []
    tmp_dir = tempfile.mkdtemp()
    for i in range(5):
        path = os.path.join(tmp_dir, f"photo_{i+1}.jpg")
        urllib.request.urlretrieve(
            f"https://picsum.photos/800/600?random={i+1}", path
        )
        paths.append(path)
        print(f"  Foto placeholder scaricata: {path}")
    return paths


def _dismiss_cookie_popup(page):
    """Chiudi popup cookie/GDPR PRIMA del login — necessario perché copre i campi."""
    for btn_text in ["Ok", "Accetta", "Accept", "Accetto", "Ho capito",
                     "Accetta tutti", "Accept all", "Agree", "OK"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Popup cookie chiuso (bottone '{btn_text}')")
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass
    # Fallback: cerca qualsiasi bottone "Ok" (case-insensitive)
    try:
        btn = page.locator("button", has_text="Ok")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            print("  Popup cookie chiuso (fallback 'Ok')")
            page.wait_for_timeout(1000)
            return
    except Exception:
        pass
    # ReactModal overlay
    try:
        modal = page.locator(".ReactModal__Overlay")
        if modal.count() > 0 and modal.first.is_visible():
            close = modal.locator("button").first
            if close.count() > 0:
                close.click()
            else:
                modal.click(position={"x": 10, "y": 10})
            print("  ReactModal chiuso")
            page.wait_for_timeout(1000)
            return
    except Exception:
        pass
    print("  Nessun popup cookie trovato")


def login(page):
    """Login su CaseVacanza.it — prova diversi selettori per email e password."""
    print("Login CaseVacanza.it...")
    page.goto("https://my.casevacanza.it", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_page")
    save_html(page, "login_page")
    print(f"  URL login: {page.url}")

    # IMPORTANTE: chiudere popup cookie PRIMA di cercare i campi login
    # (il popup copre i campi e wait_for_selector fallisce con timeout)
    _dismiss_cookie_popup(page)

    # Controlla se il login form è dentro un iframe (comune con Keycloak SSO)
    iframes = page.frames
    login_frame = page
    if len(iframes) > 1:
        for frame in iframes:
            try:
                if frame.locator("input[type='password']").count() > 0:
                    login_frame = frame
                    print(f"  Login form trovato in iframe: {frame.url}")
                    break
            except Exception:
                pass

    # Aspetta che compaia un campo input
    INPUT_SELECTOR = (
        "#username, #email, input[name='username'], input[name='email'], "
        "input[type='email'], input[type='text'], input[type='password']"
    )
    try:
        login_frame.wait_for_selector(INPUT_SELECTOR, timeout=30_000)
    except Exception:
        # Fallback: prova con state="attached" (il campo c'è ma potrebbe non essere "visible")
        print("  [WARN] Campi non visibili, provo state=attached...")
        screenshot(page, "login_fields_not_visible")
        save_html(page, "login_fields_not_visible")
        _dismiss_cookie_popup(page)  # riprova a chiudere popup
        try:
            login_frame.wait_for_selector(INPUT_SELECTOR, timeout=15_000, state="attached")
        except Exception:
            screenshot(page, "login_timeout_final")
            save_html(page, "login_timeout_final")
            raise RuntimeError("Campi login non trovati dopo aver chiuso popup e provato iframe")
    wait(page, 2000)

    # Trova il campo email/username (usa login_frame per supporto iframe)
    email_selectors = [
        "#username",
        "#email",
        "input[name='username']",
        "input[name='email']",
        "input[name='loginname']",
        "input[type='email']",
        "input[type='text']",
    ]
    email_field = None
    for sel in email_selectors:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            email_field = loc.first
            print(f"  Campo email trovato: {sel}")
            break
    if email_field is None:
        for lbl in ["Email", "Username", "E-mail", "Indirizzo email"]:
            loc = login_frame.get_by_label(lbl)
            if loc.count() > 0:
                email_field = loc.first
                print(f"  Campo email trovato (label): {lbl}")
                break
    if email_field is None:
        screenshot(page, "login_no_email_field")
        save_html(page, "login_no_email_field")
        raise RuntimeError("Campo email/username non trovato nella pagina di login")

    email_field.fill(EMAIL)
    wait(page, 1000)

    # Trova il campo password
    pw_selectors = [
        "#password",
        "input[name='password']",
        "input[type='password']",
    ]
    pw_field = None
    for sel in pw_selectors:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            pw_field = loc.first
            print(f"  Campo password trovato: {sel}")
            break
    if pw_field is None:
        screenshot(page, "login_no_pw_field")
        raise RuntimeError("Campo password non trovato nella pagina di login")

    pw_field.fill(PASSWORD)
    wait(page, 1000)
    screenshot(page, "login_credenziali")

    # Trova il bottone di login
    login_selectors = [
        "#kc-login",
        "button[type='submit']",
        "input[type='submit']",
    ]
    login_btn = None
    for sel in login_selectors:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            login_btn = loc.first
            print(f"  Bottone login trovato: {sel}")
            break
    if login_btn is None:
        for lbl in ["Accedi", "Login", "Sign in", "Entra"]:
            loc = login_frame.get_by_text(lbl, exact=True)
            if loc.count() > 0:
                login_btn = loc.first
                print(f"  Bottone login trovato (text): {lbl}")
                break
    if login_btn is None:
        raise RuntimeError("Bottone login non trovato")

    login_btn.click()
    wait(page, 8000)
    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")
    print("Login effettuato.")


def dismiss_popups(page):
    """Close cookies popup and ReactModal overlay."""
    wait(page, 3000)

    ok_btn = page.locator("button", has_text="Ok")
    if ok_btn.count() > 0:
        ok_btn.first.click()
        print("Popup cookies chiuso.")
        wait(page, 1000)

    modal_overlay = page.locator(".ReactModal__Overlay")
    if modal_overlay.count() > 0:
        close_btn = modal_overlay.locator("button").first
        if close_btn.count() > 0:
            close_btn.click()
        else:
            modal_overlay.click(position={"x": 10, "y": 10})
        wait(page, 1000)
        print("ReactModal chiuso.")


def navigate_to_add_property(page):
    """Navigate: Proprietà → Aggiungi una proprietà."""
    page.locator("a", has_text="Proprietà").first.click()
    wait(page)
    print("Navigato a Proprietà.")

    page.get_by_text("Aggiungi una proprietà").click()
    wait(page)
    print("Navigato a Aggiungi una proprietà.")


def try_step(page, step_name, func):
    """Execute a step wrapped in try/except. Always screenshot."""
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")


def insert_property(page):
    """Complete the full property insertion wizard."""
    photo_paths = load_photo_paths()

    # --- Step 1: Click "Proprietà a unità singola" ---
    print("Step 1: Proprietà a unità singola")
    page.get_by_text("Proprietà a unità singola").click()
    wait(page)
    screenshot(page, "tipo_proprietà")

    # --- Step 2: Seleziona tipo struttura dal dropdown ---
    tipo = PROP["identificativi"]["tipo_struttura"]
    print(f"Step 2: Seleziona {tipo}")
    select = page.locator("select")
    if select.count() > 0:
        select.first.select_option(label=tipo)
    else:
        page.get_by_text(tipo).click()
    wait(page)
    screenshot(page, "appartamento_selezionato")

    # --- Step 3: Click "Intero alloggio" ---
    print("Step 3: Intero alloggio")
    page.get_by_text("Intero alloggio").click()
    wait(page)
    screenshot(page, "intero_alloggio")

    # --- Step 4: Continua (tipo proprietà) ---
    print("Step 4: Continua (tipo proprietà)")
    click_save(page)
    screenshot(page, "dopo_tipo")

    # --- Step 5: Compila indirizzo (modalità manuale) ---
    print("Step 5: Indirizzo")
    page.get_by_text("Inseriscilo manualmente").click()
    wait(page, 3000)
    screenshot(page, "campi_manuali")

    ident = PROP["identificativi"]
    # Separa via e numero civico dall'indirizzo (es. "Via Dettori 20")
    addr_parts = ident["indirizzo"].rsplit(" ", 1)
    via = addr_parts[0] if len(addr_parts) > 1 else ident["indirizzo"]
    civico = addr_parts[1] if len(addr_parts) > 1 else ""

    page.locator('[data-test="stateOrProvince"]').fill(ident["regione"])
    wait(page, 1000)
    page.locator('[data-test="city"]').fill(ident["comune"])
    wait(page, 1000)
    page.locator('[data-test="street"]').fill(via)
    wait(page, 1000)
    page.locator('[data-test="houseNumberOrName"]').fill(civico)
    wait(page, 1000)
    page.locator('[data-test="postalCode"]').fill(ident["cap"])
    wait(page, 1000)
    screenshot(page, "indirizzo_compilato")

    # --- Step 6: Continua (indirizzo) ---
    print("Step 6: Continua (indirizzo)")
    click_save(page)
    screenshot(page, "dopo_indirizzo")

    # --- Step 7: Mappa — Imposta coordinate GPS se presenti nel JSON ---
    print("Step 7: Mappa")

    def do_step7():
        screenshot(page, "mappa_pagina")
        save_html(page, "step7_mappa")
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

        click_save(page)
        screenshot(page, "dopo_mappa")

    try_step(page, "step7_mappa", do_step7)

    # --- Step 8: Ospiti e camere (data-test counters) ---
    comp = PROP["composizione"]
    print(f"Step 8: Ospiti e camere ({comp['max_ospiti']} ospiti, "
          f"{comp['camere']} cam, {comp['bagni']} bagni)")
    # guest-count default=1, click (max_ospiti - 1) volte
    for _ in range(comp["max_ospiti"] - 1):
        page.locator('[data-test="guest-count"] [data-test="counter-add-btn"]').click()
        page.wait_for_timeout(500)
    # bedroom default=1, click (camere - 1) volte
    for _ in range(comp["camere"] - 1):
        page.locator('[data-test="bedroom"] [data-test="counter-add-btn"]').click()
        page.wait_for_timeout(500)
    # bath_room default=0, click bagni volte
    for _ in range(comp["bagni"]):
        page.locator('[data-test="bath_room"] [data-test="counter-add-btn"]').click()
        page.wait_for_timeout(500)
    wait(page)
    screenshot(page, "ospiti_camere")

    # --- Step 9: Continua (ospiti) ---
    print("Step 9: Continua (ospiti)")
    click_save(page)
    screenshot(page, "dopo_ospiti")

    # --- Step 10: Configura letti (dal JSON composizione.letti) ---
    print("Step 10: Configura letti")

    # Mappa tipo letto JSON → indice bottone CaseVacanza
    # CaseVacanza ordina: 0=Divano letto, 1=Matrimoniale, 2=Francese, 3=Singolo
    LETTO_INDEX = {
        "matrimoniale": 1,
        "francese": 2,
        "singolo": 3,
        "divano_letto": 0,
    }

    def do_step10():
        save_html(page, "step10_letti_before")
        add_btns = page.locator('[data-test="counter-add-btn"]')
        count = add_btns.count()
        print(f"  Trovati {count} counter-add-btn")

        letti = comp.get("letti", [])
        if not letti:
            print("  ATTENZIONE: nessun dato letti nel JSON, skip")
        for letto in letti:
            tipo = letto["tipo"]
            quantita = letto["quantita"]
            idx = LETTO_INDEX.get(tipo)
            if idx is None:
                print(f"  Tipo letto sconosciuto: {tipo}, skip")
                continue
            if idx >= count:
                print(f"  Indice {idx} fuori range ({count} bottoni), skip {tipo}")
                continue
            for _ in range(quantita):
                add_btns.nth(idx).click()
                page.wait_for_timeout(500)
            print(f"  {tipo}: +{quantita} (indice {idx})")

        wait(page)
        screenshot(page, "letti_configurati")
        save_html(page, "step10_letti_after")

    try_step(page, "step10_letti", do_step10)

    # --- Step 11: Continua (letti) ---
    print("Step 11: Continua (letti)")

    def do_step11():
        click_save(page)
        screenshot(page, "dopo_letti")

    try_step(page, "step11_continua_letti", do_step11)

    # --- Step 12: Upload 5 foto ---
    print("Step 12: Upload foto")

    def do_step12():
        screenshot(page, "foto_pagina")
        save_html(page, "step12_foto")

        uploaded = False

        # Strategy 1: standard input[type="file"]
        try:
            fi = page.locator("input[type='file']")
            if fi.count() > 0:
                fi.set_input_files(photo_paths, timeout=5000)
                uploaded = True
                print("  Upload via input[type='file']")
        except Exception as e:
            print(f"  Strategy 1 fallita: {e}")

        # Strategy 2: input[accept*="image"]
        if not uploaded:
            try:
                fi = page.locator("input[accept*='image']")
                if fi.count() > 0:
                    fi.set_input_files(photo_paths, timeout=5000)
                    uploaded = True
                    print("  Upload via input[accept*='image']")
            except Exception as e:
                print(f"  Strategy 2 fallita: {e}")

        # Strategy 3: force display on hidden input
        if not uploaded:
            try:
                fi = page.locator("input[type='file']")
                if fi.count() > 0:
                    fi.evaluate("el => el.style.display = 'block'")
                    fi.set_input_files(photo_paths, timeout=5000)
                    uploaded = True
                    print("  Upload via forced display input[type='file']")
            except Exception as e:
                print(f"  Strategy 3 fallita: {e}")

        if uploaded:
            wait(page, 10_000)
            screenshot(page, "foto_caricate")
        else:
            print("  SKIP foto: nessuna strategia ha funzionato")
            screenshot(page, "foto_skip")

    try_step(page, "step12_foto", do_step12)

    # --- Step 13: Continua (foto) ---
    print("Step 13: Continua (foto)")

    def do_step13():
        click_save(page)
        screenshot(page, "dopo_foto")

    try_step(page, "step13_continua_foto", do_step13)

    # --- Step 14: Seleziona servizi (SOLO quelli true nel JSON) ---
    print("Step 14: Servizi")
    print(f"  Servizi da selezionare dal JSON: {SERVIZI}")

    def do_step14():
        screenshot(page, "servizi_pagina")
        save_html(page, "step14_servizi")

        # 1) Clicca la tab "Tutti" per mostrare TUTTI i servizi
        #    (Piano cottura, Frigorifero, Microonde, Asciugacapelli, ecc.
        #     non sono nella tab "Servizi popolari")
        for tab_label in ["Tutti", "tutti", "All", "all"]:
            try:
                tab = page.get_by_role("tab", name=tab_label)
                if tab.count() > 0:
                    tab.first.click()
                    wait(page, 2000)
                    print(f"  Tab '{tab_label}' cliccata (role=tab)")
                    screenshot(page, "servizi_tab_tutti")
                    break
            except Exception:
                pass
        else:
            # Fallback: clicca link/button con testo "Tutti"
            try:
                tab = page.get_by_text("Tutti", exact=True)
                if tab.count() > 0:
                    tab.first.click()
                    wait(page, 2000)
                    print("  Tab 'Tutti' cliccata (text fallback)")
                    screenshot(page, "servizi_tab_tutti")
            except Exception as e:
                print(f"  [WARN] Tab 'Tutti' non trovata: {e}")

        # 2) Debug: logga tutti gli elementi checkbox/role visibili
        debug_info = page.evaluate("""() => {
            const items = [];
            // Standard checkboxes
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                const row = cb.closest('label') || cb.closest('[class]') || cb.parentElement;
                items.push({
                    type: 'input-checkbox',
                    text: (row?.textContent || '').trim().substring(0, 80),
                    checked: cb.checked,
                });
            });
            // ARIA role=checkbox (custom components)
            document.querySelectorAll('[role="checkbox"]').forEach(el => {
                items.push({
                    type: 'role-checkbox',
                    text: (el.textContent || '').trim().substring(0, 80),
                    checked: el.getAttribute('aria-checked') === 'true',
                });
            });
            // ARIA role=switch
            document.querySelectorAll('[role="switch"]').forEach(el => {
                items.push({
                    type: 'role-switch',
                    text: (el.textContent || '').trim().substring(0, 80),
                    checked: el.getAttribute('aria-checked') === 'true',
                });
            });
            return items;
        }""")
        print(f"  Elementi checkbox trovati: {len(debug_info)}")
        for item in debug_info:
            print(f"    [{item.get('type')}] {item.get('text')} (checked={item.get('checked')})")

        # Se nessun checkbox standard trovato, logga la struttura HTML
        if len(debug_info) == 0:
            html_structure = page.evaluate("""() => {
                // Trova tutti gli elementi che contengono testi di servizi noti
                const known = ['TV', 'Aria condizionata', 'Parcheggio', 'Terrazza'];
                const results = [];
                for (const name of known) {
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null, false
                    );
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.textContent.trim() === name) {
                            let el = node.parentElement;
                            // Risali 5 livelli e logga la struttura
                            const chain = [];
                            for (let i = 0; i < 5 && el; i++) {
                                chain.push({
                                    tag: el.tagName,
                                    classes: (el.className || '').toString().substring(0, 60),
                                    role: el.getAttribute('role') || '',
                                    ariaChecked: el.getAttribute('aria-checked') || '',
                                    dataTest: el.getAttribute('data-test') || '',
                                    clickable: el.onclick !== null || el.tagName === 'BUTTON' ||
                                               el.tagName === 'LABEL' || el.tagName === 'A',
                                });
                                el = el.parentElement;
                            }
                            results.push({name, chain});
                            break;
                        }
                    }
                }
                return results;
            }""")
            print("  Struttura HTML dei servizi noti:")
            for r in html_structure:
                print(f"    '{r.get('name')}':")
                for c in r.get("chain", []):
                    print(f"      <{c.get('tag')}> class='{c.get('classes')}' "
                          f"role='{c.get('role')}' aria-checked='{c.get('ariaChecked')}' "
                          f"data-test='{c.get('dataTest')}' clickable={c.get('clickable')}")

        # 3) Seleziona ogni servizio con 4 strategie progressive
        for servizio in SERVIZI:
            selected = False

            # Strategia 1: get_by_role("checkbox") — il metodo Playwright raccomandato
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

            # Strategia 2: get_by_label — trova checkbox associata al testo
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

            # Strategia 3: JS — cerca checkbox nel contenitore del testo
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
                                return {found: true, method: 'js-checkbox', text: text.substring(0, 60)};
                            }
                        }
                        return {found: false};
                    }""", servizio)
                    if result.get("found"):
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (JS: {result.get('method')})")
                        selected = True
                except Exception as e:
                    print(f"  [WARN] {servizio} JS: {e}")

            # Strategia 4: Clicca direttamente il testo o il suo contenitore
            if not selected:
                try:
                    el = page.get_by_text(servizio, exact=True)
                    if el.count() > 0:
                        # Clicca il genitore del testo (spesso è la riga cliccabile)
                        el.first.locator("..").click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (click parent of text)")
                        selected = True
                except Exception:
                    pass

            if not selected:
                try:
                    el = page.get_by_text(servizio, exact=True)
                    if el.count() > 0:
                        el.first.click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (click text directly)")
                        selected = True
                except Exception:
                    pass

            if not selected:
                print(f"  [MISS] {servizio} — non trovato sulla pagina")

        wait(page, 2000)
        screenshot(page, "servizi_selezionati")
        save_html(page, "step14_servizi_dopo")

    try_step(page, "step14_servizi", do_step14)

    # --- Step 15: Continua (servizi) ---
    print("Step 15: Continua (servizi)")

    def do_step15():
        click_save(page)
        screenshot(page, "dopo_servizi")

    try_step(page, "step15_continua_servizi", do_step15)

    # --- Step 16: Click "Li scrivo io" ---
    print("Step 16: Li scrivo io")

    def do_step16():
        screenshot(page, "titolo_desc_pagina")
        save_html(page, "step16_titolo_desc")
        page.get_by_text("Li scrivo io").click()
        wait(page)
        screenshot(page, "li_scrivo_io")

    try_step(page, "step16_li_scrivo_io", do_step16)

    # --- Step 17: Titolo e descrizione ---
    print("Step 17: Titolo e descrizione")

    def do_step17():
        titolo = PROP.get("marketing", {}).get("titolo") or PROP["identificativi"]["nome_struttura"]

        titolo_field = page.get_by_label("Titolo")
        if titolo_field.count() > 0:
            titolo_field.fill(titolo)
        else:
            page.locator("input[name*='titolo'], input[name*='title'], input[placeholder*='Titolo']").first.fill(titolo)
        wait(page, 1000)

        desc_field = page.get_by_label("Descrizione")
        if desc_field.count() > 0:
            desc_field.fill(DESCRIPTION)
        else:
            page.locator("textarea").first.fill(DESCRIPTION)
        wait(page, 1000)
        screenshot(page, "titolo_descrizione")

    try_step(page, "step17_titolo_desc", do_step17)

    # --- Step 18: Continua (titolo/descrizione) ---
    print("Step 18: Continua (titolo/descrizione)")

    def do_step18():
        click_save(page)
        screenshot(page, "dopo_titolo_desc")

    try_step(page, "step18_continua_titolo", do_step18)

    # --- Step 19: Prezzo (dal JSON se presente, altrimenti skip) ---
    print("Step 19: Prezzo")

    def do_step19():
        screenshot(page, "prezzo_pagina")
        save_html(page, "step19_prezzo")

        listino = PROP.get("condizioni", {}).get("listino_prezzi", [])
        prezzo = PROP.get("condizioni", {}).get("prezzo_notte")

        if listino:
            # Multi-period pricing: use median as base price for the wizard.
            # Detailed per-period pricing is managed post-creation via calendar.
            prezzi = [p["prezzo_notte"] for p in listino if p.get("prezzo_notte")]
            base_prezzo = sorted(prezzi)[len(prezzi) // 2] if prezzi else None
            if base_prezzo:
                prezzo_str = str(base_prezzo)
                prezzo_field = page.get_by_label("Prezzo")
                if prezzo_field.count() > 0:
                    prezzo_field.fill(prezzo_str)
                else:
                    page.locator(
                        "input[type='number'], input[name*='prezz'], input[name*='price']"
                    ).first.fill(prezzo_str)
                print(f"  Prezzo base: {prezzo_str} EUR/notte (mediana di {len(prezzi)} periodi)")
            else:
                print("  Listino presente ma nessun prezzo valido — lascio vuoto")
        elif prezzo is not None:
            prezzo_str = str(prezzo)
            prezzo_field = page.get_by_label("Prezzo")
            if prezzo_field.count() > 0:
                prezzo_field.fill(prezzo_str)
            else:
                page.locator(
                    "input[type='number'], input[name*='prezz'], input[name*='price']"
                ).first.fill(prezzo_str)
            print(f"  Prezzo: {prezzo_str} EUR/notte (dal JSON)")
        else:
            print("  Prezzo non presente nel JSON — lascio vuoto")

        wait(page)
        screenshot(page, "prezzo")

    try_step(page, "step19_prezzo", do_step19)

    # --- Step 20: Continua (prezzo) ---
    print("Step 20: Continua (prezzo)")

    def do_step20():
        click_save(page)
        screenshot(page, "dopo_prezzo")

    try_step(page, "step20_continua_prezzo", do_step20)

    # --- Step 21: Impostazioni avanzate prezzi — cauzione 300 EUR ---
    print("Step 21: Impostazioni prezzi avanzate (cauzione)")

    def do_step21():
        screenshot(page, "prezzi_avanzati_pagina")
        save_html(page, "step21_prezzi_avanzati")

        cauzione_val = PROP.get("condizioni", {}).get("cauzione_euro")
        if cauzione_val is None:
            print("  Cauzione non presente nel JSON — skip")
            click_save(page)
            screenshot(page, "dopo_prezzi_avanzati")
            return
        cauzione = str(cauzione_val)

        filled = False
        # Strategia 1: label Playwright
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

        # Strategia 2: selettori CSS (input e select)
        if not filled:
            for sel in [
                "input[name*='cauzione']", "input[name*='deposit']",
                "input[name*='Cauzione']", "input[name*='Deposit']",
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

        # Strategia 3: JS — cerca input/select il cui contenitore menzioni cauzione
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

        wait(page, 1000)
        click_save(page)
        screenshot(page, "dopo_prezzi_avanzati")

    try_step(page, "step21_prezzi_avanzati", do_step21)

    # --- Step 22: Pulizie, biancheria, soggiorno minimo ---
    print("Step 22: Condizioni — pulizie, biancheria, soggiorno minimo")

    def _fill_field(value, labels, css_selectors, field_name):
        """Helper: compila un campo con strategia 3-livelli (label/CSS/JS)."""
        if not value:
            return
        filled = False
        # Strategia 1: label Playwright
        for lbl in labels:
            try:
                f = page.get_by_label(lbl)
                if f.count() > 0:
                    tag = f.first.evaluate("el => el.tagName")
                    if tag == "SELECT":
                        try:
                            f.first.select_option(label=value)
                        except Exception:
                            f.first.select_option(value=value)
                    else:
                        f.first.fill(value)
                    filled = True
                    print(f"  {field_name}: {value} (label '{lbl}')")
                    break
            except Exception:
                continue
        # Strategia 2: selettori CSS
        if not filled:
            for sel in css_selectors:
                try:
                    f = page.locator(sel)
                    if f.count() > 0:
                        tag = f.first.evaluate("el => el.tagName")
                        if tag == "SELECT":
                            try:
                                f.first.select_option(label=value)
                            except Exception:
                                f.first.select_option(value=value)
                        else:
                            f.first.fill(value)
                        filled = True
                        print(f"  {field_name}: {value} (CSS '{sel}')")
                        break
                except Exception:
                    continue
        # Strategia 3: JS — cerca input il cui contenitore contenga keyword
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
            }""", {"val": value, "keywords": keywords})
            if filled:
                print(f"  {field_name}: {value} (JS)")
        if not filled:
            print(f"  [WARN] {field_name} non trovato — {value}")
        wait(page, 1000)

    def do_step22():
        screenshot(page, "condizioni_pagina")
        save_html(page, "step22_condizioni")

        cond = PROP["condizioni"]

        # Pulizia finale
        _fill_field(
            cond.get("pulizia_finale", ""),
            ["Pulizia finale", "Pulizie", "Cleaning", "Pulizia"],
            ["input[name*='puliz']", "textarea[name*='puliz']",
             "input[name*='clean']", "textarea[name*='clean']"],
            "Pulizia finale"
        )

        # Asciugamani
        _fill_field(
            cond.get("asciugamani", ""),
            ["Asciugamani", "Towels"],
            ["input[name*='asciugam']", "textarea[name*='asciugam']",
             "input[name*='towel']"],
            "Asciugamani"
        )

        # Lenzuola
        _fill_field(
            cond.get("lenzuola", ""),
            ["Lenzuola", "Bed linen", "Sheets"],
            ["input[name*='lenzuol']", "textarea[name*='lenzuol']",
             "input[name*='linen']", "input[name*='sheet']"],
            "Lenzuola"
        )

        # Biancheria (legacy, per retrocompatibilita con Il Faro)
        _fill_field(
            cond.get("biancheria", ""),
            ["Biancheria", "Linen", "Biancheria da letto"],
            ["input[name*='bianch']", "textarea[name*='bianch']"],
            "Biancheria"
        )

        # Soggiorno minimo — usa il valore piu basso tra i periodi
        sog_bassa = cond.get("soggiorno_minimo_bassa", {})
        sog_alta = cond.get("soggiorno_minimo_alta", {})
        notti = str(sog_bassa.get("notti", sog_alta.get("notti", "")))
        if notti:
            _fill_field(
                notti,
                ["Soggiorno minimo", "Notti minime", "Minimum stay"],
                ["input[name*='soggiorno']", "input[name*='minim']",
                 "input[name*='stay']", "select[name*='soggiorno']"],
                "Soggiorno minimo"
            )

        screenshot(page, "condizioni_compilate")

    try_step(page, "step22_condizioni", do_step22)

    # --- Step 23: Continua (condizioni) ---
    print("Step 23: Continua (condizioni)")

    def do_step23():
        click_save(page)
        screenshot(page, "dopo_condizioni")

    try_step(page, "step23_continua_condizioni", do_step23)

    # --- Step 24: Regole check-in / check-out ---
    print("Step 24: Regole — check-in, check-out, regole casa")

    def do_step24():
        screenshot(page, "regole_pagina")
        save_html(page, "step24_regole")

        cond = PROP["condizioni"]

        # Check-in
        _fill_field(
            cond.get("check_in", ""),
            ["Check-in", "Check in", "Orario arrivo", "Arrivo"],
            ["input[name*='check_in']", "input[name*='checkin']",
             "select[name*='check_in']", "select[name*='checkin']",
             "input[name*='arriv']"],
            "Check-in"
        )

        # Check-out
        _fill_field(
            cond.get("check_out", ""),
            ["Check-out", "Check out", "Orario partenza", "Partenza"],
            ["input[name*='check_out']", "input[name*='checkout']",
             "select[name*='check_out']", "select[name*='checkout']",
             "input[name*='parten']"],
            "Check-out"
        )

        # Regole della casa
        _fill_field(
            cond.get("regole_casa", ""),
            ["Regole", "Regole della casa", "House rules", "Regolamento"],
            ["textarea[name*='regol']", "textarea[name*='rule']",
             "textarea[name*='house']"],
            "Regole casa"
        )

        screenshot(page, "regole_compilate")

    try_step(page, "step24_regole", do_step24)

    # --- Step 25: Continua (regole) ---
    print("Step 25: Continua (regole)")

    def do_step25():
        click_save(page)
        screenshot(page, "dopo_regole")

    try_step(page, "step25_continua_regole", do_step25)

    # --- Step 26: Calendario ---
    print("Step 26: Calendario")

    def do_step26():
        screenshot(page, "calendario_pagina")
        save_html(page, "step26_calendario")

        ical_url = PROP.get("condizioni", {}).get("ical_url")
        if ical_url:
            imported = False
            for btn_text in ["Importa", "Sincronizza", "iCal", "Import", "Sync",
                             "Importa calendario", "Collega calendario"]:
                try:
                    btn = page.get_by_text(btn_text)
                    if btn.count() > 0:
                        btn.first.click()
                        wait(page, 2000)
                        print(f"  Cliccato '{btn_text}' sulla pagina calendario")
                        screenshot(page, "ical_dialog")

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
                                        wait(page, 3000)
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
                print("  L'URL iCal dovra essere inserito manualmente post-creazione")
        else:
            print("  Nessun iCal URL nel JSON — skip import calendario")

        click_save(page)
        screenshot(page, "dopo_calendario")

    try_step(page, "step26_calendario", do_step26)

    # --- Step 27: Requisiti regionali — CIN ---
    print("Step 27: Requisiti regionali (CIN)")

    def do_step27():
        screenshot(page, "requisiti_pagina")
        save_html(page, "step27_requisiti")

        # Compila il CIN (Codice Identificativo Nazionale)
        try:
            cin_field = page.get_by_label("CIN")
            if cin_field.count() > 0:
                cin_field.fill(PROP["identificativi"]["cin"])
                print("  CIN compilato (label)")
            else:
                cin_field = page.locator(
                    "input[name*='cin'], input[name*='CIN'], "
                    "input[name*='codice'], input[placeholder*='CIN']"
                )
                if cin_field.count() > 0:
                    cin_field.first.fill(PROP["identificativi"]["cin"])
                    print("  CIN compilato (name/placeholder)")
                else:
                    # Ultimo tentativo: cerca qualsiasi input di testo nella pagina
                    text_inputs = page.locator("input[type='text']")
                    if text_inputs.count() > 0:
                        text_inputs.first.fill(PROP["identificativi"]["cin"])
                        print("  CIN compilato (primo input text)")
                    else:
                        print("  Campo CIN non trovato, skip")
        except Exception as e:
            print(f"  Errore CIN: {e}")

        wait(page, 1000)
        click_save(page)
        screenshot(page, "dopo_requisiti")

    try_step(page, "step27_requisiti", do_step27)

    # --- Step 28: Pagina finale — solo screenshot, NON inviare ---
    print("Step 28: Pagina finale — SOLO screenshot")

    def do_step28():
        wait(page)
        screenshot(page, "pagina_finale")
        save_html(page, "step28_finale")
        print("Flusso completato! NON inviato per la verifica.")

    try_step(page, "step28_finale", do_step28)


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            login(page)
            dismiss_popups(page)
            navigate_to_add_property(page)
            screenshot(page, "pagina_iniziale")
            insert_property(page)
        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
