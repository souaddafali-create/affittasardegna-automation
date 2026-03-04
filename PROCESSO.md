# PROCESSO.md — Stato del progetto CaseVacanza Uploader

Ultimo aggiornamento: 2026-03-04

---

## 1. Cosa funziona

| Fase | Stato | Dettagli |
|------|-------|----------|
| Login Keycloak SSO | OK | `#username`, `#password`, `#kc-login` su `my.casevacanza.it` |
| Chiusura popup cookie | OK | Bottone "Ok" + fallback ReactModal overlay |
| Navigazione wizard | OK | Link "Proprietà" → "Aggiungi una proprietà" → `/properties/new` |
| Lettura JSON proprietà | OK | `PROPERTY_DATA` env var o default `Il_Faro_Badesi_DATI.json` |

---

## 2. Wizard — Step noti (da codice attuale)

Il wizard in `casevacanza_uploader.py` ha 28 step hardcoded. **Molti selettori non sono mai stati verificati sulla pagina reale.**

| # | Descrizione | Selettori usati | Stato |
|---|-------------|-----------------|-------|
| 1 | "Proprietà a unità singola" | `get_by_text("Proprietà a unità singola")` | DA VERIFICARE |
| 2 | Tipo struttura (dropdown) | `page.locator("select")` → `select_option(label=tipo)` | DA VERIFICARE |
| 3 | "Intero alloggio" | `get_by_text("Intero alloggio")` | DA VERIFICARE |
| 4 | Continua (tipo) | `[data-test="save-button"]` | DA VERIFICARE |
| 5 | Indirizzo manuale | `get_by_text("Inseriscilo manualmente")` + `[data-test="stateOrProvince"]`, `[data-test="city"]`, `[data-test="street"]`, `[data-test="houseNumberOrName"]`, `[data-test="postalCode"]` | DA VERIFICARE |
| 6 | Continua (indirizzo) | `[data-test="save-button"]` | DA VERIFICARE |
| 7 | Mappa (coordinate GPS) | JS: hidden inputs lat/lng, Google Maps, Leaflet | DA VERIFICARE |
| 8 | Ospiti e camere | `[data-test="guest-count"]` OK, `[data-test="bedroom"]` **ROTTO**, `[data-test="bath_room"]` **ROTTO** | **ROTTO** |
| 9 | Continua (ospiti) | `[data-test="save-button"]` | DA VERIFICARE |
| 10 | Letti | `[data-test="counter-add-btn"]` per indice (0=divano, 1=matrim, 2=francese, 3=singolo) | DA VERIFICARE |
| 11 | Continua (letti) | `[data-test="save-button"]` | DA VERIFICARE |
| 12 | Upload foto | `input[type='file']`, `input[accept*='image']`, force display | **PROBLEMATICO** |
| 13 | Continua (foto) | `[data-test="save-button"]` | DA VERIFICARE |
| 14 | Servizi | Tab "Tutti" + checkbox/role-checkbox/JS/click text | DA VERIFICARE |
| 15 | Continua (servizi) | `[data-test="save-button"]` | DA VERIFICARE |
| 16 | "Li scrivo io" | `get_by_text("Li scrivo io")` | DA VERIFICARE |
| 17 | Titolo + descrizione | `get_by_label("Titolo")`, `get_by_label("Descrizione")` / `textarea` | DA VERIFICARE |
| 18 | Continua (titolo) | `[data-test="save-button"]` | DA VERIFICARE |
| 19 | Prezzo | `get_by_label("Prezzo")` / `input[type='number']` / `input[name*='prezz']` | DA VERIFICARE |
| 20 | Continua (prezzo) | `[data-test="save-button"]` | DA VERIFICARE |
| 21 | Cauzione | `get_by_label("Cauzione")` / `input[name*='cauzione']` / JS | DA VERIFICARE |
| 22 | Pulizie, biancheria, soggiorno min | Label/CSS/JS multi-strategia | DA VERIFICARE |
| 23 | Continua (condizioni) | `[data-test="save-button"]` | DA VERIFICARE |
| 24 | Check-in/out, regole | Label/CSS/JS multi-strategia | DA VERIFICARE |
| 25 | Continua (regole) | `[data-test="save-button"]` | DA VERIFICARE |
| 26 | Calendario (iCal) | Bottoni "Importa"/"Sincronizza" + `input[type='url']` | DA VERIFICARE |
| 27 | CIN | `get_by_label("CIN")` / `input[name*='cin']` / primo `input[type='text']` | DA VERIFICARE |
| 28 | Pagina finale | Solo screenshot, NO submit | DA VERIFICARE |

---

## 3. Problemi noti

### 3.1 Step 8 — Counter camere/bagni (ROTTO)

I selettori `[data-test="bedroom"]` e `[data-test="bath_room"]` non esistono sulla pagina reale. Solo `[data-test="guest-count"]` funziona. I counter per camere e bagni usano probabilmente label testuali ("Camera da letto", "Bagno") con bottoni +/- adiacenti.

**Impatto**: Il wizard non imposta correttamente il numero di camere e bagni. Per Il Faro (1 camera, 1 bagno) l'errore è meno grave perché il default potrebbe essere 1. Per Villa La Vela (2 camere, 1 bagno) manca almeno un click su camera da letto.

### 3.2 Step 12 — Foto (PROBLEMATICO)

