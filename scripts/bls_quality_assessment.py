
"""IS477 - BLS LAUS pre-integration data quality assessment.

Assess raw BLS annual county observations; compare FIPS coverage with ACS
only in a separate integration-readiness section. No cleaning or joining.

Run from repository root: python scripts/bls_quality_assessment.py
Writes (overwrites): quality_assessment/bls_quality_report.txt
"""

import hashlib
import json
import textwrap
from datetime import date
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
BLS_PATH = ROOT / "data/raw/bls_laus_2015_2024_annual.json"
ACS_PATH = ROOT / "data/raw/acs_2024_county_full.csv"
OUTPUT = ROOT / "quality_assessment/bls_quality_report.txt"

YEARS = list(range(2015, 2025))
PRE_YEARS = list(range(2015, 2020))

MEASURES = {
    "03": "Unemployment rate (%)",
    "04": "Unemployed (persons)",
    "05": "Employed (persons)",
    "06": "Labor force (persons)",
}

MISSING_TOKENS = {"-", "--", "N/A", "NA", "NULL", "NAN", "(NA)"}

# Diagnostic thresholds, not official BLS error thresholds.
LF_TOL = 2.0
RATE_TOL = 0.15

REPORT_WIDTH = 88


# ============================================================
# 1. DATA LOADING AND PROFILING
# ============================================================

def sha256(path):
    """Calculate a source-file checksum without modifying the file."""
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def read_bls():
    """Load nested BLS API responses into a diagnostic long-form table."""

    with BLS_PATH.open(encoding="utf-8") as stream:
        raw = json.load(stream)

    records = []
    statuses = []

    def walk(node, inherited_sid=""):
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_sid)
            return

        if not isinstance(node, dict):
            return

        status = node.get("status")

        if isinstance(status, str) and status.startswith("REQUEST_"):
            statuses.append(status)

        sid = (
            node.get("seriesID")
            or node.get("seriesId")
            or inherited_sid
        )

        if "year" in node and ("value" in node or "period" in node):
            records.append({
                "series_id": str(sid or "").strip(),
                "year_raw": node.get("year"),
                "period_raw": node.get("period"),
                "value_raw": node.get("value"),
            })
            return

        for key in ("Results", "results", "series", "data", "responses"):
            if key in node:
                walk(node[key], sid)

    walk(raw)

    if not records:
        raise ValueError(
            "No BLS observations found. Check the raw JSON structure."
        )

    df = pd.DataFrame(records)

    # Extract identifiers without altering the raw records.
    df["fips"] = df["series_id"].str[5:10]
    df["measure"] = df["series_id"].str[-2:]

    df["year"] = pd.to_numeric(
        df["year_raw"],
        errors="coerce"
    )

    df["period"] = (
        df["period_raw"]
        .astype("string")
        .str.strip()
    )

    # Classify unavailable values before numeric conversion.
    text = df["value_raw"].astype("string").str.strip()

    df["empty_value"] = (
        text.isna() | text.eq("")
    ).fillna(False)

    df["missing_marker"] = (
        text.str.upper().isin(MISSING_TOKENS)
    ).fillna(False)

    df["value"] = pd.to_numeric(
        text.str.replace(",", "", regex=False),
        errors="coerce"
    )

    df["unparseable_value"] = (
        df["value"].isna()
        & ~df["empty_value"]
        & ~df["missing_marker"]
    )

    return df, statuses


def read_acs_fips():
    """Load ACS county FIPS for a separate integration-readiness check."""

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

    non_pr = ~fips.str.startswith("72", na=False)

    counties = set(
        fips.loc[valid & non_pr].dropna()
    )

    info = {
        "rows": len(acs),
        "invalid": int((~valid).sum()),
        "duplicates": int(fips.loc[valid].duplicated().sum()),
    }

    return counties, info


# ============================================================
# 2. QUALITY ASSESSMENT
# ============================================================

