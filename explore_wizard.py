"""
explore_wizard.py — Esplorazione wizard CaseVacanza.it

NON compila nulla. Solo:
1. Login
2. Naviga a /properties/new
3. Per ogni step: screenshot + HTML + estrazione elementi form
4. Prova a cliccare "Continua" senza compilare
5. Salva report completo in screenshots/WIZARD_MAP.json

Eseguire: CASEVACANZA_EMAIL=... CASEVACANZA_PASSWORD=... python explore_wizard.py
"""

import json
import os

from playwright.sync_api import sync_playwright

EMAIL = os.environ["CASEVACANZA_EMAIL"]
PASSWORD = os.environ["CASEVACANZA_PASSWORD"]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SCREENSHOT_DIR = "screenshots"
step_counter = 0


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
    print(f"  HTML: {path}")


def wait(page, ms=5000):
    page.wait_for_timeout(ms)


# ---------------------------------------------------------------------------
# Login (copiato da casevacanza_uploader.py)
# ---------------------------------------------------------------------------

def _dismiss_cookie_popup(page):
    for btn_text in ["Ok", "Accetta", "Accept", "Accetto", "Ho capito",
                     "Accetta tutti", "Accept all", "Agree", "OK"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=True)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                print(f"  Popup cookie chiuso ('{btn_text}')")
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass
    try:
        btn = page.locator("button", has_text="Ok")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            print("  Popup cookie chiuso (fallback 'Ok')")
            page.wait_for_timeout(1000)
            return
    except Exception:
        pass
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
    print("Login CaseVacanza.it...")
    page.goto("https://my.casevacanza.it", timeout=60_000)
    wait(page, 5000)
    screenshot(page, "login_page")
    save_html(page, "login_page")
    print(f"  URL login: {page.url}")

    _dismiss_cookie_popup(page)

    # Iframe check (Keycloak SSO)
    iframes = page.frames
    login_frame = page
    if len(iframes) > 1:
        for frame in iframes:
            try:
                if frame.locator("input[type='password']").count() > 0:
                    login_frame = frame
                    print(f"  Login in iframe: {frame.url}")
                    break
            except Exception:
                pass

    INPUT_SELECTOR = (
        "#username, #email, input[name='username'], input[name='email'], "
        "input[type='email'], input[type='text'], input[type='password']"
    )
    try:
        login_frame.wait_for_selector(INPUT_SELECTOR, timeout=30_000)
    except Exception:
        print("  [WARN] Campi non visibili, provo state=attached...")
        _dismiss_cookie_popup(page)
        try:
            login_frame.wait_for_selector(INPUT_SELECTOR, timeout=15_000, state="attached")
        except Exception:
            screenshot(page, "login_timeout")
            save_html(page, "login_timeout")
            raise RuntimeError("Campi login non trovati")
    wait(page, 2000)

    # Email
    email_field = None
    for sel in ["#username", "#email", "input[name='username']", "input[name='email']",
                "input[name='loginname']", "input[type='email']", "input[type='text']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            email_field = loc.first
            print(f"  Campo email: {sel}")
            break
    if email_field is None:
        for lbl in ["Email", "Username", "E-mail", "Indirizzo email"]:
            loc = login_frame.get_by_label(lbl)
            if loc.count() > 0:
                email_field = loc.first
                break
    if email_field is None:
        raise RuntimeError("Campo email non trovato")
    email_field.fill(EMAIL)
    wait(page, 1000)

    # Password
    pw_field = None
    for sel in ["#password", "input[name='password']", "input[type='password']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            pw_field = loc.first
            print(f"  Campo password: {sel}")
            break
    if pw_field is None:
        raise RuntimeError("Campo password non trovato")
    pw_field.fill(PASSWORD)
    wait(page, 1000)

    # Login button
    login_btn = None
    for sel in ["#kc-login", "button[type='submit']", "input[type='submit']"]:
        loc = login_frame.locator(sel)
        if loc.count() > 0:
            login_btn = loc.first
            break
    if login_btn is None:
        for lbl in ["Accedi", "Login", "Sign in", "Entra"]:
            loc = login_frame.get_by_text(lbl, exact=True)
            if loc.count() > 0:
                login_btn = loc.first
                break
    if login_btn is None:
        raise RuntimeError("Bottone login non trovato")
    login_btn.click()
    wait(page, 8000)
    screenshot(page, "dopo_login")
    print(f"  URL dopo login: {page.url}")
    print("Login OK.")


def dismiss_popups(page):
    wait(page, 3000)
    ok_btn = page.locator("button", has_text="Ok")
    if ok_btn.count() > 0:
        ok_btn.first.click()
        print("Popup cookies chiuso.")
        wait(page, 1000)
    # Chiudi TUTTI i ReactModal overlay (possono essere multipli)
    for attempt in range(5):
        modal_overlay = page.locator(".ReactModal__Overlay")
        if modal_overlay.count() == 0:
            break
        print(f"  ReactModal trovato (tentativo {attempt+1}), chiudo...")
        # Prova bottone di chiusura
        close_btn = modal_overlay.locator("button")
        if close_btn.count() > 0:
            try:
                close_btn.first.click(timeout=2000)
            except Exception:
                pass
        # Fallback: rimuovi via JS
        page.evaluate("""() => {
            document.querySelectorAll('.ReactModal__Overlay').forEach(el => el.remove());
            document.querySelectorAll('.ReactModal__Body--open').forEach(el => {
                el.classList.remove('ReactModal__Body--open');
            });
        }""")
        wait(page, 1000)
    if page.locator(".ReactModal__Overlay").count() == 0:
        print("ReactModal chiuso.")


def navigate_to_add_property(page):
    # Rimuovi eventuali modal residui prima di cliccare
    page.evaluate("""() => {
        document.querySelectorAll('.ReactModal__Overlay').forEach(el => el.remove());
        document.querySelectorAll('.ReactModal__Body--open').forEach(el => {
            el.classList.remove('ReactModal__Body--open');
        });
    }""")
    wait(page, 500)
    page.locator("a", has_text="Proprietà").first.click()
    wait(page)
    print("Navigato a Proprietà.")
    page.get_by_text("Aggiungi una proprietà").click()
    wait(page)
    print("Navigato a Aggiungi una proprietà.")


# ---------------------------------------------------------------------------
# Esplorazione wizard
# ---------------------------------------------------------------------------

def extract_form_elements(page, step_num):
    """Estrae TUTTI gli elementi interattivi della pagina corrente."""
    return page.evaluate("""(stepNum) => {
        const elements = [];
        const seen = new Set();

        // 1) Input, select, textarea
        document.querySelectorAll('input, select, textarea').forEach(el => {
            const key = el.tagName + '|' + (el.name || '') + '|' + (el.id || '') + '|' + (el.type || '');
            if (seen.has(key)) return;
            seen.add(key);

            let label = '';
            if (el.id) {
                const lbl = document.querySelector('label[for="' + el.id + '"]');
                if (lbl) label = lbl.textContent.trim();
            }
            if (!label) {
                const closest = el.closest('label');
                if (closest) label = closest.textContent.trim();
            }
            // Fallback: look at preceding sibling or parent text
            if (!label && el.parentElement) {
                const prev = el.previousElementSibling;
                if (prev && prev.tagName !== 'INPUT') {
                    label = prev.textContent.trim();
                }
            }

            elements.push({
                category: 'form-field',
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                label: (label || '').substring(0, 120),
                dataTest: el.getAttribute('data-test') || '',
                role: el.getAttribute('role') || '',
                ariaLabel: el.getAttribute('aria-label') || '',
                classes: (el.className || '').toString().substring(0, 120),
                visible: el.offsetParent !== null,
                value: (el.value || '').substring(0, 50),
                required: el.required || false,
                disabled: el.disabled || false,
            });

            // If select, also dump options
            if (el.tagName === 'SELECT') {
                const opts = [];
                for (const o of el.options) {
                    opts.push({ value: o.value, text: o.text.substring(0, 80) });
                }
                elements.push({
                    category: 'select-options',
                    forName: el.name || el.id || '',
                    options: opts.slice(0, 50),
                });
            }
        });

        // 2) role=checkbox, role=switch
        document.querySelectorAll('[role="checkbox"], [role="switch"]').forEach(el => {
            elements.push({
                category: 'role-toggle',
                tag: el.tagName,
                role: el.getAttribute('role'),
                text: (el.textContent || '').trim().substring(0, 120),
                ariaChecked: el.getAttribute('aria-checked'),
                dataTest: el.getAttribute('data-test') || '',
                classes: (el.className || '').toString().substring(0, 120),
                visible: el.offsetParent !== null,
            });
        });

        // 3) Buttons
        document.querySelectorAll('button, [role="button"]').forEach(el => {
            const text = (el.textContent || '').trim().substring(0, 100);
            if (!text) return;
            elements.push({
                category: 'button',
                tag: el.tagName,
                text: text,
                dataTest: el.getAttribute('data-test') || '',
                type: el.getAttribute('type') || '',
                disabled: el.disabled || false,
                visible: el.offsetParent !== null,
                classes: (el.className || '').toString().substring(0, 120),
            });
        });

        // 4) All data-test elements
        const dataTestEls = [];
        document.querySelectorAll('[data-test]').forEach(el => {
            dataTestEls.push({
                tag: el.tagName,
                dataTest: el.getAttribute('data-test'),
                text: (el.textContent || '').trim().substring(0, 80),
                role: el.getAttribute('role') || '',
                classes: (el.className || '').toString().substring(0, 80),
            });
        });

        // 5) Counter widgets (the +/- buttons for guests, rooms, beds)
        const counters = [];
        document.querySelectorAll('[data-test*="counter"], [class*="counter"], [class*="Counter"]').forEach(el => {
            counters.push({
                tag: el.tagName,
                dataTest: el.getAttribute('data-test') || '',
                text: (el.textContent || '').trim().substring(0, 80),
                classes: (el.className || '').toString().substring(0, 80),
                parentText: (el.parentElement?.textContent || '').trim().substring(0, 80),
            });
        });

        // 6) Heading
        const heading = (document.querySelector('h1, h2, h3') || {}).textContent || '';

        // 7) Page title
        const title = document.title || '';

        // 8) Any visible text blocks that might be labels/instructions
        const textBlocks = [];
        document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, [class*="title"], [class*="label"], [class*="heading"]').forEach(el => {
            const t = (el.textContent || '').trim();
            if (t && t.length > 2 && t.length < 200 && el.offsetParent !== null) {
                textBlocks.push({
                    tag: el.tagName,
                    text: t.substring(0, 150),
                    classes: (el.className || '').toString().substring(0, 80),
                });
            }
        });

        return {
            step: stepNum,
            url: location.href,
            title: title,
            heading: heading.trim().substring(0, 200),
            formFields: elements,
            dataTestElements: dataTestEls,
            counterWidgets: counters,
            textBlocks: textBlocks.slice(0, 30),
        };
    }""", step_num)


def get_page_signature(page):
    """Ritorna una firma della pagina corrente per rilevare avanzamento."""
    try:
        return page.evaluate("""() => {
            const h = (document.querySelector('h1, h2, h3') || {}).textContent || '';
            // Also check for unique form content as some steps have same heading
            const inputs = document.querySelectorAll('input, select, textarea');
            const inputSig = Array.from(inputs).map(i =>
                (i.getAttribute('data-test') || i.name || i.type || '')).join(',');
            return {
                url: location.href,
                heading: h.trim().substring(0, 200),
                inputSignature: inputSig.substring(0, 500),
            };
        }""")
    except Exception:
        return {"url": page.url, "heading": "", "inputSignature": ""}


def print_step_summary(data):
    """Stampa un riassunto leggibile dello step."""
    print(f"\n{'='*60}")
    print(f"STEP {data['step']}")
    print(f"  URL: {data['url']}")
    print(f"  Heading: {data['heading']}")
    print(f"  Title: {data['title']}")

    form_fields = [e for e in data.get("formFields", []) if e.get("category") == "form-field"]
    toggles = [e for e in data.get("formFields", []) if e.get("category") == "role-toggle"]
    buttons = [e for e in data.get("formFields", []) if e.get("category") == "button"]

    print(f"  Form fields: {len(form_fields)}")
    for f in form_fields:
        vis = "V" if f.get("visible") else "H"
        req = "*" if f.get("required") else ""
        dt = f" data-test='{f['dataTest']}'" if f.get("dataTest") else ""
        print(f"    [{vis}] <{f['tag']} type='{f.get('type', '')}' "
              f"name='{f.get('name', '')}' id='{f.get('id', '')}'{dt}> "
              f"label='{f.get('label', '')[:60]}' placeholder='{f.get('placeholder', '')[:40]}'{req}")

    if toggles:
        print(f"  Checkboxes/switches: {len(toggles)}")
        for t in toggles:
            print(f"    [{t.get('role')}] {t.get('text', '')[:60]} "
                  f"checked={t.get('ariaChecked')}")

    if buttons:
        print(f"  Buttons: {len(buttons)}")
        for b in buttons:
            vis = "V" if b.get("visible") else "H"
            dt = f" data-test='{b['dataTest']}'" if b.get("dataTest") else ""
            print(f"    [{vis}] '{b.get('text', '')[:50]}'{dt}")

    dt_els = data.get("dataTestElements", [])
    if dt_els:
        print(f"  data-test elements: {len(dt_els)}")
        for d in dt_els:
            print(f"    <{d['tag']} data-test='{d['dataTest']}'> "
                  f"text='{d.get('text', '')[:50]}'")

    counters = data.get("counterWidgets", [])
    if counters:
        print(f"  Counter widgets: {len(counters)}")
        for c in counters:
            print(f"    <{c['tag']} data-test='{c.get('dataTest', '')}'> "
                  f"text='{c.get('text', '')[:50]}' parent='{c.get('parentText', '')[:50]}'")

    texts = data.get("textBlocks", [])
    if texts:
        print(f"  Text blocks: {len(texts)}")
        for t in texts[:10]:
            print(f"    <{t['tag']}> '{t['text'][:80]}'")

    print(f"{'='*60}\n")


def try_advance(page):
    """Prova a cliccare save-button. Ritorna True se il wizard avanza."""
    before = get_page_signature(page)

    save_btn = page.locator('[data-test="save-button"]')
    if save_btn.count() > 0 and save_btn.first.is_visible():
        print("  Cliccando save-button...")
        save_btn.first.click()
        wait(page, 5000)
    else:
        # Fallback: cerca bottoni "Continua", "Avanti", "Salva"
        for text in ["Continua", "Avanti", "Salva", "Continue", "Next", "Save"]:
            try:
                btn = page.get_by_role("button", name=text)
                if btn.count() > 0 and btn.first.is_visible():
                    print(f"  Cliccando '{text}'...")
                    btn.first.click()
                    wait(page, 5000)
                    break
            except Exception:
                continue
        else:
            print("  Nessun bottone avanti trovato")
            return False

    after = get_page_signature(page)

    advanced = (
        before["url"] != after["url"]
        or before["heading"] != after["heading"]
        or before["inputSignature"] != after["inputSignature"]
    )

    # Check for validation errors
    errors = page.evaluate("""() => {
        const errs = [];
        document.querySelectorAll(
            '[class*="error" i], [class*="invalid" i], [role="alert"]'
        ).forEach(el => {
            const t = (el.textContent || '').trim();
            if (t && el.offsetParent !== null) {
                errs.push(t.substring(0, 120));
            }
        });
        return errs;
    }""")
    if errors:
        print(f"  Errori di validazione: {errors}")

    return advanced


def main():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    all_steps = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(user_agent=USER_AGENT)

        try:
            # --- Login e navigazione ---
            login(page)
            dismiss_popups(page)
            navigate_to_add_property(page)
            screenshot(page, "wizard_start")
            save_html(page, "wizard_start")

            # --- Esplorazione step-by-step ---
            max_steps = 35
            consecutive_blocks = 0

            for step_num in range(1, max_steps + 1):
                print(f"\n>>> Esplorazione step {step_num} <<<")

                # Cattura stato corrente
                screenshot(page, f"explore_{step_num:02d}")
                save_html(page, f"explore_{step_num:02d}")
                data = extract_form_elements(page, step_num)
                all_steps.append(data)
                print_step_summary(data)

                # Prova ad avanzare
                advanced = try_advance(page)
                if advanced:
                    consecutive_blocks = 0
                    screenshot(page, f"explore_{step_num:02d}_after_advance")
                    print(f"  >>> AVANZATO (step {step_num} -> {step_num + 1})")
                else:
                    consecutive_blocks += 1
                    screenshot(page, f"explore_{step_num:02d}_blocked")
                    save_html(page, f"explore_{step_num:02d}_blocked")
                    print(f"  >>> BLOCCATO a step {step_num} "
                          f"(tentativo {consecutive_blocks})")

                    if consecutive_blocks >= 2:
                        print(f"\n*** WIZARD BLOCCATO DOPO {step_num} STEP ***")
                        print("Lo step richiede compilazione per avanzare.")
                        print("Eseguire il workflow per scaricare screenshot e HTML.")
                        break

            # --- Salva report ---
            report_path = f"{SCREENSHOT_DIR}/WIZARD_MAP.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(all_steps, f, indent=2, ensure_ascii=False)
            print(f"\nReport salvato: {report_path}")
            print(f"Step esplorati: {len(all_steps)}")

        finally:
            try:
                screenshot(page, "final_state")
                save_html(page, "final_state")
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
