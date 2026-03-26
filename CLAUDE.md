# CLAUDE.md — Mappa del progetto affittasardegna-automation

## REGOLA FONDAMENTALE: solo dati dal Google Sheet

**Il Google Sheet MASTER_PROPRIETÀ è la UNICA fonte di verità. Zero eccezioni.**

1. Gli uploader NON devono MAI inventare dati. Leggono TUTTO dal Google Sheet.
2. Se un dato non è presente nello sheet, NON lo inseriscono (lasciano vuoto).
3. Se una dotazione è `false` nello sheet, NON la spuntano.
4. Se una dotazione è `true`, la spuntano.
5. Prezzi: dallo sheet (`condizioni.listino_prezzi` mediana, o `condizioni.prezzo_notte`), altrimenti vuoto.
6. Letti: dallo sheet (`composizione.letti` come JSON inline) con tipo e quantità.
7. Condizioni: soggiorno minimo, cauzione, pulizie, biancheria, check-in/out dallo sheet.
8. Marketing: titolo e descrizione dallo sheet, mai testo inventato.

Ogni proprietà è una riga nel foglio con servizi diversi. Gli uploader si adattano automaticamente.

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

## Cosa fa questo progetto

Automazione per pubblicare proprietà in affitto breve su più portali (CaseVacanza.it, Booking.com) partendo da un Google Sheet centralizzato.

Flusso principale:

```
Contratto proprietà + CIN
        │
        ▼
  Google Sheet MASTER_PROPRIETÀ    ← unica fonte dati (gspread)
  (Sheet ID: 1pL0H0kJDvovg7w1nfF0PrFJYcR9UwLgszAoacYx6CEA)
        │
        ├──► casevacanza_uploader.py  → CaseVacanza.it
        └──► booking_uploader.py      → Booking Extranet
```

Ogni uploader legge la riga della proprietà dal Google Sheet via gspread, fa login sul portale, compila il wizard di inserimento proprietà con Playwright e si ferma prima dell'invio finale (screenshot di verifica).

---

## Struttura Google Sheet MASTER_PROPRIETÀ

Le colonne usano **dot-notation** corrispondente alla struttura JSON originale. Ogni riga è una proprietà. Valori complessi (array/oggetti) vanno inseriti come JSON inline nella cella.

| Colonna (header) | Tipo | Esempio |
|-------------------|------|---------|
| `identificativi.nome_struttura` | testo | Il Faro |
| `identificativi.tipo_struttura` | testo | Appartamento |
| `identificativi.indirizzo` | testo | Via Dettori 20 |
| `identificativi.cap` | testo | 07030 |
| `identificativi.comune` | testo | Badesi |
| `identificativi.provincia` | testo | SS |
| `identificativi.regione` | testo | Sardegna |
| `identificativi.cin` | testo | IT090081C2000U0391 |
| `identificativi.cir` | testo | 090081C2000U0391 |
| `composizione.max_ospiti` | numero | 4 |
| `composizione.camere` | numero | 1 |
| `composizione.posti_letto` | numero | 4 |
| `composizione.bagni` | numero | 1 |
| `composizione.letti` | JSON inline | `[{"tipo":"matrimoniale","quantita":1},{"tipo":"singolo","quantita":2}]` |
| `composizione.bagno_con_doccia` | true/false | true |
| `dotazioni.tv` | true/false | true |
| `dotazioni.aria_condizionata` | true/false | true |
| `dotazioni.*` | true/false | (una colonna per dotazione) |
| `dotazioni.altro_dotazioni` | testo | posto auto libero del residence |
| `condizioni.cauzione_euro` | numero | 300 |
| `condizioni.check_in` | testo | 15:00 - 20:00 |
| `condizioni.listino_prezzi` | JSON inline | `[{"da":"28-mar","a":"04-apr","prezzo_notte":137}]` |
| `marketing.descrizione_breve` | testo | ... |
| `marketing.descrizione_lunga` | testo | ... |
| `marketing.punti_forza` | JSON inline | `["Piscina","Vista mare"]` |
| `marketing.distanze` | JSON inline | `[{"luogo":"Spiaggia","km":3}]` |

---

## Mappa file

### Dati proprietà

| Fonte | Descrizione |
|-------|-------------|
| Google Sheet `MASTER_PROPRIETÀ` | Tutte le proprietà in un unico foglio. Ogni riga = una proprietà. Sheet ID: `1pL0H0kJDvovg7w1nfF0PrFJYcR9UwLgszAoacYx6CEA` |
| `Il_Faro_Badesi_DATI.json` | (Legacy) Dati JSON della proprietà "Il Faro" — ora migrati nel Google Sheet. |
| `Villa_La_Vela_DATI.json` | (Legacy) Dati JSON della proprietà "Villa La Vela" — ora migrati nel Google Sheet. |

