#!/usr/bin/env python3
"""
Test suite per il WhatsApp bot AffittaSardegna.

Test divisi in 2 sezioni:
1. Unit test (no API, no network) — sempre eseguiti
2. Claude API integration test — solo se ANTHROPIC_API_KEY è impostata

Uso:
    python whatsapp_bot/test_bot.py                          # solo unit test
    ANTHROPIC_API_KEY=sk-... python whatsapp_bot/test_bot.py  # tutti i test
"""

import json
import os
import sys
from pathlib import Path

# Prova httpx (più moderno), fallback su urllib (stdlib)
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_HTTPX = False


SCRIPT_DIR = Path(__file__).parent
SYSTEM_PROMPT_FILE = SCRIPT_DIR / "system_prompt.txt"

# ===================================================================
# UNIT TESTS (no network, always run)
# ===================================================================


def test_system_prompt_exists():
    """Verifica che system_prompt.txt esista e non sia vuoto."""
    assert SYSTEM_PROMPT_FILE.exists(), "system_prompt.txt non trovato"
    content = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    assert len(content) > 500, f"system_prompt.txt troppo corto: {len(content)} chars"
    return "system_prompt.txt esiste e ha contenuto"


def test_system_prompt_has_required_sections():
    """Verifica che il system prompt contenga tutte le sezioni necessarie."""
    content = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    required = [
        "FLUSSO 1",
        "FLUSSO 2",
        "FLUSSO 3",
        "FLUSSO 4",
        "FLUSSO 5",
        "FORMATO RISPOSTA",
        "needs_human",
        "REGOLE ASSOLUTE",
        "book.affittasardegna.it",
        "Il Faro",
        "Villa La Vela",
        "FLUSSO ENGLISH",
    ]
    missing = [s for s in required if s not in content]
    assert not missing, f"Sezioni mancanti nel system prompt: {missing}"
    return "Tutte le sezioni richieste presenti"


def test_config_json_valid():
    """Verifica che config.json sia JSON valido con i campi necessari."""
    config_file = SCRIPT_DIR / "config.json"
    assert config_file.exists(), "config.json non trovato"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    assert "company" in config, "Manca campo 'company'"
    assert "whatsapp" in config, "Manca campo 'whatsapp'"
    assert "claude_api" in config, "Manca campo 'claude_api'"
    assert "flows" in config, "Manca campo 'flows'"
    return "config.json valido con tutti i campi"


def test_n8n_workflow_valid():
    """Verifica che n8n_workflow.json sia JSON valido con fallback."""
    workflow_file = SCRIPT_DIR / "n8n_workflow.json"
    assert workflow_file.exists(), "n8n_workflow.json non trovato"
    workflow = json.loads(workflow_file.read_text(encoding="utf-8"))
    assert "nodes" in workflow, "Manca campo 'nodes'"
    assert "connections" in workflow, "Manca campo 'connections'"
    assert len(workflow["nodes"]) >= 5, f"Troppo pochi nodi: {len(workflow['nodes'])}"

    # Verifica che esista il nodo fallback (continueOnFail su Claude API)
    claude_node = [n for n in workflow["nodes"] if n["id"] == "claude-api"]
    assert claude_node, "Manca nodo Claude API"
    assert claude_node[0].get("continueOnFail") is True, "Claude API manca continueOnFail (fallback)"

    # Verifica nodo notifica operatore
    notify_node = [n for n in workflow["nodes"] if n["id"] == "notify-operator"]
    assert notify_node, "Manca nodo Notify Operator"

    return f"n8n_workflow.json valido con {len(workflow['nodes'])} nodi e fallback attivo"


def test_no_respond_io_references():
    """Verifica che non ci siano riferimenti a Respond.io (rimosso)."""
    for fname in ["config.json", "SETUP.md", "n8n_workflow.json"]:
        fpath = SCRIPT_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").lower()
            assert "respond.io" not in content, f"Riferimento a Respond.io trovato in {fname}"
            assert "wati" not in content, f"Riferimento a Wati trovato in {fname}"
    return "Nessun riferimento a tool esterni (Respond.io/Wati) — solo WhatsApp diretto"


# ===================================================================
# CLAUDE API INTEGRATION TESTS (require ANTHROPIC_API_KEY)
# ===================================================================

# Test messaggi italiani
TEST_MESSAGES_IT = [
    {
        "name": "Ospite — disponibilità Stintino",
        "message": "Buongiorno! Avete disponibilità a Stintino dal 10 al 17 agosto per 4 persone?",
        "check_category_in": ["ospite_info", "ospite_prenotazione", "ospite_disponibilita"],
        "check_needs_human": True,
    },
    {
        "name": "Ospite — info proprietà nota (Il Faro)",
        "message": "Ciao, l'appartamento Il Faro ha il WiFi? E si possono portare cani?",
        "check_category_in": ["ospite_info", "ospite_disponibilita"],
        "check_needs_human": False,
    },
    {
        "name": "Ospite — problema urgente",
        "message": "Aiuto! Siamo a Villa La Vela e non funziona l'aria condizionata!",
        "check_category_in": ["ospite_problema"],
        "check_needs_human": True,
        "check_priority": "urgent",
    },
    {
        "name": "Proprietario nuovo",
        "message": "Buongiorno, ho una villa a Porto Cervo e vorrei affidarvi la gestione.",
        "check_category_in": ["proprietario_nuovo", "proprietario"],
        "check_needs_human": True,
    },
    {
        "name": "Altro — info generali",
        "message": "Fate anche vendita di immobili?",
        "check_category_in": ["altro"],
        "check_needs_human": True,
    },
]

