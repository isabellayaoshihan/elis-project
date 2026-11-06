"""IS477 Milestone 3: BLS LAUS pre-integration data quality assessment.

Assess the original BLS JSON without cleaning or modifying it.
The 2024 ACS county FIPS list is used only as a geographic coverage reference.

Output: quality_assessment/bls_quality_assessment.txt
Run: python scripts/bls_quality_assessment.py
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
RESULTS_DIR = ROOT / "quality_assessment"

BLS_PATH = RAW_DIR / "bls_laus_2015_2024_annual.json"
ACS_PATH = RAW_DIR / "acs_2024_county_full.csv"

YEARS = tuple(range(2015, 2025))
PRE_YEARS = tuple(range(2015, 2020))
MEASURES = {
    "03": "unemployment_rate",
    "04": "unemployed",
    "05": "employed",
    "06": "labor_force",
}

# Screening tolerances, not official BLS error thresholds.
LABOR_FORCE_TOL = 2          # Persons, allowing for rounding of annual averages
RATE_TOL_PP = 0.15           # Percentage points, plus rounding of count inputs
SAMPLE_SIZE = 5


def file_sha256(path):
    """Document the exact input snapshot without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bls():
    """Read BLS API response batches into a diagnostic long-form table."""
    with BLS_PATH.open("r", encoding="utf-8") as stream:
        raw = json.load(stream)

    rows = []
    api_statuses = []

    def visit(obj, series_id=None):
        if isinstance(obj, list):
            for item in obj:
                visit(item, series_id)
            return
        if not isinstance(obj, dict):
            return

        if isinstance(obj.get("status"), str) and obj["status"].startswith("REQUEST_"):
            api_statuses.append(obj["status"])

        sid = obj.get("seriesID") or obj.get("seriesId") or series_id

        # Include an observation even when the value field is absent.
        if "year" in obj and ("period" in obj or "value" in obj):
            rows.append({
                "series_id": str(sid or "").strip(),
                "year_raw": obj.get("year"),
                "period": obj.get("period"),
                "value_raw": obj.get("value"),
            })
            return

        for key in ("Results", "results", "series", "data", "responses"):
            if key in obj:
                visit(obj[key], sid)

    visit(raw)

    if not rows:
        raise ValueError("No BLS data records found. Check the raw JSON structure.")

    df = pd.DataFrame(rows)

    # Extract county FIPS and measure codes.
    df["fips"] = df["series_id"].str[5:10]
    df["measure"] = df["series_id"].str[-2:]

    # Convert values for assessment without changing the raw file.
    df["year"] = pd.to_numeric(df["year_raw"], errors="coerce")
    df["period"] = df["period"].astype("string").str.strip()

    text = df["value_raw"].astype("string").str.strip()

    df["missing_value"] = (text.isna() | text.eq("")).fillna(False)

    df["value"] = pd.to_numeric(
        text.str.replace(",", "", regex=False),
        errors="coerce"
    )

    df["non_numeric_value"] = ~df["missing_value"] & df["value"].isna()

    df.attrs["api_statuses"] = api_statuses

    return df


def load_acs_counties():
    """Use ACS geography to assess join feasibility; this is NOT integration."""
    acs = pd.read_csv(
        ACS_PATH,
        usecols=["county_fips"],
        dtype="string"
    )

    fips = acs["county_fips"].str.strip().str.zfill(5)

    valid = (
        fips.str.fullmatch(r"\d{5}", na=False)
        & fips.ne("00000")
    )

    outside_pr = ~fips.str.startswith("72", na=False)

    counties = sorted(
        fips.loc[valid & outside_pr].dropna().unique()
    )

    if not counties:
        raise ValueError("No valid non-Puerto Rico county FIPS found in ACS.")

    return counties, {
        "acs_rows": len(acs),
        "invalid_acs_fips": int((~valid).sum()),
        "duplicate_acs_fips": int(fips.loc[valid].duplicated().sum()),
    }


