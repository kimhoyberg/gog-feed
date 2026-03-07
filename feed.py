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

def parse_html_to_text(html_str):
    """Konverterer HTML-streng til ren tekst uden tags."""
    soup = BeautifulSoup(html_str, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def fetch_data(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, 'html.parser')

    # Find alle "Article"-containere — hver svarer til ét produkt
    # Framer renderer hver artikel som en selvstændig container
    # Vi finder dem via slug-mønsteret i teksten
    slug_pattern = re.compile(r'^[a-zæøå0-9][a-zæøå0-9\-]{3,}$')
    image_pattern = re.compile(r'https://framerusercontent\.com/\S+')

    # Hent al tekst og img-tags pr. "blok" ved at parse den fulde tekst
    full_text = soup.get_text(separator='\n')
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    # Find alle framerusercontent billed-URLs fra img-tags
    all_images_in_page = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if 'framerusercontent' in src:
            all_images_in_page.append(src)

    ads_dict = {}
    i = 0
    while i < len(lines):
        slug = lines[i].lower()
        if not slug_pattern.match(slug):
            i += 1
            continue

        # De 8 faste felter
        if i + 8 > len(lines):
            break

        chunk = lines[i:i+8]
        slug_val      = chunk[0].lower()
        type_val      = chunk[1]
        model_name    = chunk[2]
        year          = chunk[3]
        price         = chunk[4]
        own           = chunk[5]
        total         = chunk[6]
        stand         = chunk[7]

        # Tilbehør: saml linjer efter de 8 faste felter indtil næste slug
        tilbehoer_parts = []
        j = i + 8
        while j < len(lines):
            next_val = lines[j]
            if slug_pattern.match(next_val.lower()) and len(next_val) > 3:
                break
            # Spring billed-URLs og produktlinks over
            if image_pattern.match(next_val) or next_val.startswith('http') or next_val.startswith('/camping'):
                j += 1
                continue
            # Spring "Sælges" over
            if next_val in ['Sælges', 'Købes']:
                j += 1
                continue
            tilbehoer_parts.append(next_val)
            j += 1

        tilbehoer = ', '.join(
            re.sub(r'^✅\s*', '', t).strip()
            for t in tilbehoer_parts
            if t.strip() and not t.startswith('http')
        )

        if slug_val not in ads_dict:
            ads_dict[slug_val] = {
                "slug": slug_val,
                "type_val": type_val,
                "model_name": model_name,
                "year": year,
                "price": price,
                "own": own,
                "total": total,
                "stand": stand,
                "tilbehoer": tilbehoer,
            }

        i = j

    # Tilknyt billeder til produkter baseret på rækkefølge i HTML
    # Find img-tags grupperet efter deres position relativt til slug-tekst
    # Enklere: brug img-tags direkte fra HTML i den rækkefølge de optræder
    # og match dem til produkter via produktets link-URL i siden
    for ad_id, ad in ads_dict.items():
        ad['images'] = []

    # Find billeder pr. produkt ved at søge i HTML-strukturen
    # Hvert produkt har sine billeder samlet i en container
    # Vi finder containers der indeholder slug-teksten
    for container in soup.find_all(True):
        text_content = container.get_text()
        for ad_id, ad in ads_dict.items():
            if ad_id in text_content.lower() and not ad['images']:
                imgs = container.find_all('img')
                urls = [img.get('src','') for img in imgs if 'framerusercontent' in img.get('src','')]
                if urls:
                    ad['images'] = urls[:6]
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

        # Billeder
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