# Test messaggi inglesi
TEST_MESSAGES_EN = [
    {
        "name": "English guest — availability",
        "message": "Hi! Do you have any houses available in Alghero for July? We are 6 people.",
        "check_category_in": ["ospite_info", "ospite_prenotazione", "ospite_disponibilita"],
        "check_needs_human": True,
        "check_language": "en",
    },
    {
        "name": "English guest — general info",
        "message": "Hello, are pets allowed in your properties? We have a small dog.",
        "check_category_in": ["ospite_info", "ospite_disponibilita"],
        "check_needs_human": False,
        "check_language": "en",
    },
]

# Test edge cases
TEST_MESSAGES_EDGE = [
    {
        "name": "Richiesta contatto diretto",
        "message": "Mi può chiamare? Vorrei parlare con qualcuno.",
        "check_needs_human": True,
    },
    {
        "name": "Conversazione già avviata",
        "message": "Ok perfetto, confermo la prenotazione come d'accordo ieri.",
        "check_needs_human": True,
    },
    {
        "name": "Messaggio molto corto",
        "message": "Ciao",
        "check_needs_human": False,
    },
    {
        "name": "Località senza proprietà note",
        "message": "Avete case a Porto Cervo per 2 persone?",
        "check_category_in": ["ospite_info", "ospite_prenotazione", "ospite_disponibilita"],
    },
]


def call_claude_api(api_key, system_prompt, message):
    """Chiama Claude API e ritorna la risposta parsata."""
    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": message}],
    }).encode("utf-8")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    if HAS_HTTPX:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            content=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    else:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

    response_text = data["content"][0]["text"]

    # Estrai JSON dalla risposta (potrebbe essere wrappato in markdown)
    clean = response_text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        clean = clean.rsplit("```", 1)[0]
    return json.loads(clean.strip())


def run_api_test(api_key, system_prompt, test):
    """Esegue un singolo test con Claude API. Ritorna (status, details)."""
    response = call_claude_api(api_key, system_prompt, test["message"])

    issues = []

    # Check category
    if "check_category_in" in test:
        cat = response.get("category", "")
        if cat not in test["check_category_in"]:
            issues.append(f"category={cat}, atteso uno di {test['check_category_in']}")

    # Check needs_human
    if "check_needs_human" in test:
        nh = response.get("needs_human")
        if nh != test["check_needs_human"]:
            issues.append(f"needs_human={nh}, atteso {test['check_needs_human']}")

    # Check priority
    if "check_priority" in test:
        pri = response.get("priority", "")
        if pri != test["check_priority"]:
            issues.append(f"priority={pri}, atteso {test['check_priority']}")

    # Check language in response
    if "check_language" in test and test["check_language"] == "en":
        resp_text = response.get("response_text", "")
        italian_starters = ["Ciao", "Buongiorno", "Grazie", "Salve"]
        if any(resp_text.strip().startswith(w) for w in italian_starters):
            issues.append("Risposta in italiano invece che inglese")

    # Check response_text exists
    if not response.get("response_text"):
        issues.append("response_text vuoto")

    # Check JSON structure
    required_fields = ["category", "needs_human", "priority", "response_text", "summary"]
    missing = [f for f in required_fields if f not in response]
    if missing:
        issues.append(f"Campi mancanti: {missing}")

    status = "PASS" if not issues else "WARN"
    return status, response, issues


# ===================================================================
# MAIN
# ===================================================================

def main():
    print("=" * 60)
    print("TEST WhatsApp Bot AffittaSardegna")
    print("=" * 60)

    results = []

    # --- UNIT TESTS ---
    print("\n--- UNIT TEST (no network) ---")

    unit_tests = [
        ("System prompt esiste", test_system_prompt_exists),
        ("Sezioni richieste", test_system_prompt_has_required_sections),
        ("Config JSON valido", test_config_json_valid),
        ("n8n workflow valido + fallback", test_n8n_workflow_valid),
        ("Nessun tool esterno", test_no_respond_io_references),
    ]

    for name, test_fn in unit_tests:
        try:
            detail = test_fn()
            print(f"  PASS  {name}: {detail}")
            results.append("PASS")
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            results.append("FAIL")
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            results.append("FAIL")

    # --- API TESTS ---
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n  SKIP  ANTHROPIC_API_KEY non impostata — test API saltati")
    else:
        system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")

        for section_name, test_list in [
            ("--- TEST ITALIANI ---", TEST_MESSAGES_IT),
            ("--- TEST INGLESI ---", TEST_MESSAGES_EN),
            ("--- TEST EDGE CASE ---", TEST_MESSAGES_EDGE),
        ]:
            print(f"\n{section_name}")

            for test in test_list:
                try:
                    status, response, issues = run_api_test(
                        api_key, system_prompt, test
                    )
                    results.append(status)

                    icon = "PASS" if status == "PASS" else "WARN"
                    print(f"  {icon}  {test['name']}")
                    print(f"        cat={response.get('category')} human={response.get('needs_human')} pri={response.get('priority')}")
                    resp_preview = response.get('response_text', '')[:100]
                    print(f"        > {resp_preview}...")
                    if issues:
                        for issue in issues:
                            print(f"        ! {issue}")

                except json.JSONDecodeError as e:
                    print(f"  FAIL  {test['name']}: JSON non valido: {e}")
                    results.append("FAIL")
                except Exception as e:
                    print(f"  FAIL  {test['name']}: {e}")
                    results.append("FAIL")

    # --- SUMMARY ---
    print("\n" + "=" * 60)
    passed = results.count("PASS")
    warned = results.count("WARN")
    failed = results.count("FAIL")
    total = len(results)
    print(f"Risultati: {passed} PASS, {warned} WARN, {failed} FAIL su {total} test")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
