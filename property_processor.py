#!/usr/bin/env python3
"""
Script per la preparazione dei dati delle proprietà in affitto
per l'inserimento su portali di affitti vacanze.

Supporta i formati di esportazione per:
- Airbnb
- Booking.com
- HomeAway / Vrbo
- Immobiliare.it Vacanze
"""

import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------

TIPI_PROPRIETA_VALIDI = {
    "villa", "appartamento", "agriturismo", "bungalow",
    "casa", "chalet", "monolocale", "mansarda", "loft",
}

PROVINCE_SARDEGNA = {
    "CA", "SS", "NU", "OR", "SU",
}


@dataclass
class Proprieta:
    nome: str
    descrizione: str
    prezzo_notte: float
    indirizzo: str
    citta: str
    provincia: str
    cap: str
    posti_letto: int
    bagni: int
    metri_quadri: float
    tipo_proprieta: str
    disponibile_da: str
    disponibile_a: str
    contatto_email: str
    contatto_telefono: str
    errori: list = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return len(self.errori) == 0


# ---------------------------------------------------------------------------
# Lettura e validazione
# ---------------------------------------------------------------------------

CAMPI_OBBLIGATORI = [
    "nome", "descrizione", "prezzo_notte", "indirizzo",
    "citta", "provincia", "cap", "posti_letto", "bagni",
    "metri_quadri", "tipo_proprieta", "disponibile_da",
    "disponibile_a", "contatto_email",
]


def _valida_email(email: str) -> bool:
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email.strip()))