def product_keys(counties, years, measures):
    """Generate expected county-year-measure combinations."""

    return pd.MultiIndex.from_product(
        [sorted(counties), years, measures],
        names=["fips", "year", "measure"]
    ).to_frame(index=False)


def unobserved(expected, actual, keys):
    """Identify expected keys absent from the observed dataset."""

    merged = expected.merge(
        actual[keys].drop_duplicates(),
        how="left",
        on=keys,
        indicator=True
    )

    return merged.loc[
        merged["_merge"].eq("left_only"),
        keys
    ].copy()


def assess(df, acs_counties):
    """Assess accuracy, completeness, timeliness, and consistency."""

    df = df.copy()

    # --------------------------------------------------------
    # A. IDENTIFIER AND NUMERIC VALIDITY
    # --------------------------------------------------------

    df["invalid_fips"] = (
        ~df["fips"].str.fullmatch(r"\d{5}", na=False)
        | df["fips"].eq("00000")
    )

    df["invalid_series"] = ~df["series_id"].str.fullmatch(
        r"LAUCN\d{5}0{8}(03|04|05|06)",
        na=False
    )

    df["invalid_measure"] = ~df["measure"].isin(MEASURES)

    df["invalid_year"] = (
        ~df["year"].isin(YEARS)
        | ~df["year_raw"].astype("string").str.fullmatch(
            r"\d{4}",
            na=False
        )
    )

    df["not_annual"] = ~df["period"].eq("M13").fillna(False)

    df["puerto_rico"] = (
        df["fips"].str.startswith("72", na=False)
    )

    rate = df["measure"].eq("03")
    count = df["measure"].isin(("04", "05", "06"))
    value = df["value"]

    df["invalid_numeric"] = (
        (rate & value.notna() & ~value.between(0, 100))
        | (
            count
            & value.notna()
            & ((value < 0) | value.mod(1).ne(0))
        )
        | (df["measure"].eq("06") & value.eq(0))
        | value.isin((float("inf"), -float("inf")))
    )

    # --------------------------------------------------------
    # B. KEY CONSISTENCY
    # --------------------------------------------------------

    structure_flags = [
        "invalid_fips",
        "invalid_series",
        "invalid_measure",
        "invalid_year",
        "not_annual",
    ]

    df["valid_key"] = ~df[structure_flags].any(axis=1)

    df["duplicate_key"] = False

    ok = df["valid_key"]

    df.loc[ok, "duplicate_key"] = df.loc[ok].duplicated(
        ["fips", "year", "measure"],
        keep=False
    )

    # Valid, unique, usable numerical observations.
    df["usable_numeric"] = (
        df["valid_key"]
        & ~df["duplicate_key"]
        & ~df["empty_value"]
        & ~df["missing_marker"]
        & ~df["unparseable_value"]
        & ~df["invalid_numeric"]
    )

    # --------------------------------------------------------
    # C. BLS GEOGRAPHIC FOOTPRINT AND COMPLETENESS
    # --------------------------------------------------------

    bls_counties = set(
        df.loc[
            ~df["invalid_fips"]
            & ~df["puerto_rico"]
            & ~df["invalid_series"],
            "fips"
        ]
    )

    observed = df.loc[
        df["valid_key"] & ~df["puerto_rico"],
        ["fips", "year", "measure"]
    ].drop_duplicates()

    usable = df.loc[
        df["usable_numeric"] & ~df["puerto_rico"],
        ["fips", "year", "measure"]
    ].drop_duplicates()

    # BLS-only completeness baseline.
    expected_bls = product_keys(
        bls_counties,
        YEARS,
        list(MEASURES)
    )

    missing_bls = unobserved(
        expected_bls,
        observed,
        ["fips", "year", "measure"]
    )

    pre_bls = product_keys(
        bls_counties,
        PRE_YEARS,
        ["03"]
    )

    unusable_pre_bls = unobserved(
        pre_bls,
        usable,
        ["fips", "year", "measure"]
    )

    # --------------------------------------------------------
    # D. ACS-REFERENCED INTEGRATION READINESS
    # --------------------------------------------------------

    expected_acs = product_keys(
        acs_counties,
        YEARS,
        list(MEASURES)
    )

    missing_acs = unobserved(
        expected_acs,
        observed,
        ["fips", "year", "measure"]
    )

    pre_acs = product_keys(
        acs_counties,
        PRE_YEARS,
        ["03"]
    )

    unusable_pre_acs = unobserved(
        pre_acs,
        usable,
        ["fips", "year", "measure"]
    )

    # --------------------------------------------------------
    # E. INTERNAL ARITHMETIC CONSISTENCY
    # --------------------------------------------------------

    numeric = df.loc[
        df["usable_numeric"] & ~df["puerto_rico"],
        ["fips", "year", "measure", "value"]
    ]

    wide = numeric.pivot(
        index=["fips", "year"],
        columns="measure",
        values="value"
    ).reindex(columns=list(MEASURES))

    # Labor force approximately equals employed + unemployed.
    counts = wide.dropna(
        subset=["04", "05", "06"]
    ).copy()

    counts["difference"] = (
        counts["06"] - counts["05"] - counts["04"]
    ).abs()

    counts["warning"] = counts["difference"].gt(LF_TOL)

    # Unemployment rate approximately equals unemployed / labor force.
    rates = wide.dropna(
        subset=["03", "04", "06"]
    ).copy()

    rates = rates.loc[rates["06"] > 0].copy()

    rates["difference"] = (
        rates["03"] - 100 * rates["04"] / rates["06"]
    ).abs()

    rates["tolerance"] = RATE_TOL + 100 / rates["06"]

    rates["warning"] = rates["difference"].gt(
        rates["tolerance"]
    )

    return {
        "df": df,
        "bls_counties": bls_counties,
        "acs_counties": acs_counties,
        "observed": observed,
        "usable": usable,
        "expected_bls": expected_bls,
        "missing_bls": missing_bls,
        "pre_bls": pre_bls,
        "unusable_pre_bls": unusable_pre_bls,
        "expected_acs": expected_acs,
        "missing_acs": missing_acs,
        "pre_acs": pre_acs,
        "unusable_pre_acs": unusable_pre_acs,
        "counts": counts,
        "rates": rates,
    }


