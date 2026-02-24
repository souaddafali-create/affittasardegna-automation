#!/usr/bin/env python3
"""
Test end-to-end per booking_uploader.py.

Avvia un mini-server HTTP locale che imita il wizard di registrazione
Booking.com Extranet (login + form a più step), poi esegue l'uploader
contro questo server e verifica che tutti i campi vengano compilati
correttamente.

Non richiede connessione internet né credenziali reali.

Proprietà di test: Appartamento Test Stintino (output/booking_test.csv)
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
# HTML del mock server — simula le schermate del wizard Booking.com Extranet
# ---------------------------------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Booking.com TEST - Sign in</title></head>
<body>
  <h1>Sign in</h1>
  <form method="POST" action="/login">
    <input id="loginname"  name="loginname" type="email"    placeholder="Email" />
    <input id="password"   name="password"  type="password" placeholder="Password" />
    <button type="submit" class="bui-button--primary">Sign in</button>
  </form>
</body>
</html>"""

EXTRANET_HOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Booking.com TEST - Extranet</title></head>
<body>
  <h1>Extranet</h1>
  <nav>
    <a href="/hotel/hoteladmin/overview/create/">List your property</a>
    <a href="/hotel/hoteladmin/overview/create/">Add property</a>
  </nav>
</body>
</html>"""

# Form singola pagina che raggruppa tutti i campi del wizard
# (il wizard reale è multi-step; qui testiamo tutti i campi su una pagina sola)
WIZARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Booking.com TEST - Register property</title></head>
<body>
  <h1>Register your property</h1>
  <form method="POST" action="/salva">

    <!-- Step 1: Property type -->
    <label>
      <input type="radio" name="property_type" value="apartment" /> Apartment
    </label>
    <label>
      <input type="radio" name="property_type" value="villa" /> Villa
    </label>
    <label>
      <input type="radio" name="property_type" value="house" /> House
    </label>
    <label>
      <input type="radio" name="property_type" value="hotel" /> Hotel
    </label>

    <!-- Step 2: Property details -->
    <input  name="property_name"   placeholder="Property name" />
    <textarea name="description"   rows="4" placeholder="Description"></textarea>

    <!-- Step 3: Location -->
    <input  name="address"         placeholder="Street address" />
    <input  name="city"            placeholder="City" />
    <input  name="postcode"        placeholder="Postcode" />
    <select name="country">
      <option value="">Country</option>
      <option value="IT">Italy</option>
      <option value="DE">Germany</option>
      <option value="FR">France</option>
    </select>

    <!-- Step 4: Property details -->
    <input  name="max_guests"      type="number" placeholder="Max guests" />
    <input  name="bathrooms"       type="number" placeholder="Bathrooms" />
    <input  name="size"            type="number" step="0.1" placeholder="Size sqm" />

    <!-- Step 5: Pricing -->
    <input  name="price"           type="number" step="0.01" placeholder="Price per night" />

    <!-- Step 6: Check-in / Check-out -->
    <input  name="check_in"        placeholder="Check-in from (e.g. 15:00)" />
    <input  name="check_out"       placeholder="Check-out until (e.g. 10:00)" />

    <!-- Step 7: Contact -->
    <input  name="contact_email"   type="email" placeholder="Contact email" />
    <input  name="phone"           type="tel"   placeholder="Phone number" />

    <button type="submit">Save and continue</button>
  </form>
</body>
</html>"""

CONFERMA_HTML = (
    b"<html><body>"
    b"<h1>Registration complete</h1>"
    b"<p>Your property has been submitted successfully.</p>"
    b"</body></html>"
)


# ---------------------------------------------------------------------------
# Mini HTTP server
# ---------------------------------------------------------------------------

_dati_ricevuti: list[dict] = []
_lock = threading.Lock()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silenzioso durante i test

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/sign-in", "/login"):
            body = LOGIN_HTML.encode()
        elif path in ("/", "/admin", "/extranet"):
            body = EXTRANET_HOME_HTML.encode()
        elif path in ("/hotel/hoteladmin/overview/create/",
                      "/partner", "/join"):
            body = WIZARD_HTML.encode()
        else:
            # Qualsiasi altra path: se arriva dopo il login, mostra il wizard
            if path.startswith("/hotel") or path.startswith("/partner"):
                body = WIZARD_HTML.encode()
            else:
                body = EXTRANET_HOME_HTML.encode()
        self._risposta(200, body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        flat = {k: v[0] for k, v in parsed.items()}

        path = urlparse(self.path).path
        if path == "/login":
            # Simula login riuscito: redirect all'extranet
            self.send_response(302)
            self.send_header("Location", "/hotel/hoteladmin/overview/create/")
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
    import booking_uploader as uploader

    # Override degli URL verso il server locale
    uploader.LOGIN_URL        = f"{base_url}/login"
    uploader.EXTRANET_URL     = f"{base_url}/hotel/hoteladmin/overview/create/"
    uploader.NEW_PROPERTY_URLS = [
        f"{base_url}/hotel/hoteladmin/overview/create/",
    ]

    proprieta = uploader.leggi_csv(csv_path)
    da_caricare = [proprieta[indice]]

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
            for p in da_caricare:
                uploader.inserisci_proprieta(page, p)
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

    PORT   = 18082
    CSV    = "output/booking_test.csv"
    INDICE = 0  # Appartamento Test Stintino

    print(f"\n{'='*65}")
    print("TEST END-TO-END — booking_uploader.py")
    print(f"{'='*65}")

    # Dati attesi dal CSV
    with open(CSV, newline="", encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    atteso = righe[INDICE]

    print(f"Proprietà di test : {atteso['property_name']!r}")
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
    # (campo_form, valore_atteso_csv, etichetta)
    controlli = [
        ("property_name",  atteso["property_name"],         "nome proprietà"),
        ("description",    atteso["description_it"][:80],   "descrizione (primi 80 car.)"),
        ("address",        atteso["address_line1"],          "indirizzo"),
        ("city",           atteso["city"],                   "città"),
        ("postcode",       atteso["postal_code"],            "codice postale"),
        ("country",        atteso["country"],                "paese"),
        ("max_guests",     atteso["max_guests"],             "ospiti max"),
        ("bathrooms",      atteso["bathrooms"],              "bagni"),
        ("size",           atteso["size_sqm"],               "superficie m²"),
        ("price",          atteso["price_per_night_eur"],    "prezzo per notte"),
        ("check_in",       atteso["check_in_from"],          "check-in"),
        ("check_out",      atteso["check_out_until"],        "check-out"),
        ("contact_email",  atteso["contact_email"],          "email contatto"),
        ("phone",          atteso["contact_phone"],          "telefono"),
    ]

    for campo, val_atteso, etichetta in controlli:
        val_ricevuto = ricevuto.get(campo, "")
        ok = str(val_atteso) in val_ricevuto or val_ricevuto == str(val_atteso)
        _assert(ok, f"{etichetta:<32} atteso={str(val_atteso)!r:<25} ricevuto={val_ricevuto!r}")

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
