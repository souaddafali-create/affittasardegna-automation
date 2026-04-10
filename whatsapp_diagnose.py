#!/usr/bin/env python3
"""
Diagnostica WhatsApp Business API — AffittaSardegna Messaging Bot

Verifica:
1. Token valido e scopes corretti
2. Numeri registrati sul WABA
3. Phone Number ID corretto e raggiungibile
4. Stato registrazione del numero

Uso:
    export WA_ACCESS_TOKEN="il_tuo_token"
    python whatsapp_diagnose.py

Oppure con override:
    export WA_WABA_ID="2285999315221819"
    export WA_PHONE_NUMBER_ID="1066684723197247"
    python whatsapp_diagnose.py
"""

import os
import sys
import json
import urllib.request
import urllib.error

API_VERSION = "v19.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

WABA_ID = os.environ.get("WA_WABA_ID", "2285999315221819")
PHONE_NUMBER_ID = os.environ.get("WA_PHONE_NUMBER_ID", "1066684723197247")
ACCESS_TOKEN = os.environ.get("WA_ACCESS_TOKEN", "")

def api_get(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    sep = "&" if "?" in url else "?"
    url += f"{sep}access_token={ACCESS_TOKEN}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"error": {"message": raw.decode("utf-8", errors="replace")}}
        return body, e.code
    except Exception as e:
        return {"error": {"message": str(e)}}, 0


def check_token():
    print("\n=== 1. VERIFICA TOKEN ===")
    if not ACCESS_TOKEN:
        print("ERRORE: WA_ACCESS_TOKEN non impostato.")
        print("  export WA_ACCESS_TOKEN='EAA...'")
        return False

    data, status = api_get(f"debug_token?input_token={ACCESS_TOKEN}")
    if status != 200:
        err = data.get("error", {}).get("message", "sconosciuto")
        print(f"ERRORE ({status}): {err}")
        return False

    info = data.get("data", {})
    app_id = info.get("app_id", "?")
    app_name = info.get("application", "?")
    scopes = info.get("scopes", [])
    is_valid = info.get("is_valid", False)

    print(f"  App ID:    {app_id}")
    print(f"  App Name:  {app_name}")
    print(f"  Valido:    {'SI' if is_valid else 'NO'}")
    print(f"  Scopes:    {', '.join(scopes) if scopes else 'NESSUNO'}")

    required = {"whatsapp_business_management", "whatsapp_business_messaging"}
    missing = required - set(scopes)
    if missing:
        print(f"  MANCANTI:  {', '.join(missing)}")
    else:
        print("  Scopes OK")

    return is_valid


def check_waba_phone_numbers():
    print(f"\n=== 2. NUMERI REGISTRATI SUL WABA {WABA_ID} ===")
    data, status = api_get(f"{WABA_ID}/phone_numbers")

    if status != 200:
        err = data.get("error", {}).get("message", "sconosciuto")
        code = data.get("error", {}).get("code", "?")
        print(f"ERRORE ({status}, code {code}): {err}")
        if status == 403 or "permission" in err.lower():
            print("  -> Il token non ha accesso al WABA.")
            print("  -> Verifica: Business Settings > System Users > Assigned Assets")
        return []

    numbers = data.get("data", [])
    if not numbers:
        print("  NESSUN NUMERO REGISTRATO sul WABA!")
        print("  -> Vai su WhatsApp Manager > Phone Numbers > Add Phone Number")
        return []

    print(f"  Trovati {len(numbers)} numero/i:\n")
    for n in numbers:
        pid = n.get("id", "?")
        display = n.get("display_phone_number", "?")
        verified = n.get("verified_name", "?")
        quality = n.get("quality_rating", "?")
        status_val = n.get("status", "?")
        print(f"  Phone Number ID:  {pid}")
        print(f"  Numero:           {display}")
        print(f"  Nome verificato:  {verified}")
        print(f"  Quality rating:   {quality}")
        print(f"  Status:           {status_val}")
        if pid == PHONE_NUMBER_ID:
            print(f"  >>> MATCH con ID corrente ({PHONE_NUMBER_ID})")
        print()

    return numbers


def check_phone_number_direct():
    print(f"\n=== 3. ACCESSO DIRETTO A PHONE NUMBER ID {PHONE_NUMBER_ID} ===")
    data, status = api_get(PHONE_NUMBER_ID)

    if status == 200:
        display = data.get("display_phone_number", "?")
        verified = data.get("verified_name", "?")
        print(f"  OK - Numero raggiungibile")
        print(f"  Numero:          {display}")
        print(f"  Nome verificato: {verified}")
        return True

    err = data.get("error", {})
    msg = err.get("message", "sconosciuto")
    code = err.get("code", "?")
    subcode = err.get("error_subcode", "?")
    print(f"  ERRORE ({status}, code {code}, subcode {subcode})")
    print(f"  Messaggio: {msg}")

    if "does not exist" in msg.lower():
        print("\n  DIAGNOSI: Il Phone Number ID non esiste.")
        print("  Cause possibili:")
        print("    a) ID cambiato dopo passaggio a Live mode")
        print("    b) Numero eliminato e ri-registrato (nuovo ID)")
        print("    c) ID mai valido per questo WABA")
        print("  SOLUZIONE: Usa il Phone Number ID dallo Step 2 sopra.")
    elif "permission" in msg.lower():
        print("\n  DIAGNOSI: Permessi insufficienti.")
        print("  SOLUZIONE: Assegna il WABA al System User con Full Control.")

    return False


def check_business_profile():
    print(f"\n=== 4. BUSINESS PROFILE (phone {PHONE_NUMBER_ID}) ===")
    data, status = api_get(f"{PHONE_NUMBER_ID}/whatsapp_business_profile?fields=about,address,description,vertical,websites,profile_picture_url")

    if status == 200:
        profile = data.get("data", [{}])[0] if data.get("data") else {}
        if profile:
            print(f"  About:       {profile.get('about', '-')}")
            print(f"  Vertical:    {profile.get('vertical', '-')}")
            print(f"  Descrizione: {profile.get('description', '-')[:80]}")
            print("  Profilo business OK")
        else:
            print("  Profilo business vuoto (non ancora configurato)")
        return True

    print(f"  Non raggiungibile (status {status}) — normale se Step 3 fallito")
    return False


def main():
    print("=" * 55)
    print("  DIAGNOSTICA WHATSAPP — AffittaSardegna Messaging Bot")
    print("=" * 55)
    print(f"  WABA ID:          {WABA_ID}")
    print(f"  Phone Number ID:  {PHONE_NUMBER_ID}")
    print(f"  Token:            {'...'+ACCESS_TOKEN[-8:] if len(ACCESS_TOKEN) > 8 else '(non impostato)'}")

    if not ACCESS_TOKEN:
        print("\n  ERRORE: Imposta WA_ACCESS_TOKEN prima di eseguire.")
        print("  export WA_ACCESS_TOKEN='EAA...'")
        sys.exit(1)

    token_ok = check_token()
    numbers = check_waba_phone_numbers()
    direct_ok = check_phone_number_direct()

    if direct_ok:
        check_business_profile()

    # Riepilogo
    print("\n" + "=" * 55)
    print("  RIEPILOGO")
    print("=" * 55)

    if not token_ok:
        print("  TOKEN NON VALIDO — rigenera il token System User")
    elif not numbers:
        print("  NESSUN NUMERO SUL WABA — registra il numero in WhatsApp Manager")
    elif not direct_ok:
        real_ids = [n["id"] for n in numbers]
        if PHONE_NUMBER_ID not in real_ids:
            print(f"  PHONE NUMBER ID ERRATO!")
            print(f"  Stai usando:  {PHONE_NUMBER_ID}")
            print(f"  ID reale/i:   {', '.join(real_ids)}")
            print(f"\n  AZIONE: sostituisci {PHONE_NUMBER_ID} con {real_ids[0]} nel codice/config")
        else:
            print("  ID presente nel WABA ma non raggiungibile — problema di permessi token")
    else:
        print("  TUTTO OK — Phone Number ID raggiungibile e funzionante")

    print()


if __name__ == "__main__":
    main()
