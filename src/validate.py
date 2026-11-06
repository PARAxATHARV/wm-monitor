"""Step 4: convert types, record issues per field, and build products_clean (no rows dropped)."""
import sqlite3

import numpy as np
import pandas as pd

import config as c

NUMERIC = ["rated_capacity_kg", "eei", "energy_kwh_per_cycle_eco4060",
           "energy_kwh_per_100_cycles_eco4060", "water_l_per_cycle_eco4060",
           "duration_min_rated", "noise_db_spin", "commercial_guarantee_months"]
DATES = ["first_placement_date", "end_placement_date"]
OPTIONAL = ["gtin", "end_placement_date"]   # blank here is normal, not a problem
ENERGY_TOLERANCE_KWH = 1.0                  # per 100 cycles
EPS = 1e-9                                  # so 1.0000000001 from float maths is not flagged

with sqlite3.connect(c.DB_PATH) as con:
    work = pd.read_sql("SELECT * FROM products_working", con)

clean = work.copy()     # text fields (IDs, GTIN, brand ...) stay text
issues = []             # one record per problem: which row, which field, what kind, raw value


def log(mask, field, issue_type, detail=""):
    for _, r in work.loc[mask, ["source_row", "eprel_id", field]].iterrows():
        issues.append({"source_row": r["source_row"], "eprel_id": r["eprel_id"], "field": field,
                       "issue_type": issue_type, "raw_value": r[field], "detail": detail})


# 1. Missing values: blank text. Required fields only; optional blanks are expected
for field in c.COLUMN_MAP:
    if field not in OPTIONAL:
        log(work[field].str.strip() == "", field, "missing")

# 2. Numbers: blank -> NULL (already logged above); non-blank that will not parse -> malformed
for field in NUMERIC:
    raw = work[field].str.strip()
    num = pd.to_numeric(raw, errors="coerce")
    num = num.where(np.isfinite(num))                       # 'inf' etc. counts as malformed
    log((raw != "") & num.isna(), field, "malformed", "not a number")
    clean[field] = num

# 3. Dates: day/month/year -> ISO text YYYY-MM-DD; blank -> NULL; unparseable -> malformed
for field in DATES:
    raw = work[field].str.strip()
    parsed = pd.to_datetime(raw, format="%d/%m/%Y", errors="coerce")
    log((raw != "") & parsed.isna(), field, "malformed", "not a d/m/Y date")
    clean[field] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), None)
    clean[field + "_dt"] = parsed                           # temporary, for the date check

# 4. Plausibility screening: parsed values outside PLAUSIBLE are kept, only flagged
for field, (lo, hi) in c.PLAUSIBLE.items():
    v = clean[field]
    log(v.notna() & ((v < lo) | (v > hi)), field, "out_of_range", f"outside {lo}-{hi}")

# 5. Date logic: end before first placement (future end dates are fine)
log(clean["end_placement_date_dt"] < clean["first_placement_date_dt"],
    "end_placement_date", "end_before_first", "end date earlier than first placement")
clean = clean.drop(columns=[f + "_dt" for f in DATES])

# 6. Energy consistency: only when both values parsed; both declared values are kept
pc, p100 = clean["energy_kwh_per_cycle_eco4060"], clean["energy_kwh_per_100_cycles_eco4060"]
eligible = pc.notna() & p100.notna()
clean["energy_check_diff_kwh"] = (pc * 100 - p100).abs().where(eligible).round(6)
energy_flag = clean["energy_check_diff_kwh"] > ENERGY_TOLERANCE_KWH + EPS
log(energy_flag, "energy_kwh_per_100_cycles_eco4060", "energy_inconsistent",
    f"|per_cycle*100 - per_100| > {ENERGY_TOLERANCE_KWH} kWh")

issues = pd.DataFrame(issues, columns=["source_row", "eprel_id", "field",
                                       "issue_type", "raw_value", "detail"])
clean["n_issues"] = clean["source_row"].map(issues["source_row"].value_counts()).fillna(0).astype(int)

# 7. Preservation checks: every input row once, with its provenance
assert len(clean) == len(work)
assert set(clean["source_row"]) == set(work["source_row"])
assert clean["eprel_id"].is_unique
assert (clean[["snapshot_id", "source_file", "source_row"]] ==
        work[["snapshot_id", "source_file", "source_row"]]).all().all()

# 8. Write (replace, so a rerun gives the same tables, never duplicates)
with sqlite3.connect(c.DB_PATH) as con:
    clean.to_sql("products_clean", con, if_exists="replace", index=False)
    issues.to_sql("validation_issues", con, if_exists="replace", index=False)

# 9. Summary
print("rows in / out:", len(work), "/", len(clean))
print("optional blanks (not issues): gtin", (work["gtin"].str.strip() == "").sum(),
      "| end_placement_date", (work["end_placement_date"].str.strip() == "").sum())
print("\nissues by type and field:")
print(issues.groupby(["issue_type", "field"]).size().to_string() if len(issues) else "  none")
print(f"\nenergy check: {int(energy_flag.sum())} of {int(eligible.sum())} eligible models "
      f"differ by more than {ENERGY_TOLERANCE_KWH} kWh per 100 cycles")
print("models with at least one issue:", int((clean["n_issues"] > 0).sum()))