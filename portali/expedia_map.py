"""
Mappatura dotazioni JSON → label checkbox Expedia/Vrbo owner dashboard.

Le label corrispondono ai checkbox nella pagina di inserimento proprietà
su Vrbo owner dashboard. Supporta label IT e EN con fallback.
"""

DOTAZIONI_MAP = {
    "tv": "TV",
    "piano_cottura": "Stove",
    "frigo_congelatore": "Refrigerator",
    "forno": "Oven",
    "microonde": "Microwave",
    "lavatrice": "Washing machine",
    "lavastoviglie": "Dishwasher",
    "aria_condizionata": "Air conditioning",
    "riscaldamento": "Heating",
    "internet_wifi": "Internet/Wi-Fi",
    "phon": "Hair dryer",
    "ferro_stiro": "Iron",
    "terrazza": "Terrace",
    "giardino": "Garden",
    "piscina": "Pool",
    "arredi_esterno": "Outdoor furniture",
    "barbecue": "Barbecue grill",
    "culla": "Crib",
    "seggiolone": "High chair",
    "animali_ammessi": "Pets allowed",
}

# Label alternative in italiano (fallback)
DOTAZIONI_MAP_IT = {
    "tv": "TV",
    "piano_cottura": "Piano cottura",
    "frigo_congelatore": "Frigorifero",
    "forno": "Forno",
    "microonde": "Microonde",
    "lavatrice": "Lavatrice",
    "lavastoviglie": "Lavastoviglie",
    "aria_condizionata": "Aria condizionata",
    "riscaldamento": "Riscaldamento",
    "internet_wifi": "WiFi",
    "phon": "Asciugacapelli",
    "ferro_stiro": "Ferro da stiro",
    "terrazza": "Terrazza",
    "giardino": "Giardino",
    "piscina": "Piscina",
    "arredi_esterno": "Arredi da esterno",
    "barbecue": "Barbecue",
    "culla": "Culla",
    "seggiolone": "Seggiolone",
    "animali_ammessi": "Animali ammessi",
}
