# WhatsApp Bot — Guida Setup Completa

## Architettura

```
Ospite WhatsApp
      │
      ▼
Meta Cloud API ──webhook──► n8n (affittasardegna.app.n8n.cloud)
                                │
                                ├──► Claude API (classifica + risponde)
                                │        │
                                │        ▼
                                ├──► WhatsApp Reply (risposta automatica)
                                │
                                └──► Inbox Umana (Respond.io/Wati)
                                     Souad & Edoardo intervengono qui
```

## Passaggio 1 — Prerequisiti

- [x] App Meta creata: "AffittaSardegna Messaging Bot" (ID: 126921442533925)
- [x] n8n attivo: affittasardegna.app.n8n.cloud
- [x] Webhook n8n: /webhook/33d39489-b64a-42d4-b571-9a0384059a14
- [ ] Token permanente Meta Graph API (vedi sotto)
- [ ] API key Anthropic
- [ ] Inbox umana configurata (Respond.io o Wati)

## Passaggio 2 — Genera Token Permanente Meta

Il token di test dura 24h. Per produzione serve un token permanente:

1. Vai su https://developers.facebook.com → App → Impostazioni
2. Crea un "System User" nel Business Manager:
   - Business Settings → System Users → Add
   - Ruolo: Admin
3. Assegna l'app al System User
4. Genera token con permessi:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
5. Copia il token e salvalo come credential in n8n

## Passaggio 3 — Configura Webhook Meta → n8n

### 3.1 Prepara n8n

1. Apri n8n → crea nuovo workflow (o importa `n8n_workflow.json`)
2. Il nodo "WhatsApp Webhook" è il trigger
3. **ATTIVA il workflow** (toggle ON in alto a destra) — DEVE essere attivo prima di verificare su Meta

### 3.2 Configura su Meta Developers

1. Vai su https://developers.facebook.com/apps/126921442533925/
2. Menu laterale → **WhatsApp** → **Configurazione** (Configuration)
3. Sezione **Webhook**:
   - Clicca **Modifica** (Edit)
   - **Callback URL**: `https://affittasardegna.app.n8n.cloud/webhook/33d39489-b64a-42d4-b571-9a0384059a14`
   - **Verify Token**: il valore che hai scelto (es. `affittasardegna_wh_2024`)
   - Clicca **Verifica e salva**

### 3.3 NOTA IMPORTANTE sulla verifica

n8n gestisce automaticamente la verifica webhook (challenge response) MA:
- Il workflow DEVE essere ATTIVO
- Usa il path `/webhook/` (NON `/webhook-test/`)
- Se la verifica fallisce, controlla:
  1. Workflow attivo?
  2. Il Verify Token in n8n corrisponde a quello su Meta?
  3. Il nodo Webhook è il primo nodo del workflow?

### 3.4 Sottoscrivi eventi

Dopo la verifica:
1. Nella sezione "Webhook fields", clicca **Gestisci** (Manage)
2. Attiva: **messages** (obbligatorio)
3. Opzionale: **message_deliveries**, **message_reads** (per spunte blu)

### 3.5 Collega il numero di telefono

1. Sezione **Numeri di telefono** → clicca il numero WhatsApp Business
2. Se non hai ancora un numero Business:
   - Opzione A: Usa il numero di test Meta (per sviluppo)
   - Opzione B: Registra 3478056842 (secondo numero aziendale) come WhatsApp Business API

   **NOTA**: Il numero principale 3494787272 resta per WhatsApp Web degli operatori.
   Il bot usa il secondo numero aziendale +39 347 805 6842.

## Passaggio 4 — Configura Credenziali n8n

In n8n → Settings → Environment Variables, aggiungi:

| Variabile | Valore |
|-----------|--------|
| `WHATSAPP_ACCESS_TOKEN` | Token permanente Meta (dal Passaggio 2) |
| `ANTHROPIC_API_KEY` | API key Anthropic |
| `WHATSAPP_VERIFY_TOKEN` | Token scelto (es. `affittasardegna_wh_2024`) |
| `WHATSAPP_BOT_SYSTEM_PROMPT` | Contenuto di `system_prompt.txt` |
| `HUMAN_INBOX_WEBHOOK_URL` | URL webhook Respond.io/Wati |

## Passaggio 5 — Importa Workflow n8n

1. In n8n → Workflows → Import from File
2. Seleziona `n8n_workflow.json`
3. Verifica che tutti i nodi siano collegati:
   ```
   Webhook → Is Text? → Extract → Claude API → Parse → Send Reply
                                                    └──→ Needs Human? → Notify Inbox
   ```
4. Attiva il workflow

## Passaggio 6 — Test

### Test con numero Meta di test
1. Nella console Meta, usa "Send Test Message" con il numero di test
2. Invia un messaggio tipo "Quanto costa Villa La Vela ad agosto?"
3. Verifica in n8n che il webhook riceva il messaggio
4. Verifica che Claude risponda correttamente
5. Verifica che la risposta arrivi su WhatsApp

### Test dei 5 percorsi
1. **Ospite disponibilità**: "Buongiorno, avete disponibilità a Stintino dal 10 al 17 agosto?"
2. **Ospite problema**: "Aiuto, non funziona l'aria condizionata nella villa!"
3. **Proprietario**: "Sono Mario Rossi, proprietario di un appartamento a Olbia"
4. **Collaboratore**: "Ciao, sono il manutentore. La piscina di Villa La Vela ha bisogno di intervento"
5. **Altro**: "Ciao, volevo sapere se fate anche vendita immobili"

## Passaggio 7 — Inbox Umana (Respond.io o Wati)

### Opzione A: Respond.io
- Piano gratuito fino a 100 contatti/mese
- Integrazione WhatsApp Business API
- Inbox condivisa per Souad ed Edoardo
- Webhook in entrata per notifiche dal bot

### Opzione B: Wati
- Specializzato WhatsApp
- Template messages pre-approvati
- Piano base da ~39 EUR/mese

### Configurazione inbox
1. Crea account su Respond.io/Wati
2. Collega lo stesso numero WhatsApp Business API
3. Configura il webhook in entrata (URL da mettere in `HUMAN_INBOX_WEBHOOK_URL`)
4. Aggiungi Souad ed Edoardo come operatori
5. Configura regole di assegnazione automatica

## Troubleshooting

| Problema | Soluzione |
|----------|----------|
| Webhook verifica fallisce | Workflow n8n attivo? Path corretto (no -test)? Token match? |
| Messaggi non arrivano | Sottoscritto a "messages"? Numero collegato? |
| Claude non risponde | ANTHROPIC_API_KEY valida? System prompt configurato? |
| Risposta non inviata | WHATSAPP_ACCESS_TOKEN valido? Numero mittente corretto? |
| Doppi messaggi | Aggiungere dedup su message_id nel workflow |
