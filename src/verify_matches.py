"""Retailer pilot, step 5: check every match against the shop's official product sheet.

Run from the project root (after match_listings.py; needs: pip install pypdf):
    python src/verify_matches.py

For each listing, downloads the energy product information sheet (PDF) that the shop
links, unless it is already saved, saves it unchanged with a provenance record, and reads
the EPREL registration number and the model identifier printed on it.

Two different kinds of check are kept apart:

1. Explicit EPREL ID (reference_type "eprel_number"): the sheet prints an EPREL
   registration number. This is an independent reference for that listing.
     correct                     our match has the same EPREL ID as the sheet
     wrong                       our match has a different EPREL ID
     missed                      no accepted match, but the sheet's ID IS in our snapshot
     reference_outside_snapshot  no accepted match, and the sheet's ID is not in our snapshot
   Precision and recall are computed on this subset only. Recall leaves out listings
   whose sheet ID is not in our snapshot (we could not have found them).

2. Model-name consistency (reference_type "sheet_model"): the sheet prints no EPREL
   number, so its model identifier is looked up in the snapshot with the same
   normalisation and brand rule as the matcher. This is NOT independent ground truth.
   It only says whether our match agrees with the model name on the sheet.
     consistent                  the lookup gives exactly our matched EPREL ID
     inconsistent                the lookup gives one different EPREL ID
     candidate_found_unmatched   no accepted match, but the lookup gives one EPREL ID
     ambiguous_model_match       the lookup gives several EPREL IDs
     unresolved_no_model_match   the lookup finds nothing. This does NOT show that the
                                 machine is absent from EPREL or from our snapshot.

   no_reference (reference_type "none"): no sheet, or nothing usable on it.

Pauses between downloads. Writes outputs/match_verification.csv, a short
outputs/match_verification_summary.json, and table match_verification in
outputs/monitor.sqlite (replaced on every run).
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

EXPLICIT_OUTCOMES = ["correct", "wrong", "missed", "reference_outside_snapshot"]
MODEL_OUTCOMES = ["consistent", "inconsistent", "candidate_found_unmatched",
                  "ambiguous_model_match", "unresolved_no_model_match"]


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


def classify(our_id, sheet_id, sheet_model, model_ids, snapshot_ids):
    """Return (reference_type, outcome) for one listing.

    our_id       EPREL ID of our accepted match, "" if none
    sheet_id     EPREL number printed on the sheet, "" if none
    sheet_model  model identifier printed on the sheet, "" if none
    model_ids    brand-compatible snapshot EPREL IDs whose model equals sheet_model
    """
    if sheet_id:
        if our_id:
            return "eprel_number", "correct" if our_id == sheet_id else "wrong"
        return "eprel_number", "missed" if sheet_id in snapshot_ids else "reference_outside_snapshot"
    if sheet_model:
        if not model_ids:
            return "sheet_model", "unresolved_no_model_match"
        if len(model_ids) > 1:
            return "sheet_model", "ambiguous_model_match"
        if our_id:
            return "sheet_model", "consistent" if our_id == model_ids[0] else "inconsistent"
        return "sheet_model", "candidate_found_unmatched"
    return "none", "no_reference"


def summarise(rows):
    """Counts for reporting. rows: list of dicts with match_status, reference_type, outcome."""
    n = len(rows)
    count = lambda ref, out: sum(1 for r in rows if r["reference_type"] == ref and r["outcome"] == out)
    explicit = {o: count("eprel_number", o) for o in EXPLICIT_OUTCOMES}
    model = {o: count("sheet_model", o) for o in MODEL_OUTCOMES}
    checked = explicit["correct"] + explicit["wrong"]
    findable = explicit["correct"] + explicit["missed"] + sum(
        1 for r in rows if r["reference_type"] == "eprel_number" and r["outcome"] == "wrong"
        and r.get("sheet_id_in_snapshot", True))
    return {
        "listings": n,
        "matched": sum(1 for r in rows if r["match_status"] == "matched"),
        "explicit_id_subset": sum(explicit.values()),
        "explicit_id_outcomes": explicit,
        "precision_explicit": [explicit["correct"], checked],
        "recall_explicit": [explicit["correct"], findable],
        "explicit_reference_outside_snapshot": explicit["reference_outside_snapshot"],
        "model_name_subset": sum(model.values()),
        "model_name_outcomes": model,
        "no_reference": count("none", "no_reference"),
    }


def report(s):
    lines = [f"Coverage: {s['matched']}/{s['listings']} listings have an accepted match.",
             "",
             f"Explicit EPREL ID on the sheet: {s['explicit_id_subset']} of {s['listings']} listings "
             "(independent reference)."]
    lines += [f"  {k}: {v}" for k, v in s["explicit_id_outcomes"].items()]
    p, r = s["precision_explicit"], s["recall_explicit"]
    if p[1]:
        lines.append(f"  Precision: {p[0]}/{p[1]} accepted matches in this subset are correct.")
    if r[1]:
        lines.append(f"  Recall: {r[0]}/{r[1]} listings in this subset whose sheet ID is in the "
                     "snapshot were matched correctly"
                     + (f" ({s['explicit_reference_outside_snapshot']} excluded: ID not in snapshot)."
                        if s["explicit_reference_outside_snapshot"] else "."))
    lines += ["",
              f"Model-name consistency only (sheet prints no EPREL number): {s['model_name_subset']} "
              "listings. Not independent ground truth; awaiting manual review."]
    lines += [f"  {k}: {v}" for k, v in s["model_name_outcomes"].items()]
    lines.append(f"\nNo usable reference: {s['no_reference']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    for n, m in matches.iterrows():
        url = sheets.get((m["shop"], m["shop_product_id"]), "") or ""
        sheet_id, sheet_model, note, sheet_file = "", "", "", ""
        if url:
            dest = ROOT / "data" / "raw" / m["shop"].split(".")[0] / "datasheets" / f"{m['shop_product_id']}.pdf"
            sheet_file = str(dest.relative_to(ROOT))
            try:
                if not dest.exists():
                    download(url, dest)
                    time.sleep(PAUSE_SECONDS)
                sheet_id, sheet_model = read_sheet(dest)
            except Exception as err:          # keep going; record why
                note = f"{type(err).__name__}: {err}"
        ours = m["eprel_id"] if m["match_status"] == "matched" else ""
        model_ids = []
        if sheet_model:
            model_ids = [i for i in by_model.get(norm_model(sheet_model), [])
                         if brand_ok(m["brand_text"], brand_of[i])]
        ref_type, outcome = classify(ours, sheet_id, sheet_model, model_ids, snapshot_ids)
        rows.append({"shop": m["shop"], "shop_product_id": m["shop_product_id"],
                     "brand_text": m["brand_text"], "model_text": m["model_text"],
                     "match_status": m["match_status"], "match_method": m["match_method"],
                     "our_eprel_id": ours,
                     "sheet_eprel_id": sheet_id,                 # only a number printed on the sheet
                     "sheet_id_in_snapshot": (sheet_id in snapshot_ids) if sheet_id else "",
                     "sheet_model": sheet_model,
                     "model_lookup_eprel_ids": ";".join(model_ids),
                     "reference_type": ref_type, "outcome": outcome,
                     "datasheet_file": sheet_file, "datasheet_pdf": url, "note": note})
        print(f"[{n + 1}/{len(matches)}] {m['brand_text']} {m['model_text']}: {ref_type} / {outcome}")

    res = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.output_dir / "match_verification.csv", index=False)
    with closing(sqlite3.connect(args.db)) as con:
        res.to_sql("match_verification", con, if_exists="replace", index=False)
        con.commit()

    summary = summarise(rows)
    (args.output_dir / "match_verification_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print("\n" + report(summary))


if __name__ == "__main__":
    main()
