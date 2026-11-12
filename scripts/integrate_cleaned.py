"""Recheck cleaned inputs and join county-level pre-2020 predictors to ACS.

Run: python scripts/integrate_cleaned.py
No API access needed. Raw and processed inputs are never overwritten.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data/processed'
OUT = ROOT / 'data/integrated'
QA = ROOT / 'quality_assessment'
REVIEW = QA / 'county_geography_review.csv'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inputs = sorted((ROOT / 'data/raw').glob('*')) + sorted(PROCESSED.glob('*.csv')) + [REVIEW]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in inputs if p.is_file()}
    # Verify all stored raw checksums, including BLS (its cleaner only records it).
    for name in ['acs_2024_county_full', 'bea_cagdp1_county', 'bls_laus_2015_2024_annual']:
        suffix = '.json' if name.startswith('bls') else '.csv'
        require(digest(ROOT / 'data/raw' / (name + suffix)) ==
                (ROOT / 'data/raw' / (name + '.sha256')).read_text().split()[0],
                f'Raw checksum mismatch: {name}')
    # Rebuild in isolation and compare every cell, including missing values.
    with tempfile.TemporaryDirectory(prefix='is477-recheck-') as directory:
        tmp = Path(directory)
        for folder in ['data', 'scripts']:
            shutil.copytree(ROOT / folder, tmp / folder)
        for source in ['acs', 'bls', 'bea']:
            subprocess.run([sys.executable, str(tmp / 'scripts' / f'{source}_clean.py')],
                           cwd=tmp, check=True, capture_output=True, text=True)
        for name in ['acs_2024_county_clean.csv', 'bls_laus_clean.csv',
                     'bea_cagdp1_clean.csv', 'bea_fips_crosswalk.csv']:
            pd.testing.assert_frame_equal(pd.read_csv(PROCESSED / name, dtype=str),
                                          pd.read_csv(tmp / 'data/processed' / name, dtype=str))

    acs = pd.read_csv(PROCESSED / 'acs_2024_county_clean.csv',
                      dtype={'county_fips': str, 'state': str, 'county': str})
    for column in acs:
        if column.startswith('B') and column.endswith(('E', 'M')):
            acs[column] = acs[column].astype('Int64')
    bls = pd.read_csv(PROCESSED / 'bls_laus_clean.csv', dtype={'fips': str})
    bea = pd.read_csv(PROCESSED / 'bea_cagdp1_clean.csv', dtype={'bea_fips': str})
    xw = pd.read_csv(PROCESSED / 'bea_fips_crosswalk.csv',
                     dtype={'bea_fips': str, 'county_fips': str})
    review = pd.read_csv(REVIEW, dtype={'county_fips': str, 'bea_fips': str})
    require(review.county_fips.is_unique, 'Duplicate geography review decisions')
    require(review.decision.isin(['include', 'exclude']).all(), 'Invalid review decision')
    reviewed_inclusions = set(review.loc[review.decision.eq('include'), 'county_fips'])
    reviewed_exclusions = set(review.loc[review.decision.eq('exclude'), 'county_fips'])
    for frame, key in [(acs, ['county_fips']), (bls, ['fips', 'year']),
                       (bea, ['bea_fips', 'year'])]:
        require(not frame.duplicated(key).any(), f'Duplicate keys: {key}')
        require(frame[key[0]].str.fullmatch(r'\d{5}').all(), 'Invalid FIPS')
    require(np.allclose((bls.employed + bls.unemployed).dropna(),
                        bls.loc[bls.employed.notna() & bls.unemployed.notna(), 'labor_force']),
            'BLS employment identity failed')
    rate_error = (100 * bls.unemployed / bls.labor_force - bls.unemployment_rate).abs()
    require(rate_error.dropna().le(0.050001).all(), 'BLS rates inconsistent with counts')
    estimates = [c for c in acs if c.endswith('E') and c.startswith('B')]
    require(acs[estimates].notna().all().all() and acs[estimates].ge(0).all().all(),
            'ACS missing/negative estimates')
    require(bea.real_gdp_missing.equals(bea.real_gdp_k_2017usd.isna()), 'BEA NA flag mismatch')

    # Five published annual rates are required; never average partial windows.
    pre = bls.loc[bls.year.between(2015, 2019)]
    labor = pre.groupby('fips').unemployment_rate.agg(['count', 'mean']).reset_index()
    labor.columns = ['county_fips', 'bls_years_2015_2019', 'unemployment_rate_mean_2015_2019_pct']
    labor.loc[labor.bls_years_2015_2019.ne(5), 'unemployment_rate_mean_2015_2019_pct'] = np.nan

    # Only one-to-one geographies get county GDP. Combined-unit GDP is not allocated.
    direct = xw.loc[xw.match_type.eq('direct')].copy()
    endpoints = bea.pivot(index='bea_fips', columns='year', values='real_gdp_k_2017usd')
    econ = endpoints[[2015, 2019]].rename(columns={
        2015: 'real_gdp_2015_k_2017usd', 2019: 'real_gdp_2019_k_2017usd'}).reset_index()
    econ = econ.merge(bea[['bea_fips', 'bea_footnoted']].drop_duplicates(),
                      on='bea_fips', validate='one_to_one')
    econ = direct[['county_fips', 'bea_fips']].merge(econ, on='bea_fips', validate='one_to_one')
    valid = econ.real_gdp_2015_k_2017usd.gt(0) & econ.real_gdp_2019_k_2017usd.gt(0)
    econ['real_gdp_cagr_2015_2019_pct'] = np.nan
    econ.loc[valid, 'real_gdp_cagr_2015_2019_pct'] = 100 * (
        (econ.loc[valid, 'real_gdp_2019_k_2017usd'] /
         econ.loc[valid, 'real_gdp_2015_k_2017usd']) ** (1 / 4) - 1)
    mapped = xw.loc[xw.county_fips.notna(), ['county_fips', 'match_type', 'bea_fips']]
    require(not mapped.county_fips.duplicated().any(), 'Crosswalk is ambiguous')
    joined = acs.merge(labor, on='county_fips', how='left', validate='one_to_one')
    joined = joined.merge(econ.drop(columns='bea_fips'), on='county_fips', how='left', validate='one_to_one')
    joined = joined.merge(mapped, on='county_fips', how='left', validate='one_to_one')
    joined['acs_period'] = '2020-2024 pooled; mobility refers to residence one year earlier'

    def reasons(row):
        result = []
        if row.match_type != 'direct':
            result.append('combined_BEA_geography' if row.match_type == 'combined_unit' else 'no_BEA_match')
        if pd.isna(row.unemployment_rate_mean_2015_2019_pct):
            result.append('incomplete_BLS_2015_2019')
        if row.match_type == 'direct' and pd.isna(row.real_gdp_cagr_2015_2019_pct):
            result.append('missing_BEA_GDP_endpoints')
        # Historical footnotes cleared in the sourced county review are allowed.
        if (row.match_type == 'direct' and row.bea_footnoted == True
                and row.county_fips not in reviewed_inclusions
                and row.county_fips not in reviewed_exclusions):
            result.append('BEA_geography_footnote_needs_review')
        if row.county_fips in reviewed_exclusions and not result:
            result.append('excluded_after_geography_review')
        return ';'.join(result)

    joined['exclusion_reasons'] = joined.apply(reasons, axis=1)
    joined['geography_review'] = joined.county_fips.map(review.set_index('county_fips').decision).fillna('not_flagged')
    joined['screened_sample_eligible'] = joined.exclusion_reasons.eq('')
    screened = joined.loc[joined.screened_sample_eligible].copy()
    excluded = joined.loc[~joined.screened_sample_eligible, [
        'county_fips', 'NAME', 'bea_fips', 'match_type', 'bls_years_2015_2019',
        'bea_footnoted', 'exclusion_reasons']]
    require(len(joined) == len(acs) and joined.county_fips.is_unique, 'Join changed ACS cardinality')
    require(len(screened) + len(excluded) == len(acs), 'Disposition does not reconcile')
    require(screened[['unemployment_rate_mean_2015_2019_pct',
                      'real_gdp_cagr_2015_2019_pct']].notna().all().all(), 'Incomplete screened predictors')
    require(reviewed_inclusions.issubset(set(screened.county_fips)), 'Reviewed inclusions not restored')
    require(all(digest(ROOT / p) == value for p, value in hashes.items()), 'Input modified')
    OUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    for name, frame in [('county_join_audit.csv', joined), ('county_screened.csv', screened),
                        ('integration_exclusions.csv', excluded)]:
        frame.to_csv(OUT / name, index=False)
        reloaded = pd.read_csv(OUT / name, dtype={'county_fips': str, 'state': str, 'county': str,
                                                'bea_fips': str}, keep_default_na=True, low_memory=False)
        require(reloaded.county_fips.tolist() == frame.county_fips.tolist(), 'CSV lost FIPS')
    counts = excluded.exclusion_reasons.str.split(';').explode().value_counts().to_dict()
    manifest = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'input_sha256': hashes, 'acs_rows': len(acs), 'bls_rows': len(bls), 'bea_rows': len(bea),
                'screened_rows': len(screened), 'held_out_rows': len(excluded), 'reason_counts_overlap': counts}
    (QA / 'integration_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    report = f'''# County data integration

Source commit: `{manifest['source_commit']}`. Run `python scripts/integrate_cleaned.py` from the repository root (Python, pandas and NumPy required).

Then run `python scripts/check_integration.py`. This separate check reads the exported CSVs and independently recalculates the predictors from raw BLS JSON and BEA CSV. It also compares all 312 original ACS fields, checks combined-area membership and reconciles the included and excluded county sets. Its result is saved in `integration_verification.json`.

## Recheck results

- All three raw-file checksums match the stored records.
- Rerunning the cleaners reproduces every cleaned-data and crosswalk cell.
- ACS: {len(acs):,} rows, {len(acs.columns)} columns, unique county keys, no missing or negative estimates.
- BLS: {len(bls):,} county-year rows; unique keys. Employment plus unemployment equals labor force; published rates reconcile within 0.05 percentage point rounding.
- BEA: {len(bea):,} geography-year rows; unique keys and missing-GDP flags reconcile. Missing-value codes remain missing, not zero.
- Integration leaves all raw and cleaned inputs unchanged.

These checks establish internal consistency and reproducibility of the stored extraction. They do not independently verify every published value against current agency data. The older BEA quality report says BLS has 3,144 units; the current cleaned BLS file has {bls.fips.nunique():,}. Kalawao (15005) is absent from BLS.

## Join and output

ACS remains one row per county with all original estimate and MOE columns. BLS is summarized to the mean of all five 2015–2019 published annual unemployment rates. BEA growth is `100 * ((GDP2019 / GDP2015) ** (1/4) - 1)`, using real GDP in thousands of chained 2017 dollars. Both predictors are percentages. ACS is a pooled 2020–2024 estimate, not cumulative migration or an annual outcome.

The one-to-one left joins retain {len(joined):,} ACS rows. The screened table has {len(screened):,} rows and two complete economic predictors. {len(excluded):,} counties are held out with explicit reasons. No missing values are imputed. The audit table includes held-out records and must not be used as the screened analysis sample.

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
'''
    (QA / 'integration_recheck.md').write_text(report)
    print(json.dumps({k: v for k, v in manifest.items() if k != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
