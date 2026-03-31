#!/usr/bin/env python3
"""
Import Fidelity CSV exports from ~/Downloads into the data/ directory.
Renames files to: {Account_Name}_{MMDDYYYY}.csv
"""

import csv
import re
import shutil
from datetime import datetime
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

today = datetime.now().strftime("%m%d%Y")
files = sorted(DOWNLOADS.glob("Portfolio_Positions*.csv"))

if not files:
    print("No Portfolio_Positions*.csv files found in ~/Downloads")
    exit()

print(f"Found {len(files)} file(s) to import:\n")

for src in files:
    # Read account name from first data row
    with open(src, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first_row = next(reader, None)

    if not first_row:
        print(f"  SKIP  {src.name} (empty file)")
        continue

    account_name = (first_row.get("Account Name") or "").strip()
    if not account_name:
        print(f"  SKIP  {src.name} (no Account Name found)")
        continue

    # Sanitize: replace spaces/special chars with underscores
    safe_name = re.sub(r"[^\w]+", "_", account_name).strip("_")
    dest_name = f"{safe_name}_{today}.csv"
    dest = DATA_DIR / dest_name

    shutil.move(str(src), str(dest))
    print(f"  DONE  {src.name}")
    print(f"    →   data/{dest_name}  ({account_name})")

print("\nImport complete.")