- `Villa_La_Vela_DATI.json` ha `"foto": []` (array vuoto)
- Il fallback scarica da `picsum.photos` → inaffidabile in CI (timeout, rate limit, WebP invece di JPEG)
- Le immagini 800x600 sono borderline per il requisito minimo di 768px larghezza
- CaseVacanza potrebbe usare drag-and-drop senza `<input type="file">` standard

### 3.3 try_step swallows errors

```python
def try_step(page, step_name, func):
    try:
        func()
    except Exception as e:
        print(f"  ERRORE in {step_name}: {e}")
        # CONTINUA COMUNQUE → cascata di errori
```

Se step 8 fallisce, step 9 (click_save) potrebbe non avanzare il wizard. Tutti gli step successivi operano sulla pagina sbagliata. Nessuna verifica che il wizard sia effettivamente avanzato.

### 3.4 Step 19-28 — Selettori mai verificati

I selettori per prezzo, cauzione, pulizie, biancheria, check-in/out, calendario e CIN sono educated guesses basati su pattern comuni. Mai eseguiti su pagina reale. Probabilmente alcuni funzionano (es. label "Titolo"), altri no.

---

## 4. Proprietà configurate

### Il Faro (Badesi)

| Campo | Valore |
|-------|--------|
| File JSON | `Il_Faro_Badesi_DATI.json` |
| Tipo | Appartamento |
| Indirizzo | Via Ferraris 1, 07030 Badesi (SS) |
| Ospiti / Camere / Bagni | 4 / 1 / 1 |
| Letti | 1 matrimoniale, 2 singoli |
| Foto | Da verificare |
| Prezzo base | Calcolato da listino (mediana) |
| CIN | IT090006C2NV5B4C60 |

### Villa La Vela (Stintino)

| Campo | Valore |
|-------|--------|
| File JSON | `Villa_La_Vela_DATI.json` |
| Tipo | Villa |
| Indirizzo | Via Bruncu Spina 46A, 07040 Stintino (SS) |
| Ospiti / Camere / Bagni | 6 / 2 / 1 |
| Letti | 1 matrimoniale, 2 singoli, 1 divano letto |
| Foto | **NESSUNA** (`foto: []`) |
| Piscina | Privata |
| Prezzo base | ~240 EUR/notte (mediana 30 periodi) |
| CIN | IT090089C2000Q1525 |
| iCal | Sì (krossbooking.com) |

---

## 5. Funzionalità implementate

### 5.1 Verifica avanzamento wizard (`click_save_and_verify`)

Dopo ogni click su `[data-test="save-button"]`, il codice:
- Confronta URL e heading prima/dopo il click
- Se il wizard NON avanza, logga gli errori di validazione trovati sulla pagina
- Questo evita la "cascata di errori" dove step successivi operano sulla pagina sbagliata

### 5.2 Tariffe stagionali post-wizard

Dopo il wizard, se `condizioni.listino_prezzi` contiene periodi, il codice:
1. **Consolida** le entry settimanali in stagioni contigue (stesso prezzo) → `consolidate_seasonal_prices()`
2. **Naviga** alla lista proprietà → apre la proprietà appena creata
3. **Apre** il tab "Tariffe e disponibilità"
4. Per ogni stagione, clicca "Aggiungi prezzo stagionale" e compila: date, prezzo, soggiorno minimo

Per Villa La Vela → 12 stagioni consolidate (da 29 entry settimanali):
| Periodo | Prezzo | Min notti |
|---------|--------|-----------|
| 28 mar → 25 apr | €137 | 5 |
| 25 apr → 30 mag | €171 | 5 |
| 30 mag → 13 giu | €206 | 5 |
| 13 giu → 27 giu | €240 | 5 |
| 27 giu → 11 lug | €274 | 5 |
| 11 lug → 25 lug | €309 | 5 |
| 25 lug → 01 ago | €343 | 5 |
| 01 ago → 22 ago | €377 | 7 |
| 22 ago → 29 ago | €343 | 5 |
| 29 ago → 12 set | €240 | 5 |
| 12 set → 26 set | €206 | 5 |
| 26 set → 31 ott | €171 | 5 |

### 5.3 Step critici

Step 1 (unità singola) e Step 2 (tipo struttura) sono marcati `critical=True`:
se falliscono, il wizard si ferma subito invece di continuare alla cieca.

---

## 6. Prossimi passi

1. **Eseguire** il workflow Villa La Vela e verificare con gli screenshot
2. **Verificare** selettori reali dai screenshot/HTML di debug
3. **Aggiustare** eventuali selettori sbagliati
4. **Eseguire** l'uploader per Il Faro per confermare retrocompatibilità

---

## 6. File del progetto

| File | Ruolo |
|------|-------|
| `casevacanza_uploader.py` | Uploader principale CaseVacanza.it (28 step) |
| `booking_uploader.py` | Uploader Booking.com (con OTP) |
| `explore_wizard.py` | **NUOVO** — Esplorazione wizard senza compilare |
| `Il_Faro_Badesi_DATI.json` | Dati proprietà Il Faro |
| `Villa_La_Vela_DATI.json` | Dati proprietà Villa La Vela |
| `.github/workflows/upload.yml` | CI/CD uploader Il Faro |
| `.github/workflows/upload_villa_la_vela.yml` | CI/CD uploader Villa La Vela |
| `.github/workflows/explore_wizard.yml` | **NUOVO** — Workflow esplorazione |
| `CLAUDE.md` | Mappa progetto per AI |
| `PROCESSO.md` | **QUESTO FILE** — Stato e processo |
