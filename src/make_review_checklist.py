"""Retailer pilot, step 6: build the manual review checklist (one row per listing).

Run from the project root (after verify_matches.py):
    python src/make_review_checklist.py

Uses only what is already saved: tables matches, retail_listings and match_verification
in outputs/monitor.sqlite, and the provenance records of the saved product sheets.
Nothing is downloaded.

Writes review/manual_review_checklist.csv. Every new row starts with review_decision
"pending". Write correct / incorrect / unsure there after checking. The review columns (review_decision, reviewer_notes, reviewed_by,
reviewed_at) are filled in by hand. When the file already exists, those columns are
kept for every listing, so rerunning this script never erases a manual decision.
"""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

import config as c

ROOT = Path(__file__).resolve().parents[1]
REVIEW_COLS = ["review_decision", "reviewer_notes", "reviewed_by", "reviewed_at"]
KEY = ["shop", "shop_product_id"]


def evidence_text(v):
    if v["reference_type"] == "eprel_number":
        return f"Product sheet prints EPREL registration number {v['sheet_eprel_id']}."
    if v["reference_type"] == "sheet_model":
        found = v["model_lookup_eprel_ids"] or "no snapshot record"
        return (f"Product sheet prints no EPREL number; its model identifier '{v['sheet_model']}' "
                f"was looked up in the 2 Nov snapshot: {found}.")
    return "No usable product sheet reference."


def open_questions(m, v):
    q = []
    out = v["outcome"]
    if out == "correct":
        q.append("Automated check agrees; open the sheet and confirm it belongs to this listing.")
    if out == "wrong":
        q.append(f"Our match {v['our_eprel_id']} differs from the sheet's EPREL {v['sheet_eprel_id']}: why?")
    if out == "missed":
        q.append(f"No accepted match, but the sheet's EPREL {v['sheet_eprel_id']} is in the snapshot. "
                 "Is the shop's model text a variant name of that model?")
    if out == "reference_outside_snapshot":
        q.append("Sheet's EPREL ID is not in the snapshot: newer registration, or a different product?")
    if v["reference_type"] == "sheet_model":
        q.append("Sheet has no EPREL number, so the check is model-name consistency only. "
                 "Confirm the EPREL record by looking it up in the public EPREL database.")
    if out == "candidate_found_unmatched":
        q.append(f"Sheet model points to EPREL {v['model_lookup_eprel_ids']} but our rules accepted no match. "
                 "Is it the same product?")
    if out == "inconsistent":
        q.append("Sheet model points to a different EPREL record than our match.")
    if out == "ambiguous_model_match":
        q.append("Sheet model fits several EPREL records; which one is the listing?")
    if out == "unresolved_no_model_match":
        q.append("No snapshot record has the sheet's model identifier. Unresolved: the model may be "
                 "missing from the snapshot, registered later, or listed under another identifier.")
    if m["match_method"] == "model_core":
        q.append("Matched on the first word of the shop name only (extra series words dropped): "
                 "check it is the same variant.")
    if m["match_status"] == "matched" and str(m["class_agrees"]) != "True":
        q.append("Shop energy class differs from EPREL.")
    return " ".join(q)


def sheet_provenance(sheet_file):
    """(sha256, collected_at_utc) of a saved sheet; hash computed if no record exists."""
    if not sheet_file:
        return "", ""
    pdf = ROOT / sheet_file
    meta_path = pdf.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("sha256", ""), meta.get("collected_at_utc", "")
    if pdf.exists():
        return hashlib.sha256(pdf.read_bytes()).hexdigest(), ""
    return "", ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--out", type=Path, default=ROOT / "review" / "manual_review_checklist.csv")
    args = parser.parse_args()

    with closing(sqlite3.connect(args.db)) as con:
        matches = pd.read_sql_query("SELECT * FROM matches", con, dtype=str).fillna("")
        listings = pd.read_sql_query("SELECT * FROM retail_listings", con, dtype=str).fillna("")
        verif = pd.read_sql_query("SELECT * FROM match_verification", con, dtype=str).fillna("")
    listings = (listings.sort_values("collected_at_utc")
                .drop_duplicates(KEY, keep="last").set_index(KEY))
    verif = verif.set_index(KEY)

    rows = []
    for _, m in matches.iterrows():
        key = (m["shop"], m["shop_product_id"])
        lst, v = listings.loc[key], verif.loc[key]
        sha, sheet_time = sheet_provenance(v["datasheet_file"])
        rows.append({
            "shop": m["shop"], "shop_product_id": m["shop_product_id"],
            "brand_text": m["brand_text"], "model_text": m["model_text"],
            "proposed_eprel_id": m["eprel_id"] if m["match_status"] == "matched" else "",
            "proposed_eprel_model": m["eprel_model_identifier"] if m["match_status"] == "matched" else "",
            "match_status": m["match_status"], "match_method": m["match_method"],
            "candidate_eprel_ids": m["candidate_eprel_ids"],
            "reference_type": v["reference_type"], "automated_outcome": v["outcome"],
            "sheet_eprel_id": v["sheet_eprel_id"], "sheet_model": v["sheet_model"],
            "model_lookup_eprel_ids": v["model_lookup_eprel_ids"],
            "evidence": evidence_text(v), "open_questions": open_questions(m, v),
            "listing_url": lst["url"], "listing_collected_at_utc": lst["collected_at_utc"],
            "raw_page_file": lst["raw_file"], "raw_page_sha256": lst["raw_sha256"],
            "datasheet_file": v["datasheet_file"], "datasheet_sha256": sha,
            "datasheet_collected_at_utc": sheet_time, "datasheet_url": v["datasheet_pdf"],
            "review_decision": "pending", "reviewer_notes": "", "reviewed_by": "", "reviewed_at": "",
        })
    res = pd.DataFrame(rows)

    kept = 0
    if args.out.exists():                      # never overwrite manual decisions
        old = pd.read_csv(args.out, dtype=str).fillna("").set_index(KEY)
        for i, r in res.iterrows():
            key = (r["shop"], r["shop_product_id"])
            if key in old.index:
                for col in REVIEW_COLS:
                    if col in old.columns and old.at[key, col] != "":
                        res.at[i, col] = old.at[key, col]
                kept += old.at[key, "review_decision"] not in ("", "pending")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.out, index=False)
    print(f"Wrote {len(res)} listings to {args.out}; "
          f"{kept} existing manual decisions kept, "
          f"{(res['review_decision'] == 'pending').sum()} pending.")
    print(res.groupby(["reference_type", "automated_outcome"]).size().rename("listings").to_string())


if __name__ == "__main__":
    main()
