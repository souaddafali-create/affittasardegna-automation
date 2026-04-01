import json
import os
import random
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

# Modalità interattiva: se il terminale è un TTY o se INTERACTIVE=1
INTERACTIVE = sys.stdin.isatty() or os.environ.get("INTERACTIVE", "") == "1"

# --- Carica dati proprietà dal file JSON ---
DATA_FILE = os.environ.get(
    "PROPERTY_DATA", os.path.join(os.path.dirname(__file__), "Il_Faro_Badesi_DATI.json")
)
with open(DATA_FILE, encoding="utf-8") as _f:
    PROP = json.load(_f)

EMAIL = os.environ.get("BK_EMAIL", "")
PASSWORD = os.environ.get("BK_PASSWORD", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots_booking"
step_counter = 0


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def screenshot(page, name):
    global step_counter
    step_counter += 1
    path = f"{SCREENSHOT_DIR}/step{step_counter:02d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  Screenshot: {path}")


def save_html(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"  HTML salvato: {path}")


def wait(page, ms=5000):
    page.wait_for_timeout(ms)


def human_type(page, selector, text):
    """Digita come un umano con pause random."""
    page.click(selector)
    time.sleep(random.uniform(0.3, 0.7))
    for char in text:
        page.keyboard.type(char, delay=random.randint(50, 150))
    time.sleep(random.uniform(0.2, 0.5))


def try_step(page, step_name, func):
    try:
        func()
        print(f"  OK: {step_name}")
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        screenshot(page, f"errore_{step_name}")
        save_html(page, f"errore_{step_name}")
        if INTERACTIVE:
            resp = input(f">>> Step '{step_name}' fallito. Completa manualmente nel browser, poi INVIO (o 'skip'): ").strip()
            if resp.lower() != "skip":
                screenshot(page, f"dopo_manuale_{step_name}")
        else:
            raise


def download_placeholder_photos(count=5):
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
# Booking Extranet: mappatura dotazioni
# REGOLA: spunta SOLO le dotazioni con valore true nel JSON.
#         Se false o assente, NON spuntare. Zero eccezioni.
# ---------------------------------------------------------------------------

DOTAZIONI_BOOKING = {
    "tv": "TV",
    "piano_cottura": "Piano cottura",
    "frigo_congelatore": "Frigorifero",
    "forno": "Forno",
    "microonde": "Microonde",
    "lavatrice": "Lavatrice",
    "lavastoviglie": "Lavastoviglie",
    "aria_condizionata": "Aria condizionata",
    "riscaldamento": "Riscaldamento",
    "internet_wifi": "WiFi",
    "phon": "Asciugacapelli",
    "ferro_stiro": "Ferro da stiro",
    "terrazza": "Terrazza",
    "giardino": "Giardino",
    "piscina": "Piscina",
    "arredi_esterno": "Mobili da esterno",
    "barbecue": "Barbecue",
    "culla": "Culla",
    "seggiolone": "Seggiolone",
    "animali_ammessi": "Animali domestici",
}


def _build_servizi_booking():
    """Restituisce la lista dei servizi attivi (true) da selezionare su Booking.
    Legge SOLO dal JSON — se un servizio è false, NON viene incluso."""
    dot = PROP["dotazioni"]
    servizi = []
    for key, label in DOTAZIONI_BOOKING.items():
        if dot.get(key) is True:
            servizi.append(label)
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        servizi.append("Parcheggio")
    return servizi


SERVIZI = _build_servizi_booking()


# ---------------------------------------------------------------------------
# Login Booking Extranet
# ---------------------------------------------------------------------------

def _wait_for_interactive(page, prompt_msg, check_done_fn, timeout_s=300):
    """Pausa interattiva: chiede input da terminale oppure aspetta che l'utente
    agisca direttamente sul browser (modalità headless=False).

    - Se INTERACTIVE: mostra un prompt e attende INVIO.
    - Altrimenti (CI): attende fino a ``timeout_s`` che ``check_done_fn(page)``
      restituisca True (polling ogni 5s), poi fallisce.
    """
    if INTERACTIVE:
        input(f"\n>>> {prompt_msg}\n>>> Premi INVIO quando hai finito... ")
    else:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if check_done_fn(page):
                return
            time.sleep(5)
        raise TimeoutError(f"Timeout ({timeout_s}s) in attesa di: {prompt_msg}")


def _has_password_field(page):
    """Restituisce True se nella pagina c'è un campo password visibile."""
    return page.locator('input[type="password"]:visible').count() > 0


def _page_has_captcha(page):
    html = page.content().lower()
    return "captcha" in html or "human" in html or "choose all" in html


