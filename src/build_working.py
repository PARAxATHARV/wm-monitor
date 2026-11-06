"""Step 3b: load the raw export into SQLite, unchanged, and build the working table."""
import sqlite3

import pandas as pd

import config as c

# 1. Read the raw export exactly as delivered: every value as text, empty cells stay ""
raw = pd.read_csv(c.RAW_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")

# 2. Provenance: which snapshot, which file, which row (row 1 = first data row under the header)
raw.insert(0, "snapshot_id", c.SNAPSHOT_ID)
raw.insert(1, "source_file", c.RAW_FILE)
raw.insert(2, "source_row", range(1, len(raw) + 1))

# 3. Working table: provenance + our 18 fields, renamed. Still all text, no conversions yet
working = raw[["snapshot_id", "source_file", "source_row"] + list(c.COLUMN_MAP.values())]
working = working.rename(columns={v: k for k, v in c.COLUMN_MAP.items()})

# 4. Checks before writing anything
assert len(working) == 22802, len(working)
assert working["eprel_id"].is_unique
assert list(working.columns[3:]) == list(c.COLUMN_MAP.keys())

# 5. Write both layers to the database (replacing them if the script is run again)
with sqlite3.connect(c.DB_PATH) as con:
    raw.to_sql("raw_export", con, if_exists="replace", index=False)
    working.to_sql("products_working", con, if_exists="replace", index=False)

print("raw_export:", raw.shape)
print("products_working:", working.shape)

DB_PATH = "outputs/monitor.sqlite"