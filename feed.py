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
    all_text = [t.get_text().strip() for t in soup.find_all(['p', 'span']) if t.get_text().strip()]

    # Slugs er lowercase og indeholder kun bogstaver, tal og bindestreger
    slug_pattern = re.compile(r'^[a-zæøå0-9][a-zæøå0-9\-]+$')

    ads_dict = {}
    i = 0
    while i < len(all_text):
        slug = all_text[i].lower()
        if not slug_pattern.match(slug):
            i += 1
            continue

        if i + 8 > len(all_text):
            break

        chunk_fixed = all_text[i:i+8]

        # Tilbehør: saml alle efterfølgende linjer indtil næste slug
        tilbehoer_parts = []
        j = i + 8
        while j < len(all_text):
            next_val = all_text[j]
            if slug_pattern.match(next_val.lower()) and len(next_val) > 3:
                break
            tilbehoer_parts.append(next_val)
            j += 1

        tilbehoer = ', '.join(
            re.sub(r'^✅\s*', '', t).strip()
            for t in tilbehoer_parts
            if t.strip()
        )

        if slug not in ads_dict:
            ads_dict[slug] = {
                "slug": slug, "type_val": chunk_fixed[1], "model_name": chunk_fixed[2],
                "year": chunk_fixed[3], "price": chunk_fixed[4], "own": chunk_fixed[5],
                "total": chunk_fixed[6], "stand": chunk_fixed[7],
                "tilbehoer": tilbehoer,
            }

        i = j

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
