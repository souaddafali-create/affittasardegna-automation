"""
immobiliare_uploader.py — Upload proprietà su Immobiliare.it via REST API XML.

Niente Playwright! Usa l'API REST ufficiale di feed.immobiliare.it.
Ref: https://feed.immobiliare.it/integration/ii/docs/import/payload-specifications

Env vars richieste:
    IMMOBILIARE_EMAIL    — email agenzia (usata per auth HTTP Basic)
    IMMOBILIARE_PASSWORD — password API (fornita dal supporto Immobiliare.it)
    IMMOBILIARE_SOURCE   — valore header X-IMMO-SOURCE (fornito dal supporto)
    PROPERTY_DATA        — (opzionale) path al JSON proprietà

REGOLA: tutti i dati vengono dal JSON. Zero valori inventati.
"""

import os
import sys
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring

import requests

from uploader_base import load_property_data
from portali.immobiliare_map import (
    BUILDING_TYPES, DOTAZIONI_MAP, DOTAZIONI_DESCRIZIONE, LETTI_MAP,
)

# --- Configurazione ---
PROP = load_property_data()

API_EMAIL = os.environ["IMMOBILIARE_EMAIL"]
API_PASSWORD = os.environ["IMMOBILIARE_PASSWORD"]
API_SOURCE = os.environ.get("IMMOBILIARE_SOURCE", "affittasardegna")

# Endpoint REST — base URL ufficiale feed.immobiliare.it
API_BASE = "https://feed.immobiliare.it/ws/import/immobiliare/property"

# Dry-run: se True, stampa XML senza inviare
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"


# ---------------------------------------------------------------------------
# Costruzione XML
# ---------------------------------------------------------------------------

