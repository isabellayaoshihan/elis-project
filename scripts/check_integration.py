"""Check exported joins against raw data without using the integration functions.

Run after integrate_cleaned.py. Uses Python's csv/statistics modules so the
calculation and matching checks are independent of the pandas merge pipeline.
"""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with (ROOT / path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, label):
    check(actual != '' and math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-10), label)


def main():
    raw_acs = {r['county_fips']: r for r in read_csv('data/raw/acs_2024_county_full.csv')
               if not r['county_fips'].startswith('72')}
    raw_bea = read_csv('data/raw/bea_cagdp1_county.csv')
    gdp = {}
    for row in raw_bea:
        if row['LineCode'] == '1':
            key = (row['GeoFips'], int(row['TimePeriod']))
            check(key not in gdp, 'Duplicate raw BEA key')
            check(row['UNIT_MULT'] == '3' and '2017' in row['CL_UNIT'], 'Unexpected GDP units')
            gdp[key] = None if '(NA)' in row['NoteRef'] else float(row['DataValue'])
    rates = {}
    raw = json.loads((ROOT / 'data/raw/bls_laus_2015_2024_annual.json').read_text())
    for batch in raw:
        check(batch['status'] == 'REQUEST_SUCCEEDED', 'Failed BLS response')
        for series in batch['Results']['series']:
            sid = series['seriesID']
            if not sid.startswith('LAUCN') or not sid.endswith('03'):
                continue
            fips = sid[5:10]
            for point in series['data']:
                year = int(point['year'])
                if point['period'] == 'M13' and 2015 <= year <= 2019:
                    key = (fips, year)
                    value = float(point['value'])
                    check(key not in rates or rates[key] == value, 'Conflicting raw BLS rate')
                    rates[key] = value

    crosswalk = read_csv('data/processed/bea_fips_crosswalk.csv')
    mapping = {r['county_fips']: r for r in crosswalk if r['county_fips']}
    check(len(mapping) == sum(bool(r['county_fips']) for r in crosswalk), 'Duplicate crosswalk membership')
    check(set(mapping) == set(raw_acs), 'Crosswalk coverage differs from ACS')
    groups = defaultdict(list)
    for fips, row in mapping.items():
        check(row['county_name'] == raw_acs[fips]['NAME'], 'Crosswalk county-name mismatch')
        if row['match_type'] == 'direct':
            check(row['bea_fips'] == fips, 'Non-identical direct FIPS')
        else:
            groups[row['bea_fips']].append(fips)
    # Resolve every combined name independently, preserving county/city distinctions.
    for code, members in groups.items():
        row = mapping[members[0]]
        names = row['geo_name'].rsplit(', ', 1)[0].replace(' + ', ', ').split(', ')
        expected = []
        state = 'Hawaii' if code.startswith('15') else 'Virginia'
        for index, name in enumerate(names):
            county_name = (name + ' County' if index == 0 or state == 'Hawaii'
                           else name.removesuffix(' City') + ' city') + ', ' + state
            hits = [f for f, acs in raw_acs.items() if acs['NAME'] == county_name]
            check(len(hits) == 1, f'Ambiguous combined name: {county_name}')
            expected.extend(hits)
        check(set(expected) == set(members), f'Wrong crosswalk members: {code}')
        check(all(int(mapping[f]['n_counties_in_unit']) == len(members) for f in members), 'Wrong member count')

    audit = read_csv('data/integrated/county_join_audit.csv')
    screened = read_csv('data/integrated/county_screened.csv')
    excluded = read_csv('data/integrated/integration_exclusions.csv')
    review = {r['county_fips']: r for r in read_csv('quality_assessment/county_geography_review.csv')}
    check(len(audit) == len(raw_acs) == len({r['county_fips'] for r in audit}), 'Wrong audit cardinality')
    check({r['county_fips'] for r in audit} == set(raw_acs), 'Audit lost or added counties')
    expected_eligible = set()
    for row in audit:
        fips = row['county_fips']
        for column, value in raw_acs[fips].items():
            if column.endswith('M') and value == '-555555555':
                value = ''
            check(row[column] == value, f'ACS value changed: {fips}/{column}')
        annual = [rates[(fips, y)] for y in range(2015, 2020) if (fips, y) in rates]
        check(int(float(row['bls_years_2015_2019'] or 0)) == len(annual), f'Wrong year count: {fips}')
        if len(annual) == 5:
            close(row['unemployment_rate_mean_2015_2019_pct'], mean(annual), f'Wrong mean: {fips}')
        else:
            check(row['unemployment_rate_mean_2015_2019_pct'] == '', f'Partial window averaged: {fips}')
        xw = mapping[fips]
        check(row['bea_fips'] == xw['bea_fips'] and row['match_type'] == xw['match_type'], 'Wrong BEA match')
        valid_gdp = False
        if xw['match_type'] == 'direct':
            start, end = gdp[(fips, 2015)], gdp[(fips, 2019)]
            for year, value in [(2015, start), (2019, end)]:
                field = f'real_gdp_{year}_k_2017usd'
                if value is None:
                    check(row[field] == '', 'Missing GDP became a value')
                else:
                    close(row[field], value, f'Wrong raw GDP: {fips}/{year}')
            valid_gdp = start is not None and end is not None and start > 0 and end > 0
            if valid_gdp:
                close(row['real_gdp_cagr_2015_2019_pct'],
                      100 * math.expm1((math.log(end) - math.log(start)) / 4), f'Wrong CAGR: {fips}')
            else:
                check(row['real_gdp_cagr_2015_2019_pct'] == '', 'Unavailable growth filled')
        else:
            check(all(row[c] == '' for c in ['real_gdp_2015_k_2017usd',
                  'real_gdp_2019_k_2017usd', 'real_gdp_cagr_2015_2019_pct']), 'Combined GDP assigned to county')
        eligible = valid_gdp and len(annual) == 5 and review.get(fips, {}).get('decision') != 'exclude'
        check((row['screened_sample_eligible'] == 'True') == eligible, f'Wrong eligibility: {fips}')
        check((row['exclusion_reasons'] == '') == eligible, f'Wrong exclusion flag: {fips}')
        if eligible:
            expected_eligible.add(fips)
    check({r['county_fips'] for r in screened} == expected_eligible, 'Screened counties differ')
    check(len(screened) == len(expected_eligible), 'Duplicate screened counties')
    check({r['county_fips'] for r in excluded} == set(raw_acs) - expected_eligible, 'Exclusions differ')
    lookup = {r['county_fips']: r for r in audit}
    check(all(row == lookup[row['county_fips']] for row in screened), 'Screened cells differ from audit')
    check(len(review) == 79 and sum(r['decision'] == 'include' for r in review.values()) == 15,
          'Geography review does not cover the original flagged set')
    summary = {
        'result': 'passed', 'acs_rows_checked': len(audit), 'acs_columns_checked': len(next(iter(raw_acs.values()))),
        'raw_BLS_rate_observations_checked': sum(fips in raw_acs for fips, year in rates),
        'combined_BEA_units_checked': len(groups), 'combined_county_members_checked': sum(map(len, groups.values())),
        'screened_counties': len(screened), 'excluded_counties': len(excluded),
        'restored_after_geography_review': 15,
        'checks': ['Every ACS cell compared with raw data after documented MOE recoding',
                   'Every five-year rate mean recalculated from raw BLS JSON',
                   'Every GDP endpoint and CAGR checked against raw BEA CSV',
                   'Crosswalk membership, one-row-per-county joins and exclusion sets checked',
                   'Screened CSV matches the eligible subset of the audit CSV'],
        'output_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((ROOT / 'data/integrated').glob('*.csv'))}}
    (ROOT / 'quality_assessment/integration_verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