### Uploader

| File | Portale | Dettagli |
|------|---------|----------|
| `casevacanza_uploader.py` | CaseVacanza.it | Playwright. Login su `my.casevacanza.it`, wizard 28 step. Legge dati da Google Sheet via gspread. Env vars: `CASEVACANZA_EMAIL`, `CASEVACANZA_PASSWORD`, `GOOGLE_SERVICE_ACCOUNT_JSON`. Seleziona proprietà con `PROPERTY_NAME`. |
| `booking_uploader.py` | Booking Extranet | Playwright + stealth + OTP interattivo. Login su `account.booking.com`. Wizard ~12 step. Legge dati da Google Sheet via gspread. Env vars: `BK_EMAIL`, `BK_PASSWORD`, `GOOGLE_SERVICE_ACCOUNT_JSON`. Seleziona proprietà con `PROPERTY_NAME`. Modalità interattiva: `INTERACTIVE=1`. |

### Workflow GitHub Actions

| File | Trigger | Cosa fa |
|------|---------|---------|
| `.github/workflows/upload.yml` | Push su `main` + manual | Esegue `casevacanza_uploader.py` con xvfb. Legge da Google Sheet. Artifact: `screenshots/`. |
| `.github/workflows/booking_upload.yml` | Push su `main` + manual | Esegue `booking_uploader.py` con xvfb e stealth. Legge da Google Sheet. Artifact: `screenshots_booking/`. |
| `.github/workflows/upload_villa_la_vela.yml` | Push su `main` + manual | Esegue `casevacanza_uploader.py` con `PROPERTY_NAME=Villa La Vela`. Legge da Google Sheet. Artifact: `villa-la-vela-debug-screenshots/`. |
| `.github/workflows/booking_explore.yml` | Solo manual | Script esplorativo inline per Booking.com. Non usa il JSON. |
| `.github/workflows/explore_wizard.yml` | Solo manual | Esegue `explore_wizard.py` per mappare il wizard CaseVacanza. Artifact: `wizard-exploration/`. |

### Esplorazione e documentazione

| File | Descrizione |
|------|-------------|
| `explore_wizard.py` | Script esplorativo: login + navigazione wizard CaseVacanza step-by-step SENZA compilare. Cattura screenshot, HTML e struttura form di ogni step. Salva `WIZARD_MAP.json`. |
| `PROCESSO.md` | Documentazione stato progetto: cosa funziona, cosa è rotto, selettori noti, prossimi passi. Aggiornato ad ogni sessione. |

### Altro

| File | Descrizione |
|------|-------------|
| `script.js` | Script k6 per load testing di affittasardegna.it (10 VU, 30s, GET homepage). Non correlato agli uploader. |
| `README.md` | Placeholder minimo. |

---

## Secrets GitHub necessari

| Secret | Usato da |
|--------|----------|
| `CASEVACANZA_EMAIL` | casevacanza_uploader.py |
| `CASEVACANZA_PASSWORD` | casevacanza_uploader.py |
| `BK_EMAIL` | booking_uploader.py |
| `BK_PASSWORD` | booking_uploader.py |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Tutti gli uploader (autenticazione gspread per Google Sheet) |

---

## Come aggiungere una nuova proprietà

1. Aggiungere una nuova riga nel foglio `MASTER_PROPRIETÀ` del Google Sheet
2. Compilare TUTTE le colonne: `identificativi.*`, `composizione.*` (incluso `composizione.letti` come JSON inline), `dotazioni.*` (true/false), `condizioni.*`, `marketing.*`
3. Eseguire: `PROPERTY_NAME="Nome Struttura" python casevacanza_uploader.py`
4. L'uploader spunta SOLO i servizi con `true` nello sheet, compila SOLO i dati presenti

## Come aggiungere un nuovo portale

1. Creare `nuovo_portale_uploader.py` che carica i dati dallo sheet con la stessa logica gspread
2. Aggiungere la mappatura `DOTAZIONI_MAP` specifica per quel portale
3. Aggiungere un workflow in `.github/workflows/` con trigger, secrets e `GOOGLE_SERVICE_ACCOUNT_JSON`
4. Aggiornare questa mappa

## Esecuzione locale di Booking (OTP)

Booking richiede codice verifica email. Per eseguire in locale:

```cmd
set BK_EMAIL=tua@email.com
set BK_PASSWORD=tuapassword
set GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
python booking_uploader.py
```

Il browser si apre visibile. Quando Booking chiede l'OTP, lo script pausa e chiede il codice nel terminale.