# ============================================================
# 3. REPORT GENERATION
# ============================================================

def build_report(result, statuses, acs_info):
    """Create a consistently formatted plain-text quality report."""

    d = result["df"]
    bls = result["bls_counties"]
    acs = result["acs_counties"]

    observed = result["observed"]
    usable = result["usable"]

    missing_bls = result["missing_bls"]
    missing_acs = result["missing_acs"]

    pre_bls = result["pre_bls"]
    pre_acs = result["pre_acs"]

    gaps_bls = result["unusable_pre_bls"]
    gaps_acs = result["unusable_pre_acs"]

    counts = result["counts"]
    rates = result["rates"]

    def n(column):
        return int(d[column].sum())

    def fmt(value):
        return f"{value:,}"

    def pct(numerator, denominator):
        if not denominator:
            return "N/A"
        return f"{numerator / denominator * 100:,.2f}%"

    lines = []

    # --------------------------------------------------------
    # FORMATTING HELPERS
    # --------------------------------------------------------

    def blank():
        lines.append("")

    def title(text):
        lines.extend([
            "=" * REPORT_WIDTH,
            text.center(REPORT_WIDTH),
            "=" * REPORT_WIDTH,
        ])

    def section(number, heading):
        blank()
        lines.extend([
            f"{number:02d}  {heading.upper()}",
            "-" * REPORT_WIDTH,
        ])

    def sub(heading):
        blank()
        lines.append(f"  {heading}")
        lines.append("  " + "~" * (REPORT_WIDTH - 4))

    def info(text):
        wrapped = textwrap.wrap(
            text,
            width=REPORT_WIDTH - 4,
            initial_indent="  ",
            subsequent_indent="  ",
        )
        lines.extend(wrapped or ["  "])

    def metric(label, value):
        """Align labels and statistics without truncating content."""

        if len(label) > 56:
            info(label)
            lines.append(f"  {'':<56} {str(value):>25}")
        else:
            lines.append(f"  {label:<56} {str(value):>25}")

    def table(headers, rows, widths):
        """Produce a text table with consistent column alignment."""

        def format_row(cells):
            parts = []

            for index, (cell, width) in enumerate(zip(cells, widths)):
                text = str(cell)

                if index == 0:
                    parts.append(text[:width].ljust(width))
                else:
                    parts.append(text[:width].rjust(width))

            return "  " + "  ".join(parts)

        lines.append(format_row(headers))

        lines.append(
            "  " + "  ".join("-" * width for width in widths)
        )

        for row in rows:
            lines.append(format_row(row))

    # ========================================================
    # REPORT HEADER
    # ========================================================

    title("BLS LAUS | PRE-INTEGRATION DATA QUALITY ASSESSMENT")

    lines.extend([
        "  Study: US county labor-market conditions and interstate migration",
        "  BLS: Local Area Unemployment Statistics | annual county observations",
        f"  Assessment date: {date.today():%Y-%m-%d}  |  Coverage: 2015-2024",
        "  Scope: raw BLS quality; ACS reference used only in Section 07",
    ])

    # ========================================================
    # 01. EXECUTIVE SUMMARY
    # ========================================================

    section(1, "Executive summary")

    raw_fips = d["fips"].nunique()

    pr_fips = d.loc[
        d["puerto_rico"], "fips"
    ].nunique()

    metric("Raw BLS observations", fmt(len(d)))
    metric("Distinct BLS FIPS (including Puerto Rico)", fmt(raw_fips))
    metric("BLS FIPS outside Puerto Rico", fmt(len(bls)))
    metric("Puerto Rico FIPS", fmt(pr_fips))

    metric(
        "Usable 2015-2019 unemployment-rate keys (BLS footprint)",
        f"{fmt(len(pre_bls) - len(gaps_bls))} / {fmt(len(pre_bls))}"
    )

    metric(
        "2015-2019 rate coverage (BLS footprint)",
        pct(len(pre_bls) - len(gaps_bls), len(pre_bls))
    )

    blank()

    unavailable_total = (
        n("empty_value")
        + n("missing_marker")
        + n("unparseable_value")
    )

    info(
        f"FINDINGS: {fmt(n('duplicate_key'))} duplicate rows; "
        f"{fmt(n('invalid_numeric'))} invalid numeric values; "
        f"{fmt(unavailable_total)} raw observations with unavailable "
        f"numeric values. {fmt(len(gaps_bls))} BLS-footprint "
        "pre-2020 unemployment-rate keys are absent or unusable "
        "(historical geography may explain some gaps)."
    )

    info(
        "IMPORTANT: This is an assessment, not a cleaning or "
        "integration step. No input records were changed."
    )

    # ========================================================
    # 02. DATASET PROFILE AND PROVENANCE
    # ========================================================

    section(2, "Dataset profile and provenance")

    metric("Distinct series IDs", fmt(d["series_id"].nunique()))
    metric("Requested calendar years", "2015-2024 (10)")

    metric(
        "BLS API responses with status field",
        fmt(len(statuses))
    )

    metric(
        "API responses with non-success status",
        fmt(sum(s != "REQUEST_SUCCEEDED" for s in statuses))
    )

    metric(
        "Puerto Rico raw observations (out of study scope)",
        fmt(n("puerto_rico"))
    )

    sub("Measure inventory | all raw observations")

    table(
        ["Code / measure", "Observations"],
        [
            (
                f"{code}  {name}",
                fmt(int(d["measure"].eq(code).sum()))
            )
            for code, name in MEASURES.items()
        ],
        [55, 16]
    )

    info(
        "Each observation is intended to represent one "
        "county-equivalent, year, and measure. The raw BLS "
        "series ID supplies the FIPS and measure code."
    )

    # ========================================================
    # 03. ACCURACY
    # ========================================================

    section(3, "Accuracy | identifiers and numerical validity")

    sub("Validation results | all raw observations")

    checks = [
        ("Invalid 5-digit county FIPS", n("invalid_fips")),
        ("Invalid LAUCN county series ID", n("invalid_series")),
        ("Unrecognized measure code", n("invalid_measure")),
        ("Empty or null value", n("empty_value")),
        ("Recognized missing-value marker (e.g., '-')", n("missing_marker")),
        ("Other unparseable numeric text", n("unparseable_value")),
        ("Numeric value outside validation rules", n("invalid_numeric")),
    ]

    table(
        ["Rule / condition", "Flagged"],
        [(name, fmt(number)) for name, number in checks],
        [59, 12]
    )

    sub("Missing or nonnumeric values by geography")

    geography = [
        ("Puerto Rico", d["puerto_rico"]),
        ("Study area (excluding PR)", ~d["puerto_rico"]),
    ]

    table(
        ["Geography", "Blank", "Marker", "Other text", "Bad number"],
        [
            (
                label,
                fmt(int(d.loc[mask, "empty_value"].sum())),
                fmt(int(d.loc[mask, "missing_marker"].sum())),
                fmt(int(d.loc[mask, "unparseable_value"].sum())),
                fmt(int(d.loc[mask, "invalid_numeric"].sum())),
            )
            for label, mask in geography
        ],
        [38, 8, 8, 12, 10]
    )

    if n("missing_marker"):
        frequency = (
            d.loc[d["missing_marker"], "value_raw"]
            .astype("string")
            .value_counts()
            .head(4)
        )

        detected = ", ".join(
            f"{str(token)!r} ({fmt(int(total))})"
            for token, total in frequency.items()
        )

        info(
            f"Detected missing-value markers: {detected}. "
            "These indicate unavailable numeric values, "
            "not valid zeros."
        )

    if unavailable_total:
        sub("Examples of unavailable raw values")

        samples = d.loc[
            d["empty_value"]
            | d["missing_marker"]
            | d["unparseable_value"],
            ["fips", "year_raw", "measure", "value_raw"]
        ].head(6)

        table(
            ["County FIPS", "Year", "Measure", "Raw value"],
            [
                (
                    str(row.fips),
                    str(row.year_raw),
                    str(row.measure),
                    repr(row.value_raw),
                )
                for row in samples.itertuples(index=False)
            ],
            [18, 10, 12, 18]
        )

        sub("Unavailable numeric values by measure | raw BLS")

        table(
            ["Measure", "Blank", "Marker", "Other text"],
            [
                (
                    f"{code}  {label}",
                    fmt(int(d.loc[d["measure"].eq(code), "empty_value"].sum())),
                    fmt(int(d.loc[d["measure"].eq(code), "missing_marker"].sum())),
                    fmt(int(d.loc[d["measure"].eq(code), "unparseable_value"].sum())),
                )
                for code, label in MEASURES.items()
            ],
            [44, 9, 9, 12]
        )

        missing_years = d.loc[
            d["empty_value"]
            | d["missing_marker"]
            | d["unparseable_value"],
            "year"
        ].value_counts().sort_index()

        years_text = ", ".join(
            f"{int(year)} ({fmt(int(total))})"
            for year, total in missing_years.items()
        )

        info(
            "Years with unavailable numeric values: "
            + (years_text or "none")
            + "."
        )

    info(
        "Numeric screening: unemployment rate must be 0-100; "
        "headcounts must be nonnegative integers; a zero labor-force "
        "denominator is flagged. Passing these checks does not "
        "independently verify BLS estimates."
    )

    # ========================================================
    # 04. COMPLETENESS
    # ========================================================

    section(4, "Completeness | BLS data before integration")

    sub("BLS footprint | counties observed in at least one year")

    metric("BLS counties outside Puerto Rico", fmt(len(bls)))

    metric(
        "Expected county-year-measure keys (BLS footprint)",
        fmt(len(result["expected_bls"]))
    )

    metric(
        "Absent county-year-measure keys",
        fmt(len(missing_bls))
    )

    metric(
        "Present key coverage",
        pct(
            len(result["expected_bls"]) - len(missing_bls),
            len(result["expected_bls"])
        )
    )

    info(
        "This BLS-only baseline assumes all counties seen in at "
        "least one BLS year should have all 10 years and four measures. "
        "Historic boundary changes can produce apparent gaps that "
        "are not acquisition errors. An absent key means no "
        "structurally valid annual record exists; a missing marker "
        "is counted separately."
    )

    sub("Coverage of primary research predictor | 2015-2019")

    metric(
        "Expected county-year unemployment rates",
        fmt(len(pre_bls))
    )

    metric(
        "Usable annual unemployment rates",
        fmt(len(pre_bls) - len(gaps_bls))
    )

    metric(
        "Missing / unusable annual rates",
        fmt(len(gaps_bls))
    )

    metric(
        "Counties with all 5 usable annual rates",
        fmt(len(bls) - gaps_bls["fips"].nunique())
    )

    metric(
        "Counties with at least one unusable annual rate",
        fmt(gaps_bls["fips"].nunique())
    )

    info(
        "'Usable' requires a valid annual key, one unambiguous "
        "record, a numeric rate between 0 and 100, and an in-scope "
        "year. Arithmetic warnings are evaluated separately."
    )

    sub("Observed annual coverage | within the BLS footprint")

    yearly_rows = []

    for year in YEARS:
        observed_year = observed.loc[
            observed["year"].eq(year)
        ]

        rate_year = usable.loc[
            usable["year"].eq(year)
            & usable["measure"].eq("03")
        ]

        absent = int(missing_bls["year"].eq(year).sum())

        yearly_rows.append((
            str(year),
            fmt(observed_year["fips"].nunique()),
            fmt(rate_year["fips"].nunique()),
            fmt(absent),
        ))

    table(
        [
            "Year",
            "Counties w/ record",
            "Usable rate counties",
            "Absent measure keys",
        ],
        yearly_rows,
        [8, 20, 22, 19]
    )

    # ========================================================
    # 05. TIMELINESS
    # ========================================================

    section(5, "Timeliness | temporal suitability")

    metric(
        "Observations with invalid/out-of-scope year",
        fmt(n("invalid_year"))
    )

    metric(
        "Observations with period other than M13",
        fmt(n("not_annual"))
    )

    observed_years = sorted(
        d.loc[
            ~d["invalid_year"],
            "year"
        ].dropna().unique()
    )

    if observed_years:
        year_label = (
            f"{int(min(observed_years))}-"
            f"{int(max(observed_years))} "
            f"({len(observed_years)} years)"
        )
    else:
        year_label = "none"

    metric("In-range years observed", year_label)

    info(
        "M13 denotes BLS annual-average observations. The "
        "2015-2019 window matches the planned pre-2020 "
        "unemployment-rate predictor. The raw observation year "
        "alone does not establish the release date or revision vintage."
    )

    # ========================================================
    # 06. CONSISTENCY
    # ========================================================

    section(6, "Consistency | keys and internal relationships")

    metric(
        "Duplicated county-year-measure rows (all occurrences)",
        fmt(n("duplicate_key"))
    )

    metric(
        "Eligible county-years for labor-force identity check",
        fmt(len(counts))
    )

    metric(
        f"Labor force identity warnings (> {LF_TOL:g} persons)",
        fmt(int(counts["warning"].sum()))
    )

    metric(
        "Eligible county-years for unemployment-rate check",
        fmt(len(rates))
    )

    metric(
        "Unemployment-rate arithmetic warnings",
        fmt(int(rates["warning"].sum()))
    )

    info(
        "Check A: labor force approximately equals employed "
        "+ unemployed. Check B: rate approximately equals "
        "100 x unemployed / labor force. Tolerances are "
        "diagnostic screening choices, not official BLS thresholds."
    )

    info(
        f"Screening rules: absolute labor-force difference "
        f"<= {LF_TOL:g} persons; absolute rate difference "
        f"<= {RATE_TOL:g} + 100/labor_force percentage points. "
        "Rounding of annual averages can produce small discrepancies."
    )

    if counts["warning"].any() or rates["warning"].any():
        sub("Sample arithmetic warnings")

        flagged_counts = counts.loc[
            counts["warning"],
            ["difference"]
        ].rename(columns={"difference": "lf_gap"})

        flagged_rates = rates.loc[
            rates["warning"],
            ["difference"]
        ].rename(columns={"difference": "rate_gap_pp"})

        flagged = flagged_counts.join(
            flagged_rates,
            how="outer"
        )

        for (fips, year), row in flagged.head(6).iterrows():
            lines.append(
                f"  {fips} / {int(year)}: "
                f"labor-force gap={row.get('lf_gap', float('nan')):g}, "
                f"rate gap={row.get('rate_gap_pp', float('nan')):g} pp"
            )

    # ========================================================
    # 07. INTEGRATION READINESS
    # ========================================================

    section(7, "Integration readiness | ACS geographic reference only")

    metric("ACS county FIPS outside Puerto Rico", fmt(len(acs)))
    metric("BLS county FIPS outside Puerto Rico", fmt(len(bls)))
    metric("Common BLS / ACS county FIPS", fmt(len(acs & bls)))
    metric("Only in ACS reference", fmt(len(acs - bls)))
    metric("Only in BLS source", fmt(len(bls - acs)))

    metric(
        "Expected ACS-referenced county-year-measure keys",
        fmt(len(result["expected_acs"]))
    )

    metric(
        "Absent keys relative to ACS geography",
        fmt(len(missing_acs))
    )

    metric(
        "Usable pre-2020 rates on ACS geographic reference",
        f"{fmt(len(pre_acs) - len(gaps_acs))} / {fmt(len(pre_acs))} "
        f"({pct(len(pre_acs) - len(gaps_acs), len(pre_acs))})"
    )

    metric(
        "Invalid ACS FIPS / duplicated ACS FIPS",
        f"{fmt(acs_info['invalid'])} / {fmt(acs_info['duplicates'])}"
    )

    info(
        "This section compares geographic identifiers only. "
        "No BLS-ACS data join is performed. Matching FIPS codes "
        "do not guarantee matching historical boundaries."
    )

    if acs - bls:
        listed = ", ".join(sorted(acs - bls)[:20])

        info(
            "ACS-only FIPS: " + listed
            + (" ..." if len(acs - bls) > 20 else "")
            + "."
        )

    if bls - acs:
        listed = ", ".join(sorted(bls - acs)[:20])

        info(
            "BLS-only FIPS: " + listed
            + (" ..." if len(bls - acs) > 20 else "")
            + "."
        )

    sub("Counties with missing ACS-referenced year-measure keys")

    geographic_gaps = (
        missing_acs
        .groupby("fips", as_index=False)
        .agg(
            absent_keys=("measure", "size"),
            years_affected=("year", "nunique")
        )
        .sort_values(
            ["absent_keys", "fips"],
            ascending=[False, True]
        )
    )

    if geographic_gaps.empty:
        info("None identified.")
    else:
        table(
            ["County FIPS", "Missing keys", "Years affected"],
            [
                (
                    row.fips,
                    fmt(int(row.absent_keys)),
                    fmt(int(row.years_affected)),
                )
                for row in geographic_gaps.head(12).itertuples(index=False)
            ],
            [20, 17, 19]
        )

        if len(geographic_gaps) > 12:
            info(
                f"Showing 12 of {len(geographic_gaps):,} "
                "counties with absent keys."
            )

    info(
        "Historical Alaska county-equivalent changes and "
        "Hawaii's Kalawao County should be reviewed as potential "
        "coverage or geographic-definition differences, not "
        "automatically treated as acquisition errors."
    )

    # ========================================================
    # 08. CONCLUSIONS AND CLEANING IMPLICATIONS
    # ========================================================

    section(8, "Conclusions and cleaning implications")

    if unavailable_total:
        info(
            "[REVIEW] Document the origin, measure, and year of "
            "blank or nonnumeric values. If they occur only outside "
            "the study scope, distinguish this from missingness "
            "in the US analysis population."
        )
    else:
        info(
            "[OBSERVED] No blank or nonnumeric value markers "
            "were detected."
        )

    if len(gaps_bls):
        info(
            "[REVIEW] Resolve incomplete 2015-2019 unemployment-rate "
            "coverage before calculating county means. Do not "
            "silently treat missing years as zero or assume "
            "historical county equivalence."
        )
    else:
        info(
            "[OBSERVED] Every BLS-observed county has five "
            "usable pre-2020 unemployment-rate observations."
        )

    if len(acs ^ bls) or len(missing_acs):
        info(
            "[REVIEW] Document ACS/BLS geographic differences "
            "and any validated crosswalk before integration. "
            "Do not assume that historical FIPS codes are equivalent."
        )

    any_numeric_issues = (
        n("duplicate_key")
        or n("invalid_numeric")
        or counts["warning"].any()
        or rates["warning"].any()
    )

    if any_numeric_issues:
        info(
            "[REVIEW] Investigate duplicate keys, invalid numbers "
            "or arithmetic warnings before deciding on cleaning rules."
        )
    else:
        info(
            "[OBSERVED] No duplicate key, invalid-number or "
            "arithmetic warning was detected at the selected "
            "screening thresholds."
        )

    info(
        "NEXT STAGE: The separate BLS cleaning script should "
        "record decisions and produce processed data. The "
        "post-integration assessment must then evaluate the "
        "genuinely joined dataset."
    )

    # ========================================================
    # 09. DEFINITIONS AND REPRODUCIBILITY
    # ========================================================

    section(9, "Definitions and reproducibility")

    info(
        "BLS footprint: unique valid-format county FIPS present "
        "in the BLS source during at least one year, excluding "
        "Puerto Rico. This is not an official count of counties "
        "in any single year."
    )

    info(
        "Absent key: a county-year-measure combination without "
        "a structurally valid M13 record. Unusable rate: an absent "
        "key or one with missing, invalid or duplicate numeric data."
    )

    info(
        "Value classes are mutually exclusive: blank/null, "
        "recognized missing marker, other nonnumeric text, "
        "or numeric. Flags in other categories may overlap. "
        "Arithmetic tolerances do not prove source accuracy."
    )

    info(
        "Raw data were read only. ACS contributed a FIPS "
        "reference list, not a joined table. No original "
        "observations were removed, filled or rewritten."
    )

    blank()

    lines.extend([
        f"  BLS input: data/raw/{BLS_PATH.name}",
        f"  BLS SHA-256: {sha256(BLS_PATH)}",
        f"  ACS reference: data/raw/{ACS_PATH.name}",
        f"  ACS SHA-256: {sha256(ACS_PATH)}",
        "  Script: scripts/bls_quality_assessment.py",
        "  Output: quality_assessment/bls_quality_report.txt",
        "",
        "=" * REPORT_WIDTH,
        "END OF REPORT".center(REPORT_WIDTH),
        "=" * REPORT_WIDTH,
    ])

    return "\n".join(lines) + "\n"


# ============================================================
# 4. EXECUTION
# ============================================================

def main():
    # Load inputs without modifying raw files.
    df, statuses = read_bls()
    acs_counties, acs_info = read_acs_fips()

    # Assess quality before cleaning or integration.
    result = assess(df, acs_counties)

    # Generate and overwrite the existing report.
    report = build_report(result, statuses, acs_info)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        report,
        encoding="utf-8"
    )

    print(report)
    print(f"Saved: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()