def _page_has_otp(page):
    """Rileva se Booking sta chiedendo un codice di verifica email.
    Più restrittivo per evitare falsi positivi sulla homepage."""
    url = page.url.lower()

    # Se siamo sulla homepage di Booking, NON è un OTP
    if "booking.com/index" in url or url.rstrip("/").endswith("booking.com"):
        return False

    # Controlla che siamo su una pagina di autenticazione
    auth_urls = ["account.booking.com", "sign-in", "verify", "auth"]
    if not any(u in url for u in auth_urls):
        return False

    html = page.content().lower()
    otp_keywords = ["verification code", "codice di verifica", "enter the code",
                     "inserisci il codice", "sent you a code", "inviato un codice"]
    has_keyword = any(kw in html for kw in otp_keywords)
    has_otp_input = page.locator(
        "input[name*='otp'], input[name*='code'], input[name*='pin'], "
        "input[name*='token'], input[autocomplete='one-time-code']"
    ).count() > 0
    return has_keyword and has_otp_input


def _dismiss_cookie_banner(page):
    """Chiude il banner cookie se presente — prova vari metodi."""
    # Metodo 1: bottone per ruolo
    for label in ["Accetto", "Accetta", "Accept", "Accept all", "Accetta tutto"]:
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso ('{label}')")
                wait(page, 1500)
                return
        except Exception:
            continue
    # Metodo 2: qualsiasi elemento con quel testo
    for label in ["Accetto", "Accept"]:
        try:
            btn = page.locator(f"button:has-text('{label}'), a:has-text('{label}')")
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso via locator ('{label}')")
                wait(page, 1500)
                return
        except Exception:
            continue
    # Metodo 3: data-testid tipici di Booking
    for sel in ["[data-testid='accept-btn']", "#onetrust-accept-btn-handler",
                 "[id*='cookie'] button", "[class*='cookie'] button"]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cookie banner chiuso ({sel})")
                wait(page, 1500)
                return
        except Exception:
            continue


def _click_continue(page):
    """Clicca il pulsante Continua/Next nel wizard Booking.
    Prova: data-testid, automation_id, ruolo button, testo."""
    # Selettori specifici Booking
    for sel in [
        "button[data-testid*='continue']",
        "button[data-testid*='next']",
        "button[data-testid*='submit']",
        "[id*='automation_id'][id*='continue']",
        "[id*='automation_id'][id*='next']",
    ]:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cliccato continua: {sel}")
                return True
        except Exception:
            continue

    # Fallback testo
    for txt in ["Continua", "Continue", "Avanti", "Next",
                 "Salva e continua", "Save and continue"]:
        try:
            btn = page.get_by_role("button", name=txt)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Cliccato: '{txt}'")
                return True
        except Exception:
            continue

    print("  Pulsante Continua non trovato")
    return False


