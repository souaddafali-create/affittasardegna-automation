#!/usr/bin/env python3
"""Motore preventivi AffittaSardegna.

Regola d'oro (CLAUDE.md): SOLO dati dal JSON. Se un dato manca, il motore
NON lo inventa: lo segnala come voce da confermare e lo esclude dal totale.

Uso:
    python preventivo.py <casa.json> <check-in> <check-out> <ospiti> [--cliente "Nome"] [--html out.html]

Esempio:
    python preventivo.py Villa_La_Vela_DATI.json 2026-10-01 2026-10-10 4 --cliente "D'Angeli Clemente"
"""

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request

MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
        "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12}


# ---------------------------------------------------------------- parsing

def parse_data(valore, anno_default):
    """Accetta '2025-06-13' oppure '13-giu' (anno dedotto dal soggiorno)."""
    if isinstance(valore, str):
        v = valore.strip()
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})[-/ ]([a-zA-Zàè]{3,})", v)
        if m and m[2][:3].lower() in MESI:
            return dt.date(anno_default, MESI[m[2][:3].lower()], int(m[1]))
    return None


def parse_importo(testo):
    """'250 EUR a soggiorno obbligatoria' -> (250.0, 'soggiorno').
    '20 EUR a persona a soggiorno' -> (20.0, 'persona'). None se illeggibile."""
    if testo is None:
        return None
    if isinstance(testo, (int, float)):
        return (float(testo), "soggiorno")
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(testo))
    if not m:
        return None
    importo = float(m[1].replace(",", "."))
    unita = "persona" if re.search(r"a\s+persona", str(testo), re.I) else "soggiorno"
    return (importo, unita)


def normalizza_listino(listino, anno):
    """Uniforma i due formati presenti nei JSON ({da,a} e {dal,al})."""
    righe = []
    for r in listino or []:
        inizio = parse_data(r.get("da") or r.get("dal"), anno)
        fine = parse_data(r.get("a") or r.get("al"), anno)
        prezzo = r.get("prezzo_notte")
        if inizio and fine and prezzo is not None:
            righe.append((inizio, fine, float(prezzo)))
    return sorted(righe)


def prezzo_notte(righe, giorno):
    """Range semiaperto [inizio, fine). Confronto su giorno/mese: i listini
    senza anno valgono per la stagione, qualunque sia l'anno richiesto."""
    for inizio, fine, prezzo in righe:
        if inizio <= giorno < fine:
            return prezzo
    for inizio, fine, prezzo in righe:
        if (inizio.month, inizio.day) <= (giorno.month, giorno.day) < (fine.month, fine.day):
            return prezzo
    return None


# ---------------------------------------------------------- disponibilita

