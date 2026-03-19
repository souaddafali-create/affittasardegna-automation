# Email Bot AffittaSardegna — n8n + Outlook + Claude

Bot automatico che risponde alle email su `info@affittasardegna.it`.
Crea **bozze** in Outlook (non invia automaticamente) — tu rivedi e invii.

---

## Architettura

```
Email in arrivo (Outlook)
       │
       ▼
  n8n Trigger (polling ogni 2 min)
       │
       ▼
  Filtro Spam/Auto-reply
       │
       ▼
  Parser Email (JS → testo pulito + categoria)
       │
       ▼
  System Prompt (contesto proprietà)
       │
       ▼
  Claude API (genera risposta)
       │
       ▼
  Formatta Risposta (HTML)
       │
       ├── OK → Crea Bozza in Outlook
       └── [ESCALATION] → Bozza con alert ⚠️ per Souad
```

---

## Prerequisiti

### 1. Account n8n

- **n8n Cloud**: https://app.n8n.cloud (piano Free: 5 workflow attivi)
- **Oppure self-hosted**: `docker run -d --name n8n -p 5678:5678 n8nio/n8n`

### 2. Anthropic API Key

1. Vai su https://console.anthropic.com/
2. Crea account o accedi
3. **Settings → API Keys → Create Key**
4. Copia la chiave (inizia con `sk-ant-...`)
5. Aggiungi credito: **Settings → Billing → Add funds** (min 5 USD)

Costo stimato: ~0.003 USD per email (Sonnet 4 con ~2000 token in/out)

### 3. Microsoft Outlook / Microsoft 365

Serve una **App Registration** in Azure AD per OAuth2.

#### Registra l'app in Azure:

1. Vai su https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade
2. **+ New registration**
   - Nome: `n8n-email-bot`
   - Account types: "Accounts in this organizational directory only" (se hai M365 Business)
     oppure "Accounts in any organizational directory and personal Microsoft accounts"
   - Redirect URI: `https://app.n8n.cloud/rest/oauth2-credential/callback`
     (se self-hosted: `http://tuo-server:5678/rest/oauth2-credential/callback`)
3. **Dopo la creazione**, copia:
   - Application (client) ID
   - Directory (tenant) ID
4. Vai su **Certificates & secrets → + New client secret**
   - Copia il **Value** (non l'ID)
5. Vai su **API permissions → + Add a permission → Microsoft Graph**:
   - `Mail.Read`
   - `Mail.ReadWrite`
   - `Mail.Send`
   - `offline_access`
   - `User.Read`
6. Clicca **Grant admin consent** (se sei admin del tenant)

---

## Setup in n8n (step by step)

### Step 1: Crea credenziale Anthropic

1. In n8n: **Settings → Credentials → + Add Credential**
2. Tipo: **Header Auth**
3. Nome: `Anthropic API Key`
4. Header Name: `x-api-key`
5. Header Value: `sk-ant-api03-...` (la tua chiave)

### Step 2: Crea credenziale Outlook

1. **Settings → Credentials → + Add Credential**
2. Tipo: **Microsoft Outlook OAuth2 API**
3. Compila:
   - Client ID: (dal portale Azure)
   - Client Secret: (dal portale Azure)
   - Tenant ID: (dal portale Azure, oppure `common` per account personali)
4. Clicca **Sign in with Microsoft** — accedi con `info@affittasardegna.it`
5. Autorizza i permessi

### Step 3: Importa il workflow

1. **Workflows → + Add Workflow → Import from File**
2. Seleziona `n8n_email_bot_workflow.json`
3. Si aprirà il workflow con tutti i nodi

### Step 4: Collega le credenziali

Nei nodi:
- **"Nuova Email Outlook"** → seleziona credenziale Outlook
- **"Crea Bozza (Auto)"** → seleziona credenziale Outlook
- **"Bozza + Alert Escalation"** → seleziona credenziale Outlook
- **"Claude Genera Risposta"** → seleziona credenziale Anthropic

### Step 5: Test

1. Clicca **"Test Workflow"** in n8n
2. Manda un'email di test a `info@affittasardegna.it`
3. Verifica che il workflow si attivi
4. Controlla la bozza creata in Outlook

### Step 6: Attiva

- Toggle **"Active"** in alto a destra nel workflow
- Il bot ora gira in background ogni 2 minuti

---

## Cosa fa il bot — Comportamento per categoria

| Categoria | Comportamento |
|-----------|---------------|
| **Disponibilità** | NON conferma date. Dice che verificherà e risponderà entro 24h |
| **Prezzi** | Dà i prezzi dal listino (Villa La Vela). Per Il Faro dice "su richiesta" |
| **Check-in/out** | Dà gli orari esatti dalla scheda proprietà |
| **Cancellazioni** | `[ESCALATION]` → bozza con alert, Souad gestisce |
| **Reclami** | `[ESCALATION]` → bozza con alert, Souad gestisce |
| **Proposte immobili** | Ringrazia, chiede dettagli, dice che Souad valuterà |
| **Animali** | Risponde in base alla proprietà (Il Faro: sì piccola taglia, Villa La Vela: no) |
| **Servizi extra** | Dà info su pulizie/biancheria dalla scheda |
| **Generale** | Presenta brevemente entrambe le proprietà |

---

## Sicurezza

- Il bot crea **BOZZE**, non invia mai direttamente
- Le email con `[ESCALATION]` hanno oggetto con ⚠️ per facile identificazione
- Filtro anti-spam: ignora noreply, mailer-daemon, email vuote
- Le risposte sono limitate a max 350 parole
- Zero dati inventati: se Claude non ha l'info, dice "verificherò"
- Nessuna info su credenziali/password

---

## Aggiungere una nuova proprietà

1. Crea il JSON della proprietà (es. `Nuova_Casa_DATI.json`)
2. Apri il nodo **"Carica System Prompt"** nel workflow n8n
3. Aggiungi la sezione `### 3. Nome Proprietà` nel system prompt
4. Segui lo stesso formato delle proprietà esistenti
5. Salva il workflow

---

## Passare da Bozze a Invio Automatico

Quando sei sicuro che il bot funziona bene:

1. Sostituisci i nodi **"Crea Bozza"** con **"Microsoft Outlook → Send Message"**
2. Parametri:
   - To: `{{ $json.fromEmail }}`
   - Subject: `{{ $json.oggettoRisposta }}`
   - Body: `{{ $json.rispostaHtml }}`
3. Tieni comunque il ramo escalation come bozza

---

## Troubleshooting

| Problema | Soluzione |
|----------|----------|
| Workflow non si attiva | Verifica che sia "Active" (toggle verde) |
| Errore OAuth Outlook | Rigenera il client secret in Azure, ricollega |
| Errore 401 Claude | Verifica API key, controlla credito su console.anthropic.com |
| Risposte troppo generiche | Arricchisci il system prompt con più dettagli proprietà |
| Email non trovate | Controlla che il polling sia sulla casella giusta |
| Rate limit Claude | Sonnet 4 ha limiti alti, non dovrebbe essere un problema per email |

---

## Costi stimati

| Componente | Costo |
|------------|-------|
| n8n Cloud (Free) | 0 EUR/mese (5 workflow, 200 esecuzioni) |
| n8n Cloud (Starter) | ~20 EUR/mese (illimitato) |
| Claude API (Sonnet 4) | ~0.003 EUR/email |
| Outlook/M365 | già incluso nel tuo piano |
| **Totale (50 email/mese)** | **~0.15 EUR/mese** (solo API) |
