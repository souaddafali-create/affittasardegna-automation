#!/usr/bin/env python3
"""
AffittaSardegna WhatsApp Bot — Webhook server Flask.

Riceve messaggi da Meta Cloud API, li processa con Claude,
e risponde via WhatsApp. Se Claude è giù, fallback a operatore umano.

Deploy: Render (render.yaml) o qualsiasi host WSGI.
Env vars richieste: vedi config.json → env_vars_required.
"""

import json
import logging
import os
from pathlib import Path

from flask import Flask, request, jsonify

# Prova anthropic SDK, fallback su urllib
try:
    import anthropic
    HAS_ANTHROPIC_SDK = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_ANTHROPIC_SDK = False

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
SYSTEM_PROMPT_FILE = SCRIPT_DIR / "system_prompt.txt"

WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "affittasardegna_wh_2026")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
OPERATOR_PHONES = os.environ.get("OPERATOR_PHONES", "").split(",")

CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 1024

FALLBACK_RESPONSE = {
    "category": "altro",
    "needs_human": True,
    "priority": "high",
    "response_text": "Grazie per il messaggio! Un operatore del team AffittaSardegna ti risponderà a breve.",
    "summary": "Bot non disponibile — messaggio passato agli operatori",
}


def load_system_prompt():
    """Carica system prompt da file. Cached dopo primo caricamento."""
    if not hasattr(load_system_prompt, "_cache"):
        if SYSTEM_PROMPT_FILE.exists():
            load_system_prompt._cache = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        else:
            # Fallback da env var (come in n8n)
            load_system_prompt._cache = os.environ.get("WHATSAPP_BOT_SYSTEM_PROMPT", "")
    return load_system_prompt._cache


# --- WhatsApp API helpers ---

def send_whatsapp_message(to_phone, text, phone_number_id=None):
    """Invia messaggio WhatsApp via Meta Graph API."""
    pid = phone_number_id or WHATSAPP_PHONE_NUMBER_ID
    if not pid or not WHATSAPP_ACCESS_TOKEN:
        log.error("WhatsApp credentials mancanti (PHONE_NUMBER_ID o ACCESS_TOKEN)")
        return False

    url = f"https://graph.facebook.com/v21.0/{pid}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {WHATSAPP_ACCESS_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info("WhatsApp msg inviato a %s (status %s)", to_phone, resp.status)
            return True
    except Exception as e:
        log.error("Errore invio WhatsApp a %s: %s", to_phone, e)
        return False


def notify_operators(sender_phone, sender_name, message_text, category, priority, summary):
    """Notifica operatori via WhatsApp."""
    notification = (
        f"📋 *Richiesta da gestire*\n\n"
        f"👤 {sender_name or sender_phone}\n"
        f"📞 +{sender_phone}\n"
        f"📂 {category}\n"
        f"⚡ {priority}\n"
        f"💬 {message_text[:300]}\n\n"
        f"📝 {summary}"
    )
    for phone in OPERATOR_PHONES:
        phone = phone.strip()
        if phone:
            send_whatsapp_message(phone, notification)


# --- Claude API ---

def call_claude(message_text):
    """Chiama Claude API. Ritorna dict parsato o FALLBACK_RESPONSE."""
    system_prompt = load_system_prompt()
    if not system_prompt:
        log.error("System prompt vuoto")
        return FALLBACK_RESPONSE.copy()

    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY mancante")
        return FALLBACK_RESPONSE.copy()

    try:
        if HAS_ANTHROPIC_SDK:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": message_text}],
            )
            response_text = response.content[0].text
        else:
            body = json.dumps({
                "model": CLAUDE_MODEL,
                "max_tokens": CLAUDE_MAX_TOKENS,
                "system": system_prompt,
                "messages": [{"role": "user", "content": message_text}],
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                method="POST",
            )
            req.add_header("x-api-key", ANTHROPIC_API_KEY)
            req.add_header("anthropic-version", "2023-06-01")
            req.add_header("content-type", "application/json")

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            response_text = data["content"][0]["text"]

        return parse_claude_response(response_text)

    except Exception as e:
        log.error("Claude API errore: %s", e)
        return FALLBACK_RESPONSE.copy()


def parse_claude_response(text):
    """Parsa JSON dalla risposta Claude. Fallback se non valido."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        clean = clean.rsplit("```", 1)[0]
    try:
        parsed = json.loads(clean.strip())
        # Verifica campi obbligatori
        if "response_text" not in parsed:
            raise ValueError("response_text mancante")
        return parsed
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("Risposta Claude non parsabile: %s — %s", e, text[:200])
        return {
            "category": "altro",
            "needs_human": True,
            "priority": "normal",
            "response_text": "Grazie per il messaggio! Un operatore del team AffittaSardegna ti risponderà a breve.",
            "summary": f"Risposta Claude non parsabile: {text[:200]}",
        }


# --- Routes ---

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Verifica webhook Meta (challenge handshake)."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        log.info("Webhook verificato")
        return challenge, 200
    log.warning("Webhook verifica fallita (token: %s)", token)
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    """Riceve messaggi WhatsApp da Meta Cloud API."""
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "empty"}), 200

    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0].get("value", {})
        messages = changes.get("messages", [])

        if not messages:
            # Delivery/read receipt, non un messaggio
            return jsonify({"status": "not_message"}), 200

        message = messages[0]
        if message.get("type") != "text":
            return jsonify({"status": "not_text"}), 200

        sender_phone = message["from"]
        message_text = message["text"]["body"]
        phone_number_id = changes.get("metadata", {}).get("phone_number_id", "")

        contacts = changes.get("contacts", [{}])
        sender_name = contacts[0].get("profile", {}).get("name", "") if contacts else ""

        log.info("Messaggio da %s (%s): %s", sender_name, sender_phone, message_text[:100])

        # Chiama Claude
        result = call_claude(message_text)

        # Invia risposta all'ospite
        send_whatsapp_message(
            sender_phone,
            result.get("response_text", FALLBACK_RESPONSE["response_text"]),
            phone_number_id,
        )

        # Notifica operatori se serve
        if result.get("needs_human", True):
            notify_operators(
                sender_phone=sender_phone,
                sender_name=sender_name,
                message_text=message_text,
                category=result.get("category", "altro"),
                priority=result.get("priority", "normal"),
                summary=result.get("summary", ""),
            )

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        log.error("Errore processamento messaggio: %s", e, exc_info=True)
        return jsonify({"status": "error"}), 200  # 200 per evitare retry Meta


@app.route("/health", methods=["GET"])
def health():
    """Health check per Render/monitoring."""
    return jsonify({
        "status": "ok",
        "bot": "AffittaSardegna WhatsApp Bot",
        "claude_configured": bool(ANTHROPIC_API_KEY),
        "whatsapp_configured": bool(WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("Avvio bot su porta %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
