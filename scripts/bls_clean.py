
"""IS477 Milestone 3 - Step 2: BLS LAUS data cleaning.

Inputs:
    data/raw/bls_laus_2015_2024_annual.json
    data/raw/acs_2024_county_full.csv (assessment reference only)

Outputs (overwritten on successful completion):
    data/processed/bls_laus_clean.csv
    quality_assessment/bls_cleaning_report.txt

Run from repository root: python scripts/bls_clean.py

The raw inputs are never edited. No missing values are imputed.
"""

import hashlib
import os
import tempfile
from datetime import date

import pandas as pd

from bls_quality_assessment import (
    ROOT, YEARS, assess, read_acs_fips, read_bls
)


OUTPUT = ROOT / "data" / "processed" / "bls_laus_clean.csv"
REPORT = ROOT / "quality_assessment" / "bls_cleaning_report.txt"
RAW_PATH = ROOT / "data" / "raw" / "bls_laus_2015_2024_annual.json"

# Maintain the column names expected by the later integration workflow.
MEASURE_COLUMNS = {
    "03": "unemployment_rate",
    "04": "unemployed",
    "05": "employed",
    "06": "labor_force",
}
FINAL_COLUMNS = ["fips", "year", *MEASURE_COLUMNS.values()]
PRE_YEARS = range(2015, 2020)

# Geographic scope: the 50 states and Washington, DC (no territories).
STATE_FIPS = set(
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 "
    "22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 "
    "40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split()
)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cleaned(df, source_counties):
    """Fail before overwriting old outputs if cleaning broke an invariant."""
    if list(df.columns) != FINAL_COLUMNS:
        raise ValueError("Unexpected output columns or order.")
    if len(df) != len(source_counties) * len(YEARS):
        raise ValueError("Unexpected number of cleaned county-year rows.")
    if df.duplicated(["fips", "year"]).any():
        raise ValueError("Duplicate county-year keys in cleaned BLS data.")
    if not df["year"].isin(YEARS).all():
        raise ValueError("Unexpected year in cleaned BLS data.")
    if not df["fips"].str.fullmatch(r"\d{5}", na=False).all():
        raise ValueError("Invalid FIPS in cleaned BLS data.")
    if not df["fips"].str[:2].isin(STATE_FIPS).all():
        raise ValueError("Territory or out-of-scope FIPS in cleaned BLS data.")
    if set(df["fips"]) != set(source_counties):
        raise ValueError("Cleaned BLS FIPS differ from its in-scope raw FIPS.")

    for column in MEASURE_COLUMNS.values():
        number = df[column].dropna()
        if column == "unemployment_rate":
            valid = number.between(0, 100)
        elif column == "labor_force":
            valid = number.gt(0) & number.mod(1).eq(0)
        else:
            valid = number.ge(0) & number.mod(1).eq(0)
        if not valid.all():
            raise ValueError(f"Invalid nonmissing values in {column}.")


