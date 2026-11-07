"""Step 6: data-quality and coverage summary. Every number is computed from the database.
 
Run from the project root: python src/data_quality.py
Writes outputs/data_quality.md (and prints the same text).
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
 
import pandas as pd
 
import config as c
 
ROOT = Path(__file__).resolve().parents[1]
SITE_COUNT = 22814          # results shown on the EPREL site, ~17:15 CET 2 Nov 2026 (acquisition note)
CHECK_ID = "2518490"        # Atharv's product sheet, placed on the market 2 Nov 2026
 
 
def pct(n, total):
    return f"{n:,} ({n / total:.1%})"
 
 
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
 
    uri = args.db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        d = pd.read_sql_query("SELECT * FROM products_clean", con)
        issues = pd.read_sql_query("SELECT * FROM validation_issues", con)
    n = len(d)
 
    gtin = (d["gtin"].str.strip() != "").sum()
    end = d["end_placement_date"].notna().sum()
    end_2050 = (d["end_placement_date"] == "2050-12-31").sum()
    energy_warn = (issues["issue_type"] == "energy_inconsistent").sum()
    out_range = issues[issues["issue_type"] == "out_of_range"].groupby("field").size()
    flagged = (d["n_issues"] > 0).sum()
    dup_model = d.duplicated(["brand", "model_identifier"], keep=False).sum()
    combos = d.groupby(["rated_capacity_kg", "energy_kwh_per_100_cycles_eco4060",
                        "water_l_per_cycle_eco4060"]).ngroups
    past_end = (pd.to_datetime(d["end_placement_date"]) < pd.Timestamp("2026-11-02")).sum()
    class_a = (d["energy_class"] == "A").sum()
    first = pd.to_datetime(d["first_placement_date"])
    has_check = CHECK_ID in set(d["eprel_id"])
 
    lines = [
        "# Data quality and coverage: EPREL washing machines",
        "",
        f"Snapshot `{c.SNAPSHOT_ID}`: {n:,} registered models; the EPREL site showed {SITE_COUNT:,} "
        f"at about the same time ({SITE_COUNT - n:+,}, unexplained).",
        "",
        "## What the data is",
        "- Supplier-declared values from the EU product register, not independent test results.",
        "- One row per registered model. Not sales-weighted: a model sold once counts the same as a best-seller.",
        f"- First placement dates run from {first.min():%d %b %Y} to {first.max():%d %b %Y}. "
        f"End dates before the snapshot date: {past_end:,}, so the export appears to hold "
        "models currently on the market only.",
        f"- {pct(class_a, n)} of models are energy class A.",
        "",
        "## Coverage of key fields",
        f"- GTIN (barcode): {pct(gtin, n)}. Matching to retailer data must rely on brand + model identifier.",
        f"- End-of-placement date: {pct(end, n)}; {end_2050:,} of these are 31 Dec 2050, which looks like a placeholder.",
        f"- {dup_model:,} rows share a brand + model identifier with another registration.",
        "",
        "## Validation flags (kept, not deleted)",
        f"- Energy fields inconsistent (|per cycle x 100 - per 100 cycles| > 1 kWh): {pct(energy_warn, n)}.",
        "- Outside screening ranges: " + "; ".join(f"{f} {k}" for f, k in out_range.items()) + ".",
        f"- Models with at least one flag: {pct(flagged, n)}. Missing / malformed values: "
        f"{int(issues['issue_type'].isin(['missing', 'malformed']).sum())}.",
        "",
        "## Limits for interpretation",
        f"- The {n:,} models occupy only {combos:,} distinct capacity/energy/water combinations. Values are "
        "declared as whole numbers, so identical values alone do not prove models share a platform.",
        f"- Product sheet EPREL {CHECK_ID} (placed on the market 2 Nov 2026) is "
        f"{'in' if has_check else 'NOT in'} this snapshot: the export is a point-in-time copy.",
        "- Descriptive only: no causal claim about policy impact.",
    ]
    text = "\n".join(lines) + "\n"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "data_quality.md").write_text(text, encoding="utf-8")
    print(text)
 
 
if __name__ == "__main__":
    main()
 