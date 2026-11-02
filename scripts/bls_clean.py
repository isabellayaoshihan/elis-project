
"""IS477 Milestone 3 — Step 2: BLS LAUS data cleaning."""

import pandas as pd

from bls_quality_assessment import (
    ROOT, ACS_PATH, MEASURES, YEARS, assess, load_records
)


def main():
    # Load and assess original BLS data
    raw, _ = load_records()
    df, _, _, summary = assess(raw)

    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Remove invalid and out-of-scope records
    exclude_flags = [
        "invalid_fips",
        "invalid_series_id",
        "invalid_year",
        "invalid_measure",
        "not_annual",
        "puerto_rico"
    ]

    excluded = df[exclude_flags].any(axis=1)
    clean = df.loc[~excluded].copy()

    # 2. Preserve missing values and replace invalid values with NA
    missing_count = int(clean["missing_value"].sum())
    invalid_count = int(clean["invalid_value"].sum())

    clean.loc[clean["invalid_value"], "value"] = float("nan")

    # 3. Remove identical duplicate observations
    before = len(clean)

    clean = clean.drop_duplicates(
        ["fips", "year", "measure", "value"]
    )

    duplicates_removed = before - len(clean)

    # 4. Check for conflicting duplicates
    conflicts = clean.loc[
        clean.duplicated(
            ["fips", "year", "measure"],
            keep=False
        )
    ]

    if not conflicts.empty:
        print(conflicts[
            ["fips", "year", "measure", "value"]
        ].head(10))

        raise ValueError(
            "Conflicting duplicate records found. "
            "Review before cleaning."
        )

    if clean.empty:
        raise ValueError("No valid BLS records remain.")

    # 5. Reshape the four measures into separate columns
    wide = clean.pivot(
        index=["fips", "year"],
        columns="measure",
        values="value"
    )

    wide = wide.reindex(columns=list(MEASURES))
    wide = wide.rename(columns=MEASURES)

    # 6. Use ACS as the reference for expected county coverage
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

    acs_fips = acs_fips[
        acs_fips.str.fullmatch(r"\d{5}", na=False)
        & ~acs_fips.str.startswith("72")
        & acs_fips.ne("00000")
    ]

    # Retain counties appearing in either ACS or BLS
    bls_counties = wide.index.get_level_values("fips").unique()
    counties = sorted(set(acs_fips) | set(bls_counties))

    # 7. Preserve missing county-year combinations as NA
    full_index = pd.MultiIndex.from_product(
        [counties, YEARS],
        names=["fips", "year"]
    )

    wide = wide.reindex(full_index).reset_index()
    wide["year"] = wide["year"].astype(int)

    # 8. Validate cleaned dataset
    assert not wide.duplicated(["fips", "year"]).any()
    assert wide["year"].isin(YEARS).all()
    assert wide["fips"].str.fullmatch(r"\d{5}").all()
    assert not wide["fips"].str.startswith("72").any()

    # 9. Save only the cleaned dataset
    output_path = out_dir / "bls_laus_clean.csv"

    wide.to_csv(
        output_path,
        index=False
    )

    # 10. Display cleaning summary
    print("\nBLS LAUS DATA CLEANING SUMMARY")
    print(f"Original observations: {len(raw):,}")
    print(f"Excluded observations: {int(excluded.sum()):,}")
    print(f"Puerto Rico observations: {int(df['puerto_rico'].sum()):,}")
    print(f"Original missing values retained: {missing_count:,}")
    print(f"Invalid values set to NA: {invalid_count:,}")
    print(f"Identical duplicates removed: {duplicates_removed:,}")
    print(f"Conflicting duplicates: {len(conflicts):,}")
    print(f"Counties retained: {len(counties):,}")
    print(f"Cleaned county-year rows: {len(wide):,}")
    print(f"Missing 2015-2019 unemployment rates in assessment: "
          f"{summary['missing_pre2020_rates']:,}")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
