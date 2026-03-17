"""
WhatsApp Bot webhook server for AffittaSardegna.
Receives messages via Meta Cloud API, responds using Claude, sends replies back.
"""

import hashlib
import hmac
import json
import logging
import os
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config from environment ---
VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "affittasardegna2024")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
APP_SECRET = os.environ.get("META_APP_SECRET", "")

# Operator phone numbers for human escalation notifications
OPERATOR_PHONES = os.environ.get("OPERATOR_PHONES", "").split(",")

SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")


def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def verify_signature(payload, signature):
    """Verify Meta webhook signature for security."""
    if not APP_SECRET or not signature:
        return True  # Skip verification if not configured
    expected = hmac.new(
        APP_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def call_claude(user_message, sender_name=""):
    """Call Claude API and return structured response."""
    system_prompt = load_system_prompt()
    if sender_name:
        user_content = f"[Mittente: {sender_name}]\n{user_message}"
    else:
        user_content = user_message

    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            text = data["content"][0]["text"]
            # Parse the JSON response from Claude
            # Handle case where Claude wraps JSON in markdown code blocks
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            return json.loads(clean.strip())
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return {
            "category": "altro",
            "needs_human": True,
            "priority": "normal",
            "response_text": "Grazie per il messaggio! Un operatore del team AffittaSardegna ti risponderà a breve.",
            "summary": f"Errore Claude API: {e}",
        }


def send_whatsapp_message(to, text):
    """Send a text message via WhatsApp Cloud API."""
    body = json.dumps({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }).encode()

    req = urllib.request.Request(
        f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("Message sent to %s: %s", to, result)
            return result
    except Exception as e:
        logger.error("WhatsApp send error to %s: %s", to, e)
        return None


def notify_operators(sender, sender_name, message, claude_response):
    """Notify human operators when escalation is needed."""
    summary = claude_response.get("summary", "")
    category = claude_response.get("category", "")
    priority = claude_response.get("priority", "normal")

    notification = (
        f"📋 *Nuova richiesta da gestire*\n\n"
        f"👤 Da: {sender_name or sender}\n"
        f"📂 Categoria: {category}\n"
        f"⚡ Priorità: {priority}\n"
        f"💬 Messaggio: {message[:200]}\n\n"
        f"📝 Riepilogo: {summary}"
    )

    for phone in OPERATOR_PHONES:
        phone = phone.strip()
        if phone:
            send_whatsapp_message(phone, notification)


# --- Routes ---

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "AffittaSardegna WhatsApp Bot"})


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta webhook verification (GET request)."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return challenge, 200
    else:
        logger.warning("Webhook verification failed: mode=%s", mode)
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Process incoming WhatsApp messages."""
    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(request.data, signature):
        return "Invalid signature", 403

    body = request.get_json()
    if not body:
        return "OK", 200

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    if msg.get("type") != "text":
                        continue

                    sender = msg["from"]
                    text = msg["text"]["body"]
                    sender_name = ""

                    # Try to get sender name from contacts
                    contacts = value.get("contacts", [])
                    if contacts:
                        profile = contacts[0].get("profile", {})
                        sender_name = profile.get("name", "")

                    logger.info(
                        "Message from %s (%s): %s",
                        sender_name, sender, text[:100]
                    )

                    # Get Claude's response
                    claude_resp = call_claude(text, sender_name)
                    response_text = claude_resp.get("response_text", "")

                    # Send auto-reply
                    if response_text:
                        send_whatsapp_message(sender, response_text)

                    # Notify operators if human needed
                    if claude_resp.get("needs_human", False):
                        notify_operators(
                            sender, sender_name, text, claude_resp
                        )

    except Exception as e:
        logger.error("Error processing webhook: %s", e)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
