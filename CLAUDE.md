# AffittaSardegna — Manuale di Bordo per Claude Code

> Leggi questo file prima di qualsiasi task. Contiene tutto il contesto operativo del progetto.

---

## REGOLA FONDAMENTALE: solo dati dal JSON

**Il file JSON della proprietà è la UNICA fonte di verità. Zero eccezioni.**

1. Gli uploader NON devono MAI inventare dati. Leggono TUTTO dal JSON.
2. Se un dato non è presente nel JSON, NON lo inseriscono (lasciano vuoto).
3. Se una dotazione è `false` nel JSON, NON la spuntano.
4. Se una dotazione è `true`, la spuntano.
5. Prezzi: dal JSON (`condizioni.listino_prezzi` mediana, o `condizioni.prezzo_notte`), altrimenti vuoto.
6. Letti: dal JSON (`composizione.letti[]`) con tipo e quantità.
7. Condizioni: soggiorno minimo, cauzione, pulizie, biancheria, check-in/out dal JSON.
8. Marketing: titolo e descrizione dal JSON, mai testo inventato.

Ogni proprietà avrà un JSON diverso con servizi diversi. Gli uploader si adattano automaticamente.

### Mappatura servizi CaseVacanza.it

| Chiave JSON | Label CaseVacanza |
|-------------|-------------------|
| `aria_condizionata` | Aria condizionata |
| `piscina` | Piscina (privata) o Piscina (in comune) — in base a `piscina_tipo` |
| `terrazza` | Terrazza |
| `tv` | TV |
| parcheggio (da `altro_dotazioni`) | Parcheggio |
| `lavatrice` | Lavatrice |
| `microonde` | Microonde |
| `phon` | Asciugacapelli |
| `frigo_congelatore` | Frigorifero |
| `piano_cottura` | Piano cottura |
| `arredi_esterno` | Arredi da esterno |
| `animali_ammessi` | Animali ammessi |

---

## 👤 Chi siamo

- **Azienda:** AffittaSardegna (affittasardegna.it) — gestione case vacanze dal 2011
- **Sede:** Porto Torres, Nord Sardegna
- **Fondatori:** Souad (operativa, sviluppo digitale) + Edoardo (decisioni business, dominio/billing)
- **Portfolio:** 300+ proprietà, 30+ località, Nord Sardegna
- **Modello:** Commissione 15–20% + IVA per proprietà
- **Obiettivo strategico:** Ridurre dipendenza OTA dal 80% → 60% prenotazioni dirette

---

## 🏗️ Stack Tecnico

