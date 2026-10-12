# Project Plan

## Overview
This project asks whether local economic conditions shaped where Americans moved in the early 2020s. Specifically, we test whether county labor-market conditions from 2015 through 2019 (unemployment and GDP growth) predict interstate in-migration from 2020 through 2024, and whether in-migrants differ from existing residents in education and age.

We will integrate three public U.S. government datasets at the county level: the Census Bureau's American Community Survey 2024 5-Year Estimates for in-migration by age and education, remote work, and population; the Bureau of Labor Statistics' Local Area Unemployment Statistics for annual unemployment and labor force; and the Bureau of Economic Analysis' county GDP table (CAGDP1) for economic growth. The sources link through five-digit county FIPS codes, with year as a second key for the annual series.

Since this is a data curation project, our approach centers on the curation chain. We will acquire each dataset programmatically with SHA-256 integrity checks, assess quality across accuracy, completeness, timeliness, and consistency, and clean the specific issues we find, such as Connecticut's shift to planning regions, BEA's combined Virginia independent cities, ACS margins of error in small counties, and the mismatch between pooled and annual periods. We will then integrate the cleaned data, reassess its quality, and run the analysis, all automated through a Snakemake workflow or run-all script so the results can be reproduced from a fresh clone.

## Team
| Member | GitHub | Role | Planned responsibilities | Project plan section |
|---|---|---|---|---|
| Isabella Yao | @isabellayaoshihan | Data Acquisition Lead | Acquisition scripts for all three sources with SHA-256 checks; storage and folder organization; source documentation | Datasets |
| Lyric Li | @ZehuiLi123 | Integration and Workflow Lead | FIPS-based integration and integration schema; Snakemake or run_all workflow; reproducibility testing; release management | Overview |
| Eric Shi | @HongyouEric | Data Quality and Compliance Lead | Pre- and post-integration quality assessment; cleaning scripts; license and terms of use review | Constraints, Gaps |
| Susu Tran | @susutran | Analysis and Documentation Lead | Research questions; analysis and visualization; data dictionary and metadata file; final README coordination | Research or Business Question(s) |

All members contribute to each milestone report and commit their own work, so individual contributions are visible in the Git history.


## Research Questions
Susu


## Datasets
The project will integrate three public U.S. government datasets at the county or county-equivalent level. The datasets provide complementary demographic, labor-market, and economic information. Geographic identifiers (County FIPS codes) will be harmonized before integration because some source-specific geographic definitions do not map one-to-one across all years and datasets.

### 1. American Community Survey (ACS) 5-Year Estimates

- **Source:** U.S. Census Bureau
- **Dataset:** 2024 ACS 5-Year Detailed Tables
- **Geographic level:** County
- **Acquisition method:** Census Data API
- **Raw data location:** `data/raw/`

The ACS dataset provides demographic, mobility, and commuting characteristics for U.S. counties and county equivalents. The project uses variables from several detailed tables:

- `B01003`: Total population
- `B07001`: Geographic mobility by age
- `B07009`: Geographic mobility by educational attainment
- `B08301`: Means of transportation to work, including working from home

The 2024 ACS 5-Year Estimates pool survey observations across 2020–2024. The mobility tables describe mobility status relative to residence one year earlier, so they will be treated as pooled early-2020s mobility estimates rather than cumulative five-year migration totals.

The analysis will focus on the 50 states and District of Columbia. Puerto Rico will be excluded because the ACS uses separate Puerto Rico versions of the mobility tables and the project's research question focuses on interstate migration.

### 2. Bureau of Labor Statistics (BLS) Local Area Unemployment Statistics

- **Source:** U.S. Bureau of Labor Statistics
- **Dataset:** Local Area Unemployment Statistics (LAUS), County Annual Averages
- **Years:** 2015–2024, subject to source-specific geographic availability
- **Geographic level:** County
- **Acquisition method:** BLS Public Data API
- **Raw data location:** `data/raw/`

The LAUS dataset provides annual-average county-level labor-market measures, including labor force, employment, unemployment, and unemployment rate. The primary analysis will use 2015–2019 unemployment rates to represent pre-2020 local labor-market conditions, while later years will remain available for descriptive or sensitivity analyses.

### 3. Bureau of Economic Analysis (BEA) County GDP

- **Source:** U.S. Bureau of Economic Analysis
- **Dataset:** GDP by County (CAGDP1)
- **Years:** 2015–2024, subject to data availability
- **Geographic level:** County
- **Acquisition method:** BEA Data API
- **Raw data location:** `data/raw/`

The BEA dataset provides county-level GDP measures. The acquisition script retains both real GDP and current-dollar GDP. Real GDP will be used to calculate economic growth because it allows growth to be compared without changes in the general price level being interpreted as real economic growth.

The primary analysis will summarize real GDP growth during 2015–2019 as a measure of pre-2020 county economic performance.

### Data Integration

The datasets will be standardized using five-digit county FIPS codes, constructed from state and county identifiers where necessary. BLS and BEA observations will also include a year variable because both datasets contain annual observations from 2015 through 2024. These two datasets can therefore be integrated using county FIPS code and year.

The ACS data differ because the 2024 5-Year estimates summarize characteristics over the 2020–2024 period rather than providing a separate observation for each year. ACS variables will therefore be treated as county-level demographic and socioeconomic characteristics and linked to the BLS and BEA data using county FIPS codes.

Together, the three datasets provide complementary information: ACS describes county demographic and socioeconomic characteristics, BLS measures labor-market outcomes, and BEA measures local economic performance. The integrated dataset will allow the project to examine relationships among population mobility, education, commuting and remote-work patterns, unemployment, and county-level economic performance.