def assess(df, counties):
    """Return row-level flags, completeness gaps, and arithmetic diagnostics."""
    df = df.copy()

    # ==========================================================
    # 1. ACCURACY: CODE AND VALUE VALIDITY
    # ==========================================================

    # Check county FIPS format.
    df["invalid_fips"] = (
        ~df["fips"].str.fullmatch(r"\d{5}", na=False)
        | df["fips"].eq("00000")
    )

    # Check BLS LAUS county series identifier.
    df["invalid_series_id"] = ~df["series_id"].str.fullmatch(
        r"LAUCN\d{5}0{8}(03|04|05|06)",
        na=False
    )

    # Validate years, measure codes and annual-average periods.
    df["invalid_year"] = ~df["year"].isin(YEARS)

    df["invalid_measure"] = ~df["measure"].isin(MEASURES)

    df["not_annual"] = ~df["period"].eq("M13").fillna(False)

    # Flag Puerto Rico, which is outside the study scope.
    df["puerto_rico"] = df["fips"].str.startswith("72", na=False)

    # Validate numerical values.
    is_rate = df["measure"].eq("03")
    is_count = df["measure"].isin(("04", "05", "06"))
    is_labor_force = df["measure"].eq("06")

    number = df["value"]

    df["invalid_value"] = (
        # Unemployment rate must be between 0 and 100.
        (is_rate & number.notna() & ~number.between(0, 100))

        # Employment-related counts cannot be negative.
        | (is_count & number.notna() & (number < 0))

        # Labor force denominator cannot be zero.
        | (is_labor_force & number.notna() & (number == 0))

        # Published counts should be whole numbers.
        | (is_count & number.notna() & number.mod(1).ne(0))

        # Reject infinite values.
        | number.isin((float("inf"), float("-inf")))
    )

    # ==========================================================
    # 2. CONSISTENCY: DUPLICATE KEYS
    # ==========================================================

    key_flags = [
        "invalid_fips",
        "invalid_series_id",
        "invalid_year",
        "invalid_measure",
        "not_annual",
    ]

    key_ok = ~df[key_flags].any(axis=1)

    df["duplicate_key"] = False

    df.loc[key_ok, "duplicate_key"] = df.loc[key_ok].duplicated(
        ["fips", "year", "measure"],
        keep=False
    )

    # ==========================================================
    # 3. GEOGRAPHIC COMPATIBILITY WITH ACS
    # ==========================================================

    # Flag geographic mismatches but do not exclude or remap them.
    df["not_in_acs"] = (
        ~df["fips"].isin(counties)
        & ~df["puerto_rico"]
        & ~df["invalid_fips"]
    )

    # ==========================================================
    # 4. COMPLETENESS: COUNTY-YEAR-MEASURE RECORDS
    # ==========================================================

    # Identify observed structurally valid annual records.
    observed_keys = df.loc[
        key_ok & ~df["puerto_rico"],
        ["fips", "year", "measure"]
    ].drop_duplicates()

    # Expected records based on ACS 2024 county geography.
    expected = pd.MultiIndex.from_product(
        [counties, YEARS, list(MEASURES)],
        names=["fips", "year", "measure"],
    ).to_frame(index=False)

    missing = expected.merge(
        observed_keys,
        on=["fips", "year", "measure"],
        how="left",
        indicator=True,
    )

    missing = missing.loc[
        missing["_merge"].eq("left_only"),
        ["fips", "year", "measure"]
    ].copy()

    # ==========================================================
    # 5. RESEARCH-SPECIFIC COMPLETENESS: 2015-2019 RATES
    # ==========================================================

    # A usable unemployment-rate observation must have:
    # - valid structure
    # - valid year
    # - no duplicate key
    # - valid numerical value
    # - geographic coverage consistent with ACS
    # - year within 2015-2019

    usable_rate_keys = df.loc[
        key_ok
        & ~df["puerto_rico"]
        & ~df["not_in_acs"]
        & ~df["duplicate_key"]
        & ~df["missing_value"]
        & ~df["non_numeric_value"]
        & ~df["invalid_value"]
        & df["measure"].eq("03")
        & df["year"].isin(PRE_YEARS),
        ["fips", "year"],
    ].drop_duplicates()

    expected_rates = pd.MultiIndex.from_product(
        [counties, PRE_YEARS],
        names=["fips", "year"]
    ).to_frame(index=False)

    pre_gaps = expected_rates.merge(
        usable_rate_keys,
        on=["fips", "year"],
        how="left",
        indicator=True,
    )

    pre_gaps = pre_gaps.loc[
        pre_gaps["_merge"].eq("left_only"),
        ["fips", "year"]
    ].copy()

    # ==========================================================
    # 6. ACCURACY / CONSISTENCY: ARITHMETIC CHECKS
    # ==========================================================

    # Compare labor force, employed, unemployed and unemployment
    # rate only for valid, unique, numeric observations.

    comparable = df.loc[
        key_ok
        & ~df["puerto_rico"]
        & ~df["duplicate_key"]
        & ~df["missing_value"]
        & ~df["non_numeric_value"]
        & ~df["invalid_value"],
        ["fips", "year", "measure", "value"],
    ]

    # Reshape measures into separate columns for comparison.
    wide = comparable.pivot(
        index=["fips", "year"],
        columns="measure",
        values="value"
    ).reindex(columns=list(MEASURES))

    arithmetic = wide.dropna(subset=list(MEASURES)).copy()

    # Labor force should approximately equal employed + unemployed.
    arithmetic["labor_force_difference"] = (
        arithmetic["06"] - arithmetic["05"] - arithmetic["04"]
    ).abs()

    # Expected unemployment rate based on employment-related counts.
    arithmetic["expected_rate"] = (
        100.0 * arithmetic["04"] / arithmetic["06"]
    )

    arithmetic["rate_difference_pp"] = (
        arithmetic["03"] - arithmetic["expected_rate"]
    ).abs()

    # Small counties can be more sensitive to rounding.
    arithmetic["rate_tolerance_pp"] = (
        RATE_TOL_PP + 100.0 / arithmetic["06"]
    )

    arithmetic["labor_force_warning"] = (
        arithmetic["labor_force_difference"] > LABOR_FORCE_TOL
    )

    arithmetic["rate_warning"] = (
        arithmetic["rate_difference_pp"]
        > arithmetic["rate_tolerance_pp"]
    )

    # ==========================================================
    # 7. COLLECT QUALITY FLAGS
    # ==========================================================

    flags = [
        "invalid_fips",
        "invalid_series_id",
        "invalid_year",
        "invalid_measure",
        "not_annual",
        "missing_value",
        "non_numeric_value",
        "invalid_value",
        "duplicate_key",
        "puerto_rico",
        "not_in_acs",
    ]

    return df, missing, pre_gaps, arithmetic, flags


