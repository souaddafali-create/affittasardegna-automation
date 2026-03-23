"""
WhatsApp Bot webhook server for AffittaSardegna.
Receives messages via Meta Cloud API, responds using Claude, sends replies back.

Features:
- Conversation memory (last 20 messages per sender, 24h TTL)
- Message deduplication (ignores already-processed message IDs)
- Rate limiting (max 10 messages per minute per sender)
"""

import hashlib
import hmac
import json
import logging
import os
import time
import threading
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

# --- Conversation memory ---
# {phone_number: {"messages": [{"role": ..., "content": ...}], "updated": timestamp}}
_conversations = {}
_conv_lock = threading.Lock()
CONV_MAX_MESSAGES = 20  # keep last 20 messages per conversation
CONV_TTL_SECONDS = 24 * 60 * 60  # expire after 24 hours of inactivity

# --- Message deduplication ---
# Set of recently processed message IDs (with timestamps for cleanup)
_processed_messages = {}  # {message_id: timestamp}
_dedup_lock = threading.Lock()
DEDUP_TTL_SECONDS = 60 * 5  # remember message IDs for 5 minutes

# --- Rate limiting ---
# {phone_number: [timestamp, timestamp, ...]}
_rate_limits = {}
_rate_lock = threading.Lock()
RATE_LIMIT_MAX = 10  # max messages per window
RATE_LIMIT_WINDOW = 60  # window in seconds


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


# --- Conversation memory helpers ---

def _cleanup_expired():
    """Remove expired conversations, dedup entries, and rate limit entries."""
    now = time.time()
    with _conv_lock:
        expired = [k for k, v in _conversations.items()
                   if now - v["updated"] > CONV_TTL_SECONDS]
        for k in expired:
            del _conversations[k]

    with _dedup_lock:
        expired = [k for k, v in _processed_messages.items()
                   if now - v > DEDUP_TTL_SECONDS]
        for k in expired:
            del _processed_messages[k]

    with _rate_lock:
        expired = [k for k, v in _rate_limits.items() if not v]
        for k in expired:
            del _rate_limits[k]


def get_conversation(sender):
    """Get conversation history for a sender."""
    with _conv_lock:
        conv = _conversations.get(sender)
        if conv and (time.time() - conv["updated"]) < CONV_TTL_SECONDS:
            return list(conv["messages"])
        return []


def add_message(sender, role, content):
    """Add a message to conversation history."""
    with _conv_lock:
        if sender not in _conversations:
            _conversations[sender] = {"messages": [], "updated": time.time()}
        conv = _conversations[sender]
        conv["messages"].append({"role": role, "content": content})
        # Keep only last N messages
        if len(conv["messages"]) > CONV_MAX_MESSAGES:
            conv["messages"] = conv["messages"][-CONV_MAX_MESSAGES:]
        conv["updated"] = time.time()


def is_duplicate(message_id):
    """Check if a message ID was already processed."""
    with _dedup_lock:
        if message_id in _processed_messages:
            return True
        _processed_messages[message_id] = time.time()
        return False


def is_rate_limited(sender):
    """Check if sender has exceeded rate limit. Returns True if blocked."""
    now = time.time()
    with _rate_lock:
        if sender not in _rate_limits:
            _rate_limits[sender] = []
        # Remove timestamps outside the window
        _rate_limits[sender] = [
            t for t in _rate_limits[sender]
            if now - t < RATE_LIMIT_WINDOW
        ]
        if len(_rate_limits[sender]) >= RATE_LIMIT_MAX:
            return True
        _rate_limits[sender].append(now)
        return False


# --- Claude API ---

def call_claude(user_message, sender, sender_name=""):
    """Call Claude API with conversation history and return structured response."""
    system_prompt = load_system_prompt()

    # Build user content with sender info
    if sender_name:
        user_content = f"[Mittente: {sender_name}]\n{user_message}"
    else:
        user_content = user_message

    # Get conversation history and append new user message
    history = get_conversation(sender)
    history.append({"role": "user", "content": user_content})

    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": history,
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

            # Save to conversation memory
            add_message(sender, "user", user_content)
            add_message(sender, "assistant", text)

            # Parse the JSON response from Claude
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
    """Health check endpoint."""
    with _conv_lock:
        active_conversations = len(_conversations)
    return jsonify({
        "status": "ok",
        "service": "AffittaSardegna WhatsApp Bot",
        "active_conversations": active_conversations,
    })


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

    # Periodic cleanup of expired data
    _cleanup_expired()

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    if msg.get("type") != "text":
                        continue

                    # Deduplication: skip already-processed messages
                    message_id = msg.get("id", "")
                    if message_id and is_duplicate(message_id):
                        logger.info("Skipping duplicate message: %s", message_id)
                        continue

                    sender = msg["from"]
                    text = msg["text"]["body"]

                    # Rate limiting
                    if is_rate_limited(sender):
                        logger.warning("Rate limited sender: %s", sender)
                        continue

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

                    # Get Claude's response (with conversation history)
                    claude_resp = call_claude(text, sender, sender_name)
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