| Sistema | Ruolo |
|---|---|
| WordPress + Elementor | Sito principale |
| Kross PMS | Booking engine (brand colors: #09b1c0 e #fdc709) |
| GetResponse | Email marketing |
| TranslatePress | Sito in 9 lingue |
| FlyingPress | Cache (comando: Purge & Preload) |
| SEOPress PRO | SEO on-page |
| n8n Cloud | Hub automazioni (~€20/mese) |
| 360dialog | WhatsApp Business API (~€8/mese) |
| Tawk.to | Live chat |
| GA4 + Clarity | Analytics |
| IONOS | Solo email/dominio (NON hosting) |
| Web Maremma | Ha configurato l'hosting originale (contratto terminato) |
| GitHub repo | `affittasardegna-automation` (questo repo) |

---

## Cosa fa questo progetto

Automazione per pubblicare proprietà in affitto breve su più portali (CaseVacanza.it, Booking.com) partendo da un unico file JSON dati + WhatsApp Bot per gestione messaggi.

Flusso principale:

```
Contratto proprietà + CIN
        │
        ▼
  <proprietà>_DATI.json          ← unica fonte dati
        │
        ├──► casevacanza_uploader.py  → CaseVacanza.it
        └──► booking_uploader.py      → Booking Extranet

WhatsApp (347 805 6842)
        │
        ▼
  360dialog → n8n webhook → Claude AI → risposta + handoff umano
```

Ogni uploader legge il JSON, fa login sul portale, compila il wizard di inserimento proprietà con Playwright e si ferma prima dell'invio finale (screenshot di verifica).

---

## 🤖 WhatsApp Bot

**Stack:** Claude API + n8n Cloud + 360dialog
**Numero:** +39 347 805 6842

### 5 path conversazionali:

| # | Target | Azione bot | Handoff |
|---|--------|-----------|---------|
| 1 | Ospite → disponibilità/preventivo | Info zone, prezzi, push prenotazione diretta + link Kross | Operatore per date specifiche |
| 2 | Ospite → problema durante soggiorno | Risposta rassicurante, priority: urgent | SEMPRE operatore |
| 3 | Proprietario → comunicazioni | Nuovo: raccolta info. Esistente: contesto, no automazioni | SEMPRE operatore |
| 4 | Collaboratore → operativo | Contesto, no flussi forzati | SEMPRE operatore |
| 5 | Altro → smistamento | Risposta cortese | Operatore se specifico |

### Prerequisito bloccante:
Verifica numero WhatsApp Business con Edoardo su Meta Business Manager.

### Regole bot:
- MAI inventare dati — se non sa, passa a operatore
- MAI forzare flussi automatici su conversazioni già avviate
- Firma come "Il team di AffittaSardegna", mai come bot/AI
- Risponde in italiano, inglese o nella lingua dell'ospite
- Link Kross booking engine per disponibilità: `https://book.affittasardegna.it`
- Operatori: Souad + Edoardo via WhatsApp Web

### File bot:
```
whatsapp_bot/
├── app.py              ← webhook server Flask (riceve da 360dialog/Meta)
├── system_prompt.txt   ← prompt completo per Claude AI (5 flussi, regole, proprietà)
├── config.json         ← configurazione bot (n8n, Meta, operatori)
├── n8n_workflow.json   ← workflow n8n esportato
├── test_bot.py         ← test del bot
├── requirements.txt    ← dipendenze Python
└── SETUP.md            ← guida setup
```

---

## Struttura file JSON proprietà

```json
{
  "identificativi": {
    "nome_struttura": "...",
    "tipo_struttura": "Appartamento",
    "indirizzo": "Via ... N",
    "cap": "...", "comune": "...", "provincia": "...", "regione": "...",
    "residence_complesso": "...",
    "interno": "...", "piano": "...",
    "cin": "...", "cir": "...",
    "codice_proprieta": "...",
    "coordinate": {"latitudine": 40.913928, "longitudine": 8.203492}
  },
  "composizione": {
    "max_ospiti": 4, "camere": 1, "posti_letto": 4, "bagni": 1,
    "letti": [
      {"tipo": "matrimoniale", "quantita": 1},
      {"tipo": "singolo", "quantita": 2}
    ],
    "bagno_con_doccia": true, "bagno_con_vasca": false
  },
  "dotazioni": {
    "tv": true, "piano_cottura": true, "forno": false, "...": "true/false per ogni servizio",
    "altro_dotazioni": "testo libero (es. posto auto)"
  },
  "condizioni": {
    "soggiorno_minimo_bassa": {"notti": 3, "periodo": "..."},
    "soggiorno_minimo_alta": {"notti": 5, "periodo": "..."},
    "cauzione_euro": 300,
    "prezzo_notte": null,
    "pulizia_finale": "...",
    "biancheria": "...",
    "check_in": "15:00 - 20:00",
    "check_out": "entro le 10:00",
    "regole_casa": "...",
    "listino_prezzi": [{"da": "28-mar", "a": "04-apr", "prezzo_notte": 137}],
    "ical_url": "https://..."
  },
  "marketing": {
    "titolo": "...",
    "descrizione_breve": "...",
    "descrizione_lunga": "...",
    "punti_forza": ["...", "..."],
    "distanze": [{"luogo": "...", "km": 3, "tempo": "..."}],
    "servizi_vicinanze": [{"nome": "...", "indirizzo": "...", "km": 8.4}],
    "keywords": ["...", "..."]
  }
}
```

---

## 📁 Mappa file

### Dati proprietà

| File | Descrizione |
|------|-------------|
| `Il_Faro_Badesi_DATI.json` | Dati completi della proprietà "Il Faro" a Badesi (SS). Fonte unica: tutti gli uploader leggono da qui. |
| `Villa_La_Vela_DATI.json` | Dati completi della proprietà "Villa La Vela" a Stintino (SS). Villa con piscina privata, 6 ospiti. Include coordinate GPS, listino multi-periodo e iCal. |

### Uploader

| File | Portale | Dettagli |
|------|---------|----------|
| `casevacanza_uploader.py` | CaseVacanza.it | Playwright. Login su `my.casevacanza.it`, wizard 28 step. Env vars: `CASEVACANZA_EMAIL`, `CASEVACANZA_PASSWORD`. Override JSON con `PROPERTY_DATA`. |
| `booking_uploader.py` | Booking Extranet | Playwright + stealth + OTP interattivo. Login su `account.booking.com`. Env vars: `BK_EMAIL`, `BK_PASSWORD`. Override JSON con `PROPERTY_DATA`. Modalità interattiva: `INTERACTIVE=1`. |

### Workflow GitHub Actions

| File | Trigger | Cosa fa |
|------|---------|---------|
| `.github/workflows/upload.yml` | Push su `main` + manual | Esegue `casevacanza_uploader.py` con xvfb. |
| `.github/workflows/booking_upload.yml` | Push su `main` + manual | Esegue `booking_uploader.py` con xvfb e stealth. |
| `.github/workflows/upload_villa_la_vela.yml` | Push su `main` + manual | Esegue `casevacanza_uploader.py` con `PROPERTY_DATA=Villa_La_Vela_DATI.json`. |
| `.github/workflows/booking_explore.yml` | Solo manual | Script esplorativo Booking.com. |
| `.github/workflows/explore_wizard.yml` | Solo manual | Esegue `explore_wizard.py` per mappare wizard CaseVacanza. |

### Esplorazione e documentazione

| File | Descrizione |
|------|-------------|
| `explore_wizard.py` | Script esplorativo wizard CaseVacanza. Salva `WIZARD_MAP.json`. |
| `PROCESSO.md` | Documentazione stato progetto. |

---

## 📧 Email Marketing — GetResponse

### Liste principali:

| Lista | Contatti | Note |
|---|---|---|
| MASTER_IT | ~5.935 | Italiani |
| MASTER_EN | ~990 | Internazionali |
| LEAD-SITO-SCONDO10 | Lead sito | Sequenza automazione 5 email (Day 0/2/4/6/10) |

### Upload CSV — logica classificazione IT/EN:
1. Campo `Cittadinanza` → primo criterio
2. Dominio email → fallback
3. Email OTA-masked (noreply@guest.booking.com ecc.) → RIMUOVERE sempre

### Export Kross:
- Fonte: preventivi + prenotazioni da Kross
- Ultimo export processato: 19/02/2026
- Riserva rolling: ~7.188 contatti Kross disponibili

---

## Secrets GitHub necessari

| Secret | Usato da |
|--------|----------|
| `CASEVACANZA_EMAIL` | casevacanza_uploader.py |
| `CASEVACANZA_PASSWORD` | casevacanza_uploader.py |
| `BK_EMAIL` | booking_uploader.py |
| `BK_PASSWORD` | booking_uploader.py |

---

## 🌐 SEO & Contenuti

### Lingue sito: IT, EN, DE, FR, ES, NL, PL, DA, SV

### Bug critico attivo
**Badesi e Costa Paradiso** hanno link errati in tutti gli articoli e pagine del sito.
→ Correggere sistematicamente prima di qualsiasi pubblicazione.

### Traduzioni in corso (17/03/2026):
- TranslatePress → String Translation → Regular
- Cerca: "Rent Sardinia" e "Affitta Sardegna" (separato)
- Sostituire con: **AffittaSardegna** (tutto attaccato) in tutte le 8 lingue non-IT

### Guide destinazione da creare:
- [ ] Guida Nord Sardegna (hub, slug: `/guida-nord-sardegna/`)
- [ ] Guida Stintino, Alghero, San Teodoro, Santa Teresa, Castelsardo, Cala Gonone, Palau/La Maddalena, Costa Paradiso

### Serie blog (26 articoli totali, 2-3/settimana DOPO le guide):
- Dark Sky ×4, Mercati ×4, Cantine ×4, Autunno in Barbagia ×6, Laghetti ×4, Fari/torri ×4

---

## ⚠️ Regole Operative Critiche

### Output file:
- **MAI ZIP** — Souad usa Notepad, non può aprire archivi compressi
- File singoli in `/mnt/user-data/outputs/` o direttamente nel repo

### Elementor:
- **Featured Image:** widget "Immagine" → dropdown nascosto → "Immagine in evidenza" → risoluzione "Pieno"
- **MAI** usare "Posizione: Assoluto" → usare CSS aggiuntivo
- Cache dopo modifiche: FlyingPress → Purge & Preload

### Hosting:
- IONOS = solo email/dominio
- Hosting reale: configurato da Web Maremma (contratto terminato)
- Credenziali hosting: chiedere a Edoardo

---

## Come aggiungere una nuova proprietà

1. Creare un nuovo file JSON seguendo la struttura sopra (copiare `Il_Faro_Badesi_DATI.json` come template)
2. Compilare TUTTI i campi: identificativi, composizione (incluso `letti`), dotazioni (true/false per ciascuna), condizioni, marketing
3. Eseguire: `PROPERTY_DATA=nuovo_file.json python casevacanza_uploader.py`
4. L'uploader spunta SOLO i servizi con `true` nel JSON, compila SOLO i dati presenti

## Come aggiungere un nuovo portale

1. Creare `nuovo_portale_uploader.py` che carica il JSON con la stessa logica
2. Aggiungere la mappatura `DOTAZIONI_MAP` specifica per quel portale
3. Aggiungere un workflow in `.github/workflows/` con trigger e secrets adeguati
4. Aggiornare questa mappa

---

## 🔧 Automazioni da Completare

| Task | Stato | Blocco |
|---|---|---|
| CaseVacanza uploader | Parziale | React synthetic events sui contatori stanze |
| Booking.com automazione | Bloccata | CAPTCHA su datacenter IP → eseguire locale |
| WhatsApp bot | In corso | Verifica numero con Edoardo su Meta |
| n8n + Claude API | In corso | Collegato a setup WhatsApp bot |
| Proprietari email sequence | Da iniziare | 5 email, alta priorità |

---

## 📍 Priorità Sprint Corrente

> Aggiornare questa sezione ogni settimana

- [ ] Correggere link Badesi e Costa Paradiso su tutto il sito
- [ ] Completare traduzioni "Rent Sardinia" → "AffittaSardegna" in TranslatePress
- [ ] Setup n8n + Claude API + WhatsApp bot (360dialog)
- [ ] Verificare sparizione "Rent Sardinia" da Google: `site:affittasardegna.it/en`
- [ ] Rimuovere Facebook Pixel test code TEST14379
- [ ] Redirect `/spiagge-poco-affollate-alghero-stintino/` ancora pending
- [ ] Sezione Proprietari da aggiungere a ogni pagina località

---

## 💡 Contesto Strategico

- **Brand concept:** "Sardegna Segreta" — conoscenza insider autentica
- **Edge competitivo:** 15 anni sul territorio, 9 lingue, autenticità locale
- **Competitor:** Sardinia Unlimited, ClickSardegna, Faendho, Domos Sardinia
- **Risk brand:** AffittaFSardegna.it (con O) — sito confusione brand
- **Social:** @affittasardegna (Instagram, 131 follower)
- **Meta Business:** @affittasardegna riconnesso come account primario IG

---

*Ultimo aggiornamento: 17 marzo 2026*
*Maintainer: Souad — aggiornare sezione "Priorità Sprint Corrente" ogni lunedì*
