"""
Mappatura dotazioni JSON → tag XML Immobiliare.it (feed REST API v2).

Ref: https://feed.immobiliare.it/integration/ii/docs/import/payload-specifications
I codici numerici features saranno confermati con le credenziali API ufficiali.
"""

# Tipo struttura → IDType building
# Ref: http://feed.immobiliare.it/import/docs/building-types.xml
# 7 = Appartamento, 15 = Attico, 23 = Villa unifamiliare,
# 199-216 = Casa vacanza (variants)
BUILDING_TYPES = {
    "Appartamento": "7",
    "Villa": "23",
    "Villa bifamiliare": "24",
    "Attico": "15",
    "Casa indipendente": "21",
    "Monolocale": "7",
}

# Dotazioni JSON → XML element/attribute per <extra-features>
# L'API Immobiliare.it usa elementi XML dedicati per feature principali
# (aria condizionata, riscaldamento, giardino, terrazza, parcheggio, arredamento)
# Feature minori (TV, lavatrice, microonde, ecc.) vanno nella descrizione testuale.
DOTAZIONI_MAP = {
    "aria_condizionata": "air-conditioning",
    "riscaldamento": "heating",
    "terrazza": "terrace",
    "giardino": "garden",
    "piscina": "pool",
    "arredi_esterno": "furniture",
    "animali_ammessi": "pets-allowed",
}

# Feature minori che andranno menzionate nella descrizione (no tag XML dedicato)
DOTAZIONI_DESCRIZIONE = {
    "tv": "TV",
    "lavatrice": "lavatrice",
    "lavastoviglie": "lavastoviglie",
    "microonde": "microonde",
    "forno": "forno",
    "internet_wifi": "WiFi",
    "phon": "asciugacapelli",
    "ferro_stiro": "ferro da stiro",
    "barbecue": "barbecue",
    "culla": "culla",
    "seggiolone": "seggiolone",
}

# Tipo letto → label per descrizione XML
LETTI_MAP = {
    "matrimoniale": "letto matrimoniale",
    "singolo": "letto singolo",
    "divano_letto": "divano letto",
    "letto_castello": "letto a castello",
}