def examples(df, flag, limit=SAMPLE_SIZE):
    """Return a few problematic observations for the report."""
    rows = df.loc[
        df[flag],
        ["fips", "year_raw", "measure", "value_raw"]
    ].head(limit)

    if rows.empty:
        return "none"

    return "; ".join(
        f"({row.fips}, {row.year_raw}, {row.measure}, {row.value_raw})"
        for row in rows.itertuples(index=False)
    )


def make_report(
    df, counties, acs_info, assessed, missing,
    pre_gaps, arithmetic, flags
):
    """Generate a readable quality assessment report."""

    count = lambda flag: int(assessed[flag].sum())

    years = sorted(
        assessed.loc[
            assessed["year"].isin(YEARS), "year"
        ].dropna().unique().astype(int).tolist()
    )

    observed_counties = set(
        assessed.loc[
            ~assessed["invalid_fips"]
            & ~assessed["puerto_rico"],
            "fips"
        ]
    )

    no_bls = sorted(set(counties) - observed_counties)

    unmatched = sorted(
        assessed.loc[assessed["not_in_acs"], "fips"].unique()
    )

    complete_rate_counties = (
        len(counties) - pre_gaps["fips"].nunique()
    )

    annual_coverage = assessed.loc[
        ~assessed["invalid_series_id"]
        & ~assessed["invalid_year"]
        & ~assessed["not_annual"]
        & ~assessed["puerto_rico"],
        ["fips", "year"],
    ].drop_duplicates()

    lines = [
        "BLS LAUS PRE-INTEGRATION QUALITY ASSESSMENT",
        "=" * 56,
        f"Assessment date: {date.today().isoformat()}",
        f"Raw BLS source: data/raw/{BLS_PATH.name}",
        f"Raw BLS SHA-256: {file_sha256(BLS_PATH)}",
        f"ACS geographic reference: data/raw/{ACS_PATH.name}",
        "Study geography: 50 states and DC (Puerto Rico excluded)",
        "Study period: 2015-2024; primary predictor: 2015-2019 unemployment rate",
        "",
        "SOURCE PROFILE",
        f"Raw BLS observations: {len(df):,}",
        f"BLS API response statuses observed: {len(df.attrs.get('api_statuses', [])):,}",
        f"BLS API responses not marked successful: "
        f"{sum(s != 'REQUEST_SUCCEEDED' for s in df.attrs.get('api_statuses', [])):,}",
        f"Distinct observed series IDs: {df['series_id'].nunique():,}",
        f"Distinct observed FIPS strings (including invalid/PR): {df['fips'].nunique():,}",
        f"Observed years: {years}",
        f"ACS reference rows: {acs_info['acs_rows']:,}",
        f"ACS valid distinct counties excluding PR: {len(counties):,}",
        f"ACS invalid FIPS rows: {acs_info['invalid_acs_fips']:,}",
        f"ACS duplicate FIPS rows: {acs_info['duplicate_acs_fips']:,}",
        "",
        "1. ACCURACY: CODE AND VALUE VALIDITY",
        "Flags count raw observations; categories can overlap.",
    ]

    for flag in [
        "invalid_fips",
        "invalid_series_id",
        "invalid_measure",
        "missing_value",
        "non_numeric_value",
        "invalid_value",
    ]:
        lines.append(f"  {flag}: {count(flag):,}")

    lines.extend([
        "  All checks are screening rules, not proof of statistical accuracy.",
        "",
        "2. COMPLETENESS: OBSERVATIONS AND RESEARCH INPUTS",
        f"Expected ACS-referenced county-year-measure keys: {len(counties)*len(YEARS)*len(MEASURES):,}",
        f"Unobserved keys versus 2024 ACS geography: {len(missing):,} "
        f"({100 * len(missing) / (len(counties)*len(YEARS)*len(MEASURES)):.2f}%)",
        f"ACS counties with no BLS observations: {len(no_bls):,}",
        f"  Examples of wholly unmatched ACS counties: {', '.join(no_bls[:10]) or 'none'}",
        "Missing keys by calendar year (each missing measure counts separately):",
    ])

    by_year = missing.groupby("year").size()

    for year in YEARS:
        lines.append(f"  {year}: {int(by_year.get(year, 0)):,}")

    lines.append(
        "Missing numerical BLS values by measure (valid annual keys only):"
    )

    usable_keys = ~assessed[
        [
            "invalid_fips",
            "invalid_series_id",
            "invalid_year",
            "invalid_measure",
            "not_annual",
            "puerto_rico",
        ]
    ].any(axis=1)

    missing_by_measure = assessed.loc[
        usable_keys & assessed["missing_value"]
    ].groupby("measure").size()

    for measure, label in MEASURES.items():
        lines.append(
            f"  {label}: {int(missing_by_measure.get(measure, 0)):,}"
        )

    lines.extend([
        f"Usable 2015-2019 county-year unemployment rates: {len(counties)*5 - len(pre_gaps):,} / {len(counties)*5:,} "
        f"({100 * (1 - len(pre_gaps)/(len(counties)*5)):.2f}%)",
        f"Missing/unusable pre-2020 county-year rates: {len(pre_gaps):,}",
        f"Counties with all five usable pre-2020 rates: {complete_rate_counties:,}",
        f"Counties with fewer than five usable rates: {pre_gaps['fips'].nunique():,}",
        "  'Unusable' here means missing, duplicate, malformed, or outside allowed range.",
        "  Arithmetic warnings below are reviewed separately (not auto-excluded).",
        "",
        "3. TIMELINESS: TIME WINDOW AND RESEARCH FITNESS",
        f"Invalid/out-of-range year observations: {count('invalid_year'):,}",
        f"Non-annual (not M13) observations: {count('not_annual'):,}",
        f"Last observed in-range annual year: {int(annual_coverage['year'].max()) if not annual_coverage.empty else 'none'}",
        "Distinct counties with an annual observation, by year:",
    ])

    for year in YEARS:
        n = annual_coverage.loc[
            annual_coverage["year"].eq(year), "fips"
        ].nunique()
        lines.append(f"  {year}: {n:,}")

    lines.extend([
        "  The 2015-2019 data align with the pre-2020 research predictor.",
        "  The 2020-2024 data are retained for secondary comparisons.",
        "  Reference ACS 2024 5-year estimates pool 2020-2024; they are NOT annual rows.",
        "  A verified BLS release/vintage date is not established by the year field.",
        "",
        "4. CONSISTENCY: KEYS, GEOGRAPHY AND ARITHMETIC",
        f"Duplicate annual county-year-measure observations: {count('duplicate_key'):,}",
        f"Puerto Rico observations outside study scope: {count('puerto_rico'):,}",
        f"BLS observations whose FIPS is not in ACS reference (excluding PR/invalid): {count('not_in_acs'):,}",
        f"Distinct unmatched BLS FIPS: {len(unmatched):,}",
        f"  Examples of unmatched BLS FIPS: {', '.join(unmatched[:10]) or 'none'}",
        f"County-years eligible for 4-measure arithmetic checks: {len(arithmetic):,}",
        f"Labor force != employed + unemployed beyond {LABOR_FORCE_TOL} people: {int(arithmetic['labor_force_warning'].sum()):,}",
        f"Unemployment rate disagrees with 100*unemployed/labor_force beyond rounding tolerance: {int(arithmetic['rate_warning'].sum()):,}",
        f"  Rate tolerance = {RATE_TOL_PP} percentage points + 100/labor_force.",
        "  BLS rounding and independently averaged annual estimates may explain small differences.",
        "",
        "GEOGRAPHIC REVIEW AREAS (COUNTS ARE NOT AUTOMATIC ERRORS)",
    ])

    # Geography-related issues discussed in the project plan.
    for state, label in [
        ("02", "Alaska"),
        ("09", "Connecticut"),
        ("15", "Hawaii"),
        ("51", "Virginia"),
    ]:
        gap_rows = missing.loc[
            missing["fips"].str.startswith(state)
        ]

        extra = [
            f for f in unmatched if f.startswith(state)
        ]

        lines.append(
            f"  {label}: {gap_rows['fips'].nunique()} ACS counties with missing keys; "
            f"{len(gap_rows)} absent keys; {len(extra)} unmatched BLS FIPS"
        )

    lines.extend([
        "  A 2024 ACS FIPS may not have existed throughout 2015-2024.",
        "  Investigate historic county-equivalent changes before exclusion or mapping.",
        "",
        "SAMPLE RECORDS TO INVESTIGATE (fips, year, measure, raw value)",
    ])

    for flag in [
        "invalid_series_id",
        "not_annual",
        "duplicate_key",
        "missing_value",
        "non_numeric_value",
        "invalid_value",
        "not_in_acs",
    ]:
        lines.append(
            f"  {flag}: {examples(assessed, flag)}"
        )

    if not arithmetic.empty:
        warnings = arithmetic.loc[
            arithmetic["labor_force_warning"]
            | arithmetic["rate_warning"]
        ].head(SAMPLE_SIZE)

        arithmetic_samples = "; ".join(
            f"({fips}, {int(year)}, LF gap={row.labor_force_difference:.1f}, "
            f"rate gap={row.rate_difference_pp:.3f} pp)"
            for (fips, year), row in warnings.iterrows()
        )

        lines.append(
            f"  arithmetic warnings: {arithmetic_samples or 'none'}"
        )

    lines.extend([
        "",
        "INTERPRETATION AND NEXT STEPS",
        "  Raw BLS and ACS inputs were read without modification.",
        "  ACS matching is only a pre-integration feasibility check, not a join.",
        "  Coordinate FIPS harmonization with ACS and BEA cleaning before integration.",
        "  Investigate invalid/duplicate values and arithmetic warnings; do not auto-impute.",
        "  In the separate cleaning stage, document every rule and rerun assessment.",
        "  This report does not validate the geographic definition behind a matching FIPS.",
    ])

    return "\n".join(lines) + "\n"



def main():
    # Read raw data and geographic reference.
    df = load_bls()
    counties, acs_info = load_acs_counties()

    # Perform pre-integration quality checks.
    assessed, missing, pre_gaps, arithmetic, flags = assess(
        df, counties
    )

    # Generate assessment report.
    report = make_report(
        df,
        counties,
        acs_info,
        assessed,
        missing,
        pre_gaps,
        arithmetic,
        flags
    )

    # Create output folder if necessary.
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Overwrite the existing quality assessment report.
    output = RESULTS_DIR / "bls_quality_report.txt"

    output.write_text(
        report,
        encoding="utf-8"
    )

    # Print report.
    print(report)
    print(f"Saved: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
