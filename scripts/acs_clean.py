"""Clean the county-level ACS extract and preserve the original raw file."""

import os
import tempfile

import pandas as pd

from acs_quality_assessment import CONTROLLED_MOE, ROOT, assess, load_raw


OUTPUT_PATH = ROOT / "data/processed/acs_2024_county_clean.csv"


def main():
    raw = load_raw()
    in_scope, estimates, margins, counts = assess(raw)
    if not counts["SHA-256 matches recorded checksum"]:
        raise ValueError("ACS raw file does not match its recorded checksum.")

    blocking_checks = (
        "Unknown state or territory rows",
        "Duplicate FIPS (additional occurrences)",
        "Invalid or inconsistent FIPS rows",
        "Blank county names",
        "Nonnumeric nonblank estimate/MOE cells",
        "Unexpected negative estimate/MOE cells",
    )
    issues = [label for label in blocking_checks if counts[label]]
    if issues:
        raise ValueError(f"Resolve ACS quality issues before cleaning: {', '.join(issues)}")

    clean = raw.loc[in_scope].copy()
    clean[margins] = clean[margins].replace(CONTROLLED_MOE, "")
    for column in estimates + margins:
        clean[column] = clean[column].replace("", None).astype("Int64")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write completely before replacing the previous output.
    with tempfile.NamedTemporaryFile(dir=OUTPUT_PATH.parent, suffix=".csv", delete=False) as file:
        temporary = file.name
    try:
        clean.to_csv(temporary, index=False)
        reloaded = pd.read_csv(temporary, dtype="string", keep_default_na=False)
        expected = raw.loc[in_scope].copy()
        expected[margins] = expected[margins].replace(CONTROLLED_MOE, "")
        pd.testing.assert_frame_equal(reloaded, expected.reset_index(drop=True))
        os.replace(temporary, OUTPUT_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    report = [
        "ACS cleaning and post-cleaning validation",
        f"Input rows: {len(raw)}",
        f"Excluded Puerto Rico rows: {counts['Puerto Rico rows']}",
        f"Output rows: {len(clean)}",
        f"Output columns: {len(clean.columns)}",
        f"Controlled MOE cells exported as blank: {counts['Controlled MOE codes, in scope']}",
        f"Remaining blank estimate cells: {int(clean[estimates].isna().sum().sum())}",
        f"Blank MOE cells: {int(clean[margins].isna().sum().sum())}",
        "Round-trip comparison against every expected output cell: PASS",
        "County FIPS uniqueness and format: PASS",
        "Raw checksum validation: PASS",
        "",
        "Controlled MOE locations remain recoverable from the raw CSV using",
        "county_fips and the variable name. Column counts are in acs_column_quality.csv.",
        "Use dtype={'county_fips': str, 'state': str, 'county': str} when reading CSV.",
        "CSV has no stored data types; opening in Excel may remove leading zeros.",
        "No imputation or statistical outlier removal was applied.",
        "Reliability thresholds and geographic crosswalks require group decisions.",
        "Use county_fips to link county-level ACS to summarized BLS/BEA measures.",
        "Treat a repeated ACS observation in a county-year join as the same pooled estimate.",
    ]
    report_path = ROOT / "quality_assessment/acs_cleaning_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(clean):,} county rows")


if __name__ == "__main__":
    main()
