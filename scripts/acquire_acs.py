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

params = {
    "get": "NAME,B01003_001E",
    "for": "county:*",
    "in": "state:*",
    "key": API_KEY
}

# Send request
response = requests.get(url, params=params)

# Raise error if request failed or returned HTML error
response.raise_for_status()

# Convert Census response to JSON
data = response.json()

# Convert to pandas DataFrame
df = pd.DataFrame(data[1:], columns=data[0])
df["county_fips"] = df["state"] + df["county"]

print(df.head())
print("Number of rows:", len(df))

# Ensure the output directory exists so it doesn't error on a clean clone
os.makedirs("data/raw", exist_ok=True)

# Export raw dataset
output_path = "data/raw/acs_2024_county.csv"
df.to_csv(output_path, index=False)

print("ACS data saved to data/raw/acs_2024.csv")