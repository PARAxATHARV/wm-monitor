import hashlib
import pandas as pd

PATH = "data/raw/eprel_export_2026-11-02/washingmachines2019_EN.csv"

# 1. Fingerprint the raw file so we can prove it never changed
with open(PATH, "rb") as f:
    print("sha256:", hashlib.sha256(f.read()).hexdigest())

# 2. Read every value as text: no guessing of types yet
df = pd.read_csv(PATH, dtype=str, keep_default_na=False)
print("rows, columns:", df.shape)

# 3. For each column: how many rows are filled, and an example
for col in df.columns:
    filled = (df[col].str.strip() != "").sum()
    example = df.loc[df[col] != "", col].head(1).tolist()
    print(f"{filled:6d}  {col[:60]:60s} {example}")