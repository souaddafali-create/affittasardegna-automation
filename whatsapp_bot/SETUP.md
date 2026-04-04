# WhatsApp Bot — Guida Setup

## Architettura (3 pezzi, stop)

```
Ospite scrive su WhatsApp (+39 347 805 6842)
      │
      ▼
Meta Cloud API (gratis)
      │
      ▼
n8n Cloud (affittasardegna.app.n8n.cloud, ~20 EUR/mese)
      │
      ├──► Claude API → risposta automatica al cliente
      │
      └──► Se serve umano → WhatsApp diretto a Souad/Edoardo
```

**Se n8n o Claude vanno giù:** il messaggio arriva comunque su WhatsApp Web. Semplicemente non c'è risposta automatica — rispondete a mano come avete sempre fatto.

---

## Prerequisiti

- [x] App Meta: "AffittaSardegna Messaging Bot" (ID: 126921442533925)
- [x] n8n attivo: affittasardegna.app.n8n.cloud
- [x] Numero 347 805 6842 aggiunto al WABA
- [ ] Token permanente Meta (vedi sotto)
- [ ] API key Anthropic (Claude)

---

## Passaggio 1 — Token Permanente Meta

Il token di test dura 24h. Per produzione serve un token permanente:

1. Vai su https://developers.facebook.com → App → Impostazioni
2. Business Settings → System Users → Add
   - Ruolo: Admin
3. Assegna l'app al System User
4. Genera token con permessi:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
5. Copia il token → lo metterai in n8n

## Passaggio 2 — Webhook Meta → n8n

### 2.1 In n8n
1. Importa `n8n_workflow.json` (oppure crea workflow e copia i nodi)
2. **ATTIVA il workflow** (toggle ON) — DEVE essere attivo prima di verificare su Meta

### 2.2 Su Meta Developers
1. https://developers.facebook.com/apps/126921442533925/
2. WhatsApp → Configurazione → Webhook
3. **Callback URL**: `https://affittasardegna.app.n8n.cloud/webhook/33d39489-b64a-42d4-b571-9a0384059a14`
4. **Verify Token**: scegli un valore (es. `affittasardegna_wh_2026`)
5. Clicca "Verifica e salva"

### 2.3 Sottoscrivi eventi
- Attiva: **messages** (obbligatorio)
- Opzionale: message_deliveries, message_reads

### 2.4 Collega il numero
- Collega il numero +39 347 805 6842 al webhook

## Passaggio 3 — Variabili n8n

In n8n → Settings → Environment Variables:

| Variabile | Valore |
|-----------|--------|
| `WHATSAPP_ACCESS_TOKEN` | Token permanente Meta (dal Passaggio 1) |
| `ANTHROPIC_API_KEY` | API key Anthropic |
| `WHATSAPP_BOT_SYSTEM_PROMPT` | Contenuto di `system_prompt.txt` |
| `OPERATOR_PHONE` | Numero Souad in formato internazionale (es. `39349XXXXXXX`) |

## Passaggio 4 — Test

Invia questi messaggi al 347 805 6842 e verifica le risposte:

1. "Buongiorno, avete disponibilità a Stintino dal 10 al 17 agosto?" → Risposta automatica + operatore notificato
2. "Aiuto, non funziona l'aria condizionata nella villa!" → Risposta + operatore notificato (urgente)
3. "Ciao, ho una villa a Olbia da affittare" → Risposta + operatore notificato
4. "Ciao" → Risposta automatica (senza disturbare operatore)

---

## Troubleshooting

| Problema | Soluzione |
|----------|----------|
| Webhook verifica fallisce | Workflow n8n attivo? Path corretto? Token match? |
| Messaggi non arrivano | Sottoscritto a "messages"? Numero collegato? |
| Claude non risponde | Il bot invia "Un operatore ti risponderà a breve" + notifica a voi |
| Risposta non inviata | WHATSAPP_ACCESS_TOKEN valido? |
| Doppi messaggi | Aggiungere dedup su message_id |

## Numeri

| Numero | Uso |
|--------|-----|
| +39 349 478 7272 | Operatori (WhatsApp Web) — NON toccare |
| +39 347 805 6842 | Bot WhatsApp (Cloud API + n8n) |
