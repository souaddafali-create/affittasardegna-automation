# CLAUDE.md — Mappa del progetto affittasardegna-automation

## Cosa fa questo progetto

Automazione per pubblicare proprietà in affitto breve su più portali (CaseVacanza.it, Booking.com) partendo da un unico file JSON dati.

Flusso principale:

```
Contratto proprietà + CIN
        │
        ▼
  Il_Faro_Badesi_DATI.json    ← unica fonte dati
        │
        ├──► casevacanza_uploader.py  → CaseVacanza.it
        └──► booking_uploader.py      → Booking Extranet
```

Ogni uploader legge il JSON, fa login sul portale, compila il wizard di inserimento proprietà con Playwright e si ferma prima dell'invio finale (screenshot di verifica).

---

## Mappa file

### Dati proprietà

| File | Descrizione |
|------|-------------|
| `Il_Faro_Badesi_DATI.json` | Dati completi della proprietà "Il Faro" a Badesi (SS). Contiene: identificativi (nome, indirizzo, CIN, CIR), composizione (ospiti, camere, bagni, letti), dotazioni (booleani per ogni servizio), condizioni (cauzione, soggiorni minimi), marketing (descrizioni, punti di forza, distanze). Questo file è la fonte unica: tutti gli uploader leggono da qui. |

### Uploader

| File | Portale | Dettagli |
|------|---------|----------|
| `casevacanza_uploader.py` | CaseVacanza.it | Playwright headless. Login su `my.casevacanza.it`, wizard 24 step: tipo struttura → indirizzo → mappa → ospiti/camere → letti → foto → servizi → titolo/descrizione → prezzo → cauzione → calendario → CIN → pagina finale. Env vars: `CASEVACANZA_EMAIL`, `CASEVACANZA_PASSWORD`. Override JSON con `PROPERTY_DATA`. |
| `booking_uploader.py` | Booking Extranet | Playwright con stealth mode (`playwright-stealth`). Login su `account.booking.com`, wizard ~12 step: tipo → nome → indirizzo → composizione → letti → servizi → foto → descrizione → prezzo/cauzione → CIN/CIR → finale. Env vars: `BK_EMAIL`, `BK_PASSWORD`. Override JSON con `PROPERTY_DATA`. |

### Workflow GitHub Actions

| File | Trigger | Cosa fa |
|------|---------|---------|
| `.github/workflows/upload.yml` | Push su `main` (se cambia `casevacanza_uploader.py` o il JSON) + manual | Esegue `casevacanza_uploader.py` con xvfb. Artifact: `screenshots/`. |
| `.github/workflows/booking_upload.yml` | Push su `main` (se cambia `booking_uploader.py` o il JSON) + manual | Esegue `booking_uploader.py` con xvfb e stealth. Artifact: `screenshots_booking/`. |
| `.github/workflows/booking_explore.yml` | Solo manual | Script esplorativo inline per Booking.com (stealth, human-like typing, CAPTCHA detection). Non usa il JSON. |

### Altro

| File | Descrizione |
|------|-------------|
| `script.js` | Script k6 per load testing di affittasardegna.it (10 VU, 30s, GET homepage). Non correlato agli uploader. |
| `README.md` | Placeholder minimo. |

---

## Proprietà attuale: Il Faro — Badesi (SS)

- **Tipo**: Appartamento, intero alloggio
- **Indirizzo**: Via Dettori 20, 07030 Badesi (SS), residence Le Onde, piano 2
- **CIN**: IT090081C2000U0391
- **Composizione**: max 4 ospiti, 1 camera, 4 posti letto (1 matrimoniale + 2 singoli), 1 bagno con doccia
- **Dotazioni presenti**: TV, piano cottura, frigo+congelatore, microonde, lavatrice, aria condizionata, phon, terrazza, arredi esterno, piscina comune, animali piccola taglia, parcheggio libero
- **Dotazioni assenti**: forno, lavastoviglie, riscaldamento, WiFi, ferro stiro, giardino, barbecue, culla, seggiolone
- **Cauzione**: 300 EUR

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

1. Creare un nuovo file JSON seguendo la stessa struttura di `Il_Faro_Badesi_DATI.json`
2. Eseguire gli uploader con `PROPERTY_DATA=nuovo_file.json python casevacanza_uploader.py`
3. Oppure modificare il default `DATA_FILE` in ciascun uploader

## Come aggiungere un nuovo portale

1. Creare `nuovo_portale_uploader.py` che carica il JSON con la stessa logica
2. Aggiungere un workflow in `.github/workflows/` con trigger e secrets adeguati
3. Aggiornare questa mappa
