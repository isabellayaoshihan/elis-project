# Status Report: County Economic Conditions and Interstate Migration

- **Team:** Isabella Yao, Eric Shi, Susu Tran, Lyric Li
- **Milestone:** 3 (Interim Status Report)
- **Status as of:** November 12, 2026

We have acquired, assessed, and cleaned all three datasets, and the first version of the integrated table is complete: 3,080 of 3,144 counties have complete records from all three sources. The post-integration quality assessment is in progress. Workflow automation, analysis, and documentation are scheduled for late November and early December.

## 1. Progress on Planned Tasks

Task numbers below match the timeline in Section 2.

### Tasks 1 and 2: Project plan and lifecycle mapping (completed)

The [project plan](ProjectPlan.md) defines our research questions, datasets, and timeline, and maps our workflow to the DataONE data lifecycle.

### Task 3: Data acquisition (completed)

Each source has its own acquisition script, and each raw file has a SHA-256 checksum stored next to it.

| Source | Script | Raw file | Size |
|---|---|---|---|
| ACS 2024 5-Year | [`acquire_acs.py`](scripts/acquire_acs.py) | [`acs_2024_county_full.csv`](data/raw/acs_2024_county_full.csv) | 3,222 rows, 312 columns |
| BLS LAUS | [`acquire_bls.py`](scripts/acquire_bls.py) | [`bls_laus_2015_2024_annual.json`](data/raw/bls_laus_2015_2024_annual.json) | 12,884 series, requested in 258 batches |
| BEA CAGDP1 | [`acquire_bea.py`](scripts/acquire_bea.py) | [`bea_cagdp1_county.csv`](data/raw/bea_cagdp1_county.csv) | 62,540 rows |

### Tasks 4 and 5: Storage, organization, and licensing (completed)