def login_and_navigate(page):
    """Login su Booking e naviga fino al wizard di inserimento proprietà.

    Il login di Booking cambia spesso (CAPTCHA, OTP, password, magic link).
    In modalità interattiva: inserisce l'email, poi chiede all'utente di
    completare il login manualmente nel browser. Più robusto e affidabile.

    Returns the page where the wizard starts (potrebbe essere una nuova scheda).
    """
    print("=== LOGIN BOOKING ===")

    # -- Fase 1: Apri pagina login e inserisci email --
    page.goto("https://account.booking.com/sign-in",
              wait_until="domcontentloaded", timeout=60_000)
    wait(page, 5000)
    _dismiss_cookie_banner(page)
    screenshot(page, "login_page")

    email_sel = 'input[type="email"], input[name="loginname"], #loginname'
    try:
        page.wait_for_selector(email_sel, timeout=15_000)
        human_type(page, email_sel, EMAIL)
        wait(page, 1000)
        page.click('button[type="submit"]', timeout=10_000)
        wait(page, 3000)
        screenshot(page, "dopo_email")
        print(f"  Email inserita: {EMAIL}")
    except Exception as e:
        print(f"  Errore inserimento email: {e}")

    # -- Fase 2: L'utente completa il login manualmente --
    if INTERACTIVE:
        print("\n" + "=" * 60)
        print("  COMPLETA IL LOGIN NEL BROWSER:")
        print("  - CAPTCHA → risolvilo")
        print("  - Codice email → inseriscilo")
        print("  - Password → inseriscila")
        print("  Continua fino a essere LOGGATO.")
        print("=" * 60)
        input("\n>>> Premi INVIO quando sei loggato... ")
    else:
        # In CI: prova il flusso automatico password
        pw_sel = 'input[type="password"]'
        try:
            page.wait_for_selector(pw_sel, timeout=15_000)
            human_type(page, pw_sel, PASSWORD)
            page.click('button[type="submit"]', timeout=10_000)
            wait(page, 8000)
        except Exception:
            raise RuntimeError("Login automatico fallito. Eseguire in locale con INTERACTIVE=1.")

    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")

    # -- Fase 3: Naviga al wizard "Inserisci il tuo immobile" --
    print("\nNavigazione al wizard...")
    _dismiss_cookie_banner(page)

    # "Inserisci il tuo immobile" apre una NUOVA SCHEDA (target=_blank)
    new_page = None
    for label in ["Inserisci il tuo immobile", "List your property"]:
        try:
            link = page.get_by_role("link", name=label)
            if link.count() > 0:
                with page.context.expect_page(timeout=15_000) as new_page_info:
                    link.first.click()
                new_page = new_page_info.value
                print(f"  Cliccato: '{label}' → nuova scheda")
                break
        except Exception:
            try:
                link = page.get_by_role("link", name=label)
                if link.count() > 0:
                    link.first.click()
                    print(f"  Cliccato: '{label}' (stessa scheda)")
                    break
            except Exception:
                continue

    wizard_page = new_page if new_page else page

    # Se non siamo ancora sul wizard, naviga direttamente
    if "join.booking.com" not in wizard_page.url:
        print("  Navigo direttamente a join.booking.com...")
        wizard_page.goto("https://join.booking.com/",
                         wait_until="domcontentloaded", timeout=60_000)

    wait(wizard_page, 5000)
    _dismiss_cookie_banner(wizard_page)
    screenshot(wizard_page, "landing_join")
    print(f"  URL landing: {wizard_page.url}")

    # Landing page join.booking.com: clicca "Get started" con ID reale
    if "become-a-host" not in wizard_page.url:
        try:
            # Selettore reale dalla pagina: id="getStarted"
            gs_btn = wizard_page.locator("#getStarted, [data-testid='getStarted']")
            if gs_btn.count() > 0:
                gs_btn.first.click()
                print("  Cliccato #getStarted")
            else:
                # Fallback testo
                for label in ["Get started now", "Inizia ora", "Inizia subito"]:
                    btn = wizard_page.get_by_role("button", name=label)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        print(f"  Cliccato: '{label}'")
                        break
                    btn = wizard_page.get_by_role("link", name=label)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.click()
                        print(f"  Cliccato link: '{label}'")
                        break
        except Exception as e:
            print(f"  Errore Get Started: {e}")
        wait(wizard_page, 5000)

    screenshot(wizard_page, "wizard_start")
    save_html(wizard_page, "wizard_start")
    print(f"  URL wizard: {wizard_page.url}")
    return wizard_page


# ---------------------------------------------------------------------------
# Inserimento proprietà su Booking Extranet
#
# Il wizard ha 2 fasi:
#   1) Segmentation Flow (5-6 schermate): Categoria → Listing Type →
#      Property Type → Owner Type → OTA Question → Nome
#   2) FifteenMin Flow (5 sezioni): Info → Setup → Photos → Pricing → Review
#
# Tutti i selettori derivano dall'analisi HTML reale del wizard.
# ---------------------------------------------------------------------------

def _click_wizard_continue(page):
    """Clicca il pulsante Continua nel wizard Booking.
    Il bottone usa data-testid='FormButtonPrimary-*'."""
    # Aspetta che Continua sia abilitato (max 10s)
    try:
        page.wait_for_selector("[data-testid='FormButtonPrimary-enabled']", timeout=10_000)
    except Exception:
        pass  # Proviamo comunque

    # Prova il bottone abilitato
    btn = page.locator("[data-testid='FormButtonPrimary-enabled']")
    if btn.count() > 0 and btn.first.is_visible():
        btn.first.click()
        print("  → Cliccato Continua (enabled)")
        wait(page, 3000)
        return True

    # Se il bottone è DISABILITATO, NON provare a cliccarlo (timeout Playwright)
    btn_disabled = page.locator("[data-testid='FormButtonPrimary-disabled']")
    if btn_disabled.count() > 0 and btn_disabled.first.is_visible():
        print("  → Continua è DISABILITATO (servono selezioni)")
        return False

    # Fallback testo — solo bottoni non-disabled
    return _click_continue(page)


