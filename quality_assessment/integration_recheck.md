# County data integration

Source commit: `7d484d8db11254bec6f2fc85e5d6b2194ccf07e8`. Run `python scripts/integrate_cleaned.py` from the repository root (Python, pandas and NumPy required).

Then run `python scripts/check_integration.py`. This separate check reads the exported CSVs and independently recalculates the predictors from raw BLS JSON and BEA CSV. It also compares all 312 original ACS fields, checks combined-area membership and reconciles the included and excluded county sets. Its result is saved in `integration_verification.json`.

## Recheck results

- All three raw-file checksums match the stored records.
- Rerunning the cleaners reproduces every cleaned-data and crosswalk cell.
- ACS: 3,144 rows, 312 columns, unique county keys, no missing or negative estimates.
- BLS: 31,430 county-year rows; unique keys. Employment plus unemployment equals labor force; published rates reconcile within 0.05 percentage point rounding.
- BEA: 31,270 geography-year rows; unique keys and missing-GDP flags reconcile. Missing-value codes remain missing, not zero.
- Integration leaves all raw and cleaned inputs unchanged.

These checks establish internal consistency and reproducibility of the stored extraction. They do not independently verify every published value against current agency data. The older BEA quality report says BLS has 3,144 units; the current cleaned BLS file has 3,143. Kalawao (15005) is absent from BLS.

## Join and output

ACS remains one row per county with all original estimate and MOE columns. BLS is summarized to the mean of all five 2015–2019 published annual unemployment rates. BEA growth is `100 * ((GDP2019 / GDP2015) ** (1/4) - 1)`, using real GDP in thousands of chained 2017 dollars. Both predictors are percentages. ACS is a pooled 2020–2024 estimate, not cumulative migration or an annual outcome.

The one-to-one left joins retain 3,144 ACS rows. The screened table has 3,080 rows and two complete economic predictors. 64 counties are held out with explicit reasons. No missing values are imputed. The audit table includes held-out records and must not be used as the screened analysis sample.

The excluded set consists of 53 counties in combined BEA units, nine Connecticut planning regions and two Alaska census areas. Three of these counties also lack the full BLS predictor window. These overlapping reasons are recorded in the exclusion CSV.

Combined BEA units are mapped for audit only; their GDP or growth is not copied to constituent counties. The 51 Virginia counties/cities could be represented by 23 combined units in a separate analysis after aggregating ACS counts and BLS labor-force counts. Rates cannot simply be averaged across counties. Maui and Kalawao form the remaining combined unit, and Kalawao has no BLS series in this extract. We retain county-level observations here, as specified in the project plan.

The geography review restores 15 counties excluded in the first screening: eight Alaska areas, five Colorado counties, Oglala Lakota and Bedford. The footnotes refer to changes before 2015 or to name/code changes. All 15 have the required economic observations. The review CSV gives a decision and official source for each of the original 79 flagged counties. No footnote-only exclusions remain.

Connecticut's nine planning regions lack BEA GDP for 2015 and 2019. Chugach and Copper River lack both the historical GDP endpoints and BLS rates. We do not divide old-county GDP between new geographies or fill these gaps with zeros.

ACS MOEs are retained, including unavailable MOEs. No small-county or statistical-reliability threshold has been imposed; those analysis choices remain open. This step merges cleaned inputs and economic predictors; it does not calculate RQ2/RQ3 outcomes or claim causal effects.

## Artifacts

- [Recheck and integration script](../scripts/integrate_cleaned.py)
- [All-county join audit](../data/integrated/county_join_audit.csv)
- [Screened county data](../data/integrated/county_screened.csv)
- [Review of the 79 flagged counties](county_geography_review.csv)
- [Independent output verification](integration_verification.json)
- [County exclusion details](../data/integrated/integration_exclusions.csv)
- [Source hashes and counts](integration_manifest.json)
- [Project definitions](../ProjectPlan.md)
- [BEA geography crosswalk](../data/processed/bea_fips_crosswalk.csv)

## Geographic references

- [BEA CAGDP1 footnotes](https://apps.bea.gov/itable/index.html?appid=70&stepnum=40&TableId=533)
- [Census county changes, 1990s](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes/1990.html)
- [Census county changes, 2000s](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.2000.html)
- [Census county changes, 2010s](https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.2010.html)
- [Census 2015 name/code changes](https://www.census.gov/programs-surveys/acs/technical-documentation/table-and-geography-changes/2015/geography-changes.html)
- [BEA 2024 release and Connecticut geography change](https://www.bea.gov/news/2026/gross-domestic-product-county-and-personal-income-county-2024)
