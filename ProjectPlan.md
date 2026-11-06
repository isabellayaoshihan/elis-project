# Project Plan

## Overview
This project asks whether local economic conditions shaped where Americans moved. Specifically, we test whether county labor-market conditions from 2015 through 2019 (unemployment and GDP growth) predict interstate in-migration from 2020 through 2024, and whether in-migrants differ from existing residents in education and age.

We will integrate three public U.S. government datasets at the county level: ACS for migration, demographics, and remote work; Bureau of Labor Statistics (BLS) Local Area Unemployment Statistics (LAUS) for employment and unemployment; and Bureau of Economic Analysis (BEA) County GDP (CAGDP1) for economic output. The sources link through five-digit county FIPS codes, although some geographic definitions differ and require additional handling before integration.

Our approach follows the data curation lifecycle. We will acquire each dataset programmatically with SHA-256 integrity checks and assess its quality for accuracy, completeness, timeliness, and consistency. Each dataset will be cleaned separately, while the original files remain unchanged. We will then resolve differences in geographic coverage, combine the cleaned datasets at the county level, and assess the quality of the integrated data. Finally, we will conduct the analysis and document the results. The process will be supported by a reproducible workflow using Snakemake or a run-all script.


## Team
| Member | Role | Planned responsibilities |
|---|---|---|
| Isabella Yao | Data Acquisition Lead | Acquisition scripts for ACS and BLS with SHA-256 checks; storage and folder organization; source documentation; BLS quality assessment and cleaning | 
| Lyric Li | Integration and Workflow Lead | FIPS-based integration and integration schema; Snakemake or run_all workflow; reproducibility testing; release management |
| Eric Shi | Data Quality and Compliance Lead | ACS quality assessment and cleaning; support for post-integration quality assessment; license and terms of use review |
| Susu Tran | Analysis and Documentation Lead | BEA acquisition, quality assessment, and cleaning; research questions; analysis and visualization; data dictionary and metadata file; final README coordination |

## Research Question

**Main question:** Did county labor-market conditions before 2020 predict interstate in-migration in the early 2020s?

