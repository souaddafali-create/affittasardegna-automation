# LOCAL_RUN.md — Esecuzione locale di `casevacanza_computer_use.py`

> **Perché non gira su GitHub Actions**: gli IP dei runner Azure sono bloccati
> da Cloudflare davanti a `user.casevacanza.it`. Risultato:
> `ERR_NAME_NOT_RESOLVED` al primo `Page.goto`. Vedi `BOT_MEMORY.md`
> sezione 2026-05-05 (run #5).
>
> **Soluzione operativa**: lanciare l'agente dal PC residenziale di Souad
> (Windows, IP consumer non in blacklist).

---

## Prerequisiti (una sola volta)

1. **Python 3.12** (64-bit) installato e nel PATH.
   Verifica:
   ```powershell
   python --version
   ```
   Deve stampare `Python 3.12.x`. Se no, installa da
   https://www.python.org/downloads/ spuntando "Add Python to PATH".

2. **Repo clonato in locale**, ad esempio in `C:\Users\Souad\affittasardegna-automation`:
   ```powershell
   cd C:\Users\Souad
   git clone https://github.com/souaddafali-create/affittasardegna-automation.git
   cd affittasardegna-automation
   ```

3. **Dipendenze Python**:
   ```powershell
   pip install playwright anthropic
   ```

4. **Browser Chromium per Playwright** (download ~150 MB, una sola volta):
   ```powershell
   playwright install chromium
   ```

---

## Variabili d'ambiente

L'agente legge tre env var. Impostarle nella **stessa sessione PowerShell**
prima di lanciare lo script:

```powershell
$env:CV_EMAIL        = "email@casevacanza.it"
$env:CV_PASSWORD     = "passwordCaseVacanza"
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

> Le variabili impostate con `$env:` valgono solo per la finestra PowerShell
> aperta. Chiudi → si perdono. Per renderle permanenti usa
> `[Environment]::SetEnvironmentVariable("CV_EMAIL", "...", "User")` (richiede
> riavvio del terminale).

---

## Comando di esempio

Da PowerShell, dentro la cartella del repo:

```powershell
python casevacanza_computer_use.py Casa_Adelasia_A_DATI.json
```

Per un'altra proprietà basta cambiare il file JSON:

```powershell
python casevacanza_computer_use.py Villa_La_Vela_DATI.json
```

Default (senza argomenti) = `Casa_Adelasia_A_DATI.json`.

---

## Cosa aspettarsi a video

1. **Stampa di header** nel terminale con nome proprietà, modello (`claude-sonnet-4-6`),
   risoluzione (1280×800) e numero massimo turni (200).
2. **Si apre una finestra Chrome reale** (non headless): l'agente la usa come
   display. Non chiuderla, non cliccarci dentro mentre lavora.
3. Il browser naviga a `https://user.casevacanza.it/login` e Claude inizia a:
   - leggere la pagina via screenshot (1 ogni azione, salvati in `screenshots/cu_stepNNN.png`)
   - digitare email e password, fare login
   - cliccare "Aggiungi proprietà" e percorrere il wizard step by step
   - compilare ogni campo leggendo i dati dal JSON della proprietà
4. Nel terminale vedi una riga per ogni azione del modello (mouse click, type,
   key press, screenshot). Le password vengono mascherate come `***`.
5. **Tempo stimato**: 10–25 minuti per proprietà. **Costo stimato API**: $0.30–$1.00.
6. L'agente **si ferma prima dell'invio finale**: lascia il draft compilato in
   CaseVacanza per revisione manuale prima della pubblicazione.

---

## Troubleshooting rapido

| Sintomo | Causa probabile | Cosa fare |
|---------|-----------------|-----------|
| `KeyError: 'CV_EMAIL'` | env var non impostata in questa shell | Rilancia i 3 `$env:...` sopra |
| Chrome non si apre / "Executable doesn't exist" | mancato `playwright install` | `playwright install chromium` |
| `ERR_NAME_NOT_RESOLVED` anche da PC locale | DNS rotto / VPN aziendale che blocca | Disattiva VPN, prova a navigare a mano su `https://user.casevacanza.it` |
| Loop infinito su una schermata | wizard CaseVacanza cambiato in modo radicale | Interrompi con Ctrl+C, manda gli ultimi screenshot in `screenshots/` |
| `RateLimitError` Anthropic | troppi turni / immagini grandi | Aspetta 60s e rilancia, oppure verifica quota API key |

---

## Cosa NON fare durante l'esecuzione

- Non usare il PC mentre l'agente lavora (anche solo muovere il mouse sopra la
  finestra Chrome può confonderlo).
- Non chiudere la finestra Chrome a metà: il draft su CaseVacanza resta
  parziale e va completato a mano o ricreato da zero.
- Non lanciare due istanze in parallelo sullo stesso account CaseVacanza
  (vedi `BOT_MEMORY.md` 2026-05-03: il login SSO non gestisce sessioni
  concorrenti).
