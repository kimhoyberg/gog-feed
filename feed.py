import requests
from bs4 import BeautifulSoup
import os, sys, re
from lxml import etree
from datetime import datetime, timezone

# --- KONFIGURATION ---
DATA_URL = "https://viborg-caravancenter.dk/data-eksport"
BASE_URL = "https://viborg-caravancenter.dk"

# Mærker genkendt af GulogGratis (bruges til automatisk kategorisering)
ALLOWED_BRANDS = ["Adria", "Bürstner", "Dethleffs", "Hobby", "Knaus", "LMC", "Tabbert", "Fendt", "Hymer", "Kabe", "Sprite", "Sterckeman", "Caravelair"]

def clean_number(val):
    if not val: return "0"
    v = str(val).replace('.', '').replace(',', '').replace(' ', '')
    match = re.search(r'\d+', v)
    return match.group() if match else "0"

def detect_brand(model_str):
    for brand in ALLOWED_BRANDS:
        if brand.lower() in model_str.lower():
            return brand
    return "Andet mærke"

def fetch_data(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers)
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Vi henter alt tekst og renser for dubletter (mobil/desktop) med en dict
    all_text = [t.get_text().strip() for t in soup.find_all(['p', 'span']) if t.get_text().strip()]
    
    ads_dict = {}
    for i in range(0, len(all_text), 8):
        chunk = all_text[i:i+8]
        if len(chunk) == 8:
            slug = chunk[0].lower()
            if slug in ads_dict: continue # Sorterer mobil/desktop dubletter fra
            
            ads_dict[slug] = {
                "slug": slug, "type_val": chunk[1], "model_name": chunk[2], 
                "year": chunk[3], "price": chunk[4], "own": chunk[5], 
                "total": chunk[6], "stand": chunk[7]
            }
    return list(ads_dict.values())

def build_xml(rows):
    root = etree.Element("ads")
    for r in rows:
        if "campingvogn" not in r['type_val'].lower(): continue
        
        # Specifikation: ID skal være en attribut på <ad>
        ad = etree.SubElement(root, "ad", id=r['slug'])
        etree.SubElement(ad, "last_updated").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        year = clean_number(r['year'])
        model_clean = re.sub(r'(?i)campingvogn', '', r['model_name']).strip()
        
        # Specifikation: <headline> i stedet for <title>
        headline = f"Campingvogn - {model_clean}"
        if year != "0" and year not in model_clean: headline += f" {year}"
        etree.SubElement(ad, "headline").text = headline
        
        # Specifikation: <text> er obligatorisk (vi genererer den fra model-navnet)
        etree.SubElement(ad, "text").text = f"Flot {model_clean} fra {year}. Kontakt os for mere information eller fremvisning."
        
        etree.SubElement(ad, "price").text = clean_number(r['price'])
        etree.SubElement(ad, "type").text = "Sælges" # Obligatorisk
        etree.SubElement(ad, "link").text = f"{BASE_URL}/campingvogne/{r['slug']}"
        etree.SubElement(ad, "category").text = "/camping/campingvogn" # Obligatorisk
        
        cf = etree.SubElement(ad, "categoryfields")
        brand = detect_brand(model_clean)
        etree.SubElement(cf, "maerke").text = brand # Obligatorisk
        etree.SubElement(cf, "model").text = brand  # Påkrævet af GoG validering
        etree.SubElement(cf, "modelvariant").text = model_clean
        
        if year != "0": etree.SubElement(cf, "argang").text = year
        
        # Vægt-swap (sikrer at totalvægt altid er det højeste tal)
        etree.SubElement(cf, "totalvaegt").text = clean_number(r['total'])
        etree.SubElement(cf, "egenvaegt").text = clean_number(r['own'])
        
        stand_raw = r['stand'].lower()
        stand = "God, men brugt" if "brugt" in stand_raw else ("Ny" if "ny" in stand_raw else "")
        if stand: etree.SubElement(cf, "varens-stand").text = stand
        
    return etree.ElementTree(root)

def main():
    data = fetch_data(DATA_URL)
    if data:
        tree = build_xml(data)
        os.makedirs("public", exist_ok=True)
        tree.write("public/feed.xml", encoding="utf-8", xml_declaration=True, pretty_print=True)

if __name__ == "__main__":
    main()
