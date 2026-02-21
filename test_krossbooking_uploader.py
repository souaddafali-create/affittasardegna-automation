#!/usr/bin/env python3
"""
Test end-to-end per krossbooking_uploader.py.

Avvia un mini-server HTTP locale che serve un form HTML a più tab che
imita l'interfaccia KrossBooking PMS, poi esegue l'uploader contro questo
server e verifica che tutti i campi vengano compilati correttamente.

Non richiede connessione internet né credenziali reali.
"""

import csv
import http.server
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# HTML del mock server
# ---------------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>KrossBooking TEST - Login</title></head>
<body>
  <h1>Login</h1>
  <form method="POST" action="/login">
    <input type="email"    name="email"    placeholder="Email" />
    <input type="password" name="password" placeholder="Password" />
    <button type="submit">Accedi</button>
  </form>
</body>
</html>"""

# Form a singola pagina (KrossBooking può usare tab JS; qui testiamo
# tutti i campi in un'unica pagina per semplicità nel test).
STRUTTURE_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>KrossBooking TEST - Strutture</title></head>
<body>
  <h1>Le tue strutture</h1>
  <a href="/strutture/nuova">Nuova struttura</a>
</body>
</html>"""

FORM_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>KrossBooking TEST - Nuova Struttura</title></head>
<body>
  <h1>Nuova Struttura</h1>
  <form method="POST" action="/salva">

    <!-- Dati Generali -->
    <input  name="codice"              placeholder="Codice struttura" />
    <input  name="nome"                placeholder="Nome proprietà" />
    <select name="tipo">
      <option value="">Seleziona tipo</option>
      <option value="Villa">Villa</option>
      <option value="Appartamento">Appartamento</option>
      <option value="Agriturismo">Agriturismo</option>
      <option value="Bungalow">Bungalow</option>
      <option value="Casa Vacanze">Casa Vacanze</option>
      <option value="Chalet">Chalet</option>
      <option value="Monolocale">Monolocale</option>
      <option value="Mansarda">Mansarda</option>
      <option value="Loft">Loft</option>
    </select>
    <input  name="max_ospiti"          type="number" />
    <input  name="letti"               type="number" />
    <input  name="bagni"               type="number" />
    <input  name="superficie"          type="number" step="0.1" />
    <input  name="check_in"            placeholder="15:00" />
    <input  name="check_out"           placeholder="10:00" />
    <select name="politica_cancellazione">
      <option value="">Seleziona politica</option>
      <option value="Flessibile">Flessibile</option>
      <option value="Moderata">Moderata</option>
      <option value="Rigida">Rigida</option>
    </select>

    <!-- Ubicazione -->
    <input  name="indirizzo" />
    <input  name="citta" />
    <select name="provincia">
      <option value="">Provincia</option>
      <option value="CA">CA</option>
      <option value="SS">SS</option>
      <option value="NU">NU</option>
      <option value="OR">OR</option>
      <option value="SU">SU</option>
    </select>
    <input  name="cap" />
    <select name="nazione">
      <option value="">Nazione</option>
      <option value="Italia">Italia</option>
      <option value="Germany">Germania</option>
    </select>

    <!-- Descrizione -->
    <textarea name="descrizione" rows="5"></textarea>

    <!-- Tariffe -->
    <input  name="prezzo_notte"        type="number" step="0.01" />
    <input  name="prezzo_settimana"    type="number" step="0.01" />
    <input  name="cauzione"            type="number" step="0.01" />
    <input  name="pulizie"             type="number" step="0.01" />

    <!-- Disponibilità -->
    <input  name="disponibile_dal"     type="date" />
    <input  name="disponibile_al"      type="date" />
    <input  name="soggiorno_minimo"    type="number" />

    <!-- Contatti -->
    <input  name="email_contatto"      type="email" />
    <input  name="telefono"            type="tel" />

    <button type="submit">Salva e Pubblica</button>
  </form>