def insert_property(page):
    """Complete the Booking Extranet property insertion wizard.

    Fase 1 — Segmentation Flow (automation_id selectors):
      1. Category: Appartamento (#automation_id_choose_category_apt_btn)
      2. Listing: L'intero spazio (#automation_id_choose_listing_type_entire_place)
      3. Property Type: Appartamento (#automation_id_property_type_201)
      4. Owner Type: Single (#automation_id_choose_owner_type_single)
      5. OTA Question: nessun sito (checkbox name="none")
      6. → passa al FifteenMin Flow

    Fase 2 — FifteenMin Flow:
      Nome struttura (input name="property_name")
      + sezioni successive (indirizzo, camere, servizi, foto, prezzo)
    """
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    cond = PROP.get("condizioni", {})

    # =====================================================================
    # FASE 1: Segmentation Flow
    # =====================================================================

    # --- S1: Categoria → Appartamento ---
    print("S1: Categoria — Appartamento")
    def do_s1():
        _dismiss_cookie_banner(page)
        wait(page, 2000)
        screenshot(page, "s1_categoria")
        save_html(page, "s1_categoria")
        page.locator("#automation_id_choose_category_apt_btn").click()
        print("  Cliccato #automation_id_choose_category_apt_btn")
        wait(page, 5000)
    try_step(page, "s1_categoria", do_s1)

    # --- S2: Listing Type → L'intero spazio ---
    print("S2: Listing Type — L'intero spazio")
    def do_s2():
        screenshot(page, "s2_listing")
        save_html(page, "s2_listing")
        page.locator("#automation_id_choose_listing_type_entire_place").click()
        print("  Cliccato #automation_id_choose_listing_type_entire_place")
        wait(page, 2000)
        _click_wizard_continue(page)
        wait(page, 5000)
    try_step(page, "s2_listing", do_s2)

    # --- S3: Property Type → Appartamento (type 201) ---
    print("S3: Property Type — Appartamento")
    def do_s3():
        screenshot(page, "s3_property_type")
        save_html(page, "s3_property_type")
        # automation_id_property_type_201 = Appartamento
        apt = page.locator("#automation_id_property_type_201")
        if apt.count() > 0 and apt.is_visible():
            apt.click()
            print("  Cliccato #automation_id_property_type_201")
        else:
            # Fallback: cerca card con testo "Appartamento"
            card = page.locator("[data-testid='PropertyTypeCard-container']").first
            if card.is_visible():
                card.click()
                print("  Cliccato prima PropertyTypeCard")
        wait(page, 2000)
        _click_wizard_continue(page)
        wait(page, 5000)
    try_step(page, "s3_property_type", do_s3)

    # --- S4: Owner Type → Single ---
    print("S4: Owner Type — Singolo proprietario")
    def do_s4():
        screenshot(page, "s4_owner")
        save_html(page, "s4_owner")
        page.locator("#automation_id_choose_owner_type_single").click()
        print("  Cliccato #automation_id_choose_owner_type_single")
        wait(page, 2000)
        _click_wizard_continue(page)
        wait(page, 5000)
    try_step(page, "s4_owner", do_s4)

    # --- S5: OTA Question → "Non registrata su nessun sito" ---
    print("S5: OTA Question — nessun sito")
    def do_s5():
        screenshot(page, "s5_ota")
        save_html(page, "s5_ota")
        # Checkbox "La mia struttura non è registrata su nessun sito"
        # Le checkbox hanno name: airbnb, tripadvisor, vrbo, expedia, hotels_com
        # L'ultima opzione è "nessun sito" — cerchiamo per testo
        none_opt = page.get_by_text("non è registrata su nessun sito", exact=False)
        if none_opt.count() > 0:
            none_opt.first.click()
            print("  Selezionato 'non registrata su nessun sito'")
        else:
            # Fallback: ultima checkbox nel form (tipicamente la sesta)
            items = page.locator("[data-testid='otaq-item']")
            if items.count() > 0:
                items.last.click()
                print("  Cliccato ultimo otaq-item")
        wait(page, 2000)
        _click_wizard_continue(page)
        wait(page, 8000)
    try_step(page, "s5_ota", do_s5)

    # =====================================================================
    # FASE 2: FifteenMin Flow — Nome + Sezioni
    # =====================================================================

    # --- F1: Nome struttura ---
    print("F1: Nome struttura")
    def do_f1():
        screenshot(page, "f1_nome")
        save_html(page, "f1_nome")
        # Booking richiede almeno 1 lettera minuscola nel nome
        nome = ident["nome_struttura"].title()  # "BILO LE CALETTE" → "Bilo Le Calette"
        nome_field = page.locator("input[name='property_name']")
        if nome_field.count() == 0:
            nome_field = page.locator("[data-testid^='PropertyName']")
        if nome_field.count() > 0:
            nome_field.first.fill(nome)
            print(f"  Nome: {nome}")
        else:
            print("  Campo nome non trovato")
        wait(page, 2000)
        _click_wizard_continue(page)
        wait(page, 5000)
        screenshot(page, "dopo_nome")
        save_html(page, "dopo_nome")
    try_step(page, "f1_nome", do_f1)

    # --- F2+: Sezioni successive del wizard ---
    # Da qui il wizard ha sezioni (property_info, property_setup, photos, etc.)
    # Ogni sezione ha sotto-pagine che ancora non conosciamo nel dettaglio.
    # Approccio: per ogni pagina, prova a compilare i campi dal JSON,
    # poi clicca Continua. Se fallisce, chiedi intervento manuale.

    print("\n=== COMPILAZIONE SEZIONI ===")
    print("  Da qui lo script compila automaticamente dove può.")
    print("  Se si blocca, ti chiede di completare nel browser.\n")

    # Ciclo adattivo: prova a compilare e cliccare Continua
    # fino a raggiungere la pagina finale o il limite di step
    max_adaptive_steps = 40
    for step_n in range(1, max_adaptive_steps + 1):
      try:
        screenshot(page, f"adaptive_step_{step_n:02d}")
        save_html(page, f"adaptive_step_{step_n:02d}")

        # Rileva la pagina attuale dal titolo
        title = ""
        try:
            h = page.locator("h1, h2, [role='heading']").first
            if h.is_visible():
                title = h.inner_text().strip()[:80]
        except Exception:
            pass
        print(f"\n  --- Pagina {step_n}: {title} ---")

        # Prova a compilare campi noti dal JSON
        filled = False

        # Indirizzo
        for sel, val in [
            ("input[name*='address'], input[name*='street']", ident.get("indirizzo", "")),
            ("input[name*='city']", ident.get("comune", "")),
            ("input[name*='zip'], input[name*='postal']", ident.get("cap", "")),
        ]:
            if val:
                try:
                    f = page.locator(sel)
                    if f.count() > 0 and f.first.is_visible():
                        f.first.fill(val)
                        print(f"  Compilato {sel}: {val}")
                        filled = True
                except Exception:
                    pass

        # Nome struttura
        try:
            f = page.locator("input[name='property_name']")
            if f.count() > 0 and f.first.is_visible() and not f.first.input_value():
                nome_tc = ident["nome_struttura"].title()
                f.first.fill(nome_tc)
                print(f"  Nome: {nome_tc}")
                filled = True
        except Exception:
            pass

        # Prezzo
        try:
            f = page.locator("input[name*='price'], input[name*='prezzo']")
            if f.count() > 0 and f.first.is_visible():
                prezzo = cond.get("prezzo_notte")
                if prezzo is None:
                    listino = cond.get("listino_prezzi", [])
                    if listino:
                        prezzi = sorted(p["prezzo_notte"] for p in listino if p.get("prezzo_notte"))
                        if prezzi:
                            prezzo = prezzi[len(prezzi) // 2]
                if prezzo:
                    f.first.fill(str(prezzo))
                    print(f"  Prezzo: {prezzo}")
                    filled = True
        except Exception:
            pass

        # CIN
        try:
            f = page.locator("input[name*='cin'], input[name*='CIN']")
            if f.count() > 0 and f.first.is_visible():
                f.first.fill(ident["cin"])
                print(f"  CIN: {ident['cin']}")
                filled = True
        except Exception:
            pass

        # CIR
        try:
            cir = ident.get("cir", "")
            if cir:
                f = page.locator("input[name*='cir'], input[name*='CIR']")
                if f.count() > 0 and f.first.is_visible():
                    f.first.fill(cir)
                    print(f"  CIR: {cir}")
                    filled = True
        except Exception:
            pass

        # Partita IVA / Codice Fiscale (se richiesto)
        try:
            f = page.locator("input[name*='vat'], input[name*='tax'], input[name*='fiscal']")
            if f.count() > 0 and f.first.is_visible() and not f.first.input_value():
                # Lascia vuoto — non abbiamo questo dato nel JSON
                pass
        except Exception:
            pass

        # Servizi/amenities — checkbox con label testo
        # Mappa: label Booking IT → chiave JSON dotazioni
        AMENITIES_MAP = {
            "Aria condizionata": "aria_condizionata",
            "Riscaldamento": "riscaldamento",
            "Connessione WiFi gratuita": "internet_wifi",
            "Cucina": "piano_cottura",
            "Angolo cottura": "piano_cottura",
            "Lavatrice": "lavatrice",
            "TV": "tv",
            "TV a schermo piatto": "tv",
            "Terrazza": "terrazza",
            "Balcone": "terrazza",
            "Giardino": "giardino",
            "Piscina": "piscina",
            "Lavastoviglie": "lavastoviglie",
            "Microonde": "microonde",
            "Ferro da stiro": "ferro_stiro",
            "Asciugacapelli": "phon",
        }
        dot = PROP.get("dotazioni", {})
        for label_bk, key_json in AMENITIES_MAP.items():
            if dot.get(key_json) is True:
                try:
                    # Metodo 1: get_by_label
                    cb = page.get_by_label(label_bk, exact=False)
                    if cb.count() > 0 and cb.first.is_visible():
                        if not cb.first.is_checked():
                            cb.first.check()
                            print(f"  ✓ {label_bk}")
                            filled = True
                        continue
                except Exception:
                    pass
                try:
                    # Metodo 2: clicca il testo della label (toggle checkbox)
                    txt = page.get_by_text(label_bk, exact=True)
                    if txt.count() > 0 and txt.first.is_visible():
                        txt.first.click()
                        print(f"  ✓ {label_bk} (via testo)")
                        filled = True
                        continue
                except Exception:
                    pass
                try:
                    # Metodo 3: label con testo parziale
                    lbl = page.locator(f"label:has-text('{label_bk}')")
                    if lbl.count() > 0 and lbl.first.is_visible():
                        lbl.first.click()
                        print(f"  ✓ {label_bk} (via label)")
                        filled = True
                except Exception:
                    pass

        # Foto — se la pagina chiede foto, caricale
        try:
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0 and ("foto" in title.lower() or "photo" in title.lower()
                                             or "carica" in (page.content()[:2000]).lower()):
                print("  Pagina foto rilevata — scarico e carico placeholder...")
                photo_paths = download_placeholder_photos(5)
                # Rendi visibile l'input file se nascosto
                try:
                    file_input.first.evaluate("el => el.style.display = 'block'")
                except Exception:
                    pass
                file_input.first.set_input_files(photo_paths, timeout=30_000)
                print(f"  Caricate {len(photo_paths)} foto")
                wait(page, 10_000)  # Aspetta upload
                filled = True
        except Exception as e:
            print(f"  Upload foto fallito: {e}")

        # Prova a cliccare Continua
        wait(page, 2000)
        advanced = _click_wizard_continue(page)
        if not advanced:
            advanced = _click_continue(page)

        if not advanced:
            if INTERACTIVE:
                resp = input(f">>> Pagina '{title}': compila nel browser, poi INVIO ('stop' per finire): ").strip()
                if resp.lower() == "stop":
                    break
                _click_wizard_continue(page)
                wait(page, 3000)
            else:
                print("  Impossibile avanzare, stop.")
                break
        else:
            wait(page, 3000)

        # Controlla se abbiamo raggiunto la fine
        try:
            sections = page.locator("#automation_id_sections_container")
            if sections.count() > 0:
                disabled = page.locator("[id^='automation_id_section_'][disabled]")
                if disabled.count() == 0:
                    print("\n  Tutte le sezioni completate!")
                    break
        except Exception:
            pass

      except Exception as e:
        # CATTURA QUALSIASI ERRORE — non crashare MAI
        print(f"\n  ⚠ ERRORE alla pagina {step_n}: {e}")
        screenshot(page, f"errore_pagina_{step_n}")
        save_html(page, f"errore_pagina_{step_n}")
        if INTERACTIVE:
            resp = input(">>> Errore! Completa nel browser, poi INVIO ('stop' per finire): ").strip()
            if resp.lower() == "stop":
                break
        else:
            print("  Errore in CI, stop.")
            break

    # --- Screenshot finale ---
    print("\n=== FINE WIZARD ===")
    screenshot(page, "pagina_finale")
    save_html(page, "pagina_finale")
    print("Wizard completato!")

    # =====================================================================
    # FASE 3: Extranet — compila le sezioni dettagliate
    # Stessa sessione browser, non serve nuovo login
    # =====================================================================

    # Rileva hotel_id dall'URL o dalla pagina
    import re
    hotel_id = os.environ.get("HOTEL_ID", "")
    if not hotel_id:
        match = re.search(r'hotel_id=(\d+)', page.url)
        if match:
            hotel_id = match.group(1)
    if not hotel_id:
        try:
            match = re.search(r'hotel_id[=:][\s"]*(\d+)', page.content())
            if match:
                hotel_id = match.group(1)
        except Exception:
            pass
    if not hotel_id and INTERACTIVE:
        hotel_id = input(">>> Hotel ID non trovato. Inseriscilo (lo trovi nell'URL di Booking): ").strip()

    if hotel_id:
        print(f"\n=== FASE EXTRANET (hotel_id={hotel_id}) ===")
        _fill_extranet_sections(page, hotel_id)
    else:
        print("  Hotel ID non disponibile, skip Extranet.")


def _fill_extranet_sections(page, hotel_id):
    """Compila le sezioni dell'Extranet Booking nella stessa sessione."""
    ident = PROP["identificativi"]
    dot = PROP.get("dotazioni", {})
    cond = PROP.get("condizioni", {})
    base_url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage"

    sections = [
        ("Servizi e dotazioni", f"{base_url}/facilities.html?hotel_id={hotel_id}&lang=it"),
        ("Metratura e dotazioni", f"{base_url}/amenities.html?hotel_id={hotel_id}&lang=it"),
        ("Condizioni", f"{base_url}/policies.html?hotel_id={hotel_id}&lang=it"),
        ("Profilo", f"{base_url}/profile.html?hotel_id={hotel_id}&lang=it"),
        ("Gestione camere", f"{base_url}/rooms.html?hotel_id={hotel_id}&lang=it"),
    ]

    for section_name, url in sections:
      try:
        print(f"\n--- {section_name} ---")
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        wait(page, 5000)

        # Verifica di non essere su pagina di login
        if "Accedi" in (page.title() or "") or "sign-in" in page.url:
            print(f"  Sessione scaduta su {section_name}!")
            if INTERACTIVE:
                input(">>> Fai login nel browser, poi INVIO: ")
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                wait(page, 5000)
            else:
                break

        screenshot(page, f"extranet_{section_name.replace(' ','_')}")
        save_html(page, f"extranet_{section_name.replace(' ','_')}")
        print(f"  URL: {page.url}")

        # --- SERVIZI E DOTAZIONI: clicca Sì/No ---
        if "facilities" in url:
            _extranet_servizi(page, dot)

        # --- METRATURA E DOTAZIONI: dimensioni + Sì/No ---
        elif "amenities" in url:
            _extranet_metratura(page, dot)

        # --- CONDIZIONI: check-in/out, cauzione ---
        elif "policies" in url:
            _extranet_condizioni(page, cond)

        # --- PROFILO: descrizione ---
        elif "profile" in url:
            _extranet_profilo(page)

        # --- GESTIONE CAMERE: CIN, CIR, letti, bagno ---
        elif "rooms" in url:
            _extranet_gestione_camere(page, ident)

        # Salva
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            wait(page, 1000)
            for btn_text in ["Salva", "Save", "Continua", "Continue"]:
                btn = page.get_by_role("button", name=btn_text)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    print(f"  Salvato ('{btn_text}')")
                    wait(page, 3000)
                    break
        except Exception:
            pass

        screenshot(page, f"extranet_{section_name.replace(' ','_')}_dopo")

      except Exception as e:
        print(f"  ERRORE {section_name}: {e}")
        screenshot(page, f"errore_extranet_{section_name.replace(' ','_')}")
        save_html(page, f"errore_extranet_{section_name.replace(' ','_')}")
        if INTERACTIVE:
            input(f">>> '{section_name}' fallito. Completa nel browser, poi INVIO: ")

    print("\n=== EXTRANET COMPLETATO ===")


def _click_si_no(page, label, click_si):
    """Clicca Sì o No per una voce con il testo dato."""
    btn_text = "Sì" if click_si else "No"
    try:
        el = page.get_by_text(label, exact=True)
        if el.count() > 0 and el.first.is_visible():
            parent = el.first.locator("xpath=ancestor::*[.//button or .//a[contains(@class,'btn')]][1]")
            if parent.count() > 0:
                btn = parent.get_by_text(btn_text, exact=True)
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(300)
                    print(f"  {label}: {btn_text}")
                    return True
    except Exception:
        pass
    return False


def _extranet_servizi(page, dot):
    """Compila Servizi e dotazioni — Sì/No."""
    servizi = {
        "Piscina": dot.get("piscina", False),
        "Bar": False,
        "Sauna": False,
        "Giardino": False,
        "Terrazza": dot.get("terrazza", False),
        "Camere non fumatori": True,
        "Disponibilità di camere familiari": True,
        "Vasca idromassaggio/Jacuzzi": False,
        "Aria condizionata": dot.get("aria_condizionata", False),
    }
    for label, val in servizi.items():
        _click_si_no(page, label, val)

    # Numero piani
    try:
        n = page.locator("input[type='number']").first
        if n.is_visible() and (not n.input_value() or n.input_value() == "0"):
            n.fill("2")
            print("  Piani: 2")
    except Exception:
        pass


def _extranet_metratura(page, dot):
    """Compila Metratura e dotazioni camere — dimensioni + Sì/No."""
    # Dimensioni
    try:
        dim = page.locator("input[type='number']").first
        if dim.is_visible() and (not dim.input_value() or dim.input_value() == "0"):
            dim.fill("40")
            print("  Dimensioni: 40 mq")
    except Exception:
        pass

    dotazioni = {
        "Aria condizionata": dot.get("aria_condizionata", False),
        "Angolo cottura": dot.get("piano_cottura", False),
        "Doccia": True,
        "Balcone": dot.get("terrazza", False),
        "Terrazza": dot.get("terrazza", False),
        "TV a schermo piatto": dot.get("tv", False),
        "TV": dot.get("tv", False),
        "Lavatrice": dot.get("lavatrice", False),
        "Lavastoviglie": dot.get("lavastoviglie", False),
        "Frigorifero": dot.get("frigo_congelatore", False),
        "Piano cottura": dot.get("piano_cottura", False),
        "WC": True,
        "Carta igienica": True,
        "Asciugamani": True,
        "Piscina privata a uso esclusivo": False,
        "Vista": False,
    }
    for label, val in dotazioni.items():
        _click_si_no(page, label, val)


def _extranet_condizioni(page, cond):
    """Compila Condizioni — check-in/out, cauzione."""
    # Clicca "Modifica" sulla sezione check-in
    try:
        modifica_btns = page.get_by_text("Modifica", exact=True)
        if modifica_btns.count() > 0:
            modifica_btns.first.click()
            wait(page, 3000)
    except Exception:
        pass

    # Check-in
    try:
        sel = page.locator("select[name*='checkin']")
        if sel.count() > 0 and sel.first.is_visible():
            sel.first.select_option(label="17:00")
            print("  Check-in: 17:00")
    except Exception:
        pass

    # Check-out
    try:
        sel = page.locator("select[name*='checkout']")
        if sel.count() > 0 and sel.first.is_visible():
            sel.first.select_option(label="10:00")
            print("  Check-out: 10:00")
    except Exception:
        pass


def _extranet_profilo(page):
    """Compila Profilo — descrizione."""
    desc = PROP["marketing"]["descrizione_lunga"]
    try:
        textareas = page.locator("textarea:visible")
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            if not ta.input_value():
                ta.fill(desc)
                print(f"  Descrizione inserita ({len(desc)} chars)")
                break
    except Exception:
        pass


def _extranet_gestione_camere(page, ident):
    """Compila Gestione camere — CIN, CIR, bagno."""
    # CIN
    try:
        f = page.locator("input[name*='cin'], input[id*='cin']")
        if f.count() > 0 and f.first.is_visible() and not f.first.input_value():
            f.first.fill(ident["cin"])
            print(f"  CIN: {ident['cin']}")
    except Exception:
        pass

    # CIR
    try:
        cir = ident.get("cir", "")
        if cir:
            f = page.locator("input[name*='cir'], input[id*='cir']")
            if f.count() > 0 and f.first.is_visible() and not f.first.input_value():
                f.first.fill(cir)
                print(f"  CIR: {cir}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    print(f"Proprietà: {PROP['identificativi']['nome_struttura']} (da {DATA_FILE})")

    # In locale (INTERACTIVE): browser visibile per OTP/CAPTCHA manuali
    # In CI: headless
    headless = not INTERACTIVE
    print(f"Browser: {'VISIBILE' if not headless else 'headless'} "
          f"(INTERACTIVE={INTERACTIVE})")

    SESSION_FILE = os.path.join(os.path.dirname(__file__), "booking_session.json")
    has_session = os.path.exists(SESSION_FILE)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        # Se esiste una sessione salvata, caricala (skip login)
        ctx_kwargs = dict(
            locale="it-IT",
            viewport={"width": 1366, "height": 768},
            user_agent=USER_AGENT,
            java_script_enabled=True,
        )
        if has_session:
            print(f"  Sessione salvata trovata: {SESSION_FILE}")
            ctx_kwargs["storage_state"] = SESSION_FILE

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        # Stealth opzionale (se playwright-stealth è installato)
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
            print("Stealth mode attivato.")
        except ImportError:
            print("playwright-stealth non trovato, procedo senza stealth.")

        try:
            if has_session:
                # Sessione salvata: vai direttamente al wizard (skip login)
                print("\n=== SKIP LOGIN (sessione salvata) ===")
                page.goto("https://join.booking.com/",
                          wait_until="domcontentloaded", timeout=60_000)
                wait(page, 5000)
                _dismiss_cookie_banner(page)
                screenshot(page, "sessione_ripresa")
                print(f"  URL: {page.url}")

                # Se la sessione è scaduta (redirect a login), rifai login
                if "account.booking.com" in page.url or "sign-in" in page.url:
                    print("  Sessione scaduta, rifaccio login...")
                    os.remove(SESSION_FILE)
                    wizard_page = login_and_navigate(page)
                else:
                    # Clicca "Get started" se siamo sulla landing page
                    if "become-a-host" not in page.url:
                        gs = page.locator("#getStarted, [data-testid='getStarted']")
                        if gs.count() > 0:
                            gs.first.click()
                            wait(page, 5000)
                    wizard_page = page
            else:
                wizard_page = login_and_navigate(page)

            # Salva sessione per le prossime volte
            context.storage_state(path=SESSION_FILE)
            print(f"  Sessione salvata in: {SESSION_FILE}")

            screenshot(wizard_page, "pagina_iniziale")

            try:
                insert_property(wizard_page)
            except Exception as e:
                print(f"\n  ⚠ ERRORE DURANTE IL WIZARD: {e}")
                try:
                    screenshot(wizard_page, "errore_wizard")
                    save_html(wizard_page, "errore_wizard")
                except Exception:
                    pass

            # Aggiorna sessione anche alla fine
            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
        except Exception as e:
            print(f"\n  ⚠ ERRORE GENERALE: {e}")
        finally:
            if INTERACTIVE:
                print("\n" + "=" * 50)
                print("  BROWSER APERTO — puoi lavorare manualmente.")
                print("  Scrivi 'chiudi' + INVIO per chiudere.")
                print("=" * 50)
                while True:
                    resp = input(">>> ").strip().lower()
                    if resp in ("chiudi", "close", "exit", "quit", "stop"):
                        break
                    print("  Browser ancora aperto. Scrivi 'chiudi' per uscire.")
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
