"""Retailer pilot, step 5: check every match against the shop's official product sheet.

Run from the project root (after match_listings.py; needs: pip install pypdf):
    python src/verify_matches.py

For each matched or unmatched listing, downloads the energy product information sheet
(PDF) that the shop links, saves it unchanged with a provenance record, and reads the
EPREL registration number and model identifier printed on it. That number is the
independent reference ("ground truth") for the manual check:
  correct        our match has the same EPREL ID as the sheet
  wrong          our match has a different EPREL ID
  missed         unmatched, but the sheet's machine IS in our snapshot
  not_in_snapshot unmatched, and the sheet's machine is not in our snapshot
  no_reference   no sheet, or nothing on it that identifies one EPREL record
Not every sheet prints the EPREL number. Then the sheet's model identifier is looked up
in the snapshot instead (reference_type "sheet_model", a weaker but still independent check).
Pauses between downloads. Writes outputs/match_verification.csv and table
match_verification in outputs/monitor.sqlite (replaced on every run).
"""
import argparse
import hashlib
import json
import re
import sqlite3
import time
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

import config as c
from fetch_one import USER_AGENT
from match_listings import brand_ok, norm_model

ROOT = Path(__file__).resolve().parents[1]
PAUSE_SECONDS = 3
EPREL_RE = re.compile(r"(?:EPREL|eprel)[^0-9]{0,80}?(\d{6,8})")
MODEL_RE = re.compile(r"(?:Modellkennung|Model identifier)\s*(?:\([a-z]\)\s*)?:?\s*([^\n]+)")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    meta = {"url": url, "collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    dest.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def read_sheet(path):
    text = "".join(page.extract_text() or "" for page in PdfReader(path).pages)
    eprel, model = EPREL_RE.search(text), MODEL_RE.search(text)
    return (eprel.group(1) if eprel else ""), (model.group(1).strip() if model else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    with closing(sqlite3.connect(args.db)) as con:
        matches = pd.read_sql_query("SELECT * FROM matches", con, dtype=str)
        listings = pd.read_sql_query("SELECT shop, shop_product_id, datasheet_pdf, collected_at_utc "
                                     "FROM retail_listings", con, dtype=str)
        eprel = pd.read_sql_query("SELECT eprel_id, brand, model_identifier FROM products_clean", con)
    eprel["eprel_id"] = eprel["eprel_id"].astype(str)
    snapshot_ids = set(eprel["eprel_id"])
    by_model = eprel.groupby(eprel["model_identifier"].map(norm_model))["eprel_id"].apply(list)
    brand_of = eprel.set_index("eprel_id")["brand"]
    sheets = (listings.sort_values("collected_at_utc")
              .drop_duplicates(["shop", "shop_product_id"], keep="last")
              .set_index(["shop", "shop_product_id"])["datasheet_pdf"])

    rows = []
    for i, m in matches.iterrows():
        url = sheets.get((m["shop"], m["shop_product_id"]), "") or ""
        sheet_id, sheet_model, note = "", "", ""
        if url:
            dest = ROOT / "data" / "raw" / m["shop"].split(".")[0] / "datasheets" / f"{m['shop_product_id']}.pdf"
            try:
                if not dest.exists():
                    download(url, dest)
                    time.sleep(PAUSE_SECONDS)
                sheet_id, sheet_model = read_sheet(dest)
            except Exception as err:          # keep going; record why
                note = f"{type(err).__name__}: {err}"
        ours = m["eprel_id"] if m["match_status"] == "matched" else ""
        ref_type = "eprel_number" if sheet_id else ""
        if not sheet_id and sheet_model:      # fall back to the model identifier on the sheet
            ids = [i for i in by_model.get(norm_model(sheet_model), [])
                   if brand_ok(m["brand_text"], brand_of[i])]
            if len(ids) == 1:
                sheet_id, ref_type = ids[0], "sheet_model"
            elif not ids:
                ref_type = "sheet_model_not_found"
            else:
                ref_type = "sheet_model_ambiguous"
        if not sheet_id:
            outcome = "not_in_snapshot" if ref_type == "sheet_model_not_found" and not ours else "no_reference"
        elif ours:
            outcome = "correct" if ours == sheet_id else "wrong"
        elif sheet_id in snapshot_ids:
            outcome = "missed"
        else:
            outcome = "not_in_snapshot"
        rows.append({"shop": m["shop"], "shop_product_id": m["shop_product_id"],
                     "brand_text": m["brand_text"], "model_text": m["model_text"],
                     "match_status": m["match_status"], "match_method": m["match_method"],
                     "our_eprel_id": ours, "sheet_eprel_id": sheet_id, "sheet_model": sheet_model,
                     "reference_type": ref_type, "outcome": outcome, "datasheet_pdf": url, "note": note})
        print(f"[{i + 1}/{len(matches)}] {m['brand_text']} {m['model_text']}: {outcome}")

    res = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.output_dir / "match_verification.csv", index=False)
    with closing(sqlite3.connect(args.db)) as con:
        res.to_sql("match_verification", con, if_exists="replace", index=False)
        con.commit()

    counts = res["outcome"].value_counts()
    checked = counts.get("correct", 0) + counts.get("wrong", 0)
    findable = checked + counts.get("missed", 0)
    print("\n" + res.groupby(["outcome", "reference_type"]).size().rename("listings").to_string())
    if checked:
        print(f"\nPrecision: {counts.get('correct', 0)}/{checked} accepted matches are correct.")
    if findable:
        print(f"Recall: {counts.get('correct', 0)}/{findable} listings whose sheet ID is in the snapshot "
              "were matched correctly.")


if __name__ == "__main__":
    main()