- **RQ1.** Are lower 2015–2019 average unemployment rates and higher 2015–2019 real GDP growth associated with higher 2020–2024 interstate in-migration rates across U.S. counties?
- **RQ2.** Do interstate in-migrants differ from long-term residents in educational attainment (share with a bachelor's degree or higher, ages 25+) and age distribution?
- **RQ3.** Does the share of workers working from home (ACS B08301) weaken or explain the association in RQ1?

**Measures**
- *In-migration rate* = residents who lived in a different state one year earlier ÷ total population aged 1+ (ACS B07001, pooled 2020–2024). This measures interstate mobility among current county residents, not total migration over the entire five-year period.
- *Pre-2020 labor market* = mean LAUS unemployment rate, 2015–2019. We will calculate the average of the five annual unemployment rates for each county, using the annual-average observations (M13).
- *Pre-2020 growth* = annualized real GDP growth, 2015–2019 (BEA CAGDP1).
- *Comparison group for RQ2* = residents who lived in the same house one year earlier (B07001, B07009). Age comparisons will use B07001 (population aged 1+), while education comparisons will use B07009 (population aged 25+).

**Scope:** the 50 states and DC; Puerto Rico is excluded.

**Interpretation limits:** results show association, not causation. The pandemic and remote-work shifts confound the period, and ACS gives the destination county only, not the origin.

## Datasets
The project will integrate three public U.S. government datasets at the county or county-equivalent level. The datasets provide complementary demographic, labor-market, and economic information. Geographic identifiers (County FIPS codes) will be harmonized before integration because some source-specific geographic definitions do not map one-to-one across all years and datasets.

### 1. American Community Survey (ACS) 5-Year Estimates

- **Source:** U.S. Census Bureau
- **Dataset:** 2024 ACS 5-Year Detailed Tables
- **Acquisition method:** Census Data API
- **Time coverage:** 2020–2024, pooled five-year estimates
- **Geographic identifier:** county_fips, a five-digit code combining the state and county identifiers

The ACS dataset provides demographic, mobility, and commuting characteristics for U.S. counties and county equivalents. The project uses variables from several detailed tables:

- `B01003`: Total population
- `B07001`: Geographic mobility by age
- `B07009`: Geographic mobility by educational attainment
- `B08301`: Means of transportation to work, including working from home

The raw dataset contains 3,222 geographic records and 312 columns, including geographic identifiers, estimates, and margins of error. These four tables describe different population characteristics rather than different years.

The 2024 ACS 5-Year Estimates pool survey observations across 2020–2024. The estimates reflect information collected throughout this period rather than the arithmetic average of five separate annual datasets. The mobility tables describe mobility status relative to residence one year earlier, so they will be treated as pooled early-2020s mobility estimates rather than cumulative five-year migration totals.

For the analysis, B07001 will provide the interstate in-migration rate and age distribution of migrants, while B07009 will support comparisons of educational attainment between interstate migrants and nonmovers. B08301 will be used to calculate the share of workers working from home. Because the estimates are based on survey samples, margins of error will be considered when assessing reliability, particularly for smaller counties.

### 2. Bureau of Labor Statistics (BLS) Local Area Unemployment Statistics

- **Source:** U.S. Bureau of Labor Statistics
- **Dataset:** Local Area Unemployment Statistics (LAUS), County Annual Averages
- **Acquisition method:** BLS Public Data API
- **Time coverage:** 2015–2024, with separate annual observations
- **Geographic identifier:** County FIPS code embedded in the seriesID field

The LAUS dataset provides annual-average county-level labor-market measures, including labor force, employment, unemployment, and unemployment rate. The raw data contain four measures identified by the final two digits of each series ID: unemployment rate (03), unemployment (04), employment (05), and labor force (06). Each measure is recorded for individual years from 2015 to 2024, with M13 indicating the annual average.

The raw extraction contains 3,221 geographic identifiers with observations. Most have all four measures for all ten years, although some areas have incomplete historical coverage.

The primary analysis will use 2015–2019 unemployment rates to represent pre-2020 local labor-market conditions, while later years will remain available for descriptive or sensitivity analyses.

### 3. Bureau of Economic Analysis (BEA) County GDP

- **Source:** U.S. Bureau of Economic Analysis
- **Dataset:** GDP by County (CAGDP1)
- **Acquisition method:** BEA Data API
- **Time coverage:** 2015–2024, with separate annual observations
- **Geographic identifier:** GeoFips, which generally contains a five-digit county FIPS code but also includes identifiers for combined geographic areas

The BEA dataset provides county-level GDP measures. The acquisition script retains both real GDP and current-dollar GDP. These measures are distinguished by LineCode: 1 represents real GDP in thousands of chained 2017 dollars, while 3 represents current-dollar GDP in thousands of dollars.

Real GDP will be used to calculate economic growth because it allows growth to be compared without changes in the general price level being interpreted as real economic growth.

The raw dataset contains 62,540 rows across 3,127 geographic identifiers. Each geographic area generally appears multiple times because the dataset includes ten years and two GDP measures. These repeated observations are expected and are not duplicates when the year and GDP measure are considered.

The primary analysis will summarize real GDP growth during 2015–2019 as a measure of pre-2020 county economic performance.

### Data Integration

The datasets will be standardized using five-digit county FIPS codes, constructed from state and county identifiers where necessary. However, the datasets differ in both their time structure and geographic coverage, so they cannot be combined directly without preparation.

The ACS dataset contains one row per county and provides pooled estimates for 2020–2024. BLS and BEA contain separate annual observations from 2015–2024. Therefore, we will first summarize the BLS and BEA data into county-level measures for 2015–2019, including average unemployment rate and annualized real GDP growth.

The integration will then use county FIPS codes to join these economic measures with the ACS migration, demographic, and remote-work variables. The intended output is one row per county-level geographic unit, with separate columns for each variable used in the analysis.

Before joining the datasets, we will review geographic inconsistencies involving Connecticut's planning regions, Virginia's combined counties and independent cities, Hawaii, and Alaska. Geographic codes that appear to match will also be checked for differences in area definitions. Where reliable comparisons are not possible, affected areas will be excluded from the primary analysis and documented rather than combined using unsupported assumptions.

After integration, we will check for missing values, duplicate county identifiers, unexpected changes in row counts, and unmatched counties. We will report the final number of geographic units retained and explain any exclusions.

Together, the three datasets provide complementary information: ACS describes county demographic and socioeconomic characteristics, BLS measures labor-market outcomes, and BEA measures local economic performance. The integrated dataset will allow the project to examine relationships among population mobility, education, commuting and remote-work patterns, unemployment, and county-level economic performance.

### Data Acquisition and API Access

Data will be acquired programmatically using Python scripts stored in the `scripts/` directory. Each data source will have a separate acquisition script, and SHA-256 hashes will be used to support data-integrity checks.

API credentials will not be committed to the repository. Credentials are stored locally in `api_keys.txt`, which is excluded from version control through `.gitignore`.

Users reproducing the project can obtain their own API credentials from the following official registration pages:

- Census API key: https://api.census.gov/data/key_signup.html
- BLS Public Data API registration: https://data.bls.gov/registrationEngine/
- BEA API key registration: https://apps.bea.gov/api/signup/

Raw data retrieved by the acquisition scripts will be stored in `data/raw/` and preserved before subsequent cleaning and integration steps.

## Data Lifecycle
We follow the DataONE lifecycle. The **Plan** stage defines our research questions, data sources, and methods. During **Collect**, we acquire the three datasets through government APIs and verify file integrity using SHA-256 checksums. During **Assure**, we assess data quality and clean each dataset while preserving the raw files. During **Integrate**, we combine the cleaned data using harmonized county identifiers and assess the resulting dataset for missing values, duplicate records, and geographic mismatches. During **Analyze**, we examine the relationships described in RQ1–RQ3. **Describe** includes the data dictionary, metadata, and documentation, while **Preserve** includes checksums, version control, and project releases. If integration reveals additional data quality problems, we will return to the relevant cleaning steps and rerun the workflow.

## Storage and Organization
Data are stored as flat tabular files, organized by curation stage: `data/raw/` (unmodified API output in CSV and JSON, each with a `.sha256` checksum), `data/processed/` (cleaned source tables), `data/integrated/` (joined analysis table), `quality_assessment/` (data quality reports), `results/` (outputs and figures), and `scripts/` (one script per stage). BLS and BEA use one row per county-year, and ACS uses one row per county. FIPS codes are stored as zero-padded strings so leading zeros are not lost.

## Ethical Data Handling and Licensing
All three sources are U.S. government works in the public domain, so the raw files can be redistributed in this repository. We will follow each API's terms of use. The data are county-level aggregates with no individual records, so privacy risk is low. API keys are kept out of the repository (see Data Acquisition). No Kaggle datasets are used.

## Timeline
| # | Task | Description | Owner | Target date | Module |
|---|---|---|---|---|---|
## Timeline

| # | Task | Description | Owner | Target date | Status | Module |
|---|---|---|---|---|---|---|
| 1 | Project plan | Write ProjectPlan.md and publish the project-plan release | All | Oct 12 | Completed | |
| 2 | Lifecycle mapping | Relate the project to the DataONE data lifecycle model | Susu Tran | Oct 12 | Completed | M1 |
| 3 | Data acquisition | One script per source with SHA-256 integrity checks; raw data committed to `data/raw/`.<br>**ACS and LAUS:** Isabella Yao<br>**BEA:** Susu Tran | Isabella Yao, Susu Tran | Oct 11 | Completed | M4 |
| 4 | Storage and organization | Folder structure by curation stage, naming conventions, file formats | Isabella Yao, Susu Tran | Oct 12 | Completed | M2 |
| 5 | Ethics and licensing review | Document license and terms of use for every source | Susu Tran | Oct 12 | Completed | M3 |
| 6 | Pre-integration quality assessment | One assessment script per dataset covering accuracy, completeness, timeliness, and consistency, including missing values, duplicates, data types, and FIPS code validity; results documented in `quality_assessment/`.<br>**ACS 2024 5-Year (Census Bureau):** Eric Shi<br>**LAUS 2015 to 2024 (BLS):** Isabella Yao<br>**CAGDP1 2015 to 2024 (BEA):** Susu Tran | Eric Shi, Isabella Yao, Susu Tran | Nov 6 | Completed | M10 |
| 7 | Data cleaning | One cleaning script per dataset, separate from the assessment script. Cleaned data is exported to `data/processed/` and the raw data in `data/raw/` is left unchanged.<br>| Eric Shi, Isabella Yao, Susu Tran | Nov 6 | Completed | M11, M12 |
| 8 | Data integration | Join the cleaned ACS, LAUS, and BEA tables on 5-digit county FIPS, with LAUS and BEA aggregated to 2015 to 2019 predictors; log unmatched counties; document the integration schema. Started in a team working session on Nov 6. | All (led by Lyric Li) | Nov 14 | In progress | M7, M8 |
| 9 | Post-integration quality assessment | Same four dimensions on the integrated dataset | Lyric Li | Nov 17 | Not started | M10 |
| 10 | Plan revision | Revise ProjectPlan.md based on Milestone 2 feedback; make wording clearer and more consistent; update the timeline to reflect current progress | Lyric Li | Nov 6 | In progress | |
| 11 | Status report | StatusReport.md with each member's own contribution summary; publish the status-report release | All | Nov 19 | Not started | |
| 12 | Workflow automation | Snakemake or run_all script chaining single-purpose scripts from acquisition to analysis | Lyric Li | Nov 26 | Not started | M13 |
| 13 | Analysis and visualization | Answer the research questions with at least one visualization | Susu Tran | Nov 30 | Not started | |
| 14 | Environment and dependencies | requirements.txt, pip freeze output, relative paths throughout | Lyric Li | Dec 1 | Not started | M14 |
| 15 | Metadata and documentation | Data dictionary, DCAT or Schema.org metadata file | Susu Tran | Dec 3 | Not started | M15 |
| 16 | Licenses and references | License for our code, data license notes, citations for all data and software | Eric Shi | Dec 3 | Not started | M3 |
| 17 | Reproducibility test | Fresh clone, clean install, full workflow run | Lyric Li | Dec 5 | Not started | M14 |
| 18 | Final report and release | Complete README.md and publish the final-project release | All | Dec 7 | Not started | |

## Constraints
The project faces several data quality and integration constraints across the ACS, BLS, and BEA datasets.

**Geographic consistency:** The ACS, BLS, and BEA datasets use different geographic reporting conventions. Our initial assessment identified 3,222 geographic units in ACS and BLS, compared with 3,127 in BEA. After excluding Puerto Rico, 53 ACS geographic units could not be directly matched to BEA records. These differences involve Connecticut's planning regions, Virginia's independent cities, and certain other county equivalents. To address this issue, we will standardize county FIPS codes across all three datasets and investigate unmatched geographic units before integration. Where geographic definitions cannot be reconciled, we will document the affected counties and determine whether to exclude them from the final analysis. We will also report the number of matched and unmatched counties to evaluate the coverage of our integrated dataset.

**Data completeness and reliability:** ACS contains missing values and special codes representing unavailable margins of error. BLS includes incomplete historical series for certain Alaska counties, while BEA contains zero-valued GDP observations requiring further interpretation. These issues may affect the completeness and reliability of county-level comparisons.

**Temporal comparability:** ACS 2024 5-Year Estimates represent pooled 2020–2024 survey data, whereas BLS and BEA provide annual observations from 2015–2024. The project must account for these differences when comparing pre-2020 economic conditions with subsequent migration patterns.

**Technical and ethical constraints:** Data acquisition depends on government API availability and credentials. Reproducibility requires consistent file formats, documented transformations, and integrity verification. Although the datasets contain aggregated public statistics, source-specific usage terms, attribution requirements, and limitations of statistical interpretation must be reviewed.


## Gaps
Initial data inspection identified several issues that require further investigation and resolution.

Geographic harmonization: We need to establish mapping rules for counties and county equivalents that do not match across datasets. In particular, BEA's reporting of certain Virginia localities and Connecticut's geographic changes require additional validation before integration.

Missing and invalid observations: The initial assessment found 20,592 missing ACS cells, concentrated in Puerto Rico, which is outside the planned study scope. We also identified incomplete BLS time series and 268 zero-valued BEA GDP records. Further profiling will determine how these observations should be excluded, flagged, or otherwise handled.

Statistical reliability: The ACS dataset includes margins of error, but thresholds for identifying unreliable estimates have not yet been established. We need to determine appropriate criteria for handling estimates from small counties and document their impact on the analysis.

Variable definitions: Interstate migration rates, real GDP growth, and demographic comparison measures have not yet been finalized. We will verify the relevant variable definitions and denominators to ensure consistency with the research questions.

Integration validation and documentation: The final integration schema, cleaning procedures, and quality thresholds remain under development. We will validate join coverage, duplicate records, missing values, and potential information loss, then document the resulting transformations and remaining limitations.
