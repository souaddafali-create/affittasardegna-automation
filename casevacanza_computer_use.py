"""Agente Computer Use per CaseVacanza.it.

Pilota un browser reale via Playwright lasciando che Claude (Sonnet 4.6, Computer
Use tool) decida cosa cliccare guardando gli screenshot. Niente selettori CSS
hardcoded: l'agente legge lo schermo come un umano.

Uso:
    python casevacanza_computer_use.py [path/al/JSON]

Env vars richieste:
    CV_EMAIL, CV_PASSWORD       — credenziali CaseVacanza
    ANTHROPIC_API_KEY           — API key Anthropic

Default JSON: Casa_Adelasia_A_DATI.json (override via primo argomento CLI).
Salva uno screenshot per ogni azione del modello in screenshots/cu_stepNNN.png.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic
from playwright.sync_api import sync_playwright

# --- Config ---
SCREEN_W, SCREEN_H = 1280, 800
SCREENSHOT_DIR = Path("screenshots")
MODEL = "claude-sonnet-4-6"  # 'claude-sonnet-4-7' non esiste; questo è l'ultimo Sonnet
MAX_TURNS = 200  # cintura di sicurezza contro loop costosi
COMPUTER_BETA = "computer-use-2025-01-24"
# www.casevacanza.it non risolve dal runner GitHub Actions (vedi BOT_MEMORY 2026-05-05).
LOGIN_URL = "https://user.casevacanza.it/login"

# --- Carica dati proprietà ---
data_file = sys.argv[1] if len(sys.argv) > 1 else "Casa_Adelasia_A_DATI.json"
with open(data_file, encoding="utf-8") as fh:
    PROP = json.load(fh)

CV_EMAIL = os.environ["CV_EMAIL"]
CV_PASSWORD = os.environ["CV_PASSWORD"]
SCREENSHOT_DIR.mkdir(exist_ok=True)

print(f"=== CaseVacanza Computer Use Agent ===")
print(f"Proprietà: {PROP['identificativi']['nome_struttura']}")
print(f"JSON: {data_file}")
print(f"Modello: {MODEL}")
print(f"Display: {SCREEN_W}x{SCREEN_H}")
print(f"Max turni: {MAX_TURNS}")
print(f"=====================================\n")

# --- Browser via Playwright (solo come display) ---
playwright = sync_playwright().start()
browser = playwright.chromium.launch(
    headless=False,
    args=[f"--window-size={SCREEN_W},{SCREEN_H}", "--disable-blink-features=AutomationControlled"],
)
context = browser.new_context(viewport={"width": SCREEN_W, "height": SCREEN_H})
page = context.new_page()
page.set_default_timeout(30_000)

# Pagina di partenza: blank, poi sarà l'agente a navigare
page.goto("about:blank")


# --- Helper: screenshot e salvataggio ---
def screenshot_bytes() -> bytes:
    return page.screenshot(full_page=False)


def screenshot_b64() -> str:
    return base64.standard_b64encode(screenshot_bytes()).decode("ascii")


def save_screenshot(step_idx: int, action: str) -> None:
    name = action.replace("/", "_")[:40]
    path = SCREENSHOT_DIR / f"cu_step{step_idx:03d}_{name}.png"
    page.screenshot(path=str(path))


# --- Mappa key Anthropic computer-use → Playwright ---
_KEY_MAP = {
    "Return": "Enter",
    "Page_Down": "PageDown",
    "Page_Up": "PageUp",
    "BackSpace": "Backspace",
    "Escape": "Escape",
    "ctrl": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Meta",
    "cmd": "Meta",
}


def _translate_key(combo: str) -> str:
    parts = [p.strip() for p in combo.split("+")]
    return "+".join(_KEY_MAP.get(p, p) for p in parts)


# --- Esegue un'azione computer use sul browser ---
def execute_computer_action(action_input: dict) -> str | None:
    """Esegue l'azione richiesta dal modello. Ritorna eventuale messaggio di errore
    da rimandare al modello (None se tutto ok)."""
    action = action_input.get("action")
    try:
        if action == "screenshot":
            return None  # lo screenshot viene scattato a fine turno comunque

        if action in ("left_click", "right_click", "middle_click"):
            x, y = action_input["coordinate"]
            btn = {"left_click": "left", "right_click": "right", "middle_click": "middle"}[action]
            page.mouse.click(x, y, button=btn)

        elif action == "double_click":
            x, y = action_input["coordinate"]
            page.mouse.dblclick(x, y)

        elif action == "triple_click":
            x, y = action_input["coordinate"]
            page.mouse.click(x, y, click_count=3)

        elif action == "mouse_move":
            x, y = action_input["coordinate"]
            page.mouse.move(x, y)

        elif action == "left_click_drag":
            sx, sy = action_input["start_coordinate"]
            ex, ey = action_input["coordinate"]
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move(ex, ey, steps=10)
            page.mouse.up()

        elif action == "type":
            page.keyboard.type(action_input["text"], delay=20)

        elif action == "key":
            page.keyboard.press(_translate_key(action_input["text"]))

        elif action == "wait":
            duration = float(action_input.get("duration", 1))
            time.sleep(min(duration, 10))

        elif action == "scroll":
            x, y = action_input.get("coordinate", [SCREEN_W // 2, SCREEN_H // 2])
            direction = action_input["scroll_direction"]
            amount = int(action_input.get("scroll_amount", 3)) * 100
            wheel = {"up": (0, -amount), "down": (0, amount),
                     "left": (-amount, 0), "right": (amount, 0)}[direction]
            page.mouse.move(x, y)
            page.mouse.wheel(*wheel)

        elif action == "cursor_position":
            return None  # nessuna azione, rispondiamo solo con screenshot

        else:
            return f"Azione sconosciuta: {action}"

        # Lascia che la UI si stabilizzi prima del prossimo screenshot
        page.wait_for_timeout(500)
        return None

    except Exception as exc:
        return f"Errore eseguendo {action}: {exc}"


# --- Prompt per il modello ---
SYSTEM_PROMPT = """Sei un agente che pubblica una proprietà di affitto breve sul portale CaseVacanza.it.