def occupazioni_ical(url, timeout=30):
    """Ritorna [(inizio, fine)] dalle prenotazioni Kross. None se irraggiungibile."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        testo = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:
        return None
    eventi, corrente = [], {}
    for riga in testo.splitlines():
        riga = riga.strip()
        if riga == "BEGIN:VEVENT":
            corrente = {}
        elif riga.startswith("DTSTART"):
            corrente["da"] = riga.split(":")[-1][:8]
        elif riga.startswith("DTEND"):
            corrente["a"] = riga.split(":")[-1][:8]
        elif riga.startswith("SUMMARY"):
            corrente["titolo"] = riga.split(":", 1)[-1]
        elif riga == "END:VEVENT" and {"da", "a"} <= corrente.keys():
            try:
                eventi.append((dt.datetime.strptime(corrente["da"], "%Y%m%d").date(),
                               dt.datetime.strptime(corrente["a"], "%Y%m%d").date(),
                               corrente.get("titolo", "")))
            except ValueError:
                pass
    return eventi


# -------------------------------------------------------------- preventivo

def calcola(dati, check_in, check_out, ospiti, verifica_ical=True):
    ident = dati.get("identificativi", {})
    comp = dati.get("composizione", {})
    cond = dati.get("condizioni", {})

    notti = (check_out - check_in).days
    if notti < 1:
        raise ValueError("check-out deve essere successivo al check-in")

    p = {"casa": ident.get("nome_struttura"), "comune": ident.get("comune"),
         "cin": ident.get("cin"), "check_in": check_in, "check_out": check_out,
         "ospiti": ospiti, "notti": notti, "righe": [], "avvisi": [], "blocchi": [],
         "da_confermare": [], "cauzione": None, "totale": 0.0}

    # --- capienza
    massimo = comp.get("max_ospiti")
    if massimo and ospiti > massimo:
        p["blocchi"].append(f"Capienza massima {massimo} ospiti, richiesti {ospiti}")

    # --- soggiorno
    listino = normalizza_listino(cond.get("listino_prezzi"), check_in.year)
    if listino:
        totale_notti, scoperte, fasce = 0.0, 0, {}
        for i in range(notti):
            giorno = check_in + dt.timedelta(days=i)
            tariffa = prezzo_notte(listino, giorno)
            if tariffa is None:
                scoperte += 1
                continue
            totale_notti += tariffa
            fasce[tariffa] = fasce.get(tariffa, 0) + 1
        if scoperte:
            p["blocchi"].append(f"{scoperte} notti su {notti} non coperte dal listino")
        for tariffa, quante in sorted(fasce.items()):
            p["righe"].append({"voce": f"Soggiorno — {quante} notti x {tariffa:.0f} EUR",
                               "importo": tariffa * quante})
        p["totale"] += totale_notti
    else:
        p["blocchi"].append("Listino prezzi assente nel JSON: impossibile calcolare il soggiorno")

    # --- soggiorno minimo
    minimo = None
    for fascia in cond.get("soggiorno_minimo_dettaglio") or []:
        inizio = parse_data(fascia.get("da"), check_in.year)
        fine = parse_data(fascia.get("a"), check_in.year)
        if inizio and fine and inizio <= check_in < fine:
            minimo = fascia
            break
    if minimo is None:
        minimo = cond.get("soggiorno_minimo_bassa") or {}
    if minimo.get("notti") and notti < minimo["notti"]:
        p["blocchi"].append(f"Soggiorno minimo {minimo['notti']} notti, richieste {notti}")
    if minimo.get("vincolo_giorno"):
        p["avvisi"].append(f"Vincolo periodo: {minimo['vincolo_giorno']}")

    # --- extra obbligatori
    for chiave, etichetta in [("pulizia_finale", "Pulizia finale"),
                              ("lenzuola", "Lenzuola"),
                              ("asciugamani", "Asciugamani"),
                              ("biancheria", "Biancheria")]:
        grezzo = cond.get(chiave)
        if grezzo in (None, "", []):
            continue
        parsato = parse_importo(grezzo)
        if parsato is None:
            p["da_confermare"].append(f"{etichetta}: «{grezzo}» (importo non numerico)")
            continue
        importo, unita = parsato
        if unita == "persona":
            p["righe"].append({"voce": f"{etichetta} — {ospiti} x {importo:.0f} EUR",
                               "importo": importo * ospiti})
            p["totale"] += importo * ospiti
        else:
            p["righe"].append({"voce": etichetta, "importo": importo})
            p["totale"] += importo

    # --- cauzione (rimborsabile: fuori totale)
    cauzione = parse_importo(cond.get("cauzione_euro") or cond.get("cauzione"))
    if cauzione:
        p["cauzione"] = cauzione[0]

    # --- tassa di soggiorno: mai inventata
    if not cond.get("tassa_soggiorno"):
        p["da_confermare"].append("Tassa di soggiorno: non presente nel JSON, da aggiungere se dovuta")

    p["check_in_orario"] = cond.get("check_in")
    p["check_out_orario"] = cond.get("check_out")

    # --- disponibilita da Kross
    if verifica_ical:
        occupato = occupazioni_ical(cond.get("ical_url"))
        if occupato is None:
            p["avvisi"].append("Disponibilita non verificata (iCal Kross non raggiungibile)")
        else:
            conflitti = [(a, b, t) for a, b, t in occupato if a < check_out and check_in < b]
            if conflitti:
                for a, b, t in conflitti:
                    p["blocchi"].append(f"Date occupate su Kross: {a:%d/%m/%Y}–{b:%d/%m/%Y} ({t})")
            else:
                p["avvisi"].append("Disponibilita confermata sul calendario Kross")
    return p


# ------------------------------------------------------------------ output

def stampa(p, cliente=None):
    print(f"\nPREVENTIVO — {p['casa']} ({p['comune']})")
    if cliente:
        print(f"Cliente: {cliente}")
    print(f"{p['check_in']:%d/%m/%Y} → {p['check_out']:%d/%m/%Y}  |  {p['notti']} notti  |  {p['ospiti']} ospiti")
    print("-" * 62)
    for r in p["righe"]:
        print(f"  {r['voce']:<46}{r['importo']:>10.2f} EUR")
    print("-" * 62)
    print(f"  {'TOTALE SOGGIORNO':<46}{p['totale']:>10.2f} EUR")
    if p["cauzione"]:
        print(f"  {'Cauzione (rimborsabile a fine soggiorno)':<46}{p['cauzione']:>10.2f} EUR")
    for etichetta, voci in [("BLOCCANTI", p["blocchi"]), ("DA CONFERMARE", p["da_confermare"]),
                            ("NOTE", p["avvisi"])]:
        if voci:
            print(f"\n{etichetta}:")
            for v in voci:
                print(f"  - {v}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_casa")
    ap.add_argument("check_in")
    ap.add_argument("check_out")
    ap.add_argument("ospiti", type=int)
    ap.add_argument("--cliente")
    ap.add_argument("--no-ical", action="store_true")
    args = ap.parse_args()

    with open(args.json_casa, encoding="utf-8") as f:
        dati = json.load(f)
    p = calcola(dati,
                dt.date.fromisoformat(args.check_in),
                dt.date.fromisoformat(args.check_out),
                args.ospiti,
                verifica_ical=not args.no_ical)
    stampa(p, args.cliente)
    return 1 if p["blocchi"] else 0


if __name__ == "__main__":
    sys.exit(main())
