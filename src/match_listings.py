"""Retailer pilot, step 4: match shop listings to EPREL models.

Run from the project root (after parse_listing.py):
    python src/match_listings.py

Uses the latest observation of each shop product from retail_listings and the EPREL
records in products_clean. Rules, tried in this order; the first rule with any
candidate decides:
  1. eprel_id      EPREL ID shown by the shop (if any)
  2. gtin          same GTIN (leading zeros ignored)
  3. model_exact   same full model identifier, ignoring case, spaces and punctuation
  4. model_core    the shop text's first word is an EPREL model identifier
                   (shops append series names such as "Serie 4" or "iQ300")
Every candidate must also have a compatible brand. One candidate -> "matched",
several -> "ambiguous", none -> "unmatched". Rule 4 is flagged for review.
Nothing is guessed: ambiguous and unmatched cases are kept and reported.

Writes outputs/matches.csv (with an empty review_correct column for the manual check)
and table matches in outputs/monitor.sqlite (replaced on every run).
"""
import argparse
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

import config as c

ROOT = Path(__file__).resolve().parents[1]
EPREL_COLS = ["eprel_id", "brand", "model_identifier", "gtin", "rated_capacity_kg",
              "energy_class", "energy_kwh_per_100_cycles_eco4060",
              "water_l_per_cycle_eco4060", "installation_type"]


def norm_model(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def norm_brand(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def brand_ok(shop_brand, eprel_brand):
    """Compatible if one normalised brand contains the other (LG / LG Electronics)."""
    a, b = norm_brand(shop_brand), norm_brand(eprel_brand)
    return bool(a) and bool(b) and (a in b or b in a)


def norm_gtin(text):
    digits = re.sub(r"\D", "", str(text))
    return digits.lstrip("0")


def match_one(listing, eprel, by_id, by_gtin, by_model):
    shop_brand = listing["brand_text"]
    words = str(listing["model_text"]).split()
    rules = [
        ("eprel_id", by_id.get(str(listing.get("eprel_id_shop", "")).strip(), [])),
        ("gtin", by_gtin.get(norm_gtin(listing["gtin"]), []) if norm_gtin(listing["gtin"]) else []),
        ("model_exact", by_model.get(norm_model(listing["model_text"]), [])),
        ("model_core", by_model.get(norm_model(words[0]), []) if len(words) > 1 else []),
    ]
    for method, rows in rules:
        cands = [i for i in rows if brand_ok(shop_brand, eprel.at[i, "brand"])]
        if cands:
            status = "matched" if len(cands) == 1 else "ambiguous"
            return method, status, cands
    return "", "unmatched", []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    with closing(sqlite3.connect(args.db)) as con:
        listings = pd.read_sql_query("SELECT * FROM retail_listings", con, dtype=str)
        eprel = pd.read_sql_query(f"SELECT {', '.join(EPREL_COLS)} FROM products_clean", con)
    eprel["eprel_id"] = eprel["eprel_id"].astype(str)
    eprel["gtin"] = eprel["gtin"].fillna("").astype(str)

    # latest observation per shop product
    listings = (listings.sort_values("collected_at_utc")
                .drop_duplicates(["shop", "shop_product_id"], keep="last")
                .reset_index(drop=True))

    by_id = eprel.groupby("eprel_id").groups
    by_gtin = eprel[eprel["gtin"].map(norm_gtin) != ""].groupby(eprel["gtin"].map(norm_gtin)).groups
    by_model = eprel.groupby(eprel["model_identifier"].map(norm_model)).groups

    out = []
    for _, lst in listings.iterrows():
        method, status, cands = match_one(lst, eprel, by_id, by_gtin, by_model)
        row = {
            "shop": lst["shop"], "shop_product_id": lst["shop_product_id"], "url": lst["url"],
            "collected_at_utc": lst["collected_at_utc"], "brand_text": lst["brand_text"],
            "model_text": lst["model_text"], "gtin_shop": lst["gtin"], "price": lst["price"],
            "availability": lst["availability"], "energy_class_shop": lst["energy_class_shop"],
            "match_method": method, "match_status": status, "n_candidates": len(cands),
            "needs_review": status != "matched" or method == "model_core",
            "candidate_eprel_ids": ";".join(eprel.loc[cands, "eprel_id"]),
        }
        e = eprel.loc[cands[0]] if len(cands) == 1 else None
        for col in EPREL_COLS:
            row[f"eprel_{col}" if not col.startswith("eprel") else col] = "" if e is None else e[col]
        row["class_agrees"] = "" if e is None else str(e["energy_class"] == lst["energy_class_shop"])
        row["review_correct"] = ""        # fill in by hand: yes / no
        out.append(row)

    res = pd.DataFrame(out)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.output_dir / "matches.csv", index=False)
    with closing(sqlite3.connect(args.db)) as con:
        res.to_sql("matches", con, if_exists="replace", index=False)
        con.commit()

    n = len(res)
    print(f"{n} distinct shop products matched against {len(eprel):,} EPREL models.\n")
    print(res.groupby(["match_status", "match_method"]).size().rename("listings").to_string())
    matched = res[res["match_status"] == "matched"]
    print(f"\nCoverage: {len(matched)}/{n} matched ({len(matched) / n:.0%}).")
    print(f"Energy class agrees with EPREL: {(matched['class_agrees'] == 'True').sum()}/{len(matched)} matched.")
    print(f"GTIN in shop data: {(res['gtin_shop'].str.strip() != '').sum()}/{n}; "
          f"matched by GTIN: {(res['match_method'] == 'gtin').sum()}.")
    print("\n" + res[["brand_text", "model_text", "match_status", "match_method",
                      "candidate_eprel_ids"]].to_string(index=False))


if __name__ == "__main__":
    main()
