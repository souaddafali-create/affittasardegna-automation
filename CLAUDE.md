# CLAUDE.md — Mappa del progetto affittasardegna-automation

## REGOLA FONDAMENTALE: solo dati dal JSON

**Il file JSON della proprietà è la UNICA fonte di verità. Zero eccezioni.**

1. Gli uploader NON devono MAI inventare dati. Leggono TUTTO dal JSON.
2. Se un dato non è presente nel JSON, NON lo inseriscono (lasciano vuoto).
3. Se una dotazione è `false` nel JSON, NON la spuntano.
4. Se una dotazione è `true`, la spuntano.
5. Prezzi: dal JSON (`condizioni.prezzo_notte`) se presente, altrimenti vuoto.
6. Letti: dal JSON (`composizione.letti[]`) con tipo e quantità.
7. Condizioni: soggiorno minimo, cauzione, pulizie, biancheria, check-in/out dal JSON.
8. Marketing: titolo e descrizione dal JSON, mai testo inventato.

Ogni proprietà avrà un JSON diverso con servizi diversi. Gli uploader si adattano automaticamente.

### Mappatura servizi CaseVacanza.it

| Chiave JSON | Label CaseVacanza |
|-------------|-------------------|
| `aria_condizionata` | Aria condizionata |
| `piscina` | Piscina (in comune) |
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

Automazione per pubblicare proprietà in affitto breve su più portali (CaseVacanza.it, Booking.com) partendo da un unico file JSON dati.

Flusso principale:

```
Contratto proprietà + CIN
        │
        ▼
  <proprietà>_DATI.json          ← unica fonte dati
        │
        ├──► casevacanza_uploader.py  → CaseVacanza.it
        └──► booking_uploader.py      → Booking Extranet
```

Ogni uploader legge il JSON, fa login sul portale, compila il wizard di inserimento proprietà con Playwright e si ferma prima dell'invio finale (screenshot di verifica).

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
    "cin": "...", "cir": "..."
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
    "regole_casa": "..."
  },
  "marketing": {
    "descrizione_breve": "...",
    "descrizione_lunga": "...",
    "punti_forza": ["...", "..."],
    "distanze": [{"luogo": "...", "km": 3, "tempo": "..."}]
  }
}
```

---

## Mappa file

### Dati proprietà

| File | Descrizione |
|------|-------------|
| `Il_Faro_Badesi_DATI.json` | Dati completi della proprietà "Il Faro" a Badesi (SS). Fonte unica: tutti gli uploader leggono da qui. |

### Uploader

| File | Portale | Dettagli |
|------|---------|----------|
| `casevacanza_uploader.py` | CaseVacanza.it | Playwright. Login su `my.casevacanza.it`, wizard 28 step: tipo → indirizzo → mappa → ospiti/camere → letti → foto → servizi → titolo/descrizione → prezzo → cauzione → pulizie/biancheria/soggiorno → check-in/out/regole → calendario → CIN → finale. Env vars: `CASEVACANZA_EMAIL`, `CASEVACANZA_PASSWORD`. Override JSON con `PROPERTY_DATA`. |
| `booking_uploader.py` | Booking Extranet | Playwright + stealth + OTP interattivo. Login su `account.booking.com` con supporto codice verifica email. Wizard ~12 step: tipo → nome → indirizzo → composizione → letti → servizi → foto → descrizione → prezzo/cauzione → CIN/CIR → finale. Env vars: `BK_EMAIL`, `BK_PASSWORD`. Override JSON con `PROPERTY_DATA`. Modalità interattiva: `INTERACTIVE=1` (browser visibile, OTP da terminale). |

### Workflow GitHub Actions

| File | Trigger | Cosa fa |
|------|---------|---------|
| `.github/workflows/upload.yml` | Push su `main` (se cambia `casevacanza_uploader.py` o il JSON) + manual | Esegue `casevacanza_uploader.py` con xvfb. Artifact: `screenshots/`. |
| `.github/workflows/booking_upload.yml` | Push su `main` (se cambia `booking_uploader.py` o il JSON) + manual | Esegue `booking_uploader.py` con xvfb e stealth. Artifact: `screenshots_booking/`. |
| `.github/workflows/booking_explore.yml` | Solo manual | Script esplorativo inline per Booking.com. Non usa il JSON. |

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

## Esecuzione locale di Booking (OTP)

Booking richiede codice verifica email. Per eseguire in locale:

```cmd
set BK_EMAIL=tua@email.com
set BK_PASSWORD=tuapassword
python booking_uploader.py
```

Il browser si apre visibile. Quando Booking chiede l'OTP, lo script pausa e chiede il codice nel terminale.
