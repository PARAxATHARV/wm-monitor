"""Retailer pilot, step 2: turn saved product pages into one table of listings.

Run from the project root:
    python src/parse_listing.py

Reads every saved page in data/raw/<shop>/ (written by fetch_one.py / collect_listings.py),
keeps only HTTP-200 product pages, and reads the schema.org "Product" block on each page.
Values are stored as the shop shows them; nothing is corrected here.

Writes:
    outputs/retail_listings.csv
    table retail_listings in outputs/monitor.sqlite (replaced on every run)
"""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

import config as c

ROOT = Path(__file__).resolve().parents[1]
LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
DATASHEET = re.compile(r'https?://[^"\'\s<>]+ENERGY_EFFICIENCY_DATASHEET[^"\'\s<>]+\.pdf')


def find_product(html):
    """Return the first schema.org Product object on the page, or None."""
    for block in LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def parse_page(html_path, meta):
    html = html_path.read_text(encoding="utf-8", errors="replace")
    product = find_product(html)
    if product is None:
        return None
    offer = product.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    gtin_key = next((k for k in product if k.startswith("gtin")), "")
    energy = (product.get("hasEnergyConsumptionDetails") or {}).get("hasEnergyEfficiencyCategory", "")
    brand = product.get("brand") or {}
    sheet = DATASHEET.search(html)
    return {
        "shop": meta["source"],
        "shop_product_id": str(product.get("sku", "")),
        "url": meta["url"],
        "collected_at_utc": meta["collected_at_utc"],
        "raw_file": str(html_path.relative_to(ROOT)),
        "raw_sha256": meta["sha256"],
        "brand_text": brand.get("name", "") if isinstance(brand, dict) else str(brand),
        "product_name": product.get("name", ""),
        # Alternate puts the model identifier before the first comma of the name
        "model_text": product.get("name", "").split(",")[0].strip(),
        "gtin": str(product.get(gtin_key, "")),
        "gtin_field": gtin_key,               # kept because the label can be wrong (e.g. gtin8 with 13 digits)
        "mpn": str(product.get("mpn", "")),   # shop/manufacturer article no., not the EPREL model identifier
        "price": offer.get("price", ""),
        "currency": offer.get("priceCurrency", ""),
        "availability": str(offer.get("availability", "")).rsplit("/", 1)[-1],
        "energy_class_shop": str(energy).replace("https://schema.org/EUEnergyEfficiencyCategory", ""),
        "datasheet_pdf": sheet.group(0) if sheet else "",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    rows, skipped = [], []
    for meta_path in sorted((ROOT / "data" / "raw").glob("*/*.json")):
        html_path = meta_path.with_suffix(".html")
        if not html_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("http_status") != 200:
            skipped.append((html_path.name, f"HTTP {meta.get('http_status')}"))
            continue
        row = parse_page(html_path, meta)
        if row is None:
            skipped.append((html_path.name, "no Product block (not a product page)"))
        else:
            rows.append(row)

    df = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_dir / "retail_listings.csv", index=False)
    with closing(sqlite3.connect(args.db)) as con:
        df.to_sql("retail_listings", con, if_exists="replace", index=False)
        con.commit()

    print(f"Parsed {len(df)} product pages; skipped {len(skipped)}.")
    for name, reason in skipped:
        print(f"  skipped {name}: {reason}")
    if len(df):
        print(df[["shop", "brand_text", "model_text", "gtin", "price", "availability",
                  "energy_class_shop"]].to_string(index=False))


if __name__ == "__main__":
    main()