def _build_property_xml():
    """Costruisce l'XML completo per una proprietà. Tutti i dati dal JSON."""
    ident = PROP["identificativi"]
    comp = PROP["composizione"]
    dot = PROP["dotazioni"]
    cond = PROP["condizioni"]
    mktg = PROP["marketing"]

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Root: <property>
    prop = Element("property", operation="write")

    # Identificazione
    uid = SubElement(prop, "unique-id")
    uid.text = ident.get("cin", ident["nome_struttura"].replace(" ", "_"))

    pub_date = SubElement(prop, "published-on")
    pub_date.text = now

    upd_date = SubElement(prop, "date-updated")
    upd_date.text = now

    ref = SubElement(prop, "reference-code")
    ref.text = ident.get("cir", "")

    # Tipo struttura
    tipo = ident.get("tipo_struttura", "Appartamento")
    building_id = BUILDING_TYPES.get(tipo, "7")  # default 7=Appartamento
    SubElement(prop, "building", IDType=building_id, status="buono")

    # Transazione: Affitto
    transactions = SubElement(prop, "transactions")
    transaction = SubElement(transactions, "transaction", type="R")
    prezzo_notte = cond.get("prezzo_notte")
    if prezzo_notte:
        price = SubElement(transaction, "price", currency="EUR", reserved="false")
        price.text = str(prezzo_notte)

    # Agente / Agenzia
    agent = SubElement(prop, "agent")
    office = SubElement(agent, "office-name")
    office.text = "AffittaSardegna"
    email = SubElement(agent, "email")
    email.text = API_EMAIL

    # Localizzazione
    location = SubElement(prop, "location")

    country = SubElement(location, "country-code")
    country.text = "IT"

    region = SubElement(location, "region")
    region.text = ident.get("regione", "")

    province = SubElement(location, "province")
    province.text = ident.get("provincia", "")

    city = SubElement(location, "city")
    city.text = ident.get("comune", "")

    postal = SubElement(location, "postal-code")
    postal.text = ident.get("cap", "")

    address = SubElement(location, "address")
    address.text = ident.get("indirizzo", "")

    # Descrizione — include dotazioni minori nella descrizione testuale
    desc_text = mktg.get("descrizione_lunga", "")
    amenities_text = []
    for key, label in DOTAZIONI_DESCRIZIONE.items():
        if dot.get(key) is True:
            amenities_text.append(label)
    if amenities_text:
        desc_text += "\n\nDotazioni: " + ", ".join(amenities_text) + "."

    descs = SubElement(prop, "descriptions")
    desc_it = SubElement(descs, "description", language="it")
    title_el = SubElement(desc_it, "title")
    title_el.text = mktg.get("descrizione_breve", ident["nome_struttura"])
    content_el = SubElement(desc_it, "content")
    content_el.text = desc_text

    # Composizione: camere, bagni, ospiti
    features = SubElement(prop, "features")

    rooms = SubElement(features, "rooms")
    rooms.text = str(comp.get("camere", 1))

    bathrooms = SubElement(features, "bathrooms")
    bathrooms.text = str(comp.get("bagni", 1))

    # Superficie
    if comp.get("metri_quadri"):
        size = SubElement(features, "size")
        size.text = str(comp["metri_quadri"])

    floor = SubElement(features, "floor")
    floor.text = ident.get("piano", "")

    # Letti nella descrizione features
    beds_desc = []
    for letto in comp.get("letti", []):
        tipo_letto = LETTI_MAP.get(letto["tipo"], letto["tipo"])
        beds_desc.append(f"{letto['quantita']}x {tipo_letto}")

    guests = SubElement(features, "max-guests")
    guests.text = str(comp.get("max_ospiti", 4))

    beds = SubElement(features, "beds")
    beds.text = str(comp.get("posti_letto", 4))

    if beds_desc:
        beds_detail = SubElement(features, "beds-description")
        beds_detail.text = ", ".join(beds_desc)

    # Extra features — struttura XML ufficiale Immobiliare.it
    extra = SubElement(prop, "extra-features")

    # Arredamento
    furniture = SubElement(extra, "furniture")
    furniture.text = "Arredato"

    # Contratto transitorio (affitto breve)
    rent_contract = SubElement(extra, "rent-contract")
    rent_contract.text = "Transitorio"

    # Soggiorno minimo
    min_stay = cond.get("soggiorno_minimo_bassa", {}).get("notti")
    if min_stay:
        min_el = SubElement(extra, "minimum-stay")
        min_el.text = str(min_stay)

    # Clima: aria condizionata e riscaldamento
    ambience = SubElement(extra, "ambience")
    if dot.get("aria_condizionata") is True:
        SubElement(ambience, "air-conditioning", type="Autonomo", present="true")
    if dot.get("riscaldamento") is True:
        SubElement(ambience, "heating", type="Autonomo")

    # Giardino
    if dot.get("giardino") is True:
        garden = SubElement(extra, "garden")
        garden.text = "Privato"

    # Terrazza
    if dot.get("terrazza") is True:
        terrace = SubElement(extra, "terrace")
        terrace.text = "1"

    # Piscina
    if dot.get("piscina") is True:
        pool = SubElement(extra, "pool")
        pool.text = dot.get("piscina_tipo", "Comune")

    # Parcheggio
    if dot.get("parcheggio_privato") is True or \
       "parcheggio" in (dot.get("altro_dotazioni") or "").lower():
        garage = SubElement(extra, "garage", type="PostoAuto")
        garage.text = "1"

    # Piano
    if ident.get("piano"):
        floor_ef = SubElement(extra, "floor", type="Intermedio")
        floor_ef.text = ident["piano"]

    # Cauzione
    if cond.get("cauzione_euro"):
        costs = SubElement(extra, "costs")
        deposit = SubElement(costs, "deposit", currency="EUR")
        deposit.text = str(cond["cauzione_euro"])

    return prop


def _xml_to_string(element):
    """Converte Element in stringa XML con dichiarazione."""
    xml_bytes = tostring(element, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'


# ---------------------------------------------------------------------------
# Invio API
# ---------------------------------------------------------------------------

def upload_property():
    """Invia la proprietà a Immobiliare.it via REST API."""
    xml_element = _build_property_xml()
    xml_str = _xml_to_string(xml_element)

    ident = PROP["identificativi"]
    property_id = ident.get("cin", ident["nome_struttura"].replace(" ", "_"))

    print(f"Proprietà: {ident['nome_struttura']}")
    print(f"ID univoco: {property_id}")
    print(f"Endpoint: {API_BASE}/{property_id}")

    if DRY_RUN:
        print("\n--- DRY RUN: XML generato ---")
        print(xml_str)
        print("--- Fine XML ---")
        print("\nNessun invio effettuato (DRY_RUN=1).")
        return

    response = requests.put(
        f"{API_BASE}/{property_id}",
        data=xml_str.encode("utf-8"),
        headers={
            "Content-Type": "application/xml; charset=utf-8",
            "X-IMMO-SOURCE": API_SOURCE,
        },
        auth=(API_EMAIL, API_PASSWORD),
        timeout=30,
    )

    print(f"HTTP Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")

    if response.status_code in (200, 201):
        print("Upload completato con successo!")
    else:
        print(f"ERRORE: upload fallito (HTTP {response.status_code})")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("IMMOBILIARE.IT UPLOADER — API REST XML")
    print("=" * 60)
    upload_property()


if __name__ == "__main__":
    main()