The repository is organized by curation stage, as described in the [project plan](ProjectPlan.md#storage-and-organization). All three sources are public domain U.S. government works. API keys are excluded from the repository through [`.gitignore`](.gitignore).

### Tasks 6 and 7: Quality assessment and cleaning (completed)

Each source has a quality assessment script and a separate cleaning script. Every cleaning step responds to an issue found in the assessment, and raw files are never modified.

**ACS** ([assessment script](scripts/acs_quality_assessment.py), [quality report](quality_assessment/acs_quality_report.txt), [cleaning script](scripts/acs_clean.py), [cleaning report](quality_assessment/acs_cleaning_report.txt), [cleaned file](data/processed/acs_2024_county_clean.csv))

| Issue found | Action taken |
|---|---|
| Most of the 20,592 blank cells were in the 78 Puerto Rico rows, which are outside our scope | Removed Puerto Rico, leaving 3,144 counties |
| Some margins of error are published as the code -555555555 | Stored 3,308 such cells as blank so they are never read as numbers |

**BLS LAUS** ([assessment script](scripts/bls_quality_assessment.py), [quality report](quality_assessment/bls_quality_report.txt), [cleaning script](scripts/bls_clean.py), [cleaning report](quality_assessment/bls_cleaning_report.txt), [cleaned file](data/processed/bls_laus_clean.csv))

| Issue found | Action taken |
|---|---|
| Each series ID combines the county FIPS code and a measure code | Split the ID and reshaped the data to 31,430 county-year rows with one column per measure |
| Puerto Rico is outside our scope | Removed |
| A few Alaska areas lack some years | Kept as missing; counties without all five 2015 to 2019 rates are excluded at integration |

**BEA CAGDP1** ([assessment script](scripts/bea_quality_assessment.py), [quality report](quality_assessment/bea_quality_report.txt), [cleaning script](scripts/bea_clean.py), [cleaning report](quality_assessment/bea_cleaning_report.txt), [cleaned file](data/processed/bea_cagdp1_clean.csv))

| Issue found | Action taken |
|---|---|
| 268 suppressed values (0.43%) are stored as zero | Recoded as missing |
| 24 geographic units combine several counties | Mapped the 24 units to 53 ACS counties in a [crosswalk](data/processed/bea_fips_crosswalk.csv) without splitting their GDP |
| 77 county-years show real GDP changes beyond ±50% | Kept as published; to be checked for influence during analysis |

### Task 8: Data integration (first version completed)

[`integrate_cleaned.py`](scripts/integrate_cleaned.py) runs in four steps:

1. Reruns the three cleaning scripts in a temporary folder and confirms that every cleaned file is reproduced exactly.
2. Computes each county's mean unemployment rate and real GDP growth for 2015 to 2019.
3. Applies the [county geography review](quality_assessment/county_geography_review.csv), which records a decision and official source for 79 counties whose geography differs across sources. Of these, 64 are excluded and 15 are kept.
4. Joins the economic measures to ACS on county FIPS with one-to-one checks.

The outputs are a [screened analysis table](data/integrated/county_screened.csv) of 3,080 counties, an [all-county audit table](data/integrated/county_join_audit.csv), and a [list of the 64 exclusions](data/integrated/integration_exclusions.csv) with reasons. A separate script, [`check_integration.py`](scripts/check_integration.py), recalculates every predictor from the raw files without using the integration code and confirms that all ACS values are unchanged. All checks passed ([verification results](quality_assessment/integration_verification.json), [integration report](quality_assessment/integration_recheck.md)).

### Task 9: Post-integration quality assessment (in progress)

This assessment covers what the integration checks do not: data vintages and timeliness, how the 64 excluded counties differ from the retained ones, reliability flags for small counties with large margins of error, and an overall judgment of whether the integration succeeded. Target date: November 17.

### Task 10: Plan revision (completed)

We revised the [project plan](ProjectPlan.md) in response to Milestone 2 feedback. Section 3 describes the changes.

### Task 11: Status report (in progress)

This report. Each member is adding their own contribution summary in Section 5.

### Tasks 12 to 18 (not started)

Workflow automation, analysis, dependency files, metadata, licenses, reproducibility testing, and the final report are scheduled in Section 2.

## 2. Updated Timeline

| # | Task | Owner | Target date | Status |
|---|---|---|---|---|
| 1 | Project plan | All | Oct 12 | Completed |
| 2 | Lifecycle mapping | Susu Tran | Oct 12 | Completed |
| 3 | Data acquisition | Isabella Yao, Susu Tran | Oct 11 | Completed |
| 4 | Storage and organization | Isabella Yao, Susu Tran | Oct 12 | Completed |
| 5 | Ethics and licensing review | Susu Tran | Oct 12 | Completed |
| 6 | Pre-integration quality assessment | Eric Shi, Isabella Yao, Susu Tran | Nov 6 | Completed |
| 7 | Data cleaning | Eric Shi, Isabella Yao, Susu Tran | Nov 6 | Completed |
| 8 | Data integration | Eric Shi | Nov 12 | Completed |
| 9 | Post-integration quality assessment | Lyric Li | Nov 17 | In progress |
| 10 | Plan revision | Lyric Li | Nov 12 | Completed |
| 11 | Status report | All | Nov 19 | In progress |
| 12 | Workflow automation | Lyric Li | Nov 26 | Not started |
| 13 | Analysis and visualization | Susu Tran | Nov 30 | Not started |
| 14 | Environment and dependencies | Lyric Li | Dec 1 | Not started |
| 15 | Metadata and documentation | Susu Tran | Dec 3 | Not started |
| 16 | Licenses and references | Eric Shi | Dec 3 | Not started |
| 17 | Reproducibility test | Lyric Li | Dec 5 | Not started |
| 18 | Final report and release | All | Dec 7 | Not started |

Integration finished two days ahead of schedule. All remaining tasks are on track for the December 7 deadline.

## 3. Changes to the Project Plan

### Changes based on Milestone 2 feedback

**Feedback: "The national scale is ambitious. Be sure to account for data quality consistencies across counties and jurisdictions."**

We added a section to the plan, [Consistency Across Counties and Jurisdictions](ProjectPlan.md#consistency-across-counties-and-jurisdictions), with two parts:

- **Geographic consistency.** A table lists each jurisdiction where the three agencies define counties differently (Virginia, Connecticut, Hawaii, and Alaska), what differs, and our decision. It explains why we exclude 64 counties instead of splitting or combining data, and commits us to comparing excluded and retained counties so that any bias from the exclusions is reported.
- **Measurement consistency.** A table lists issues that make a measure less reliable in some counties than in others and how we handle each. The largest is ACS sampling error: the interstate in-migrant estimate has a coefficient of variation above 40% in 784 of 3,144 counties. We will weight counties by population in the main analysis and rerun it without these 784 counties as a robustness check.

**Feedback: "Revise for clarity and relevance."**

We rewrote the Overview, Team, Storage and Organization, and Timeline sections. The revisions use shorter sentences, replace general statements with specific variables, file paths, and counts, and remove passages that repeated earlier sections. For example, the storage description is now a folder tree, and each timeline task now has a status.

### Changes based on our progress

- **Team roles** now match the work each member has done. Eric Shi leads integration, and Lyric Li leads workflow automation and reproducibility.
- **Integration outputs** are three files instead of one: a screened analysis table, an all-county audit table, and an exclusion list. The geography review is stored in `quality_assessment/` with the other quality reports.
- **Exclusion rule.** A county enters the analysis only if it has all five annual unemployment rates for 2015 to 2019 and real GDP for both 2015 and 2019 at the county level. We do not average partial windows or assign combined-unit GDP to individual counties.

## 4. Challenges and How We Addressed Them

**Different county definitions across agencies.** BEA combines 51 Virginia counties and independent cities into 23 units, reports Connecticut's new planning regions only from 2024, and combines Maui and Kalawao in Hawaii. Two Alaska areas were created in 2019. We reviewed all 79 affected counties against official Census and BEA documentation and recorded each decision with its source. Splitting combined GDP would require assumptions we cannot verify, so we excluded 64 counties and kept 15 whose changes happened before 2015.

**Missing values stored as numbers.** BEA stores 268 suppressed GDP values as zero, and ACS publishes some margins of error as -555555555. Left unchanged, both would distort averages and growth rates. We recoded them as missing during cleaning, and the integration checks confirm that no missing value became a number.

**Unreliable estimates in small counties.** About a quarter of counties have large sampling error in the ACS in-migration estimate, and 37 report zero in-migrants. Dropping them would remove much of rural America from the sample. Our plan is to weight by population and run a robustness check without these counties. The post-integration assessment (Task 9) will flag them in the data.

**Mixed time structures.** ACS pools 2020 to 2024 responses into one estimate, while LAUS and BEA report each year separately. We summarize LAUS and BEA to 2015 to 2019 measures so that the predictors come before the outcome period, and we require complete data for that window.

**BLS API limits.** The BLS API accepts 50 series per request, and we needed 12,884 series. The acquisition script sends 258 batches with a short pause between requests and saves all responses in one JSON file with a checksum.

**Keeping the repository reproducible.** An early version of the joined table was uploaded manually without a script, and one cleaned ACS file was briefly duplicated in the repository root. We replaced the manual table with outputs from `integrate_cleaned.py`, moved every file into its stage folder, and removed the duplicates. All scripts read FIPS codes as text so leading zeros are not lost.

## 5. Individual Contributions

### Isabella Yao
I reviewed and updated the Datasets section of the [project plan](ProjectPlan.md#datasets) to clarify the data sources, time coverage, variables, and geographic identifiers used for integration. I conducted the pre-integration data quality assessment of the BLS LAUS dataset ([assessment script](scripts/bls_quality_assessment.py), [quality report](quality_assessment/bls_quality_report.txt)), identifying issues related to missing values, county FIPS codes, and data completeness. Based on the assessment results, I developed the [BLS cleaning script](scripts/bls_clean.py) to restructure the raw data into county-year records, exclude Puerto Rico, and handle missing observations, producing the [cleaned BLS dataset](data/processed/bls_laus_clean.csv).


### Eric Shi

### Susu Tran

### Lyric Li：
I revised the [project plan](ProjectPlan.md) in response to the Milestone 2 feedback, adding the Consistency Across Counties and Jurisdictions section, which explains the exclusion of 64 counties, and rewriting the Overview, Team, Storage, and Timeline sections for clarity. I compiled this status report, linking each task to its artifacts and showing how each cleaning step addresses an issue found in the assessment. I am now leading the post-integration quality assessment (Task 9).
