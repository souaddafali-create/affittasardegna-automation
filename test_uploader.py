#!/usr/bin/env python3
"""
Test end-to-end per casevacanza_uploader.py.

Avvia un mini-server HTTP locale che serve un form HTML che imita la
struttura di CaseVacanza.it, poi esegue l'uploader contro questo server
e verifica che tutti i campi vengano compilati correttamente.

Non richiede connessione internet né credenziali reali.
"""

import csv
import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Form HTML che simula il login + inserimento annuncio di CaseVacanza.it
# ---------------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>CaseVacanza TEST - Login</title></head>
<body>
  <h1>Login</h1>
  <form method="POST" action="/login">
    <input type="email"    name="email"    placeholder="Email" />
    <input type="password" name="password" placeholder="Password" />
    <button type="submit">Accedi</button>
  </form>
</body>
</html>"""

FORM_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>CaseVacanza TEST - Inserisci annuncio</title></head>
<body>
  <h1>Inserisci Annuncio</h1>
  <form method="POST" action="/salva">
    <input  name="titolo"            placeholder="Titolo annuncio" />
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
    <textarea name="descrizione_breve" rows="2"></textarea>
    <textarea name="descrizione"       rows="5"></textarea>
    <input  name="prezzo_notte"        type="number" step="0.01" />
    <input  name="prezzo_settimana"    type="number" step="0.01" />
    <input  name="cauzione"            type="number" step="0.01" />
    <input  name="soggiorno_minimo"    type="number" />
    <input  name="ospiti_max"          type="number" />
    <input  name="camere"              type="number" />
    <input  name="bagni"               type="number" />
    <input  name="superficie"          type="number" step="0.1" />
    <input  name="indirizzo" />
    <input  name="localita" />
    <input  name="cap" />
    <select name="provincia">
      <option value="">Provincia</option>
      <option value="CA">CA</option>
      <option value="SS">SS</option>
      <option value="NU">NU</option>
      <option value="OR">OR</option>
      <option value="SU">SU</option>
    </select>
    <input  name="disponibile_dal"     type="date" />
    <input  name="disponibile_al"      type="date" />
    <input  name="contatto_email"      type="email" />
    <input  name="contatto_telefono" />
    <button type="submit">Salva e Pubblica</button>
  </form>
</body>
</html>"""

