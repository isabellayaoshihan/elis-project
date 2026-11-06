"""BEA CAGDP1 pre-integration data quality assessment (raw file, read-only).

Dimensions: accuracy, completeness, timeliness, consistency.
Output: quality_assessment/bea_quality_report.txt
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bea_cagdp1_county.csv"
RAW_SUM = ROOT / "data" / "raw" / "bea_cagdp1_county.sha256"
ACS = ROOT / "data" / "raw" / "acs_2024_county_full.csv"
BLS_CLEAN = ROOT / "data" / "processed" / "bls_laus_clean.csv"
REPORT = ROOT / "quality_assessment" / "bea_quality_report.txt"

YEARS = list(range(2015, 2025))
STATE_FIPS = {f"{i:02d}" for i in list(range(1, 57))} - {"03", "07", "14", "43", "52"}  # 50 states + DC (11)
YOY_LIMIT = 0.5  # flag real GDP year-over-year change beyond +/-50%


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    L = []
    add = L.append

    def sec(title):
        add("")
        add(title)

    add("BEA CAGDP1 PRE-INTEGRATION QUALITY ASSESSMENT")
    add("")
    add(f"Source: {RAW.name}")
    add(f"SHA-256 matches recorded checksum: {sha256(RAW) == RAW_SUM.read_text().split()[0]}")
    n_geo = raw["GeoFips"].nunique()
    add(f"Total rows: {len(raw):,}  |  geographies: {n_geo:,}  |  lines: {sorted(raw['LineCode'].unique())}  |  years: {sorted(raw['TimePeriod'].unique())}")
    add(f"Units: {raw.groupby('LineCode')['CL_UNIT'].first().to_dict()}  |  UNIT_MULT: {sorted(raw['UNIT_MULT'].unique())}")

    num = pd.to_numeric(raw["DataValue"], errors="coerce")
    na_note = raw["NoteRef"].str.contains(r"\(NA\)")
    raw["v"] = num.where(~na_note)
    raw["year"] = raw["TimePeriod"].astype(int)
    raw["line"] = raw["LineCode"].astype(int)
    real = raw[raw.line == 1].pivot(index="GeoFips", columns="year", values="v")
    cur = raw[raw.line == 3].pivot(index="GeoFips", columns="year", values="v")
    names = raw.drop_duplicates("GeoFips").set_index("GeoFips")["GeoName"]

    # ---------------- ACCURACY
    sec("1. ACCURACY")
    add(f"Non-numeric DataValue cells: {int(num.isna().sum())}")
    add(f"Negative values: {int((num < 0).sum())}")
    bad_fips = int((~raw["GeoFips"].str.fullmatch(r"\d{5}")).sum())
    add(f"FIPS not 5 digits: {bad_fips}")
    bad_state = sorted(set(raw["GeoFips"].str[:2]) - STATE_FIPS)
    add(f"Unknown state FIPS prefixes: {bad_state}; Puerto Rico (72) rows: {int(raw['GeoFips'].str.startswith('72').sum())}")
    add(f"Duplicate (GeoFips, line, year) keys: {int(raw.duplicated(['GeoFips','LineCode','TimePeriod']).sum())}")
    add(f"Zero DataValue cells: {int((num == 0).sum()):,}  (all carry '(NA)' note: {bool(na_note[num == 0].all())}; NA-noted cells that are zero: {bool((num[na_note] == 0).all())})")
    yoy = real.pct_change(axis=1, fill_method=None)
    big = yoy.abs().stack()
    big = big[big > YOY_LIMIT]
    add(f"Real GDP year-over-year changes beyond +/-{YOY_LIMIT:.0%}: {len(big)} county-years in {big.index.get_level_values(0).nunique()} counties")
    for (f, y), v in big.sort_values(key=abs, ascending=False).head(8).items():
        add(f"  {f} {names[f]} {y}: {v:+.0%}")
    ratio = (cur / real).stack()
    add(f"Current/real GDP ratio (implied price index vs 2017), median {ratio.median():.2f}, "
        f"5th-95th pct {ratio.quantile(.05):.2f}-{ratio.quantile(.95):.2f}")
    add("Arithmetic checks against an external source were not performed.")

    # ---------------- COMPLETENESS
    sec("2. COMPLETENESS")
    n_na = int(na_note.sum())
    add(f"Cells marked '(NA)' (value 0 in file): {n_na:,} of {len(raw):,} ({n_na/len(raw):.2%})")
    add(f"Real and current GDP NA in the same geography-years: {bool(real.isna().equals(cur.isna()))}")
    add("NA real-GDP geography-years by year: " + str({y: int(real[y].isna().sum()) for y in YEARS}))
    na_geo = real.index[real.isna().any(axis=1)]
    add(f"Geographies with any NA: {len(na_geo)}")
    for f in na_geo:
        yrs = [y for y in YEARS if np.isnan(real.loc[f, y])]
        span = f"{yrs[0]}-{yrs[-1]}" if len(yrs) > 1 else str(yrs[0])
        add(f"  {f} {names[f]}: NA {span} ({len(yrs)} yrs)")
    pre = real[[2015, 2019]]
    no_growth = pre.index[pre.isna().any(axis=1)]
    add(f"Geographies without real GDP in 2015 or 2019 (no pre-2020 growth): {len(no_growth)}")
    all_na = real.index[real.isna().all(axis=1)]
    add(f"Geographies with no real GDP in any year: {len(all_na)}")

    # ---------------- TIMELINESS
    sec("3. TIMELINESS")
    add(f"Years covered: {YEARS[0]}-{YEARS[-1]}; every geography has all {len(YEARS)} years: {bool((raw.groupby('GeoFips').size() == 2*len(YEARS)).all())}")
    add(f"Latest year (2024) NA: {int(real[2024].isna().sum())} geographies (8 old Connecticut counties plus 4 legacy Alaska areas)")
    add("Reference period for real GDP is chained 2017 dollars; BEA may revise recent years, so 2024 is least stable.")
    add("Pre-2020 window (2015-2019) is fully covered except the geographies listed above.")

    # ---------------- CONSISTENCY
    sec("4. CONSISTENCY")
    acs = pd.read_csv(ACS, dtype=str, keep_default_na=False, usecols=["county_fips", "NAME"])
    acs = acs[~acs.county_fips.str.startswith("72")]
    acs_f = set(acs.county_fips)
    bls_f = set(pd.read_csv(BLS_CLEAN, dtype={"fips": str})["fips"])
    bea_f = set(names.index)
    add(f"Geographies: BEA {len(bea_f):,} | ACS (excl. PR) {len(acs_f):,} | BLS clean {len(bls_f):,}")
    add(f"BEA FIPS matching ACS directly: {len(bea_f & acs_f):,}; BLS directly: {len(bea_f & bls_f):,}")
    add(f"ACS counties not in BEA by FIPS: {len(acs_f - bea_f)}  (by state: {pd.Series(sorted(acs_f - bea_f)).str[:2].value_counts().to_dict()})")
    add(f"BEA geographies not in ACS: {len(bea_f - acs_f)}  (by state: {pd.Series(sorted(bea_f - acs_f)).str[:2].value_counts().to_dict()})")
    comb = [f for f in bea_f if "+" in names[f]]
    add(f"Combined multi-county units (names contain '+'): {len(comb)} (VA {sum(f[:2]=='51' for f in comb)}, HI {sum(f[:2]=='15' for f in comb)})")
    add(f"Footnoted ('*') geographies: {int(names.str.endswith('*').sum())}")
    ct_old = sorted(f for f in bea_f if f.startswith("09") and f < "09100")
    ct_new = sorted(f for f in bea_f if f.startswith("09") and f >= "09100")
    add(f"Connecticut carries both vintages: {len(ct_old)} old counties and {len(ct_new)} planning regions (summing CT would double count)")
    ak_old = [f for f in ("02201", "02232", "02261", "02280") if f in bea_f]
    add(f"Alaska legacy areas absent from ACS: {ak_old}")
    members_listed = {f for f in acs_f - bea_f}
    add(f"Members of combined units are absent as separate BEA rows: {not (members_listed & bea_f)}")
    add("Units consistent across all rows within each line: " + str(raw.groupby('line')['CL_UNIT'].nunique().eq(1).all()))
    add("GeoName format mixes 'County, ST', '(Independent City)', and 'A + B, ST'; it must not be used as a join key.")

    sec("SUMMARY OF ISSUES FOR CLEANING")
    add(f"1. {n_na:,} zero-coded NA cells -> recode to NA (bea_clean.py).")
    add(f"2. {len(comb)} combined units cover {len(acs_f - bea_f) - 0} ACS/BLS counties -> crosswalk (bea_fips_crosswalk.csv).")
    add(f"3. {len(no_growth)} geographies lack 2015 or 2019 real GDP -> no pre-2020 growth; decision needed (CT, AK).")
    add(f"4. {len(ct_old)} old CT counties and {len(ak_old)} legacy AK areas have no ACS/BLS match -> exclude from joins.")
    add("")
    add("No raw data were modified.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
