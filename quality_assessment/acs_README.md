# ACS pre-integration deliverables

Run from the repository root with Python 3 and pandas installed:

```bash
python scripts/acs_quality_assessment.py
python scripts/acs_clean.py
```

Both scripts resolve paths relative to the repository and use the existing raw
CSV and SHA-256 file. No API key or new data download is required.

## Outputs

- acs_quality_report.txt contains the pre-cleaning assessment and decisions.
- acs_column_quality.csv reports blanks and controlled MOE codes by variable.
- acs_cleaning_report.txt contains the cleaning counts and output validation.
- ../data/processed/acs_2024_county_clean.csv is the county-level cleaned dataset.

The cleaned CSV retains the original 312 columns. It contains 3,144 records
after excluding 78 Puerto Rico records. All 20,592 original blank cells occur
in the excluded records. In-scope estimates are complete. The 3,308 controlled
MOE codes are exported as blank, with their locations recoverable in the raw
CSV by county_fips and variable. These blanks must be distinguished from
missing population estimates and must not be filled with zero.

## Reuse and integration

```python
import pandas as pd

acs = pd.read_csv(
    "data/processed/acs_2024_county_clean.csv",
    dtype={"county_fips": str, "state": str, "county": str},
)
```

For county-level integration, summarize the relevant annual BLS and BEA
observations first and check that their county keys are unique. The current
BLS script uses the key name fips; rename it or specify left_on/right_on.
Track matched and unmatched counties and agree on treatment of Connecticut
planning regions, Virginia city combinations, and other geographic changes.
Use a validated merge once the intended cardinality is established.

The ACS five-year window is 2020–2024. Mobility is measured relative to one
year before each respondent's survey. The measure is not a cumulative count
of moves over five years.

## Limits and remaining group decisions

FIPS checks cover syntax, valid state codes, and agreement with state/county
fields. County codes have not been independently checked against a complete
Census geography reference. The checksum confirms file integrity; it does
not establish statistical accuracy. Individual estimates have not been
independently downloaded and reconciled.

No counties were excluded based on estimated reliability. The group still
needs to choose a reliability criterion and document cross-source geographic
matching. Integration and the post-integration assessment belong to the next
stage. The current scripts stop on unexpected negative codes or invalid
records so that changed inputs require an explicit review.

## Status report wording

Completed pre-integration assessment and cleaning of the ACS county extract.
Verified the recorded checksum, paired estimate/MOE variables, numeric
formats, county-key uniqueness, and FIPS structure. Excluded Puerto Rico
according to project scope and exported controlled MOE codes as blank.
The cleaned file has 3,144 rows and 312 columns, with no missing estimate
values. Output was reread and compared cell by cell to the expected result.
Geographic harmonization and a statistical reliability threshold remain
group decisions for integration.
