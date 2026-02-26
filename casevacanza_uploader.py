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
    "internet_wifi": "Wi-Fi",
    "phon": "Asciugacapelli",
    "ferro_stiro": "Ferro da stiro",
    "terrazza": "Terrazza",
    "giardino": "Giardino",
    "piscina": "Piscina (in comune)",
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


def download_placeholder_photos(count=5):
    """Download placeholder photos from picsum.photos."""
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


def login(page):
    """Login su CaseVacanza.it — prova diversi selettori per email e password."""
    print("Login CaseVacanza.it...")
    page.goto("https://my.casevacanza.it", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_page")
    save_html(page, "login_page")
    print(f"  URL login: {page.url}")

    # Aspetta che compaia un campo input (la pagina potrebbe fare redirect a Keycloak)
    page.wait_for_selector(
        "#username, #email, input[name='username'], input[name='email'], "
        "input[type='email'], input[type='text'], input[type='password']",
        timeout=30_000,
    )
    wait(page, 2000)

    # Trova il campo email/username
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
        loc = page.locator(sel)
        if loc.count() > 0:
            email_field = loc.first
            print(f"  Campo email trovato: {sel}")
            break
    if email_field is None:
        for lbl in ["Email", "Username", "E-mail", "Indirizzo email"]:
            loc = page.get_by_label(lbl)
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
        loc = page.locator(sel)
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
        loc = page.locator(sel)
        if loc.count() > 0:
            login_btn = loc.first
            print(f"  Bottone login trovato: {sel}")
            break
    if login_btn is None:
        for lbl in ["Accedi", "Login", "Sign in", "Entra"]:
            loc = page.get_by_text(lbl, exact=True)
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
    photo_paths = download_placeholder_photos(5)

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

    # --- Step 7: Mappa — Continua senza modificare pin ---
    print("Step 7: Mappa — Continua")
    click_save(page)
    screenshot(page, "dopo_mappa")

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

        # Logga tutti gli elementi servizio visibili per debug
        all_labels = page.evaluate("""() => {
            const els = document.querySelectorAll(
                'label, [role="checkbox"], [data-test], input[type="checkbox"]'
            );
            return Array.from(els).slice(0, 60).map(e => ({
                tag: e.tagName,
                text: (e.textContent || '').trim().substring(0, 60),
                type: e.type || '',
                role: e.getAttribute('role') || '',
                classes: e.className || '',
                checked: e.checked || e.classList.contains('selected') ||
                         e.classList.contains('active') || e.getAttribute('aria-checked') === 'true',
                dataTest: e.getAttribute('data-test') || '',
            }));
        }""")
        print(f"  Elementi trovati sulla pagina: {len(all_labels)}")
        for el in all_labels[:30]:
            print(f"    {el}")

        for servizio in SERVIZI:
            selected = False

            # Strategia 1: Cerca checkbox/label tramite JavaScript
            try:
                result = page.evaluate("""(label) => {
                    // Cerca tutti gli elementi che contengono il testo
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT, null, false
                    );
                    let node;
                    while (node = walker.nextNode()) {
                        const text = node.textContent.trim();
                        if (text === label || text.includes(label)) {
                            // Risali fino a trovare un elemento cliccabile
                            let el = node.parentElement;
                            for (let i = 0; i < 5 && el; i++) {
                                // Cerca checkbox nascosta vicina
                                const inp = el.querySelector('input[type="checkbox"]');
                                if (inp) {
                                    inp.click();
                                    return {found: true, method: 'checkbox-input', tag: el.tagName};
                                }
                                // Se l'elemento stesso è una label o card cliccabile
                                if (el.tagName === 'LABEL' || el.getAttribute('role') === 'checkbox'
                                    || el.classList.contains('card') || el.classList.contains('chip')
                                    || el.classList.contains('option') || el.classList.contains('tile')
                                    || el.dataset.test) {
                                    el.click();
                                    return {found: true, method: 'parent-click', tag: el.tagName};
                                }
                                el = el.parentElement;
                            }
                            // Fallback: clicca il genitore diretto del testo
                            node.parentElement.click();
                            return {found: true, method: 'text-parent-click', tag: node.parentElement.tagName};
                        }
                    }
                    return {found: false};
                }""", servizio)

                if result.get("found"):
                    page.wait_for_timeout(500)
                    print(f"  [OK] {servizio} (JS: {result.get('method')}, {result.get('tag')})")
                    selected = True
            except Exception as e:
                print(f"  [WARN] {servizio} JS error: {e}")

            # Strategia 2: Playwright get_by_text
            if not selected:
                try:
                    btn = page.get_by_text(servizio, exact=True)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (exact)")
                        selected = True
                except Exception:
                    pass

            # Strategia 3: Playwright get_by_text partial
            if not selected:
                try:
                    btn = page.get_by_text(servizio, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (partial)")
                        selected = True
                except Exception:
                    pass

            # Strategia 4: locator label/span/div
            if not selected:
                try:
                    btn = page.locator(f"label:has-text('{servizio}'), "
                                       f"span:has-text('{servizio}'), "
                                       f"div:has-text('{servizio}')")
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(500)
                        print(f"  [OK] {servizio} (locator)")
                        selected = True
                except Exception:
                    pass

            if not selected:
                print(f"  [MISS] {servizio} — non trovato sulla pagina")

        wait(page)
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
        titolo = PROP["identificativi"]["nome_struttura"]

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

        prezzo = PROP.get("condizioni", {}).get("prezzo_notte")
        if prezzo is None:
            print("  Prezzo non presente nel JSON — lascio vuoto")
        else:
            prezzo_str = str(prezzo)
            prezzo_field = page.get_by_label("Prezzo")
            if prezzo_field.count() > 0:
                prezzo_field.fill(prezzo_str)
            else:
                page.locator(
                    "input[type='number'], input[name*='prezz'], input[name*='price']"
                ).first.fill(prezzo_str)
            print(f"  Prezzo: {prezzo_str} EUR/notte (dal JSON)")

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

        # Prova a compilare il campo cauzione/deposito
        cauzione = str(PROP["condizioni"]["cauzione_euro"])
        try:
            cauzione_field = page.get_by_label("Cauzione")
            if cauzione_field.count() > 0:
                cauzione_field.fill(cauzione)
                print(f"  Cauzione impostata: {cauzione} EUR (label)")
            else:
                cauzione_field = page.locator(
                    "input[name*='cauzione'], input[name*='deposit'], "
                    "input[name*='Cauzione']"
                )
                if cauzione_field.count() > 0:
                    cauzione_field.first.fill(cauzione)
                    print(f"  Cauzione impostata: {cauzione} EUR (name)")
                else:
                    print("  Campo cauzione non trovato, skip")
        except Exception as e:
            print(f"  Errore cauzione: {e}")

        wait(page, 1000)
        click_save(page)
        screenshot(page, "dopo_prezzi_avanzati")

    try_step(page, "step21_prezzi_avanzati", do_step21)

    # --- Step 22: Pulizie, biancheria, soggiorno minimo ---
    print("Step 22: Condizioni — pulizie, biancheria, soggiorno minimo")

    def do_step22():
        screenshot(page, "condizioni_pagina")
        save_html(page, "step22_condizioni")

        cond = PROP["condizioni"]

        # Pulizia finale
        pulizia = cond.get("pulizia_finale", "")
        if pulizia:
            for label in ["Pulizia finale", "Pulizie", "Cleaning", "Pulizia"]:
                try:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(pulizia)
                        print(f"  Pulizia finale: {pulizia}")
                        break
                except Exception:
                    continue
            else:
                # Fallback: cerca campo per name/placeholder
                pf = page.locator(
                    "input[name*='puliz'], input[name*='clean'], "
                    "textarea[name*='puliz'], textarea[name*='clean']"
                )
                if pf.count() > 0:
                    pf.first.fill(pulizia)
                    print(f"  Pulizia finale (fallback): {pulizia}")
                else:
                    print(f"  Campo pulizia non trovato, provo click etichetta")
                    try:
                        btn = page.get_by_text("A carico dell'ospite")
                        if btn.count() > 0:
                            btn.first.click()
                            print("  Pulizia: selezionato 'A carico dell'ospite'")
                    except Exception:
                        print("  Skip pulizia finale")

        wait(page, 1000)

        # Biancheria
        biancheria = cond.get("biancheria", "")
        if biancheria:
            for label in ["Biancheria", "Linen", "Biancheria da letto"]:
                try:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(biancheria)
                        print(f"  Biancheria: {biancheria}")
                        break
                except Exception:
                    continue
            else:
                bf = page.locator(
                    "input[name*='bianch'], input[name*='linen'], "
                    "textarea[name*='bianch'], textarea[name*='linen']"
                )
                if bf.count() > 0:
                    bf.first.fill(biancheria)
                    print(f"  Biancheria (fallback): {biancheria}")
                else:
                    print("  Campo biancheria non trovato, skip")

        wait(page, 1000)

        # Soggiorno minimo bassa stagione
        sog_bassa = cond.get("soggiorno_minimo_bassa", {})
        sog_alta = cond.get("soggiorno_minimo_alta", {})

        for label in ["Soggiorno minimo", "Notti minime", "Minimum stay"]:
            try:
                field = page.get_by_label(label)
                if field.count() > 0:
                    # Usa il valore più basso come default
                    notti = str(sog_bassa.get("notti", sog_alta.get("notti", 1)))
                    field.first.fill(notti)
                    print(f"  Soggiorno minimo: {notti} notti")
                    break
            except Exception:
                continue
        else:
            sf = page.locator(
                "input[name*='soggiorno'], input[name*='minim'], "
                "input[name*='stay']"
            )
            if sf.count() > 0:
                notti = str(sog_bassa.get("notti", sog_alta.get("notti", 1)))
                sf.first.fill(notti)
                print(f"  Soggiorno minimo (fallback): {notti} notti")
            else:
                print("  Campo soggiorno minimo non trovato, skip")

        wait(page, 1000)
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
        check_in = cond.get("check_in", "")
        if check_in:
            for label in ["Check-in", "Check in", "Orario arrivo", "Arrivo"]:
                try:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(check_in)
                        print(f"  Check-in: {check_in}")
                        break
                except Exception:
                    continue
            else:
                ci = page.locator(
                    "input[name*='check_in'], input[name*='checkin'], "
                    "input[name*='arriv']"
                )
                if ci.count() > 0:
                    ci.first.fill(check_in)
                    print(f"  Check-in (fallback): {check_in}")
                else:
                    print("  Campo check-in non trovato, skip")

        wait(page, 1000)

        # Check-out
        check_out = cond.get("check_out", "")
        if check_out:
            for label in ["Check-out", "Check out", "Orario partenza", "Partenza"]:
                try:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(check_out)
                        print(f"  Check-out: {check_out}")
                        break
                except Exception:
                    continue
            else:
                co = page.locator(
                    "input[name*='check_out'], input[name*='checkout'], "
                    "input[name*='parten']"
                )
                if co.count() > 0:
                    co.first.fill(check_out)
                    print(f"  Check-out (fallback): {check_out}")
                else:
                    print("  Campo check-out non trovato, skip")

        wait(page, 1000)

        # Regole della casa
        regole = cond.get("regole_casa", "")
        if regole:
            for label in ["Regole", "Regole della casa", "House rules", "Regolamento"]:
                try:
                    field = page.get_by_label(label)
                    if field.count() > 0:
                        field.first.fill(regole)
                        print("  Regole casa compilate")
                        break
                except Exception:
                    continue
            else:
                rf = page.locator(
                    "textarea[name*='regol'], textarea[name*='rule'], "
                    "textarea[name*='house']"
                )
                if rf.count() > 0:
                    rf.first.fill(regole)
                    print("  Regole casa (fallback) compilate")
                else:
                    print("  Campo regole non trovato, skip")

        wait(page, 1000)
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
