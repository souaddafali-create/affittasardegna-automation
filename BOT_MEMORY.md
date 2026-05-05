# BOT_MEMORY.md — Memoria persistente dei bot di affittasardegna-automation

> **Regola d'oro**: PRIMA di indagare un nuovo bug, leggi questo file.
> Probabilmente il problema è già successo e ha una soluzione (o una causa nota).

Questo file è la memoria a lungo termine del progetto. Tutti i bot uploader
(CaseVacanza, Booking, futuri portali) sono fragili per natura: i portali
cambiano HTML, le sessioni si confondono, i CDN bloccano gli IP. Tenere traccia
qui di **cosa si è rotto, quando, perché e come si è risolto** evita di
ripercorrere ogni volta la stessa indagine.

## Approccio Computer Use (introdotto 2026-05-04)

Da maggio 2026 il bot CaseVacanza principale è `casevacanza_computer_use.py` —
un agente Claude Computer Use che pilota il browser leggendo lo schermo, senza
selettori CSS hardcoded. Anti-fragile per costruzione: quando il portale cambia
HTML il bot non si rompe perché non legge l'HTML, legge i pixel.

`casevacanza_uploader.py` (Playwright scriptato) resta come fallback finché non
abbiamo confidenza che Computer Use sia stabile in produzione.

