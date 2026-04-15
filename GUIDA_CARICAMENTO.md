# Guida al caricamento delle proprietà

Questa guida spiega come caricare una nuova proprietà su **CaseVacanza.it** e
**Booking.com** usando lo script automatico `carica_proprieta.bat`.

---

## 1. Cosa serve sul PC (una volta sola)

Prima del primo utilizzo, verifica che sul PC siano installati:

1. **Python 3.10 o superiore**
   - Scarica da <https://www.python.org/downloads/>
   - **IMPORTANTE**: durante l'installazione spunta la casella
     **"Add Python to PATH"**.

2. **Google Chrome** (o Chromium)
   - Scarica da <https://www.google.com/chrome/>

3. **Librerie Python necessarie**
   - Apri il **Prompt dei comandi** (cerca "cmd" nel menu Start)
   - Spostati nella cartella del progetto, ad esempio:
     ```
     cd C:\Users\TuoNome\affittasardegna-automation
     ```
   - Esegui questi due comandi (solo la prima volta):
     ```
     pip install playwright
     python -m playwright install chromium
     ```

> 💡 Se qualcosa non funziona nei passi 1-3, chiedi supporto a Soua prima di
> proseguire: senza questi prerequisiti lo script non può partire.

---

## 2. Preparare il file JSON della proprietà

Ogni proprietà ha un file `.json` con tutti i suoi dati (indirizzo, prezzi,
servizi, foto, ecc.). Il file è **l'unica fonte di verità**: gli script
leggono soltanto da lì.

- Il file deve stare nella **stessa cartella** di `carica_proprieta.bat`.
- Il nome segue lo schema: `Nome_Proprieta_DATI.json`.
- Esempi già presenti: `Il_Faro_Badesi_DATI.json`,
  `Villa_La_Vela_DATI.json`, `Bilo_Le_Calette_DATI.json`.

Per una nuova proprietà, duplica uno dei file esistenti e aggiorna tutti i
campi. Se hai dubbi sulla struttura JSON, chiedi a Soua.

---

## 3. Avviare il caricamento

1. Apri la cartella del progetto con **Esplora File**.
2. **Doppio click** sul file `carica_proprieta.bat`.
3. Si aprirà una finestra nera (il Prompt dei comandi). Lo script ti chiederà,
   nell'ordine:

   | Domanda | Cosa inserire |
   |---------|--------------|
   | Email CaseVacanza | La tua email di accesso a CaseVacanza.it |
   | Password CaseVacanza | La password CaseVacanza |
   | Email Booking | La tua email di accesso a Booking Extranet |
   | Password Booking | La password Booking |
   | Nome del file JSON | Es. `Bilo_Le_Calette_DATI.json` |
   | La proprietà è già registrata su Booking? | `S` se sì, `N` se nuova |
   | HOTEL_ID Booking (solo se S) | Il numero dell'Extranet (es. `16088667`) |

4. Lo script apre automaticamente Chrome e inizia a compilare i portali:
   - **Prima CaseVacanza.it** (wizard completo)
   - **Poi Booking.com** (wizard completo oppure skip se `S` al punto 6)

5. **NON chiudere il browser** mentre lavora. Se Booking chiede un codice di
   verifica via email (OTP) o un CAPTCHA, lo script si ferma e te lo chiede
   nel Prompt dei comandi:
   - leggi il codice dalla tua casella email
   - digitalo nella finestra nera
   - premi INVIO

6. Quando hai finito di controllare che il login Booking sia completo, lo
   script ti chiede di premere INVIO per avviare l'automazione.

7. Alla fine vedrai il messaggio:
   ```
   ✅ Caricamento completato su entrambi i portali
   ```

---

## 4. Verifica finale (importante!)

Lo script **NON invia** la proprietà automaticamente: si ferma sempre sulla
pagina finale in modo che tu possa controllare tutto.

Prima di cliccare "Pubblica" o "Invia" sui portali:

- Controlla il titolo e la descrizione.
- Verifica indirizzo, numero di ospiti, camere, bagni, letti.
- Controlla i prezzi, la cauzione, le pulizie.
- Verifica che le foto siano caricate.
- Controlla CIN e CIR.

Se qualcosa è sbagliato, correggi direttamente nel portale oppure modifica il
file JSON e rilancia lo script.

---

## 5. Se qualcosa va storto

| Messaggio che vedi | Cosa fare |
|--------------------|-----------|
| `❌ Python non trovato` | Reinstalla Python spuntando "Add Python to PATH". |
| `❌ Playwright non è installato` | Esegui `pip install playwright` + `python -m playwright install chromium`. |
| `❌ file JSON non trovato` | Verifica che il file JSON sia nella stessa cartella del `.bat`. |
| `❌ file JSON contiene un errore di sintassi` | Apri il JSON con un editor e correggi (virgole, parentesi, virgolette). |
| `❌ variabile d'ambiente mancante` | Ricompare la richiesta di email/password: rispondi nel Prompt. |
| `⚠️ Caricamento terminato con errori` | Apri le cartelle `screenshots/` e `screenshots_booking/`: ogni step ha una foto + file HTML che mostrano dove si è fermato. Inviale a Soua. |
| CAPTCHA o codice OTP Booking | Lo script si ferma e aspetta: inserisci il codice ricevuto via email nella finestra nera e premi INVIO. |

### Log e screenshot per la diagnostica

Dopo ogni esecuzione trovi nella cartella del progetto:

- `screenshots/` → screenshot e HTML del wizard CaseVacanza
- `screenshots_booking/` → screenshot e HTML del wizard Booking

Se devi chiedere aiuto, allega queste cartelle al messaggio.

---

## 6. Note importanti

- 🏠 **Usa sempre il tuo PC di casa o ufficio.** Booking richiede un IP
  residenziale italiano; da cloud o VPN il login può essere bloccato.
- 🔒 **Le credenziali** vengono chieste ad ogni esecuzione e **non vengono
  salvate** sul disco. Per comodità puoi impostarle come variabili d'ambiente
  di Windows (chiedi a Soua).
- 📄 **Il JSON è l'unica fonte di verità**: gli script non inventano dati.
  Se un campo manca nel JSON, la casella resta vuota sul portale.
- 🔁 Puoi **rilanciare** lo script quante volte vuoi: non invia nulla in
  automatico, ti ferma sempre alla pagina finale.

---

## 7. Esempio di esecuzione (test)

Per verificare che tutto funzioni usa la proprietà di test già presente:

1. Doppio click su `carica_proprieta.bat`
2. Inserisci le credenziali CaseVacanza e Booking
3. Quando chiede il file JSON, scrivi: `Bilo_Le_Calette_DATI.json`
4. Alla domanda "La proprietà è già registrata su Booking?" rispondi `S`
5. HOTEL_ID: `16088667`
6. Lo script aprirà Chrome, farà login e ti porterà sulla pagina della
   struttura di test.

Se tutto va a buon fine vedrai `✅ Caricamento completato`.

---

Per qualunque dubbio scrivi a Soua con lo screenshot dell'errore e la cartella
`screenshots/` (o `screenshots_booking/`) allegata.
