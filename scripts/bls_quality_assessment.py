
"""IS477 Milestone 3 — BLS pre-integration data quality assessment."""

import json
from pathlib import Path
import pandas as pd

# File paths
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
RESULTS = ROOT / "quality_assessment"

BLS_PATH = RAW_DIR / "bls_laus_2015_2024_annual.json"
ACS_PATH = RAW_DIR / "acs_2024_county_full.csv"

YEARS = range(2015, 2025)
MEASURES = {
    "03": "unemployment_rate",
    "04": "unemployed",
    "05": "employed",
    "06": "labor_force"
}


def load_records():
    # Load original BLS JSON
    with open(BLS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []

    # Extract observations from BLS API responses
    def visit(obj, series_id=None):
        if isinstance(obj, list):
            for item in obj:
                visit(item, series_id)
            return

        if not isinstance(obj, dict):
            return

        sid = obj.get("seriesID") or series_id

        if "year" in obj and "value" in obj:
            rows.append({
                "series_id": str(sid or ""),
                "year": obj["year"],
                "period": obj.get("period"),
                "value_raw": obj["value"]
            })
            return

        for key in ("Results", "series", "data"):
            if key in obj:
                visit(obj[key], sid)

    visit(raw)

    if not rows:
        raise ValueError("No BLS observations found.")

    df = pd.DataFrame(rows)

    # Extract FIPS and measure codes
    df["fips"] = df["series_id"].str[5:10]
    df["measure"] = df["series_id"].str[-2:]

    # Convert values for assessment
    df["year"] = pd.to_numeric(
        df["year"], errors="coerce"
    )

    df["value"] = pd.to_numeric(
        df["value_raw"].astype(str)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce"
    )

    return df, BLS_PATH


def assess(df):
    df = df.copy()

    # 1. Validate FIPS and series identifiers
    df["invalid_fips"] = (
        ~df["fips"].str.fullmatch(r"\d{5}", na=False)
        | df["fips"].eq("00000")
    )

    df["invalid_series_id"] = ~df["series_id"].str.fullmatch(
        r"LAUCN\d{5}0{8}(03|04|05|06)",
        na=False
    )

    # 2. Check year, measure, and annual-average period
    df["invalid_year"] = ~df["year"].isin(YEARS)
    df["invalid_measure"] = ~df["measure"].isin(MEASURES)
    df["not_annual"] = ~df["period"].eq("M13").fillna(False)

    # 3. Identify missing numerical values
    df["missing_value"] = df["value"].isna()

    # 4. Identify invalid numerical values
    df["invalid_value"] = (
        (
            (df["measure"] == "03")
            & df["value"].notna()
            & ~df["value"].between(0, 100)
        )
        | (
            df["measure"].isin(["04", "05", "06"])
            & (df["value"] < 0)
        )
    )

    # 5. Identify Puerto Rico observations
    df["puerto_rico"] = df["fips"].str.startswith("72")

    # 6. Check duplicate county-year-measure keys
    key_flags = [
        "invalid_fips",
        "invalid_series_id",
        "invalid_year",
        "invalid_measure",
        "not_annual"
    ]

    key_ok = ~df[key_flags].any(axis=1)

    df["duplicate_key"] = False
    df.loc[key_ok, "duplicate_key"] = df.loc[
        key_ok
    ].duplicated(
        ["fips", "year", "measure"],
        keep=False
    )

    # 7. Compare geographic coverage with ACS
    acs = pd.read_csv(
        ACS_PATH,
        dtype={"county_fips": "string"}
    )

    acs_fips = (
        acs["county_fips"]
        .dropna()
        .str.strip()
        .str.zfill(5)
    )

    counties = sorted(
        acs_fips[
            acs_fips.str.fullmatch(r"\d{5}", na=False)
            & ~acs_fips.str.startswith("72")
        ].unique()
    )

    df["not_in_acs"] = (
        ~df["fips"].isin(counties)
        & ~df["puerto_rico"]
        & ~df["invalid_fips"]
    )

    # 8. Identify missing county-year-measure records
    valid = df.loc[
        key_ok & ~df["puerto_rico"]
    ].copy()

    actual = valid[
        ["fips", "year", "measure"]
    ].drop_duplicates()

    expected = pd.MultiIndex.from_product(
        [counties, YEARS, MEASURES],
        names=["fips", "year", "measure"]
    ).to_frame(index=False)

    missing = expected.merge(
        actual,
        on=["fips", "year", "measure"],
        how="left",
        indicator=True
    )

    missing = missing.loc[
        missing["_merge"] == "left_only",
        ["fips", "year", "measure"]
    ].copy()

    # 9. Check missing unemployment rates for 2015-2019
    pre_expected = pd.MultiIndex.from_product(
        [counties, range(2015, 2020)],
        names=["fips", "year"]
    ).to_frame(index=False)

    available_rates = valid.loc[
        (valid["measure"] == "03")
        & valid["value"].notna()
        & ~valid["invalid_value"],
        ["fips", "year"]
    ].drop_duplicates()

    pre_missing = pre_expected.merge(
        available_rates,
        on=["fips", "year"],
        how="left",
        indicator=True
    )

    pre_missing = pre_missing.loc[
        pre_missing["_merge"] == "left_only"
    ]

    # Collect quality flags
    flags = [
        "invalid_fips",
        "invalid_series_id",
        "invalid_year",
        "invalid_measure",
        "not_annual",
        "missing_value",
        "invalid_value",
        "duplicate_key",
        "puerto_rico",
        "not_in_acs"
    ]

    # Additional summary statistics
    summary = {
        "expected_counties": len(counties),
        "missing_counties": len(
            set(counties) - set(valid["fips"])
        ),
        "missing_pre2020_rates": len(pre_missing),
        "counties_incomplete_pre2020": pre_missing["fips"].nunique(),
        "missing_by_year": missing.groupby("year").size(),
        "missing_values_by_measure": valid.loc[
            valid["missing_value"]
        ].groupby("measure").size()
    }

    return df, missing, flags, summary


def main():
    # Load and assess BLS data
    df, source = load_records()
    assessed, missing, flags, summary = assess(df)

    RESULTS.mkdir(parents=True, exist_ok=True)

    # Overall assessment results
    lines = [
        "BLS LAUS PRE-INTEGRATION QUALITY ASSESSMENT",
        "",
        f"Source: {source.name}",
        f"Total observations: {len(df):,}",
        f"Unique county FIPS: {df['fips'].nunique():,}",
        f"Expected ACS counties (excluding Puerto Rico): "
        f"{summary['expected_counties']:,}",
        f"Observed years: "
        f"{sorted(df['year'].dropna().astype(int).unique())}",
        "",
        "QUALITY CHECKS (counts may overlap)"
    ]

    for flag in flags:
        lines.append(
            f"{flag}: {int(assessed[flag].sum()):,}"
        )

    # Missing records and county coverage
    lines.extend([
        "",
        "MISSING RECORDS AND GEOGRAPHIC COVERAGE",
        f"Missing county-year-measure records: {len(missing):,}",
        f"Counties entirely missing from BLS: "
        f"{summary['missing_counties']:,}",
        "",
        "Missing records by year:"
    ])

    for year in YEARS:
        count = summary["missing_by_year"].get(year, 0)
        lines.append(f"  {year}: {count:,}")

    # Missing values by measure
    lines.extend([
        "",
        "MISSING NUMERICAL VALUES BY MEASURE"
    ])

    for code, name in MEASURES.items():
        count = summary["missing_values_by_measure"].get(code, 0)
        lines.append(f"  {name}: {count:,}")

    # Research-specific completeness
    lines.extend([
        "",
        "PRE-2020 UNEMPLOYMENT RATE COVERAGE",
        f"Missing or unusable 2015-2019 county-year rates: "
        f"{summary['missing_pre2020_rates']:,}",
        f"Counties with incomplete 2015-2019 rates: "
        f"{summary['counties_incomplete_pre2020']:,}",
        "",
        "NOTES",
        "Expected geographic coverage is based on ACS 2024.",
        "Puerto Rico is identified for exclusion during cleaning.",
        "Missing records may reflect geographic or historical differences.",
        "Missing and invalid numerical values are assessed separately.",
        "Arithmetic consistency checks require separate validation.",
        "No raw data were modified."
    ])

    report = "\n".join(lines)

    # Save only one quality assessment report
    (RESULTS / "bls_quality_report.txt").write_text(
        report + "\n",
        encoding="utf-8"
    )

    print(report)
    print("\nSaved quality_assessment/bls_quality_report.txt")


if __name__ == "__main__":
    main()
