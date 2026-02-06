#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, os, re, sys
from datetime import datetime, timezone
from lxml import etree

CSV_PATH = os.getenv("CSV_PATH", "cms.csv")
BASE_URL = os.getenv("BASE_URL", "https://viborg-caravancenter.dk/campingvogne").rstrip("/")
CATEGORY_PATH = os.getenv("CATEGORY_PATH", "/camping/campingvogn")  # GG-kategori
AD_TYPE = "Sælges"

# Tilpas disse hvis dine CSV-kolonner hedder noget andet
CSV_COLUMNS = {
    "id": "Slug",
    "draft": ":draft",
    "type": "Type",
    "model": "Model",
    "year": "År",
    "price": "Pris",
    "category_kind": "Kategori",  # "Ny"/"Brugt" -> bruges til varens-stand
    "images": [f"Billede {i}" for i in range(1, 7)],
    "text_extra": "Yderligere oplysninger",
    "text_inst": "Installationer og tilbehør",
    "total_weight": "Totalvægt",
    "own_weight": "Egenvægt",
}

BRANDS = [
    "Andet mærke","Adria","Apollo Wilk","Eifelland","Fendt","Hero Camper","Knaus",
    "Münsterland","Rapido","Safari","Solifer","Sprite","Sterckeman","Beyerland",
    "Cabby","Carado","Dethleffs","Hobby","Home-Car","Hymer","Kabe","Kip","LMC",
    "Polar","RC Caravan","Seestern","Senator","Wilk","Bürstner","Camp-Let",
    "Caravelair","Chateau","Delta","Edelweiss","Elddis","Fleetwood","Tabbert",
    "TEC","Sun Living"
]

def read_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def now_iso_utc_z():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def norm_price_to_int_dkk(s):
    if not s: return None
    t = str(s).strip().replace("kr","").replace("DKK","").replace(" ", "").replace(".", "").replace(",-","").replace(",", ".")
    try:
        return str(int(round(float(t))))
    except Exception:
        return None

def to_int_str(s):
    if not s: return None
    t = re.sub(r"[^\d]", "", str(s))
    return t or None

def detect_brand(model):
    if not model: return "Andet mærke"
    for b in sorted(BRANDS, key=len, reverse=True):
        if b == "Andet mærke": continue
        if model.lower().startswith(b.lower()+" ") or model.lower()==b.lower():
            return b
    return "Andet mærke"

def strip_brand_prefix(model, brand):
    if not model or brand=="Andet mærke": return model or ""
    ml = model.lower()
    bl = brand.lower()
    if ml.startswith(bl):
        return model[len(brand):].strip(" -")
    return model

def build_text(row):
    parts = []
    if CSV_COLUMNS["text_extra"] in row and row[CSV_COLUMNS["text_extra"]].strip():
        parts.append(row[CSV_COLUMNS["text_extra"]].strip())
    if CSV_COLUMNS["text_inst"] in row and row[CSV_COLUMNS["text_inst"]].strip():
        bullets = re.split(r"\s*[|,;\n]\s*", row[CSV_COLUMNS["text_inst"]].strip())
        bullets = [b for b in bullets if b]
        if bullets:
            parts.append("\n".join(f"• {b}" for b in bullets))
    return "\n".join(parts)

def build_xml(rows):
    root = etree.Element("ads")
    errors = []
    for i, r in enumerate(rows, start=2):
        
        # --- FILTER 1: SPRING DRAFTS OVER ---
        is_draft = (r.get(CSV_COLUMNS["draft"]) or "").strip().lower()
        if is_draft == "true":
            continue

        # --- FILTER 2: KUN CAMPINGVOGNE ---
        # Dette sikrer at fortelte, teltvogne osv. ikke kommer med
        vogn_type = (r.get(CSV_COLUMNS["type"]) or "").strip()
        if vogn_type != "Campingvogn":
            continue

        ad_id = (r.get(CSV_COLUMNS["id"]) or "").strip()
        if not ad_id:
            errors.append(f"Row {i}: missing id/Slug")
            continue

        ad = etree.SubElement(root, "ad", id=ad_id)
        etree.SubElement(ad, "last_updated").text = now_iso_utc_z()

        model = (r.get(CSV_COLUMNS["model"]) or "").strip()
        year = (r.get(CSV_COLUMNS["year"]) or "").strip()
        headline = f"{model} ({year})" if year else model
        etree.SubElement(ad, "headline").text = headline

        etree.SubElement(ad, "text").text = build_text(r)

        p = norm_price_to_int_dkk(r.get(CSV_COLUMNS["price"]))
        if p: etree.SubElement(ad, "price").text = p

        etree.SubElement(ad, "type").text = AD_TYPE

        imgs = []
        for col in CSV_COLUMNS["images"]:
            u = (r.get(col) or "").strip()
            if u: imgs.append(u)
        if imgs:
            images = etree.SubElement(ad, "images")
            for u in imgs:
                etree.SubElement(images, "image").text = u

        if BASE_URL:
            etree.SubElement(ad, "link").text = f"{BASE_URL}/{ad_id}"

        etree.SubElement(ad, "category").text = CATEGORY_PATH

        # categoryfields (camping: maerke er påkrævet)
        cf = etree.SubElement(ad, "categoryfields")
        brand = detect_brand(model)
        etree.SubElement(cf, "maerke").text = brand
        mv = strip_brand_prefix(model, brand)
        if mv: etree.SubElement(cf, "modelvariant").text = mv

        ar = to_int_str(r.get(CSV_COLUMNS["year"]))
        if ar: etree.SubElement(cf, "argang").text = ar

        tot = to_int_str(r.get(CSV_COLUMNS["total_weight"]))
        if tot: etree.SubElement(cf, "totalvaegt").text = tot

        egen = to_int_str(r.get(CSV_COLUMNS["own_weight"]))
        if egen: etree.SubElement(cf, "egenvaegt").text = egen

        kind = (r.get(CSV_COLUMNS["category_kind"]) or "").strip().lower()
        stand = "God, men brugt" if kind == "brugt" else ("Ny" if kind == "ny" else "")
        if stand:
            etree.SubElement(cf, "varens-stand").text = stand

    return etree.ElementTree(root), errors

def main():
    rows = read_rows(CSV_PATH)
    xml_tree, errors = build_xml(rows)
    os.makedirs("public", exist_ok=True)
    out = "public/feed.xml"
    xml_tree.write(out, encoding="utf-8", xml_declaration=True, pretty_print=True)

    hard = [e for e in errors if "missing id" in e or "missing id/Slug" in e]
    for e in errors: print("[VALIDATION]", e, file=sys.stderr)
    if hard:
        sys.exit(1)

if __name__ == "__main__":
    main()
