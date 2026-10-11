import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests


# --------------------------------------------------
# Paths
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
KEY_FILE = ROOT / "api_keys.txt"

ACS_PATH = RAW_DIR / "acs_2024_county_full.csv"

OUTPUT_PATH = RAW_DIR / "bls_laus_2015_2024_annual.json"
CHECKSUM_PATH = RAW_DIR / "bls_laus_2015_2024_annual.sha256"


# --------------------------------------------------
# Read BLS API key
# --------------------------------------------------

def load_api_key(key_name):
    if not KEY_FILE.exists():
        raise FileNotFoundError("api_keys.txt was not found.")

    with open(KEY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            name, value = line.split("=", 1)

            if name.strip() == key_name:
                return value.strip().strip('"').strip("'")

    return None


BLS_API_KEY = load_api_key("BLS_API_KEY")

if not BLS_API_KEY:
    raise ValueError("BLS_API_KEY not found in api_keys.txt")

print("BLS API key loaded successfully.")


# --------------------------------------------------
# Read county FIPS codes from ACS data
# --------------------------------------------------

acs = pd.read_csv(
    ACS_PATH,
    dtype={"county_fips": "string"}
)

county_fips = (
    acs["county_fips"]
    .dropna()
    .str.zfill(5)
    .drop_duplicates()
    .sort_values()
    .tolist()
)

print(f"Number of counties: {len(county_fips)}")


# --------------------------------------------------
# Build BLS LAUS series IDs
# --------------------------------------------------

# LAUS measure codes:
# 03 = unemployment rate
# 04 = unemployment
# 05 = employment
# 06 = labor force

MEASURE_CODES = ["03", "04", "05", "06"]

series_ids = []

for fips in county_fips:
    for measure in MEASURE_CODES:
        series_id = f"LAUCN{fips}00000000{measure}"
        series_ids.append(series_id)

print(f"Total BLS series requested: {len(series_ids)}")


# --------------------------------------------------
# API settings
# --------------------------------------------------

START_YEAR = 2015
END_YEAR = 2024

EXPECTED_YEARS = {
    str(year)
    for year in range(START_YEAR, END_YEAR + 1)
}

API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

BATCH_SIZE = 50

print(f"Requested years: {START_YEAR}-{END_YEAR}")


# --------------------------------------------------
# Download data
# --------------------------------------------------

session = requests.Session()

all_responses = []

series_returned = 0
series_with_data = 0
series_without_data = 0

years_found = set()
annual_records_by_year = Counter()

total_batches = (
    len(series_ids) + BATCH_SIZE - 1
) // BATCH_SIZE


for batch_number, start in enumerate(
    range(0, len(series_ids), BATCH_SIZE),
    start=1
):

    batch = series_ids[start:start + BATCH_SIZE]

    print(
        f"Downloading batch {batch_number} "
        f"of {total_batches}..."
    )

    payload = {
        "seriesid": batch,
        "startyear": str(START_YEAR),
        "endyear": str(END_YEAR),
        "annualaverage": True,
        "registrationkey": BLS_API_KEY,
    }

    response = session.post(
        API_URL,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    result = response.json()

    if result.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(
            f"BLS API request failed: "
            f"{result.get('message')}"
        )

    returned_series = (
        result
        .get("Results", {})
        .get("series", [])
    )

    series_returned += len(returned_series)

    # --------------------------------------------------
    # KEEP ONLY M13 = ANNUAL AVERAGE
    # --------------------------------------------------

    annual_series = []

    for series in returned_series:

        annual_data = [
            observation
            for observation in series.get("data", [])
            if observation.get("period") == "M13"
        ]

        if annual_data:
            series_with_data += 1
        else:
            series_without_data += 1

        for observation in annual_data:

            year = observation.get("year")

            if year:
                years_found.add(year)
                annual_records_by_year[year] += 1

        annual_series.append(
            {
                "seriesID": series.get("seriesID"),
                "data": annual_data,
            }
        )

    # Save only annual-average observations,
    # rather than the monthly observations returned
    # by the API.

    filtered_response = {
        "status": result.get("status"),
        "responseTime": result.get("responseTime"),
        "message": result.get("message", []),
        "Results": {
            "series": annual_series
        },
    }

    all_responses.append(filtered_response)

    # Be polite to the API
    time.sleep(0.25)


# --------------------------------------------------
# Save annual-only JSON
# --------------------------------------------------

RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        all_responses,
        f,
        indent=2
    )

print("\nAnnual-average BLS data saved to:")
print(OUTPUT_PATH)


# --------------------------------------------------
# Validate downloaded data
# --------------------------------------------------

print("\n===== DATA VALIDATION =====")

print(f"Series requested: {len(series_ids)}")
print(f"Series returned: {series_returned}")
print(f"Series with annual data: {series_with_data}")
print(f"Series without annual data: {series_without_data}")

sorted_years = sorted(years_found)

print(f"Years found: {sorted_years}")

missing_years = EXPECTED_YEARS - years_found

if missing_years:
    raise ValueError(
        f"Missing requested years: "
        f"{sorted(missing_years)}"
    )

print(
    f"All requested years "
    f"{START_YEAR}-{END_YEAR} "
    f"appear in the annual data."
)

print("\nAnnual-average records by year:")

for year in sorted(
    annual_records_by_year.keys()
):
    print(
        year,
        annual_records_by_year[year]
    )


# --------------------------------------------------
# SHA-256 checksum
# --------------------------------------------------

sha256 = hashlib.sha256()

with open(OUTPUT_PATH, "rb") as f:
    for chunk in iter(
        lambda: f.read(1024 * 1024),
        b""
    ):
        sha256.update(chunk)

checksum = sha256.hexdigest()

with open(
    CHECKSUM_PATH,
    "w",
    encoding="utf-8"
) as f:
    f.write(
        f"{checksum}  "
        f"{OUTPUT_PATH.name}\n"
    )


# --------------------------------------------------
# Done
# --------------------------------------------------

print("\n===== DOWNLOAD COMPLETE =====")

print(f"Annual file: {OUTPUT_PATH}")
print(f"Checksum file: {CHECKSUM_PATH}")

print(
    f"BLS LAUS annual-average data "
    f"retained for {START_YEAR}-{END_YEAR}."
)