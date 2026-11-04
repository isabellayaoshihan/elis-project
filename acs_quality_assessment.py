"""Assess the raw county-level 2024 ACS 5-year extract before integration."""

import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data/raw/acs_2024_county_full.csv"
REPORT_PATH = ROOT / "quality_assessment/acs_quality_report.txt"
CONTROLLED_MOE = "-555555555"
STATE_CODES = set("01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split())
TABLES = ("B01003", "B07001", "B07009", "B08301")


def load_raw():
    return pd.read_csv(RAW_PATH, dtype="string", keep_default_na=False)


def assess(raw):
    estimates = [name for name in raw if name.endswith("E") and name.startswith(TABLES)]
    margins = [name for name in raw if name.endswith("M") and name.startswith(TABLES)]
    if len(estimates) != 154 or {name[:-1] for name in estimates} != {name[:-1] for name in margins}:
        raise ValueError("Expected 154 paired estimate/MOE variables; review the input schema.")
    values = raw[estimates + margins]
    in_scope = raw["state"].isin(STATE_CODES)
    invalid_fips = (
        ~raw["state"].str.fullmatch(r"[0-9]{2}")
        | ~raw["county"].str.fullmatch(r"[0-9]{3}")
        | raw["county_fips"].ne(raw["state"] + raw["county"])
    )
    nonnumeric = values.apply(lambda column: ~column.str.fullmatch(r"-?[0-9]+")) & values.ne("")
    unexpected_negative = values.apply(lambda column: column.str.startswith("-"))
    controlled = raw[margins].eq(CONTROLLED_MOE)
    unexpected_negative[margins] &= ~controlled

    expected_hash = RAW_PATH.with_suffix(".sha256").read_text().split()[0]
    actual_hash = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
    counts = {
        "SHA-256 matches recorded checksum": actual_hash == expected_hash,
        "Raw county rows": len(raw),
        "Unknown state or territory rows": int((~raw["state"].isin(STATE_CODES | {"72"})).sum()),
        "Raw columns": len(raw.columns),
        "Estimate columns": len(estimates),
        "Margin-of-error columns": len(margins),
        "Duplicate full rows (additional occurrences)": int(raw.duplicated().sum()),
        "Duplicate FIPS (additional occurrences)": int(raw["county_fips"].duplicated().sum()),
        "Invalid or inconsistent FIPS rows": int(invalid_fips.sum()),
        "Blank county names": int(raw["NAME"].eq("").sum()),
        "Nonnumeric nonblank estimate/MOE cells": int(nonnumeric.sum().sum()),
        "Unexpected negative estimate/MOE cells": int(unexpected_negative.sum().sum()),
        "Puerto Rico rows": int(raw["state"].eq("72").sum()),
        "Rows in project scope (50 states and DC)": int(in_scope.sum()),
        "Blank estimate/MOE cells, all rows": int(values.eq("").sum().sum()),
        "Blank estimate/MOE cells, in scope": int(values.loc[in_scope].eq("").sum().sum()),
        "Controlled MOE codes, all rows": int(controlled.sum().sum()),
        "Controlled MOE codes, in scope": int(controlled.loc[in_scope].sum().sum()),
        "Connecticut planning-region rows": int(raw["state"].eq("09").sum()),
    }
    return in_scope, estimates, margins, counts


def main():
    raw = load_raw()
    in_scope, estimates, margins, counts = assess(raw)
    columns = estimates + margins
    profile = pd.DataFrame({
        "variable": columns,
        "raw_blank_cells": [int(raw[c].eq("").sum()) for c in columns],
        "in_scope_blank_cells": [int(raw.loc[in_scope, c].eq("").sum()) for c in columns],
        "in_scope_controlled_moe_cells": [int(raw.loc[in_scope, c].eq(CONTROLLED_MOE).sum()) for c in columns],
    })
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    profile.to_csv(REPORT_PATH.with_name("acs_column_quality.csv"), index=False)
    lines = [
        "ACS pre-integration data quality assessment",
        "Source: U.S. Census Bureau, 2024 ACS 5-Year Detailed Tables",
        "Input: data/raw/acs_2024_county_full.csv",
        f"Tables: {', '.join(TABLES)}",
        "",
        "Accuracy, completeness, and consistency",
        *(f"{label}: {value}" for label, value in counts.items()),
        "The checksum verifies file integrity. FIPS checks verify format and",
        "internal agreement. Individual estimates were not independently verified.",
        "",
        "Timeliness and interpretation",
        "The 2024 five-year release pools 2020–2024 responses. Mobility measures",
        "compare current residence with residence one year before the survey.",
        "",
        "Cleaning decisions and integration notes",
        "Exclude Puerto Rico per the project scope. Preserve all remaining county",
        "records and estimates. Export controlled MOE codes (-555555555) as blank",
        "because they are not numeric margins of error. Zero values are retained.",
        "Source note: https://www.census.gov/help/topics/faq.in-the-acs-data-products-i-see-a-controlled-estimate.html",
        "No reliability threshold was applied. Keep Connecticut planning-region",
        "FIPS for cross-source review. Read county_fips as text when joining.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
