
import os
import time
import requests
import pandas as pd

API_KEY = None

with open("api_keys.txt", "r") as f:
    for line in f:
        line = line.strip()

        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)

            if key.strip() == "CENSUS_API_KEY":
                API_KEY = value.strip().strip('"').strip("'")
                break

if not API_KEY:
    raise ValueError(
        "CENSUS_API_KEY not found in api_keys.txt"
    )

print("API key loaded successfully.")


BASE_URL = "https://api.census.gov/data/2024/acs/acs5"

TABLES = [
    "B01003",  # Total population
    "B07001",  # Geographical mobility by age
    "B07009",  # Geographical mobility by education
    "B08301"   # Means of transportation to work
]

OUTPUT_PATH = "data/raw/acs_2024_county_full.csv"

session = requests.Session()


def download_table(table):

    print(f"\nDownloading {table}...")

    params = {
        "get": f"NAME,group({table})",
        "for": "county:*",
        "in": "state:*",
        "key": API_KEY
    }

    response = session.get(
        BASE_URL,
        params=params,
        timeout=180
    )

    print("HTTP status:", response.status_code)

    # Census may redirect to an HTML error page
    if (
        "invalid_key.html" in response.url
        or "missing_key.html" in response.url
    ):
        raise RuntimeError(
            "Census API Key is invalid, missing, "
            "or not activated. Check your API key email."
        )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type", ""
    ).lower()

    if "json" not in content_type:
        raise RuntimeError(
            f"Census returned a non-JSON response "
            f"for table {table}.\n"
            f"Content-Type: {content_type}\n"
            f"Response preview: {response.text[:300]}"
        )

    try:
        data = response.json()
    except ValueError as error:
        raise RuntimeError(
            f"Unable to parse Census response "
            f"for table {table}."
        ) from error

    df = pd.DataFrame(
        data[1:],
        columns=data[0]
    )

    # Remove duplicate API columns
    df = df.loc[:, ~df.columns.duplicated()]

    # Create 5-digit county FIPS
    df["county_fips"] = (
        df["state"].str.zfill(2)
        + df["county"].str.zfill(3)
    )

    # Keep estimates and margins of error
    columns = ["county_fips"]

    if table == "B01003":
        columns += ["NAME", "state", "county"]

    columns += [
        col for col in df.columns
        if col.startswith(table + "_")
        and col.endswith(("E", "M"))
    ]

    df = df[columns]

    if df["county_fips"].duplicated().any():
        raise ValueError(
            f"Duplicate county FIPS detected in {table}"
        )

    print(
        f"Downloaded {table}: "
        f"{len(df)} counties, "
        f"{len(df.columns)} columns"
    )

    return df



merged = None

for table in TABLES:

    df = download_table(table)

    if merged is None:
        merged = df
    else:
        merged = merged.merge(
            df,
            on="county_fips",
            how="inner",
            validate="one_to_one"
        )

    time.sleep(1)


# ========================================
# 5. Validate Final Dataset
# ========================================

print("\n===== DATA VALIDATION =====")

print("Total counties:", len(merged))
print("Total columns:", len(merged.columns))

print(
    "Duplicate FIPS:",
    merged["county_fips"].duplicated().sum()
)

print(
    "Missing FIPS:",
    merged["county_fips"].isna().sum()
)

for table in TABLES:
    count = sum(
        col.startswith(table + "_")
        for col in merged.columns
    )
    print(f"{table} columns:", count)

if merged.empty:
    raise ValueError("Merged dataset is empty.")

if merged["county_fips"].duplicated().any():
    raise ValueError("Duplicate county FIPS in merged data.")


os.makedirs("data/raw", exist_ok=True)

merged.to_csv(
    OUTPUT_PATH,
    index=False
)

print("\n===== DOWNLOAD COMPLETE =====")

print("File saved:", OUTPUT_PATH)
print("Final shape:", merged.shape)

print("\nPreview:")
print(merged.iloc[:5, :8])