Pilota il browser come farebbe un umano: scatta screenshot, clicca, scrivi, salva. Tutti i dati provengono dal JSON fornito nel primo messaggio. NON inventare nulla che non sia nel JSON.

REGOLE FONDAMENTALI:
1. La fonte di verità è il JSON. Se un dato non c'è, lascia il campo vuoto.
2. Se una dotazione è false nel JSON, NON spuntarla.
3. Le tariffe stagionali (listino_prezzi) sono manuali — saltale; inserisci solo il prezzo base.
4. NON cliccare il bottone finale "Pubblica/Invia" della proprietà: fermati alla pagina di riepilogo prima della pubblicazione, scatta screenshot e dichiara fatto.
5. Dopo ogni azione importante (cambio pagina, salvataggio step) scatta screenshot per verificare.

LOG: prima di ogni gruppo di azioni scrivi una riga in italiano del tipo "Step X: <cosa sto facendo>" così l'utente capisce dove sei. Esempi: "Step 5: Compilo indirizzo", "Step 12: Carico foto dal CDN".

GESTIONE ERRORI: se trovi un campo in errore (es. validazione rossa), descrivi cosa vedi nello screenshot e prova a correggere. Se non riesci dopo 2 tentativi, scatta screenshot, dichiaralo e fermati.

OUTPUT FINALE: quando sei alla pagina riepilogo prima della pubblicazione, scrivi: "✅ Wizard completato. Pronto per pubblicazione manuale da Souad."
"""


def _summary_for_log(prop: dict) -> str:
    ident = prop.get("identificativi", {})
    comp = prop.get("composizione", {})
    return (
        f"{ident.get('nome_struttura')} ({ident.get('tipo_struttura')}) - "
        f"{ident.get('indirizzo')}, {ident.get('comune')} ({ident.get('provincia')}) - "
        f"{comp.get('max_ospiti')} ospiti, {comp.get('camere')} camere"
    )


initial_screenshot = screenshot_b64()
initial_text = f"""Devi pubblicare questa proprietà su {LOGIN_URL}.

CREDENZIALI:
- Email: {CV_EMAIL}
- Password: {CV_PASSWORD}

DATI PROPRIETÀ ({_summary_for_log(PROP)}):

```json
{json.dumps(PROP, indent=2, ensure_ascii=False)}
```

PROCEDURA:
1. Vai su {LOGIN_URL} (digita ESATTAMENTE questo URL nella barra indirizzi del browser — NON usare www.casevacanza.it perché non risolve dal runner).
2. Login con le credenziali sopra.
3. Naviga al wizard "Aggiungi proprietà" / "Aggiungi un alloggio".
4. Compila ogni step usando SOLO i dati dal JSON:
   - tipo struttura (identificativi.tipo_struttura)
   - indirizzo completo (identificativi.indirizzo + cap + comune + provincia)
   - ospiti, camere, bagni (composizione)
   - letti specifici (composizione.letti — tipo + quantità)
   - foto: scarica e carica dagli URL in marketing.foto_urls
   - servizi/dotazioni: spunta SOLO quelle true in dotazioni
   - titolo e descrizione (marketing.titolo, marketing.descrizione_lunga)
   - prezzo base (condizioni.prezzo_base) — IGNORA condizioni.listino_prezzi
   - sincronizzazione iCal (condizioni.ical_url)
   - CIN e CIR (identificativi.cin, identificativi.cir) se presenti
5. Fermati alla pagina riepilogo prima della pubblicazione.