CONFERMA_HTML = """<!DOCTYPE html>
<html lang="it">
<head><meta charset="utf-8"><title>Annuncio Inserito</title></head>
<body>
  <h1>Annuncio inserito con successo</h1>
  <p id="dati"></p>
  <script>
    // Salva i dati POST ricevuti in sessionStorage per poterli leggere
    const params = new URLSearchParams(document.currentScript.dataset.params || '');
    document.getElementById('dati').textContent = 'Salvato';
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Mini HTTP server
# ---------------------------------------------------------------------------

_dati_ricevuti: list[dict] = []     # raccoglie i POST del form
_lock = threading.Lock()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silenzia i log del server durante il test

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/login"):
            body = LOGIN_HTML.encode()
        elif path in ("/proprietario/annunci/nuovo", "/inserisci-annuncio", "/nuovo-annuncio",
                      "/proprietario/annunci"):
            body = FORM_HTML.encode()
        elif path == "/ok":
            body = CONFERMA_HTML.encode()
        else:
            body = FORM_HTML.encode()   # fallback al form
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        flat = {k: v[0] for k, v in parsed.items()}

        path = urlparse(self.path).path
        if path == "/login":
            # Simula login riuscito: redirect al form
            self.send_response(302)
            self.send_header("Location", "/proprietario/annunci")
            self.end_headers()
        else:
            # Salva i dati del form
            with _lock:
                _dati_ricevuti.append(flat)
            body = b"<h1>Annuncio inserito con successo</h1><p>Salvato</p>"
            self.send_response(200)
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
# Helper: esegue l'uploader contro il server locale
# ---------------------------------------------------------------------------

def _esegui_uploader(base_url: str, csv_path: str, indice: int) -> list[dict]:
    """Lancia il browser via Playwright e compila il form locale."""
    # Importa qui per avere un errore chiaro se Playwright non è installato
    from playwright.sync_api import sync_playwright

    CHROMIUM_PATH = os.environ.get(
        "CHROMIUM_PATH",
        "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome",
    )

    # Override degli URL nel modulo uploader per puntare al server locale
    import casevacanza_uploader as uploader
    uploader.BASE_URL    = base_url
    uploader.LOGIN_URL   = f"{base_url}/login"
    uploader.ANNUNCI_URL = f"{base_url}/proprietario/annunci"

    proprieta = uploader.leggi_csv(csv_path)
    da_caricare = [proprieta[indice]]

    with sync_playwright() as pw:
        launch_args = dict(
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
            for p in da_caricare:
                uploader.inserisci_proprieta(page, p)
        finally:
            context.close()
            browser.close()

    return list(_dati_ricevuti)


# ---------------------------------------------------------------------------
# Asserzioni di test
# ---------------------------------------------------------------------------

def _assert(condition: bool, messaggio: str) -> None:
    if condition:
        print(f"  [PASS] {messaggio}")
    else:
        print(f"  [FAIL] {messaggio}")
        # Non abortisce: mostra tutti i fallimenti


def esegui_test() -> bool:
    PORT = 18080
    CSV  = "output/casevacanza.csv"
    INDICE = 0      # prima proprietà: Villa Sul Mare

    print(f"\n{'='*60}")
    print("TEST END-TO-END — casevacanza_uploader.py")
    print(f"{'='*60}")

    # Leggi i dati attesi direttamente dal CSV
    with open(CSV, newline="", encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    atteso = righe[INDICE]

    print(f"\nProprietà di test : {atteso['titolo_annuncio']!r}")
    print(f"Server locale     : http://127.0.0.1:{PORT}")
    print()

    # Avvia server
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
        print("\n[ERRORE] Nessun dato ricevuto dal server — il form non è stato inviato.")
        return False

    ricevuto = dati[-1]   # ultimo POST (quello del form annuncio)

    print("Campi compilati ricevuti dal form:\n")
    mappatura = [
        ("titolo",         atteso["titolo_annuncio"],           "titolo annuncio"),
        ("tipo",           atteso["tipo_immobile"],             "tipo immobile"),
        ("descrizione_breve", atteso["descrizione_breve"][:80], "descrizione breve (primi 80 car.)"),
        ("prezzo_notte",   str(atteso["prezzo_per_notte_eur"]), "prezzo per notte"),
        ("prezzo_settimana", str(atteso["prezzo_per_settimana_eur"]), "prezzo settimana"),
        ("cauzione",       str(atteso["cauzione_eur"]),         "cauzione"),
        ("soggiorno_minimo", str(atteso["soggiorno_minimo_notti"]), "soggiorno minimo"),
        ("ospiti_max",     str(atteso["numero_ospiti_max"]),    "ospiti max"),
        ("bagni",          str(atteso["numero_bagni"]),         "bagni"),
        ("superficie",     str(atteso["superficie_mq"]),        "superficie m²"),
        ("indirizzo",      atteso["indirizzo"],                 "indirizzo"),
        ("localita",       atteso["localita"],                  "localita"),
        ("cap",            atteso["cap"],                       "CAP"),
        ("provincia",      atteso["provincia"],                 "provincia"),
        ("disponibile_dal", atteso["disponibile_dal"],          "disponibile dal"),
        ("disponibile_al",  atteso["disponibile_al"],           "disponibile al"),
        ("contatto_email",  atteso["contatto_email"],           "email contatto"),
        ("contatto_telefono", atteso["contatto_telefono"],      "telefono contatto"),
    ]

    fallimenti = 0
    for campo_form, valore_atteso, etichetta in mappatura:
        val_ricevuto = ricevuto.get(campo_form, "")
        ok = valore_atteso in val_ricevuto or val_ricevuto == valore_atteso
        if not ok:
            fallimenti += 1
        _assert(ok, f"{etichetta:<30} atteso={valore_atteso!r:<25} ricevuto={val_ricevuto!r}")

    print(f"\n{'='*60}")
    if fallimenti == 0:
        print(f"RISULTATO: TUTTI I {len(mappatura)} CAMPI COMPILATI CORRETTAMENTE")
    else:
        print(f"RISULTATO: {fallimenti}/{len(mappatura)} CAMPI CON DISCREPANZE")
    print(f"{'='*60}\n")
    return fallimenti == 0


if __name__ == "__main__":
    successo = esegui_test()
    sys.exit(0 if successo else 1)
