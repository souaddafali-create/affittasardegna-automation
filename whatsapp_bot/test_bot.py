#!/usr/bin/env python3
"""
Test script per verificare il WhatsApp bot AffittaSardegna.
Simula messaggi WhatsApp e verifica le risposte di Claude.

Uso:
    ANTHROPIC_API_KEY=sk-... python whatsapp_bot/test_bot.py
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

TEST_MESSAGES = [
    {
        "name": "Ospite — disponibilità",
        "message": "Buongiorno! Avete disponibilità a Stintino dal 10 al 17 agosto per 4 persone? Quanto costerebbe?",
        "expected_category": "ospite_disponibilita",
        "expected_needs_human": True,
    },
    {
        "name": "Ospite — info generali",
        "message": "Ciao, l'appartamento Il Faro ha il WiFi? E si possono portare cani?",
        "expected_category": "ospite_disponibilita",
        "expected_needs_human": False,
    },
    {
        "name": "Ospite — problema urgente",
        "message": "Aiuto! Siamo a Villa La Vela e non funziona l'aria condizionata. Fa caldissimo!",
        "expected_category": "ospite_problema",
        "expected_needs_human": True,
    },
    {
        "name": "Proprietario",
        "message": "Buongiorno, sono Mario Rossi. Ho una villa a Porto Cervo e vorrei affidarvi la gestione degli affitti.",
        "expected_category": "proprietario",
        "expected_needs_human": True,
    },
    {
        "name": "Altro",
        "message": "Salve, fate anche vendita di immobili?",
        "expected_category": "altro",
        "expected_needs_human": True,
    },
]


def call_claude(api_key: str, system_prompt: str, message: str) -> dict:
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
    if "```json" in response_text:
        json_str = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        json_str = response_text.split("```")[1].split("```")[0].strip()
    else:
        json_str = response_text.strip()

    return json.loads(json_str)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERRORE: Imposta ANTHROPIC_API_KEY")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")

    print("=" * 60)
    print("TEST WhatsApp Bot AffittaSardegna")
    print("=" * 60)

    results = []
    for test in TEST_MESSAGES:
        print(f"\n--- {test['name']} ---")
        print(f"Messaggio: {test['message'][:80]}...")

        try:
            response = call_claude(api_key, system_prompt, test["message"])

            cat_ok = response.get("category") == test["expected_category"]
            human_ok = response.get("needs_human") == test["expected_needs_human"]

            status = "PASS" if (cat_ok and human_ok) else "WARN"
            results.append(status)

            print(f"Categoria: {response.get('category')} {'✓' if cat_ok else '✗ (atteso: ' + test['expected_category'] + ')'}")
            print(f"Needs human: {response.get('needs_human')} {'✓' if human_ok else '✗ (atteso: ' + str(test['expected_needs_human']) + ')'}")
            print(f"Priorità: {response.get('priority')}")
            print(f"Risposta: {response.get('response_text', '')[:150]}...")
            print(f"Risultato: {status}")

        except json.JSONDecodeError as e:
            print(f"ERRORE: Claude non ha risposto con JSON valido: {e}")
            results.append("FAIL")
        except Exception as e:
            print(f"ERRORE: {e}")
            results.append("FAIL")

    print("\n" + "=" * 60)
    passed = results.count("PASS")
    warned = results.count("WARN")
    failed = results.count("FAIL")
    print(f"Risultati: {passed} PASS, {warned} WARN, {failed} FAIL su {len(results)} test")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