def write_csv_validated(frame, path):
    """Check an on-disk CSV round trip, then replace the previous CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", dir=path.parent,
            encoding="utf-8", newline="", delete=False
        ) as stream:
            temporary = stream.name
            frame.to_csv(stream, index=False, na_rep="")

        reloaded = pd.read_csv(temporary, dtype={"fips": "string"})
        if list(reloaded.columns) != FINAL_COLUMNS or len(reloaded) != len(frame):
            raise ValueError("CSV round-trip changed the schema or row count.")
        if not reloaded["fips"].astype(str).equals(frame["fips"].astype(str)):
            raise ValueError("CSV round-trip changed county FIPS strings.")
        if not reloaded["year"].equals(frame["year"]):
            raise ValueError("CSV round-trip changed year values.")
        for column in MEASURE_COLUMNS.values():
            pd.testing.assert_series_equal(
                reloaded[column].astype("float64"),
                frame[column].astype("float64"),
                check_names=False, rtol=1e-12, atol=1e-10
            )
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def make_report(stats):
    """One reproducible audit trail linking assessment issues to cleaning."""
    width = 78
    lines = [
        "=" * width,
        "BLS LAUS | DATA CLEANING AND VALIDATION".center(width),
        "=" * width,
        f"Assessment date: {date.today().isoformat()}",
        "Study area: 50 states and Washington, DC (territories excluded)",
        "Study years: 2015-2024 | Predictor window: 2015-2019",
        "",
    ]

    def section(title):
        lines.extend([title, "-" * width])

    def row(label, number):
        lines.append(f"  {label:<55} {number:>15,}")

    section("01  SOURCE RECORD DISPOSITION")
    row("Original raw BLS observations", stats["raw_rows"])
    row("Raw distinct BLS county FIPS (including Puerto Rico)", stats["raw_fips"])
    row("Raw distinct Puerto Rico FIPS", stats["pr_fips"])
    row("Excluded observations (unique rows)", stats["excluded_rows"])
    row("  Puerto Rico observations", stats["pr_rows"])
    row("  Other out-of-scope state/territory observations", stats["other_area_rows"])
    row("  Structurally invalid or nonannual observations", stats["structure_rows"])
    row("In-scope observations before deduplication", stats["in_scope_rows"])
    row("Exact duplicate observations removed", stats["duplicates_removed"])
    row("Conflicting duplicate keys remaining", 0)
    row("Unique in-scope source observations", stats["unique_rows"])
    lines.extend(["", "Exclusion-reason counts can overlap; total excluded counts rows once.", ""])

    section("02  HANDLING OF MISSING AND INVALID VALUES")
    row("Blank or null values retained as NA", stats["blank"])
    row("Recognized missing markers retained as NA", stats["markers"])
    row("Invalid numeric values converted to NA", stats["bad_numeric"])
    row("Other nonnumeric text remaining", 0)
    lines.extend([
        "", "Missing markers (e.g., '-') are not zeros. No values were imputed.",
        "Only in-scope records are included in the counts above.", ""
    ])

    section("03  RESHAPING AND COUNTY-YEAR COVERAGE")
    row("BLS-observed county FIPS retained", stats["counties"])
    row("Observed county-year rows before reindexing", stats["observed_pairs"])
    row("All-NA county-year placeholder rows added", stats["placeholder_rows"])
    row("Final cleaned county-year rows", stats["output_rows"])
    row("ACS-only FIPS deliberately NOT added", stats["acs_only"])
    lines.extend([
        "", "One output row per BLS-observed county and year.",
        "Placeholders preserve absent years but do not create BLS estimates.",
        "Geographic mismatches are handled later during integration.",
    ])
    if stats["acs_only_fips"]:
        lines.append("  ACS-only FIPS not added: " + ", ".join(stats["acs_only_fips"]))
    if stats["placeholder_details"]:
        lines.append("  Missing-year placeholders (FIPS: years):")
        for fips, years in stats["placeholder_details"].items():
            lines.append(f"    {fips}: {', '.join(str(y) for y in years)}")
    lines.append("")

    section("04  RESEARCH READINESS | 2015-2019")
    row("Expected BLS-footprint county-year rates", stats["pre_expected"])
    row("Usable nonmissing unemployment rates", stats["pre_usable"])
    row("Missing annual unemployment rates", stats["pre_missing"])
    row("Counties with all five usable annual rates", stats["complete_counties"])
    lines.extend([
        "", "Rates are preserved as published; no five-year means calculated here.",
        "Historical boundary differences require review before integration.", ""
    ])

    section("05  POST-CLEANING VALIDATION AND PROVENANCE")
    lines.extend([
        "  County-year keys unique: PASS",
        "  Year/FIPS format and study scope: PASS",
        "  Numeric range/whole-person checks: PASS",
        "  Expected row and column counts: PASS",
        "  CSV round-trip value comparison: PASS",
        "  Original BLS JSON was not modified.",
        "",
        f"  Input: data/raw/{RAW_PATH.name}",
        f"  SHA-256: {stats['raw_sha256']}",
        "  Script: scripts/bls_clean.py",
        "  Output: data/processed/bls_laus_clean.csv",
        "  Report: quality_assessment/bls_cleaning_report.txt",
        "  Read cleaned CSV with dtype={'fips': 'string'} to keep leading zeros.",
        "",
        "=" * width,
        "END OF CLEANING REPORT".center(width),
        "=" * width,
    ])
    return "\n".join(lines) + "\n"


def main():
    # 1. Reuse the same extraction and screening rules as pre-integration QA.
    raw_hash_before = file_sha256(RAW_PATH)
    raw, statuses = read_bls()
    if any(status != "REQUEST_SUCCEEDED" for status in statuses):
        raise ValueError("One or more BLS API response batches were not successful.")
    acs_counties, _ = read_acs_fips()
    assessment = assess(raw, acs_counties)
    df = assessment["df"].copy()

    # 2. Select only structurally valid, annual, in-scope BLS records.
    structural_flags = [
        "invalid_fips", "invalid_series", "invalid_year",
        "invalid_measure", "not_annual"
    ]
    bad_structure = df[structural_flags].any(axis=1)
    in_area = df["fips"].str[:2].isin(STATE_FIPS)
    excluded = bad_structure | ~in_area
    clean = df.loc[~excluded].copy()

    if clean.empty:
        raise ValueError("No valid, in-scope BLS observations remain.")

    # 3. Reject unexpected nonnumeric strings rather than silently erase them.
    unknown = clean.loc[clean["unparseable_value"]]
    if not unknown.empty:
        raise ValueError(
            "Unexpected numeric text needs review:\n"
            + unknown[["fips", "year_raw", "measure", "value_raw"]]
            .head(10).to_string(index=False)
        )

    # 4. Remove exact duplicates, then refuse conflicting duplicate keys.
    # Preserve the original text during this test; recoding invalid values
    # before deduplication could make different observations look identical.
    before = len(clean)
    clean = clean.drop_duplicates(
        ["fips", "year", "measure", "value_raw"],
        keep="first"
    ).copy()
    duplicates_removed = before - len(clean)

    conflicts = clean.duplicated(
        ["fips", "year", "measure"], keep=False
    )
    if conflicts.any():
        raise ValueError(
            "Conflicting BLS observations for one county-year-measure:\n"
            + clean.loc[conflicts,
                        ["fips", "year", "measure", "value_raw"]]
            .head(12).to_string(index=False)
        )

    # 5. Keep missing markers as NA; invalidate impossible numeric values.
    blank = int(clean["empty_value"].sum())
    markers = int(clean["missing_marker"].sum())
    bad_numeric = int(clean["invalid_numeric"].sum())
    clean["value"] = clean["value"].mask(clean["invalid_numeric"])
    clean["year"] = clean["year"].astype(int)

    # 6. Pivot the four measures into the stable cleaned CSV schema.
    wide = clean.pivot(
        index=["fips", "year"], columns="measure", values="value"
    ).reindex(columns=list(MEASURE_COLUMNS))
    wide = wide.rename(columns=MEASURE_COLUMNS)
    observed_pairs = len(wide)

    # 7. Add only missing YEARS for county FIPS that actually appear in BLS.
    # Do NOT union with the ACS list: this would invent a blank BLS county.
    counties = sorted(clean["fips"].unique())
    full_index = pd.MultiIndex.from_product(
        [counties, YEARS], names=["fips", "year"]
    )
    wide = wide.reindex(full_index).reset_index()
    wide["year"] = wide["year"].astype(int)
    wide = wide[FINAL_COLUMNS].sort_values(
        ["fips", "year"], kind="stable"
    ).reset_index(drop=True)
    wide.columns.name = None
    placeholder_rows = len(wide) - observed_pairs
    original_pairs = set(zip(clean["fips"], clean["year"]))
    missing_pairs = [(f, y) for f in counties for y in YEARS if (f, y) not in original_pairs]
    placeholder_details = {}
    for fips, year in missing_pairs:
        placeholder_details.setdefault(fips, []).append(year)
    if len(missing_pairs) != placeholder_rows:
        raise ValueError("Placeholder row count does not reconcile.")

    # 8. Check that pivot/reindex preserved every nonmissing observation.
    for code, column in MEASURE_COLUMNS.items():
        source_nonmissing = int(
            clean.loc[clean["measure"].eq(code), "value"].notna().sum()
        )
        output_nonmissing = int(wide[column].notna().sum())
        if source_nonmissing != output_nonmissing:
            raise ValueError(f"Lost or duplicated valid {column} values.")

    validate_cleaned(wide, counties)

    pre = wide.loc[wide["year"].isin(PRE_YEARS)]
    pre_usable = int(pre["unemployment_rate"].notna().sum())
    pre_missing = int(pre["unemployment_rate"].isna().sum())
    complete_counties = int(
        pre.groupby("fips")["unemployment_rate"]
        .count().eq(len(PRE_YEARS)).sum()
    )

    stats = {
        "raw_rows": len(df),
        "raw_fips": df["fips"].nunique(),
        "pr_fips": df.loc[df["puerto_rico"], "fips"].nunique(),
        "excluded_rows": int(excluded.sum()),
        "pr_rows": int(df["fips"].str.startswith("72", na=False).sum()),
        "other_area_rows": int((~in_area & ~df["fips"].str.startswith("72", na=False)).sum()),
        "structure_rows": int(bad_structure.sum()),
        "in_scope_rows": before,
        "duplicates_removed": duplicates_removed,
        "unique_rows": len(clean),
        "blank": blank,
        "markers": markers,
        "bad_numeric": bad_numeric,
        "counties": len(counties),
        "observed_pairs": observed_pairs,
        "placeholder_rows": placeholder_rows,
        "output_rows": len(wide),
        "acs_only": len(acs_counties - set(counties)),
        "acs_only_fips": sorted(acs_counties - set(counties))[:15],
        "placeholder_details": placeholder_details,
        "pre_expected": len(pre),
        "pre_usable": pre_usable,
        "pre_missing": pre_missing,
        "complete_counties": complete_counties,
        "raw_sha256": raw_hash_before,
    }
    if file_sha256(RAW_PATH) != raw_hash_before:
        raise RuntimeError("Raw BLS input changed during the cleaning run.")

    # 9. Write a validated CSV and a matching human-readable audit trail.
    report = make_report(stats)
    write_csv_validated(wide, OUTPUT)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved: {OUTPUT.relative_to(ROOT)}")
    print(f"Saved: {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
