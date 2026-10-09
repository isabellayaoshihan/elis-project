import os
import json
import time
import requests
import pandas as pd


# ---------------------------------------------------------
# 1. Read BLS API key from api_keys.txt
# ---------------------------------------------------------

BLS_API_KEY = None

with open("api_keys.txt", "r") as f:
    for line in f:
        line = line.strip()

        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)

            if key.strip() == "BLS_API_KEY":
                BLS_API_KEY = val.strip().strip('"').strip("'")
                break

if BLS_API_KEY is None:
    raise ValueError("BLS_API_KEY not found in api_keys.txt")


# ---------------------------------------------------------
# 2. Get county FIPS codes from the ACS raw dataset
# ---------------------------------------------------------

acs = pd.read_csv(
    "data/raw/acs_2024_county_full.csv",
    dtype={"county_fips": str}
)

county_fips = (
    acs["county_fips"]
    .str.zfill(5)
    .drop_duplicates()
    .tolist()
)

print("Number of counties:", len(county_fips))


# ---------------------------------------------------------
# 3. Define BLS LAUS measures
# ---------------------------------------------------------

# 03 = unemployment rate
# 04 = unemployment
# 05 = employment
# 06 = labor force

measure_codes = [
    "03",
    "04",
    "05",
    "06"
]


# ---------------------------------------------------------
# 4. Construct BLS LAUS series IDs
# ---------------------------------------------------------

series_ids = []

for fips in county_fips:
    for measure in measure_codes:

        series_id = (
            "LAUCN"
            + fips
            + "00000000"
            + measure
        )

        series_ids.append(series_id)

print("Total BLS series requested:", len(series_ids))


# ---------------------------------------------------------
# 5. Request 2024 data from the BLS API
# ---------------------------------------------------------

url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

batch_size = 50

all_responses = []

total_batches = (
    len(series_ids) + batch_size - 1
) // batch_size


for start in range(0, len(series_ids), batch_size):

    batch = series_ids[start:start + batch_size]

    batch_number = start // batch_size + 1

    print(
        f"Downloading batch "
        f"{batch_number} of {total_batches}..."
    )

    payload = {
        "seriesid": batch,
        "startyear": "2024",
        "endyear": "2024",
        "annualaverage": True,
        "registrationkey": BLS_API_KEY
    }

    response = requests.post(
        url,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    result = response.json()

    if result.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(
            f"BLS API request failed: {result.get('message')}"
        )

    all_responses.append(result)

    # Brief pause between API requests
    time.sleep(0.25)


# ---------------------------------------------------------
# 6. Save raw BLS API responses
# ---------------------------------------------------------

os.makedirs("data/raw", exist_ok=True)

output_path = "data/raw/bls_laus_2024_raw.json"

with open(output_path, "w") as f:
    json.dump(
        all_responses,
        f,
        indent=2
    )


# ---------------------------------------------------------
# 7. Basic validation
# ---------------------------------------------------------

series_returned = 0

for result in all_responses:
    series_returned += len(
        result["Results"]["series"]
    )

print("\nBLS download complete.")
print("Saved to:", output_path)
print("Series returned:", series_returned)