def _valida_data(data_str: str) -> bool:
    try:
        datetime.strptime(data_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _valida_cap(cap: str) -> bool:
    return bool(re.match(r"^\d{5}$", cap.strip()))


def _normalizza_telefono(tel: str) -> str:
    """Rimuove spazi e normalizza il numero di telefono italiano."""
    tel = re.sub(r"[\s\-\.]", "", tel.strip())
    if tel.startswith("00"):
        tel = "+" + tel[2:]
    if tel.startswith("0") and not tel.startswith("+"):
        tel = "+39" + tel
    return tel


def _normalizza_testo(testo: str) -> str:
    """Rimuove spazi multipli e va a capo ridondanti."""
    return " ".join(testo.split())


def _parse_riga(riga: dict, numero_riga: int) -> Proprieta:
    errori = []

    # Campi obbligatori presenti?
    for campo in CAMPI_OBBLIGATORI:
        if not riga.get(campo, "").strip():
            errori.append(f"Campo obbligatorio mancante: '{campo}'")

    # Conversioni numeriche
    try:
        prezzo_notte = float(riga.get("prezzo_notte", "0").strip())
        if prezzo_notte <= 0:
            errori.append("prezzo_notte deve essere maggiore di zero")
    except ValueError:
        prezzo_notte = 0.0
        errori.append("prezzo_notte non è un numero valido")

    try:
        posti_letto = int(riga.get("posti_letto", "0").strip())
        if posti_letto <= 0:
            errori.append("posti_letto deve essere maggiore di zero")
    except ValueError:
        posti_letto = 0
        errori.append("posti_letto non è un intero valido")

    try:
        bagni = int(riga.get("bagni", "0").strip())
        if bagni <= 0:
            errori.append("bagni deve essere maggiore di zero")
    except ValueError:
        bagni = 0
        errori.append("bagni non è un intero valido")

    try:
        metri_quadri = float(riga.get("metri_quadri", "0").strip())
        if metri_quadri <= 0:
            errori.append("metri_quadri deve essere maggiore di zero")
    except ValueError:
        metri_quadri = 0.0
        errori.append("metri_quadri non è un numero valido")

    # Validazioni formato
    email = riga.get("contatto_email", "").strip()
    if email and not _valida_email(email):
        errori.append(f"Email non valida: '{email}'")

    cap = riga.get("cap", "").strip()
    if cap and not _valida_cap(cap):
        errori.append(f"CAP non valido: '{cap}'")

    provincia = riga.get("provincia", "").strip().upper()
    if provincia and provincia not in PROVINCE_SARDEGNA:
        errori.append(
            f"Provincia '{provincia}' non è una provincia sarda valida "
            f"(valide: {', '.join(sorted(PROVINCE_SARDEGNA))})"
        )

    tipo = riga.get("tipo_proprieta", "").strip().lower()
    if tipo and tipo not in TIPI_PROPRIETA_VALIDI:
        errori.append(
            f"Tipo proprietà '{tipo}' non riconosciuto "
            f"(validi: {', '.join(sorted(TIPI_PROPRIETA_VALIDI))})"
        )

    for campo_data in ("disponibile_da", "disponibile_a"):
        val = riga.get(campo_data, "").strip()
        if val and not _valida_data(val):
            errori.append(f"{campo_data} non è in formato YYYY-MM-DD: '{val}'")

    disp_da = riga.get("disponibile_da", "").strip()
    disp_a = riga.get("disponibile_a", "").strip()
    if _valida_data(disp_da) and _valida_data(disp_a):
        if datetime.strptime(disp_da, "%Y-%m-%d") >= datetime.strptime(disp_a, "%Y-%m-%d"):
            errori.append("disponibile_da deve essere precedente a disponibile_a")

    return Proprieta(
        nome=_normalizza_testo(riga.get("nome", "")),
        descrizione=_normalizza_testo(riga.get("descrizione", "")),
        prezzo_notte=prezzo_notte,
        indirizzo=_normalizza_testo(riga.get("indirizzo", "")),
        citta=_normalizza_testo(riga.get("citta", "")),
        provincia=provincia,
        cap=cap,
        posti_letto=posti_letto,
        bagni=bagni,
        metri_quadri=metri_quadri,
        tipo_proprieta=tipo,
        disponibile_da=disp_da,
        disponibile_a=disp_a,
        contatto_email=email,
        contatto_telefono=_normalizza_telefono(riga.get("contatto_telefono", "")),
        errori=errori,
    )


def leggi_csv(percorso: str) -> list[Proprieta]:
    """Legge il CSV e restituisce la lista di Proprieta."""
    path = Path(percorso)
    if not path.exists():
        print(f"[ERRORE] File non trovato: {percorso}", file=sys.stderr)
        sys.exit(1)

    proprieta = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, riga in enumerate(reader, start=2):  # riga 1 = intestazione
            prop = _parse_riga(riga, i)
            proprieta.append(prop)

    return proprieta


# ---------------------------------------------------------------------------
# Formati di esportazione
# ---------------------------------------------------------------------------

def _indirizzo_completo(p: Proprieta) -> str:
    return f"{p.indirizzo}, {p.cap} {p.citta} ({p.provincia}), Italia"


def esporta_airbnb(proprieta: list[Proprieta]) -> list[dict]:
    """
    Formato compatibile con l'importazione massiva di Airbnb.
    Campi principali: https://www.airbnb.com/help/article/2308
    """
    righe = []
    for p in proprieta:
        if not p.valida:
            continue
        righe.append({
            "listing_name": p.nome[:50],          # max 50 caratteri su Airbnb
            "summary": p.descrizione[:500],
            "space": f"Tipo: {p.tipo_proprieta.capitalize()}. "
                     f"Superficie: {p.metri_quadri} m².",
            "nightly_price": p.prezzo_notte,
            "currency": "EUR",
            "bedrooms": max(1, p.posti_letto // 2),
            "bathrooms": p.bagni,
            "accommodates": p.posti_letto,
            "property_type": p.tipo_proprieta.capitalize(),
            "street": p.indirizzo,
            "city": p.citta,
            "state": "Sardegna",
            "zipcode": p.cap,
            "country_code": "IT",
            "availability_start": p.disponibile_da,
            "availability_end": p.disponibile_a,
            "contact_email": p.contatto_email,
        })
    return righe


def esporta_booking(proprieta: list[Proprieta]) -> list[dict]:
    """
    Formato compatibile con Booking.com Extranet XML / CSV bulk upload.
    """
    righe = []
    for p in proprieta:
        if not p.valida:
            continue
        righe.append({
            "property_name": p.nome,
            "property_type": p.tipo_proprieta,
            "description_it": p.descrizione,
            "price_per_night_eur": p.prezzo_notte,
            "max_guests": p.posti_letto,
            "bathrooms": p.bagni,
            "size_sqm": p.metri_quadri,
            "address_line1": p.indirizzo,
            "city": p.citta,
            "postal_code": p.cap,
            "country": "IT",
            "check_in_from": p.disponibile_da,
            "check_out_until": p.disponibile_a,
            "contact_email": p.contatto_email,
            "contact_phone": p.contatto_telefono,
        })
    return righe


def esporta_homeaway(proprieta: list[Proprieta]) -> list[dict]:
    """
    Formato compatibile con HomeAway / Vrbo listing import.
    """
    righe = []
    for p in proprieta:
        if not p.valida:
            continue
        righe.append({
            "PropertyName": p.nome,
            "PropertyType": p.tipo_proprieta.capitalize(),
            "Headline": p.nome,
            "Description": p.descrizione,
            "NightlyRate": p.prezzo_notte,
            "Currency": "EUR",
            "MaxSleeps": p.posti_letto,
            "Bathrooms": p.bagni,
            "SquareMeters": p.metri_quadri,
            "FullAddress": _indirizzo_completo(p),
            "City": p.citta,
            "StateProvince": "Sardegna",
            "PostalCode": p.cap,
            "Country": "Italy",
            "AvailableFrom": p.disponibile_da,
            "AvailableTo": p.disponibile_a,
            "ContactEmail": p.contatto_email,
            "ContactPhone": p.contatto_telefono,
        })
    return righe


def esporta_immobiliare(proprieta: list[Proprieta]) -> list[dict]:
    """
    Formato compatibile con Immobiliare.it Vacanze (feed XML/CSV).
    """
    righe = []
    for p in proprieta:
        if not p.valida:
            continue
        righe.append({
            "titolo": p.nome,
            "tipologia": p.tipo_proprieta,
            "descrizione": p.descrizione,
            "prezzo_notte": p.prezzo_notte,
            "ospiti_max": p.posti_letto,
            "bagni": p.bagni,
            "superficie": p.metri_quadri,
            "indirizzo": p.indirizzo,
            "comune": p.citta,
            "provincia": p.provincia,
            "cap": p.cap,
            "nazione": "IT",
            "data_inizio": p.disponibile_da,
            "data_fine": p.disponibile_a,
            "email_contatto": p.contatto_email,
            "telefono_contatto": p.contatto_telefono,
        })
    return righe


# ---------------------------------------------------------------------------
# Output su file
# ---------------------------------------------------------------------------

def _scrivi_csv(dati: list[dict], percorso: str) -> None:
    if not dati:
        print(f"  [AVVISO] Nessun dato valido per {percorso}, file non creato.")
        return
    with open(percorso, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=dati[0].keys())
        writer.writeheader()
        writer.writerows(dati)
    print(f"  -> CSV: {percorso}  ({len(dati)} proprietà)")


def _scrivi_json(dati: list[dict], percorso: str) -> None:
    if not dati:
        return
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    print(f"  -> JSON: {percorso}  ({len(dati)} proprietà)")


def genera_output(proprieta: list[Proprieta], cartella_output: str = "output") -> None:
    os.makedirs(cartella_output, exist_ok=True)

    portali = {
        "airbnb": esporta_airbnb(proprieta),
        "booking": esporta_booking(proprieta),
        "homeaway": esporta_homeaway(proprieta),
        "immobiliare": esporta_immobiliare(proprieta),
    }

    for nome_portale, dati in portali.items():
        _scrivi_csv(dati, f"{cartella_output}/{nome_portale}.csv")
        _scrivi_json(dati, f"{cartella_output}/{nome_portale}.json")


# ---------------------------------------------------------------------------
# Report di validazione
# ---------------------------------------------------------------------------

def stampa_report(proprieta: list[Proprieta]) -> None:
    totale = len(proprieta)
    valide = sum(1 for p in proprieta if p.valida)
    non_valide = totale - valide

    print("\n" + "=" * 60)
    print("REPORT DI VALIDAZIONE")
    print("=" * 60)
    print(f"Totale proprietà lette : {totale}")
    print(f"Proprietà valide       : {valide}")
    print(f"Proprietà con errori   : {non_valide}")

    if non_valide > 0:
        print("\nDETTAGLIO ERRORI:")
        print("-" * 60)
        for i, p in enumerate(proprieta, start=1):
            if not p.valida:
                print(f"\n  Riga {i} - '{p.nome or '(senza nome)'}':")
                for err in p.errori:
                    print(f"    - {err}")

    print("\nPROPRIETA' VALIDE:")
    print("-" * 60)
    for p in proprieta:
        if p.valida:
            print(
                f"  {p.nome:<40} "
                f"{p.tipo_proprieta:<15} "
                f"€{p.prezzo_notte:>7.2f}/notte  "
                f"{p.citta}"
            )

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Processa dati proprietà da CSV e genera file per portali di affitto."
    )
    parser.add_argument(
        "csv_input",
        nargs="?",
        default="properties_sample.csv",
        help="Percorso del file CSV di input (default: properties_sample.csv)",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Cartella di output (default: output)",
    )
    parser.add_argument(
        "--solo-report",
        action="store_true",
        help="Stampa solo il report di validazione senza generare file di output",
    )
    args = parser.parse_args()

    print(f"\nLettura file: {args.csv_input}")
    proprieta = leggi_csv(args.csv_input)
    print(f"Lette {len(proprieta)} proprietà.")

    stampa_report(proprieta)

    if not args.solo_report:
        print(f"Generazione file di output in '{args.output}'...")
        genera_output(proprieta, args.output)
        print("\nEsportazione completata.")


if __name__ == "__main__":
    main()
