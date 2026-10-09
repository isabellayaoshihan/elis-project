"""Acquire BEA county GDP (CAGDP1) via the BEA API.

Reads the API key from the BEA_API_KEY environment variable, or from a line
BEA_API_KEY = "..." in api_keys.txt at the repo root (gitignored).

Outputs (relative to repo root):
  data/raw/bea_cagdp1_county.csv    flat table, values untouched
  data/raw/bea_cagdp1_county.sha256 integrity checksum
"""
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
KEY_FILE = ROOT / "api_keys.txt"
API_URL = "https://apps.bea.gov/api/data"

# CAGDP1 line codes (verify against the API's GetParameterValuesFiltered):
#   1 = Real GDP (chained dollars), 3 = Current-dollar GDP
LINE_CODES = [1, 3]
YEARS = ",".join(str(y) for y in range(2015, 2025))  # 2015-2024; adjust if BEA lags


def get_key() -> str:
    key = os.environ.get("BEA_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "BEA_API_KEY":
                key = value.strip().strip("\"'")
                break
    if not key:
        sys.exit(
            "No BEA API key found. Set the BEA_API_KEY environment variable or add "
            'a line  BEA_API_KEY = "your_key"  to api_keys.txt in the repo root '
            "(get a free key at https://apps.bea.gov/API/signup/)."
        )
    return key


def fetch_line(key: str, line_code: int) -> dict:
    params = {
        "UserID": key,
        "method": "GetData",
        "datasetname": "Regional",
        "TableName": "CAGDP1",
        "LineCode": line_code,
        "GeoFips": "COUNTY",
        "Year": YEARS,
        "ResultFormat": "JSON",
    }
    resp = requests.get(API_URL, params=params, timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("BEAAPI", {}).get("Results", {})
    if "Error" in results or "Data" not in results:
        sys.exit(f"BEA API error for LineCode {line_code}: {json.dumps(results)[:500]}")
    return payload


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    key = get_key()

    rows = []
    for lc in LINE_CODES:
        payload = fetch_line(key, lc)
        for rec in payload["BEAAPI"]["Results"]["Data"]:
            rec["LineCode"] = lc
            rows.append(rec)

    csv_path = RAW_DIR / "bea_cagdp1_county.csv"
    sum_path = RAW_DIR / "bea_cagdp1_county.sha256"

    fields = sorted({k for r in rows for k in r})
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with open(sum_path, "w") as f:
        f.write(f"{sha256(csv_path)}  {csv_path.name}\n")

    print(f"Wrote {len(rows)} rows to {csv_path.relative_to(ROOT)}")
    print(f"Checksums in {sum_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()