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

Automazione per pubblicare proprietà in affitto breve su 5 portali partendo da un unico file JSON dati.

Flusso principale:

```
Contratto proprietà + CIN
        │
        ▼
  <proprietà>_DATI.json              ← unica fonte dati
        │
        ├──► casevacanza_uploader.py   → CaseVacanza.it   (Playwright)
        ├──► booking_uploader.py       → Booking Extranet  (Playwright + stealth)
        ├──► immobiliare_uploader.py   → Immobiliare.it    (API REST-XML)
        ├──► idealista_uploader.py     → Idealista.it      (Playwright)
        └──► expedia_uploader.py       → Vrbo/Expedia      (Playwright + stealth)
```

Tutti gli uploader importano utilities condivise da `uploader_base.py`.
Le mappature dotazioni sono in `portali/<portale>_map.py`.
Krossbooking gestisce la sincronizzazione calendari e tariffe.

Ogni uploader si ferma prima dell'invio finale (screenshot di verifica).

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

### Framework condiviso

| File | Descrizione |
|------|-------------|
| `uploader_base.py` | Utilities condivise: `load_property_data()`, `screenshot()`, `save_html()`, `wait()`, `try_step()`, `download_placeholder_photos()`, `build_services()`, `create_browser_context()`. Importato da tutti gli uploader. |
| `portali/` | Directory con mappature dotazioni per portale. |
| `portali/immobiliare_map.py` | Mappatura dotazioni → XML tags per Immobiliare.it API. |
| `portali/idealista_map.py` | Mappatura dotazioni → label checkbox Idealista. |
| `portali/expedia_map.py` | Mappatura dotazioni → label checkbox Vrbo/Expedia (EN + IT). |

### Uploader

| File | Portale | Metodo | Dettagli |
|------|---------|--------|----------|
| `casevacanza_uploader.py` | CaseVacanza.it | Playwright | Login su `my.casevacanza.it`, wizard 28 step. Env: `CASEVACANZA_EMAIL`, `CASEVACANZA_PASSWORD`. |
| `booking_uploader.py` | Booking Extranet | Playwright + stealth | Login con OTP interattivo. Wizard ~12 step. Env: `BK_EMAIL`, `BK_PASSWORD`. `INTERACTIVE=1` per browser visibile. |
| `immobiliare_uploader.py` | Immobiliare.it | **API REST-XML** | Niente Playwright! PUT su `feed.immobiliare.it`. Env: `IMMOBILIARE_EMAIL`, `IMMOBILIARE_PASSWORD`, `IMMOBILIARE_SOURCE`. `DRY_RUN=1` per test. |
| `idealista_uploader.py` | Idealista.it | Playwright | Login su `idealista.it/login`, wizard ~10 step. Env: `IDEALISTA_EMAIL`, `IDEALISTA_PASSWORD`. |
| `expedia_uploader.py` | Vrbo/Expedia | Playwright + stealth | Login su `vrbo.com`, wizard ~10 step. Env: `EXPEDIA_EMAIL`, `EXPEDIA_PASSWORD`. `INTERACTIVE=1` per 2FA. |

### Workflow GitHub Actions

| File | Trigger | Cosa fa |
|------|---------|---------|
| `.github/workflows/upload.yml` | Push su `main` (se cambia `casevacanza_uploader.py` o il JSON) + manual | Esegue `casevacanza_uploader.py` con xvfb. Artifact: `screenshots/`. |
| `.github/workflows/booking_upload.yml` | Push su `main` (se cambia `booking_uploader.py` o il JSON) + manual | Esegue `booking_uploader.py` con xvfb e stealth. Artifact: `screenshots_booking/`. |
| `.github/workflows/immobiliare_upload.yml` | Push su `main` (se cambia `immobiliare_uploader.py` o il JSON) + manual | Esegue `immobiliare_uploader.py` (API, no browser). |
| `.github/workflows/idealista_upload.yml` | Push su `main` (se cambia `idealista_uploader.py` o il JSON) + manual | Esegue `idealista_uploader.py` con xvfb. Artifact: `screenshots_idealista/`. |
| `.github/workflows/expedia_upload.yml` | Push su `main` (se cambia `expedia_uploader.py` o il JSON) + manual | Esegue `expedia_uploader.py` con xvfb e stealth. Artifact: `screenshots_expedia/`. |
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
| `IMMOBILIARE_EMAIL` | immobiliare_uploader.py |
| `IMMOBILIARE_PASSWORD` | immobiliare_uploader.py |
| `IMMOBILIARE_SOURCE` | immobiliare_uploader.py |
| `IDEALISTA_EMAIL` | idealista_uploader.py |
| `IDEALISTA_PASSWORD` | idealista_uploader.py |
| `EXPEDIA_EMAIL` | expedia_uploader.py |
| `EXPEDIA_PASSWORD` | expedia_uploader.py |

---

## Come aggiungere una nuova proprietà

1. Creare un nuovo file JSON seguendo la struttura sopra (copiare `Il_Faro_Badesi_DATI.json` come template)
2. Compilare TUTTI i campi: identificativi, composizione (incluso `letti`), dotazioni (true/false per ciascuna), condizioni, marketing
3. Eseguire su tutti i portali:
   ```bash
   export PROPERTY_DATA=nuovo_file.json
   python casevacanza_uploader.py
   python booking_uploader.py
   DRY_RUN=1 python immobiliare_uploader.py   # test XML prima dell'invio
   python idealista_uploader.py
   python expedia_uploader.py
   ```
4. L'uploader spunta SOLO i servizi con `true` nel JSON, compila SOLO i dati presenti

## Come aggiungere un nuovo portale

1. Creare `portali/nuovo_portale_map.py` con la mappatura `DOTAZIONI_MAP`
2. Creare `nuovo_portale_uploader.py` che importa da `uploader_base` e dalla mappatura
3. Aggiungere un workflow in `.github/workflows/` con trigger e secrets
4. Aggiornare questa mappa e la tabella secrets

## Esecuzione locale

### Booking (richiede OTP email)
```bash
export BK_EMAIL=tua@email.com BK_PASSWORD=tuapassword
python booking_uploader.py   # browser visibile, OTP da terminale
```

### Expedia/Vrbo (richiede 2FA)
```bash
export EXPEDIA_EMAIL=tua@email.com EXPEDIA_PASSWORD=tuapassword
INTERACTIVE=1 python expedia_uploader.py   # browser visibile per 2FA
```

### Immobiliare.it (API — dry run consigliato)
```bash
export IMMOBILIARE_EMAIL=email IMMOBILIARE_PASSWORD=pwd IMMOBILIARE_SOURCE=src
DRY_RUN=1 python immobiliare_uploader.py   # stampa XML senza inviare
python immobiliare_uploader.py              # invio reale
```

### Note Immobiliare.it
Per usare l'API REST-XML serve:
1. Account agenzia su Immobiliare.it
2. Richiedere credenziali API (username, password, X-IMMO-SOURCE) al supporto
3. Registrare l'IP del server per accesso API
4. Ref: https://feed.immobiliare.it/integration/ii/docs/import/get-start
