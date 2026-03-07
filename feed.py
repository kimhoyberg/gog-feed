import os, sys, re
from lxml import etree
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- KONFIGURATION ---
DATA_URL = "https://viborg-caravancenter.dk/data-eksport"
BASE_URL = "https://viborg-caravancenter.dk"

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
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    lines = [l.strip() for l in soup.get_text(separator='\n').splitlines() if l.strip()]

    slug_pattern = re.compile(r'^[a-zæøå0-9][a-zæøå0-9\-]{3,}$')

    # Find produktstartpositioner: en slug efterfulgt af "Campingvogn" på næste linje
    product_starts = []
    for i in range(len(lines) - 1):
        if slug_pattern.match(lines[i]) and lines[i+1].lower() == 'campingvogn':
            product_starts.append(i)

    ads_dict = {}
    for idx, start in enumerate(product_starts):
        # Slutningen af dette produkt er starten på næste (eller slutningen af listen)
        end = product_starts[idx + 1] if idx + 1 < len(product_starts) else len(lines)
        block = lines[start:end]

        if len(block) < 8:
            continue

        slug_val   = block[0].lower()
        type_val   = block[1]
        model_name = block[2]
        year       = block[3]
        price      = block[4]
        own        = block[5]
        total      = block[6]
        stand      = block[7]

        # Tilbehør: alt efter felt 8, minus URLs og "Sælges"
        tilbehoer_parts = []
        for line in block[8:]:
            if line.startswith('http') or line in ['Sælges', 'Købes']:
                continue
            tilbehoer_parts.append(re.sub(r'^✅\s*', '', line).strip())

        tilbehoer = ', '.join(t for t in tilbehoer_parts if t)

        if slug_val not in ads_dict:
            ads_dict[slug_val] = {
                "slug": slug_val, "type_val": type_val, "model_name": model_name,
                "year": year, "price": price, "own": own, "total": total,
                "stand": stand, "tilbehoer": tilbehoer, "images": [],
            }

    # Tilknyt billeder: find img-tags pr. produkt via HTML-struktur
    # Hvert produkt er i en container — vi finder den container der indeholder sluggen som tekst
    # og høster img-tags fra netop den container
    visited_slugs = set()
    for tag in soup.find_all(True):
        tag_text = tag.get_text()
        for slug_val, ad in ads_dict.items():
            if slug_val in visited_slugs:
                continue
            if slug_val in tag_text.lower():
                imgs = [
                    img.get('src', '')
                    for img in tag.find_all('img')
                    if 'framerusercontent' in img.get('src', '')
                ]
                if imgs:
                    ad['images'] = imgs[:6]
                    visited_slugs.add(slug_val)
                    break

    return list(ads_dict.values())

def build_xml(rows):
    root = etree.Element("ads")
    for r in rows:
        if "campingvogn" not in r['type_val'].lower():
            continue

        ad = etree.SubElement(root, "ad", id=r['slug'])
        etree.SubElement(ad, "last_updated").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        year = clean_number(r['year'])
        model_clean = re.sub(r'(?i)campingvogn', '', r['model_name']).strip()

        headline = f"Campingvogn - {model_clean}"
        if year != "0" and year not in model_clean:
            headline += f" {year}"
        etree.SubElement(ad, "headline").text = headline

        description = r['tilbehoer'] if r['tilbehoer'] else f"Flot {model_clean} fra {year}. Kontakt os for mere information eller fremvisning."
        etree.SubElement(ad, "text").text = description

        etree.SubElement(ad, "price").text = clean_number(r['price'])
        etree.SubElement(ad, "type").text = "Sælges"
        etree.SubElement(ad, "link").text = f"{BASE_URL}/campingvogne/{r['slug']}"
        etree.SubElement(ad, "category").text = "/camping/campingvogn"

        if r.get('images'):
            images_el = etree.SubElement(ad, "images")
            for img_url in r['images']:
                etree.SubElement(images_el, "image").text = img_url

        cf = etree.SubElement(ad, "categoryfields")
        brand = detect_brand(model_clean)
        etree.SubElement(cf, "maerke").text = brand
        etree.SubElement(cf, "model").text = brand
        etree.SubElement(cf, "modelvariant").text = model_clean

        if year != "0":
            etree.SubElement(cf, "argang").text = year

        etree.SubElement(cf, "totalvaegt").text = clean_number(r['total'])
        etree.SubElement(cf, "egenvaegt").text = clean_number(r['own'])

        stand_raw = r['stand'].lower()
        stand = "God, men brugt" if "brugt" in stand_raw else ("Ny" if "ny" in stand_raw else "")
        if stand:
            etree.SubElement(cf, "varens-stand").text = stand

    return etree.ElementTree(root)

def main():
    print("Henter data med Playwright...", file=sys.stderr)
    data = fetch_data(DATA_URL)
    print(f"Fandt {len(data)} produkter.", file=sys.stderr)
    if data:
        tree = build_xml(data)
        os.makedirs("public", exist_ok=True)
        tree.write("public/feed.xml", encoding="utf-8", xml_declaration=True, pretty_print=True)
        print("✅ feed.xml gemt.", file=sys.stderr)

if __name__ == "__main__":
    main()
