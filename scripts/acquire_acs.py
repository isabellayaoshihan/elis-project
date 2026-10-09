import os
import requests
import pandas as pd

# Read and sanitize Census API key from api_keys.txt
API_KEY = None
with open("api_keys.txt", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            # Remove whitespace, double quotes, and single quotes from value
            API_KEY = val.strip().strip('"').strip("'").strip()
            break

# Debug print to verify there are no surrounding quotes or whitespace
print("Loaded API key:", repr(API_KEY))

# Census ACS 2024 5-Year API
url = "https://api.census.gov/data/2024/acs/acs5"

tables = ["B01003", "B07001", "B07009", "B08301"]

merged = None

for table in tables:
    params = {
        "get": f"NAME,group({table})",
        "for": "county:*",
        "in": "state:*",
        "key": API_KEY
    }

    response = requests.get(url, params=params, timeout=120)
    response.raise_for_status()

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])

    df = df.loc[:, ~df.columns.duplicated()]
    df["county_fips"] = df["state"] + df["county"]

    # Keep estimates, margins of error, and identifiers
    keep = ["county_fips"]

    if merged is None:
        keep += ["NAME", "state", "county"]

    keep += [
        col for col in df.columns
        if col.startswith(table + "_")
        and col.endswith(("E", "M"))
    ]

    df = df[keep]

    if merged is None:
        merged = df
    else:
        merged = merged.merge(df, on="county_fips", how="inner")

    print(f"Downloaded {table}: {len(df)} counties")

os.makedirs("data/raw", exist_ok=True)

merged.to_csv(
    "data/raw/acs_2024_county_full.csv",
    index=False
)

print("Total counties:", len(merged))
print("Total columns:", len(merged.columns))