**Cosa va in memoria qui:**
- Bug visti in produzione (con data e proprietà coinvolta).
- Causa accertata (anche se diversa dall'ipotesi iniziale).
- Soluzione applicata (PR/commit di riferimento).
- Workaround conosciuti.
- Quirk del portale CaseVacanza/Booking/Krossbooking.

**Cosa NON va qui:**
- Dettagli implementativi (vivono in CLAUDE.md e PROCESSO.md).
- TODO generici (vivono nelle issue GitHub).

---

## Storia bug e soluzioni

Formato: `[data] [bot] [proprietà] PROBLEMA → SOLUZIONE (PR #N)`

### 2026-05-03 — Run notturno 6 case CaseVacanza

**Bot**: `casevacanza_uploader.py` (Playwright). **Proprietà**: Casa Bianca 1/2/3, Casa Adelasia A/B, Mono Ibisco.

**Problema**: tutti e 6 i workflow lanciati in parallelo. Run verdi su Actions, ma sul pannello CaseVacanza:
- Adelasia A/B: 91% riempite, OK
- Casa Bianca 1/2/3 e Mono Ibisco: scheletro vuoto, no CIN, no iCal, no foto, no dotazioni

**Causa accertata**: i 6 workflow giravano in parallelo con concurrency group diverso → 6 sessioni Keycloak SSO simultanee sullo stesso account CaseVacanza. La sessione lato server ha sovrascritto/invalidato 4 draft su 6. Tutti i run risultavano comunque verdi perché `try_step` catturava silenziosamente le eccezioni e il bot continuava sulla pagina sbagliata.

**Soluzione**: concurrency group globale `casevacanza-global` con `cancel-in-progress: false` su tutti i workflow CaseVacanza → run sequenziali, mai in parallelo. PR #66 (mergiato).

**Lezione**: SaaS B2B con login SSO non gestiscono bene N sessioni concorrenti dello stesso utente. Default per qualsiasi nuovo portale: concurrency group **per account**, non per proprietà.

### 2026-05-04 (mattina) — Run di Casa Bianca 1, post-fix concurrency

**Bot**: `casevacanza_uploader.py`. **Proprietà**: Casa Bianca 1.

**Problema**: il bot arriva a step 10 (letti per camera) ma non clicca i `+`. Run verde, schermata "Quali sono le caratteristiche delle stanze" lasciata vuota.

**Causa accertata duplice**:
1. `try_step` di default catturava le eccezioni → falliment del counter letti veniva mascherato.
2. Selettore JS in `do_step10` cercava "container con il label e ≥2 button" guardando solo `parentElement.parentElement` del `+` button → struttura DOM più profonda → nessun match.

**Soluzione**: PR #67 (in revisione)
- Fix #2: `try_step` ora di default rilancia l'eccezione → run rosso quando il bot fallisce.
- Fix #6: nuovo `click_letto_counter` con verifica del valore del counter dopo i click + walk DOM più profondo.

### 2026-05-04 (pomeriggio) — Foto CDN HTTP 403

**Bot**: `casevacanza_uploader.py`. **Proprietà**: Casa Adelasia A.

**Problema**: dopo i fix di PR #67, primo run "onesto" → 21/21 foto Krossbooking restituiscono `HTTP 403 Forbidden`.

**Causa accertata**: `urllib.request.urlretrieve` usa `User-Agent: Python-urllib/3.x` di default. Il CDN Krossbooking è hot-link-protetto: rifiuta richieste senza Referer di un dominio autorizzato e/o User-Agent da browser reale.

**Soluzione**: header HTTP completi mimando Chrome 120 Win64:
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Referer: https://book.affittasardegna.it/
Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8
Sec-Fetch-Dest: image
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: cross-site
```
Commit `4aa5224` su PR #67.

**Lezione**: per qualsiasi CDN che serve risorse di un altro dominio, sempre `Referer` + `User-Agent` da browser reale. Mai default urllib.

### 2026-05-04 (pomeriggio) — Counter letto "no-op"

**Bot**: `casevacanza_uploader.py`. **Proprietà**: Casa Adelasia A.

**Problema**: `page.mouse.click(x, y)` sul `+` di "Letto matrimoniale" non incrementa il valore.

**Causa probabile** (non confermata, HTML non disponibile in locale): il `+` button è un componente React/shadcn che ascolta `pointerdown` invece del solo `click` sintetizzato a coordinate. `page.mouse.click(x, y)` colpisce le coordinate giuste ma non scatena gli handler React.

**Soluzione**: `click_letto_button_via_js` dispatcha sequenza completa pointer+mouse events DENTRO `page.evaluate`:
```js
addBtn.scrollIntoView({block: 'center'});
addBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
addBtn.dispatchEvent(new MouseEvent('mousedown', opts));
addBtn.dispatchEvent(new PointerEvent('pointerup', opts));
addBtn.dispatchEvent(new MouseEvent('mouseup', opts));
addBtn.click();
```
Più wait 600ms post-click. Commit `4aa5224` su PR #67.

**Lezione**: contro componenti React/shadcn moderni, sempre dispatchEvent dentro `page.evaluate` invece di `page.mouse.click(x, y)`. Quest'ultimo è affidabile solo per HTML statico o handler `onclick` standard.

### 2026-05-04 (sera) — Fragilità sistemica → svolta architetturale

**Decisione strategica**: 4 cicli di fix in 36 ore solo su CaseVacanza, su 6 proprietà di test. Estrapolando al volume reale di Souad (~5 case/giorno × 4 portali = ~700 inserimenti/mese), Playwright scriptato non è sostenibile.

**Soluzione**: passaggio a **Claude Computer Use** (`casevacanza_computer_use.py`).
- L'agente legge lo schermo come un umano, decide cosa cliccare guardando i pixel.
- Quando CaseVacanza cambia il colore di un bottone, sposta un campo, rinomina una label → l'agente si adatta da solo. Niente selettori da aggiornare.
- Costo stimato per inserzione: ~$0.30–$1.00 (vedi PR #68).

PR #68. `casevacanza_uploader.py` resta come fallback finché Computer Use non ha 1-2 settimane di stabilità in produzione.

### 2026-05-05 (run #3) — Screenshot iniziale Computer Use fallisce su about:blank

**Bot**: `casevacanza_computer_use.py`. **Proprietà**: Casa Adelasia A (run #3 del workflow `upload_cu_casa_adelasia_a.yml`, branch `claude/casevacanza-computer-use`, commit `da4355d`).

**Problema**: lo script crashava in 44s, prima ancora di entrare nel loop dell'agent. Stack trace:
```
File "casevacanza_computer_use.py", line 200, in <module>
    initial_screenshot = screenshot_b64()
...
playwright._impl._errors.Error: Page.screenshot: Protocol error
(Page.captureScreenshot): Unable to capture screenshot
Call log:
  - taking page screenshot
  - waiting for fonts to load...
  - fonts loaded
```
Artifact `screenshots/` vuoto perché il primo `save_screenshot` è dentro il loop, mai raggiunto.

**Causa accertata**: il browser era ancora su `about:blank` (riga `page.goto("about:blank")`) al momento del primo screenshot. Chromium su xvfb in CI non riesce a fare `captureScreenshot` su `about:blank` in modo affidabile — il protocollo CDP fallisce dopo il "fonts loaded" senza un DOM reale.

**Soluzione**: prima del primo screenshot navighiamo a `LOGIN_URL` con `wait_until="domcontentloaded"` + `wait_for_load_state("networkidle", timeout=10s)` best-effort + `time.sleep(1.5)` di settling. Lo screenshot iniziale è inoltre wrappato in retry (3 tentativi, sleep 2s tra uno e l'altro) con messaggio di errore esplicito se tutti falliscono. Commit `53f4d1e` sul branch `claude/casevacanza-computer-use`. Nota: `LOGIN_URL` puntava inizialmente a `https://www.casevacanza.it/login` (301 → user); poi cambiato a `https://user.casevacanza.it/login` per il bug DNS sotto.

**Lezione**: con xvfb + Chromium headed mode, mai chiamare `page.screenshot()` su `about:blank`. Navigare sempre a una pagina reale prima del primo screenshot, anche solo come "warm-up" del compositor.

### 2026-05-05 (run #4) — DNS ERR_NAME_NOT_RESOLVED su www.casevacanza.it dal runner

**Bot**: `casevacanza_computer_use.py`. **Proprietà**: Casa Adelasia A (run #4 GitHub Actions).

**Problema**: l'agente Computer Use fallisce al primo `Page.goto` con
`playwright._impl._errors.Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://www.casevacanza.it/login`.
Da browser normale lo stesso URL fa 301 redirect a `user.casevacanza.it/login`
e funziona; dal runner GitHub Actions invece il resolver non risolve `www`.

**Causa accertata**: il DNS resolver del runner GitHub Actions non gestisce il
subdomain `www.casevacanza.it`. Solo `user.casevacanza.it` (dominio reale del
portale gestori, target del 301) è risolvibile in quell'ambiente.

**Soluzione**: cambiata la costante `LOGIN_URL` in
`casevacanza_computer_use.py` da `https://www.casevacanza.it/login` a
`https://user.casevacanza.it/login`. Il prompt iniziale già la referenziava,
quindi l'agente ora digita direttamente il dominio risolvibile e salta il
redirect.

**Lezione**: per qualsiasi portale con redirect `www → subdomain`, puntare
direttamente al subdomain finale. I runner CI hanno DNS più rigorosi dei
browser desktop e non sempre seguono catene di redirect su domini "marketing".

### 2026-05-05 (run #5) — ERR_NAME_NOT_RESOLVED anche su user.casevacanza.it dal runner

**Bot**: `casevacanza_computer_use.py`. **Proprietà**: Casa Adelasia A (run #5 GitHub Actions, branch `claude/casevacanza-computer-use`, commit `d74ff06`).

**Problema**: dopo il fix di run #4 (LOGIN_URL → `https://user.casevacanza.it/login`), il run #5 fallisce comunque con
`playwright._impl._errors.Error: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://user.casevacanza.it/login`.
Da PC residenziale lo stesso URL risolve e carica il login senza problemi.

**Causa accertata**: non è un problema di subdomain (come ipotizzato in run #4) ma di **IP del runner**. GitHub Actions usa range IP Azure; Cloudflare davanti a CaseVacanza/Krossbooking blocca/sinkhola le query DNS provenienti da quei range come misura anti-bot/anti-scraping. Risultato: il resolver del runner restituisce NXDOMAIN (o equivalente) per `user.casevacanza.it`, a prescindere dal subdomain scelto.

**Soluzione**: **abbandonata l'esecuzione da GitHub Actions** per Computer Use CaseVacanza. Il bot va lanciato dal **PC residenziale di Souad** (Windows, IP consumer non bloccato). Istruzioni in `LOCAL_RUN.md`. I 3 fix di oggi (filtro text block vuoti, screenshot post-navigation, LOGIN_URL diretto) restano comunque validi e mergiati su main: utili per qualsiasi futura esecuzione, sia locale sia eventualmente da self-hosted runner residenziale.

**Lezione**: i runner cloud condivisi (GitHub Actions, Azure, AWS Lambda, ecc.) sono spesso in blacklist sui CDN anti-bot di portali "consumer". Per scrape/automation di SaaS B2C-ish: o IP residenziale (PC locale, self-hosted runner casalingo) oppure proxy residenziale a pagamento. Non perdere tempo a ottimizzare DNS/User-Agent quando il problema è l'ASN.

---

## Quirk noti dei portali

### CaseVacanza.it (`my.casevacanza.it`)
- Login Keycloak SSO su `id.casevacanza.it` (login frame separato).
- Wizard "Aggiungi proprietà" cambia HTML senza preavviso (almeno 2 cambi visti tra mar–mag 2026).
- Una sola sessione attiva per account: login concorrenti invalidano i precedenti draft.
- Il listino prezzi stagionali NON è inseribile dal wizard di creazione: solo dal pannello "Tariffe e disponibilità" della proprietà già creata. Resta operazione manuale.

### Booking.com (`account.booking.com`)
- Login richiede OTP via email → in CI serve gestione OTP (vedi `booking_uploader.py`, modalità `INTERACTIVE=1`).
- Anti-bot più aggressivo: serve `playwright-stealth` o equivalente.

### Krossbooking CDN (`cdn.krossbooking.com`)
- Hot-link protezione: serve `Referer: https://book.affittasardegna.it/` + User-Agent da browser reale.
- Possibile rate limit IP-based per molti download paralleli (causa sospettata 03/05). Default: download sequenziale con throttle 0.5s.

---

## Per chi aggiunge un nuovo bug a questo file

Aggiungi una sezione con il formato:

```markdown
### YYYY-MM-DD — Titolo breve

**Bot**: <file>. **Proprietà**: <nome>.

**Problema**: <cosa si è visto, link al run / artifact se utile>

**Causa accertata** (o **Causa probabile** se non confermata): <radice del problema>

**Soluzione**: <fix applicato + riferimento PR/commit>

**Lezione** (opzionale): <regola generale da ricordare per future debug>
```

Mantieni le sezioni in **ordine cronologico** (più vecchie sopra). Quando un
quirk di portale è confermato, aggiungilo anche nella sezione "Quirk noti".