### Data Acquisition and API Access

Data will be acquired programmatically using Python scripts stored in the `scripts/` directory. Each data source will have a separate acquisition script, and SHA-256 hashes will be used to support data-integrity checks.

API credentials will not be committed to the repository. Credentials are stored locally in `api_keys.txt`, which is excluded from version control through `.gitignore`.

Users reproducing the project can obtain their own API credentials from the following official registration pages:

- Census API key: https://api.census.gov/data/key_signup.html
- BLS Public Data API registration: https://data.bls.gov/registrationEngine/
- BEA API key registration: https://apps.bea.gov/api/signup/

Raw data retrieved by the acquisition scripts will be stored in `data/raw/` and preserved before subsequent cleaning and integration steps.

## Timeline
| # | Task | Description | Owner | Target date | Module |
|---|---|---|---|---|---|
| 1 | Project plan | Write ProjectPlan.md and publish the project-plan release | All | Oct 12 | |
| 2 | Lifecycle mapping | Relate the project to a data lifecycle model | Susu Tran | Oct 19 | M1 |
| 3 | Data acquisition | One script per source with SHA-256 integrity checks; commit raw data to the repository | Isabella Yao | Oct 19 | M4 |
| 4 | Storage and organization | Folder structure, naming conventions, file formats | Isabella Yao | Oct 21 | M2 |
| 5 | Ethics and licensing review | Document license and terms of use for every source | Eric Shi | Oct 23 | M3 |
| 6 | Profiling and pre-integration quality assessment | Profile each dataset; assess accuracy, completeness, timeliness, consistency | Eric Shi | Nov 2 | M10 |
| 7 | Data cleaning | Scripts that address each issue found in task 6 | Eric Shi | Nov 9 | M11, M12 |
| 8 | Data integration | Join cleaned datasets on county FIPS; document the integration schema | Lyric Li | Nov 14 | M7, M8 |
| 9 | Post-integration quality assessment | Same four dimensions on the integrated dataset |  Lyric Li | Nov 17 | M10 |
| 10 | Plan revision | Update ProjectPlan.md based on Milestone 2 feedback | All | Nov 17 | |
| 11 | Status report | StatusReport.md with each member's own contribution summary; publish the status-report release | All | Nov 19 | |
| 12 | Workflow automation | Snakemake or run_all script chaining single-purpose scripts from acquisition to analysis | Lyric Li | Nov 26 | M13 |
| 13 | Analysis and visualization | Answer the research questions with at least one visualization | Susu Tran | Nov 30 | |
| 14 | Environment and dependencies | requirements.txt, pip freeze output, relative paths throughout | Lyric Li | Dec 1 | M14 |
| 15 | Metadata and documentation | Data dictionary, DCAT or Schema.org metadata file | Susu Tran | Dec 3 | M15 |
| 16 | Licenses and references | License for our code, data license notes, citations for all data and software | Eric Shi | Dec 3 | M3 |
| 17 | Reproducibility test | Fresh clone, clean install, full workflow run | Lyric Li | Dec 5 | M14 |
| 18 | Final report and release | Complete README.md and publish the final-project release | All | Dec 7 | |
## Constraints
The project faces several data quality and integration constraints across the ACS, BLS, and BEA datasets.

Geographic consistency: The datasets use different geographic reporting conventions. The initial assessment identified 3,222 geographic units in ACS and BLS, compared with 3,127 in BEA. After excluding Puerto Rico, 53 ACS geographic units cannot be directly matched to BEA records. Differences involving Virginia independent cities, Hawaii, and Connecticut's transition to planning regions require careful FIPS harmonization.

Data completeness and reliability: ACS contains missing values and special codes representing unavailable margins of error. BLS includes incomplete historical series for certain Alaska counties, while BEA contains zero-valued GDP observations requiring further interpretation. These issues may affect the completeness and reliability of county-level comparisons.

Temporal comparability: ACS 2024 5-Year Estimates represent pooled 2020–2024 survey data, whereas BLS and BEA provide annual observations from 2015–2024. The project must account for these differences when comparing pre-2020 economic conditions with subsequent migration patterns.

Technical and ethical constraints: Data acquisition depends on government API availability and credentials. Reproducibility requires consistent file formats, documented transformations, and integrity verification. Although the datasets contain aggregated public statistics, source-specific usage terms, attribution requirements, and limitations of statistical interpretation must be reviewed.

## Gaps
Initial data inspection identified several issues that require further investigation and resolution.

Geographic harmonization: We need to establish mapping rules for counties and county equivalents that do not match across datasets. In particular, BEA's reporting of certain Virginia localities and Connecticut's geographic changes require additional validation before integration.

Missing and invalid observations: The initial assessment found 20,592 missing ACS cells, concentrated in Puerto Rico, which is outside the planned study scope. We also identified incomplete BLS time series and 268 zero-valued BEA GDP records. Further profiling will determine how these observations should be excluded, flagged, or otherwise handled.

Statistical reliability: The ACS dataset includes margins of error, but thresholds for identifying unreliable estimates have not yet been established. We need to determine appropriate criteria for handling estimates from small counties and document their impact on the analysis.

Variable definitions: Interstate migration rates, real GDP growth, and demographic comparison measures have not yet been finalized. We will verify the relevant variable definitions and denominators to ensure consistency with the research questions.

Integration validation and documentation: The final integration schema, cleaning procedures, and quality thresholds remain under development. We will validate join coverage, duplicate records, missing values, and potential information loss, then document the resulting transformations and remaining limitations.