Inizia con uno screenshot dello stato attuale per orientarti, poi naviga al sito.
"""

messages = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": initial_text},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": initial_screenshot,
                },
            },
        ],
    }
]

# --- Loop agente ---
client = Anthropic()
tools = [
    {
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": SCREEN_W,
        "display_height_px": SCREEN_H,
        "display_number": 1,
    }
]

step_idx = 0
total_input_tokens = 0
total_output_tokens = 0


def _describe_block(block) -> str:
    """Riassume un content block per debug (solo type + lunghezze, no contenuto)."""
    btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
    if btype == "text":
        text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
        return f"text(len={len(text or '')})"
    if btype == "image":
        return "image"
    if btype == "tool_use":
        inp = block.get("input", {}) if isinstance(block, dict) else getattr(block, "input", {})
        return f"tool_use(input_keys={len(inp or {})})"
    if btype == "tool_result":
        sub = block.get("content", []) if isinstance(block, dict) else getattr(block, "content", [])
        return f"tool_result(blocks={len(sub) if isinstance(sub, list) else 1})"
    return str(btype)


try:
    for turn in range(1, MAX_TURNS + 1):
        # Debug: struttura content blocks dell'ultimo message prima della chiamata API
        if messages:
            _last = messages[-1]
            _content = _last.get("content", [])
            if isinstance(_content, list):
                _structure = [_describe_block(b) for b in _content]
            else:
                _structure = [f"raw({type(_content).__name__})"]
            print(f"  [debug] turn {turn} last_msg role={_last.get('role')} blocks={_structure}")

        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=tools,
            messages=messages,
            system=SYSTEM_PROMPT,
            betas=[COMPUTER_BETA],
        )

        # Aggiorna metriche
        total_input_tokens += response.usage.input_tokens or 0
        total_output_tokens += response.usage.output_tokens or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        # Stampa il pensiero/testo del modello (in italiano grazie al system prompt)
        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"💬 {block.text.strip()}")

        if response.stop_reason == "end_turn":
            print(f"\n✅ Agente terminato (end_turn) al turno {turn}.")
            break

        if response.stop_reason != "tool_use":
            print(f"\n⚠️ Stop reason inatteso: {response.stop_reason}. Esco.")
            break

        # Re-invia tutto il content come parte della history (preserva tool_use blocks).
        # Filtra i text block vuoti: l'API Anthropic rifiuta {"type":"text","text":""}.
        filtered_content = [
            block for block in response.content
            if not (block.type == "text" and not (block.text or "").strip())
        ]
        if not filtered_content:
            print("⚠️ Agent ha restituito messaggio vuoto, stop loop")
            break
        messages.append({"role": "assistant", "content": filtered_content})

        # Esegui ogni tool_use e raccogli i tool_result
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name != "computer":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": [{"type": "text", "text": f"Tool sconosciuto: {block.name}"}],
                    "is_error": True,
                })
                continue

            step_idx += 1
            action = block.input.get("action", "?")
            extra = ""
            if "coordinate" in block.input:
                extra = f" @ {block.input['coordinate']}"
            elif "text" in block.input:
                # Maschera la password nei log
                txt = block.input["text"]
                if CV_PASSWORD and CV_PASSWORD in txt:
                    txt = txt.replace(CV_PASSWORD, "***")
                extra = f" testo='{txt[:60]}'"
            print(f"  → step {step_idx}: {action}{extra}")

            err = execute_computer_action(block.input)
            save_screenshot(step_idx, action)

            # Risposta al modello: screenshot aggiornato (+ messaggio errore se c'è)
            content_blocks: list[dict] = []
            if err:
                content_blocks.append({"type": "text", "text": err})
                print(f"     ❌ {err}")
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot_b64(),
                },
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content_blocks,
                "is_error": bool(err),
            })

        messages.append({"role": "user", "content": tool_results})

        # Diagnostica token ogni 10 turni
        if turn % 10 == 0:
            print(f"  [token cumulati] input={total_input_tokens} output={total_output_tokens} "
                  f"cache_read={cache_read} cache_write={cache_write}")

    else:
        print(f"\n⚠️ Limite di {MAX_TURNS} turni raggiunto. Esco.")

finally:
    print(f"\n=== Riassunto run ===")
    print(f"Turni eseguiti: {turn}")
    print(f"Step eseguiti: {step_idx}")
    print(f"Token input cumulati: {total_input_tokens}")
    print(f"Token output cumulati: {total_output_tokens}")
    # Costo Sonnet 4.6: $3/M input, $15/M output (cache read/write a parte)
    cost = total_input_tokens * 3 / 1_000_000 + total_output_tokens * 15 / 1_000_000
    print(f"Costo stimato (no cache): ~${cost:.3f}")
    page.screenshot(path=str(SCREENSHOT_DIR / "cu_FINAL.png"))
    context.close()
    browser.close()
    playwright.stop()