</body>
</html>"""

CONFERMA_HTML = b"<html><body><h1>Struttura creata con successo</h1></body></html>"


# ---------------------------------------------------------------------------
# Mini HTTP server
# ---------------------------------------------------------------------------

_dati_ricevuti: list[dict] = []
_lock = threading.Lock()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/login"):
            body = LOGIN_HTML.encode()
        elif path in ("/strutture",):
            body = STRUTTURE_HTML.encode()
        elif path in ("/strutture/nuova", "/struttura/nuova",
                      "/properties/new", "/property/new"):
            body = FORM_HTML.encode()
        else:
            body = FORM_HTML.encode()   # fallback
        self._risposta(200, body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        flat = {k: v[0] for k, v in parsed.items()}

        path = urlparse(self.path).path
        if path == "/login":
            self.send_response(302)
            self.send_header("Location", "/strutture")
            self.end_headers()
        else:
            with _lock:
                _dati_ricevuti.append(flat)
            self._risposta(200, CONFERMA_HTML)

    def _risposta(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _avvia_server(port: int) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# Esecuzione uploader contro il server locale
# ---------------------------------------------------------------------------

def _esegui_uploader(base_url: str, csv_path: str, indice: int) -> list[dict]:
    from playwright.sync_api import sync_playwright
    import krossbooking_uploader as uploader

    # Override degli URL verso il server locale
    uploader.BASE_URL        = base_url
    uploader.LOGIN_URL       = f"{base_url}/login"
    uploader.STRUTTURE_URL   = f"{base_url}/strutture"
    uploader.NUOVA_STRUTTURA = f"{base_url}/strutture/nuova"

    strutture = uploader.leggi_csv(csv_path)
    da_caricare = [strutture[indice]]

    CHROMIUM_PATH = os.environ.get(
        "CHROMIUM_PATH",
        "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome",
    )

    with sync_playwright() as pw:
        launch_args: dict = dict(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        if Path(CHROMIUM_PATH).exists():
            launch_args["executable_path"] = CHROMIUM_PATH

        browser = pw.chromium.launch(**launch_args)
        context = browser.new_context(locale="it-IT")
        page = context.new_page()
        try:
            uploader.login(page, email="test@test.it", password="testpwd")
            for s in da_caricare:
                uploader.inserisci_struttura(page, s)
        finally:
            context.close()
            browser.close()

    return list(_dati_ricevuti)


# ---------------------------------------------------------------------------
# Asserzioni
# ---------------------------------------------------------------------------

_fallimenti = 0


def _assert(ok: bool, etichetta: str) -> None:
    global _fallimenti
    if ok:
        print(f"  [PASS] {etichetta}")
    else:
        print(f"  [FAIL] {etichetta}")
        _fallimenti += 1


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def esegui_test() -> bool:
    global _fallimenti
    _fallimenti = 0

    PORT   = 18081
    CSV    = "output/krossbooking.csv"
    INDICE = 0  # Villa Sul Mare

    print(f"\n{'='*65}")
    print("TEST END-TO-END — krossbooking_uploader.py")
    print(f"{'='*65}")

    # Dati attesi dal CSV
    with open(CSV, newline="", encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    atteso = righe[INDICE]

    print(f"Struttura di test : {atteso['nome_proprieta']!r}")
    print(f"Server locale     : http://127.0.0.1:{PORT}\n")

    server = _avvia_server(PORT)
    time.sleep(0.2)
    try:
        dati = _esegui_uploader(
            base_url=f"http://127.0.0.1:{PORT}",
            csv_path=CSV,
            indice=INDICE,
        )
    finally:
        server.shutdown()

    if not dati:
        print("\n[ERRORE] Nessun dato ricevuto — il form non è stato inviato.")
        return False

    ricevuto = dati[-1]

    print("Verifica campi:\n")
    # (campo_form, valore_atteso, etichetta)
    controlli = [
        ("codice",                 atteso["codice_struttura"],       "codice struttura"),
        ("nome",                   atteso["nome_proprieta"],         "nome proprietà"),
        ("tipo",                   atteso["tipo_struttura"],         "tipo struttura"),
        ("max_ospiti",             atteso["max_ospiti"],             "max ospiti"),
        ("letti",                  atteso["num_letti"],              "numero letti"),
        ("bagni",                  atteso["num_bagni"],              "numero bagni"),
        ("superficie",             atteso["superficie_mq"],          "superficie m²"),
        ("check_in",               atteso["check_in_ore"],           "orario check-in"),
        ("check_out",              atteso["check_out_ore"],          "orario check-out"),
        ("politica_cancellazione", atteso["politica_cancellazione"], "politica cancellazione"),
        ("indirizzo",              atteso["indirizzo"],              "indirizzo"),
        ("citta",                  atteso["citta"],                  "città"),
        ("provincia",              atteso["provincia"],              "provincia"),
        ("cap",                    atteso["cap"],                    "CAP"),
        ("prezzo_notte",           atteso["prezzo_base_notte"],      "prezzo base notte"),
        ("prezzo_settimana",       atteso["tariffa_settimanale"],    "tariffa settimanale"),
        ("cauzione",               atteso["deposito_cauzionale"],    "deposito cauzionale"),
        ("pulizie",                atteso["tariffa_pulizie"],        "tariffa pulizie"),
        ("disponibile_dal",        atteso["disponibile_dal"],        "disponibile dal"),
        ("disponibile_al",         atteso["disponibile_al"],         "disponibile al"),
        ("soggiorno_minimo",       atteso["soggiorno_minimo"],       "soggiorno minimo"),
        ("email_contatto",         atteso["email_contatto"],         "email contatto"),
        ("telefono",               atteso["telefono_contatto"],      "telefono contatto"),
    ]

    for campo, val_atteso, etichetta in controlli:
        val_ricevuto = ricevuto.get(campo, "")
        ok = str(val_atteso) in val_ricevuto or val_ricevuto == str(val_atteso)
        _assert(ok, f"{etichetta:<32} atteso={str(val_atteso)!r:<22} ricevuto={val_ricevuto!r}")

    tot = len(controlli)
    print(f"\n{'='*65}")
    if _fallimenti == 0:
        print(f"RISULTATO: TUTTI I {tot} CAMPI COMPILATI CORRETTAMENTE")
    else:
        print(f"RISULTATO: {_fallimenti}/{tot} CAMPI CON DISCREPANZE")
    print(f"{'='*65}\n")
    return _fallimenti == 0


if __name__ == "__main__":
    ok = esegui_test()
    sys.exit(0 if ok else 1)
