import os, sys, re
from lxml import etree
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- KONFIGURATION ---
DATA_URL = "https://viborg-caravancenter.dk/data-eksport"
BASE_URL = "https://viborg-caravancenter.dk"

ALLOWED_BRANDS = ["Adria", "Bürstner", "Dethleffs", "Hobby", "Knaus", "LMC", "Tabbert",
                  "Fendt", "Hymer", "Kabe", "Sprite", "Sterckeman", "Caravelair", "Cabby", "Wilk"]

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

def fetch_product_images(page, slug):
    """Hent billeder fra den individuelle produktside med scroll for lazy-load."""
    url = f"{BASE_URL}/campingvogne/{slug}"
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Scroll ned for at trigge lazy-loading af billeder
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

        # Brug JavaScript til at finde alle framerusercontent billeder direkte i DOM
        img_srcs = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const seen = new Set();
            const result = [];
            for (const img of imgs) {
                const src = img.src || img.getAttribute('src') || '';
                if (src.includes('framerusercontent') && !seen.has(src)) {
                    seen.add(src);
                    result.push(src);
                }
            }
            return result;
        }""")
        return img_srcs[:6]
    except Exception as e:
        print(f"  Fejl ved {slug}: {e}", file=sys.stderr)
        return []

def fetch_data(url):
    slug_pattern = re.compile(r'^[a-zæøå0-9][a-zæøå0-9\-]{3,}$')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Hent data-eksport siden
        print("Henter data-eksport...", file=sys.stderr)
        page.goto(url, wait_until="networkidle")
        html = page.content()

        soup = BeautifulSoup(html, 'html.parser')
        lines = [l.strip() for l in soup.get_text(separator='\n').splitlines() if l.strip()]

        # Find produktstartpositioner: slug efterfulgt af "Campingvogn"
        product_starts = []
        for i in range(len(lines) - 1):
            if slug_pattern.match(lines[i]) and lines[i+1].lower() == 'campingvogn':
                product_starts.append(i)

        ads_dict = {}
        for idx, start in enumerate(product_starts):
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

            # Tilbehør og yderligere oplysninger: adskilt af "##"
            tilbehoer_parts = []
            yderligere_parts = []
            after_separator = False
            for line in block[8:]:
                if slug_pattern.match(line) and line != slug_val:
                    break
                if line.lower() == 'campingvogn':
                    break
                if line.startswith('http') or line in ['Sælges', 'Købes']:
                    continue
                if line.strip() == '##':
                    after_separator = True
                    continue
                clean = re.sub(r'^✅\s*', '', line).strip()
                if not clean:
                    continue
                if after_separator:
                    yderligere_parts.append(clean)
                else:
                    tilbehoer_parts.append(clean)

            tilbehoer = ', '.join(tilbehoer_parts)
            yderligere = ' '.join(yderligere_parts)

            if slug_val not in ads_dict:
                ads_dict[slug_val] = {
                    "slug": slug_val, "type_val": type_val, "model_name": model_name,
                    "year": year, "price": price, "own": own, "total": total,
                    "stand": stand, "tilbehoer": tilbehoer, "yderligere": yderligere,
                    "images": [],
                }

        # Hent billeder fra individuelle produktsider med scroll/JS
        print(f"Henter billeder for {len(ads_dict)} produkter...", file=sys.stderr)
        for slug_val, ad in ads_dict.items():
            print(f"  {slug_val}", file=sys.stderr)
            imgs = fetch_product_images(page, slug_val)
            print(f"    -> {len(imgs)} billeder fundet", file=sys.stderr)
            ad['images'] = imgs

        browser.close()

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

        if r['tilbehoer'] and r.get('yderligere'):
            description = r['tilbehoer'] + ' - ' + r['yderligere']
        elif r['tilbehoer']:
            description = r['tilbehoer']
        elif r.get('yderligere'):
            description = r['yderligere']
        else:
            description = f"Flot {model_clean} fra {year}. Kontakt os for mere information eller fremvisning."
        etree.SubElement(ad, "text").text = description

        etree.SubElement(ad, "price").text = clean_number(r['price'])
        etree.SubElement(ad, "type").text = "Sælges"
        etree.SubElement(ad, "link").text = f"{BASE_URL}/campingvogne/{r['slug']}"
        etree.SubElement(ad, "category").text = "/camping/campingvogn"

        real_images = [u for u in r.get('images', []) if not u.lower().endswith('.svg')]
        if real_images:
            images_el = etree.SubElement(ad, "images")
            for img_url in real_images:
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
    print("Starter feed-generering...", file=sys.stderr)
    data = fetch_data(DATA_URL)
    print(f"Fandt {len(data)} produkter.", file=sys.stderr)
    if data:
        tree = build_xml(data)
        os.makedirs("public", exist_ok=True)
        tree.write("public/feed.xml", encoding="utf-8", xml_declaration=True, pretty_print=True)
        print("✅ feed.xml gemt.", file=sys.stderr)

if __name__ == "__main__":
    main()
