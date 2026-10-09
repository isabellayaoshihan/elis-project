# Project Plan

## Overview
Lyric

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

The project will integrate three public U.S. government datasets at the county level. The datasets provide complementary demographic, labor-market, and economic information. County FIPS codes will be used as the primary geographic identifier for integration.

### 1. American Community Survey (ACS) 5-Year Estimates

- **Source:** U.S. Census Bureau
- **Dataset:** 2024 ACS 5-Year Detailed Tables
- **Geographic level:** County
- **Acquisition method:** Census Data API
- **Raw data location:** `data/raw/`

The ACS dataset provides demographic and socioeconomic characteristics for U.S. counties. The project uses variables from several detailed tables, including:

- `B01003`: Total population
- `B07001`: Geographic mobility by age
- `B07009`: Geographic mobility by educational attainment
- `B08301`: Means of transportation to work, including working from home

These variables will be used to examine population mobility, education, commuting behavior, and remote work across counties. The 2024 ACS 5-Year estimates represent data collected over the 2020–2024 period.

### 2. Bureau of Labor Statistics (BLS) Local Area Unemployment Statistics

- **Source:** U.S. Bureau of Labor Statistics
- **Dataset:** Local Area Unemployment Statistics (LAUS), County Annual Averages
- **Years:** 2015–2024
- **Geographic level:** County
- **Acquisition method:** BLS Public Data API
- **Raw data location:** `data/raw/`

The LAUS dataset provides county-level labor-market measures, including labor force, employment, unemployment, and unemployment rate. These data will be used to measure local labor-market conditions and compare unemployment outcomes across counties and over time.

### 3. Bureau of Economic Analysis (BEA) County GDP

- **Source:** U.S. Bureau of Economic Analysis
- **Dataset:** GDP by County (CAGDP1)
- **Years:** 2015–2024, subject to data availability
- **Geographic level:** County
- **Acquisition method:** BEA Data API
- **Raw data location:** `data/raw/`

The BEA dataset provides county-level measures of gross domestic product. It will be used to measure local economic performance and changes in GDP over time. Because BEA county-level releases may lag behind the other datasets, the final year included in the analysis will depend on data availability.

### Data Integration

The datasets will be standardized using five-digit county FIPS codes, constructed from state and county identifiers where necessary. BLS and BEA observations will also include a year variable because they contain multiple years of data.

The integrated dataset will allow the project to examine relationships among demographic and mobility characteristics, labor-market outcomes, and county-level economic performance.

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
| 6 | Profiling and pre-integration quality assessment | Profile each dataset; assess accuracy, completeness, timeliness, consistency | Eric Shi, Isabella Yao | Nov 2 | M10 |
| 7 | Data cleaning | Scripts that address each issue found in task 6 | Eric Shi | Nov 9 | M11, M12 |
| 8 | Data integration | Join cleaned datasets on county FIPS; document the integration schema | Lyric Li | Nov 14 | M7, M8 |
| 9 | Post-integration quality assessment | Same four dimensions on the integrated dataset | Eric Shi, Lyric Li | Nov 17 | M10 |
| 10 | Plan revision | Update ProjectPlan.md based on Milestone 2 feedback | All | Nov 17 | |
| 11 | Status report | StatusReport.md with each member's own contribution summary; publish the status-report release | All | Nov 19 | |
| 12 | Workflow automation | Snakemake or run_all script chaining single-purpose scripts from acquisition to analysis | Lyric Li | Nov 26 | M13 |
| 13 | Analysis and visualization | Answer the research questions with at least one visualization | Susu Tran | Nov 30 | |
| 14 | Environment and dependencies | requirements.txt, pip freeze output, relative paths throughout | Lyric Li | Dec 1 | M14 |
| 15 | Metadata and documentation | Data dictionary, DCAT or Schema.org metadata file | Susu Tran | Dec 3 | M15 |
| 16 | Licenses and references | License for our code, data license notes, citations for all data and software | Eric Shi, Susu Tran | Dec 3 | M3 |
| 17 | Reproducibility test | Fresh clone, clean install, full workflow run | Lyric Li | Dec 5 | M14 |
| 18 | Final report and release | Complete README.md and publish the final-project release | All | Dec 7 | |
## Constraints
Eric

## Gaps
Eric
