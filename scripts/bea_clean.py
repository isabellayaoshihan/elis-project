"""Clean BEA county GDP (CAGDP1) so it can be joined to the cleaned BLS and ACS tables.

Input : data/raw/bea_cagdp1_county.csv (long, one row per county x line x year)
Output: data/processed/bea_cagdp1_clean.csv      one row per BEA geography-year
        data/processed/bea_fips_crosswalk.csv    BEA geography -> ACS/BLS county FIPS
        quality_assessment/bea_cleaning_report.txt

Raw data are never modified. No imputation is performed.
"""
import hashlib
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bea_cagdp1_county.csv"
RAW_SUM = ROOT / "data" / "raw" / "bea_cagdp1_county.sha256"
ACS = ROOT / "data" / "raw" / "acs_2024_county_full.csv"
OUT_DIR = ROOT / "data" / "processed"
REPORT = ROOT / "quality_assessment" / "bea_cleaning_report.txt"

YEARS = list(range(2015, 2025))
LINES = {1: "real_gdp_k_2017usd", 3: "current_gdp_k_usd"}  # thousands of dollars (UNIT_MULT = 3)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def acs_counties():
    acs = pd.read_csv(ACS, dtype=str, keep_default_na=False, usecols=["county_fips", "NAME"])
    acs = acs[~acs["county_fips"].str.startswith("72")]  # Puerto Rico out of scope
    return acs.set_index("county_fips")["NAME"]


def combined_members(geo_name, state_name, acs_names):
    """Map a combined BEA unit ('Albemarle + Charlottesville, VA*') to ACS county FIPS.
    BEA lists the county first, then the independent cities merged into it."""
    body = re.sub(r",\s*[A-Z]{2}\*?$", "", geo_name)
    tokens = [t.strip() for t in re.split(r",|\+", body) if t.strip()]
    fips = []
    for i, tok in enumerate(tokens):
        if state_name == "Hawaii":
            target = f"{tok} County, Hawaii"
        elif i == 0:
            target = f"{tok} County, {state_name}"
        else:
            tok = re.sub(r"\s+City$", "", tok)
            target = f"{tok} city, {state_name}"
        hit = acs_names.index[acs_names == target].tolist()
        if len(hit) != 1:
            raise ValueError(f"Cannot resolve '{tok}' in '{geo_name}' (target '{target}', hits {hit})")
        fips.append(hit[0])
    return fips


def main():
    # 0. Integrity check on the raw file
    recorded = RAW_SUM.read_text().split()[0]
    if sha256(RAW) != recorded:
        raise ValueError("BEA raw file does not match its recorded checksum.")

    raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    n_raw = len(raw)

    # 1. Structure checks
    assert raw["GeoFips"].str.fullmatch(r"\d{5}").all()
    assert set(raw["LineCode"].astype(int)) == set(LINES)
    assert set(raw["UNIT_MULT"]) == {"3"}
    assert not raw.duplicated(["GeoFips", "LineCode", "TimePeriod"]).any()
    assert set(raw["TimePeriod"].astype(int)) == set(YEARS)

    # 2. BEA uses 0 with note "(NA) *" for withheld/not-available values -> NA, not a real zero
    na_mask = raw["NoteRef"].str.contains(r"\(NA\)", regex=True)
    assert (raw.loc[na_mask, "DataValue"] == "0").all()
    assert not ((raw["DataValue"] == "0") & ~na_mask).any(), "Zero values without an (NA) note"
    raw["value"] = pd.to_numeric(raw["DataValue"])
    raw.loc[na_mask, "value"] = float("nan")
    n_na = int(na_mask.sum())

    # 3. Puerto Rico out of scope (none present in this pull, kept for safety)
    raw = raw[~raw["GeoFips"].str.startswith("72")]

    # 4. Pivot real / current GDP side by side
    raw["year"] = raw["TimePeriod"].astype(int)
    raw["measure"] = raw["LineCode"].astype(int).map(LINES)
    wide = raw.pivot(index=["GeoFips", "year"], columns="measure", values="value")[list(LINES.values())]
    names = (raw.drop_duplicates("GeoFips").set_index("GeoFips")["GeoName"])
    foot = raw.groupby("GeoFips")["GeoName"].first().str.endswith("*")
    wide = wide.reset_index().rename(columns={"GeoFips": "bea_fips"})
    wide["geo_name"] = wide["bea_fips"].map(names).str.rstrip("*")
    wide["bea_footnoted"] = wide["bea_fips"].map(foot)   # BEA flags geography changes/combinations with '*'
    wide["real_gdp_missing"] = wide["real_gdp_k_2017usd"].isna()

    # 5. Crosswalk BEA geography -> ACS/BLS county FIPS
    acs_names = acs_counties()
    state_names = acs_names.str.rsplit(", ", n=1).str[-1]
    rows = []
    for fips in sorted(names.index):
        if fips in acs_names.index:
            rows.append((fips, fips, "direct"))
        elif "+" in names[fips]:
            st = state_names[acs_names.index[acs_names.index.str[:2] == fips[:2]][0]]
            for m in combined_members(names[fips], st, acs_names):
                rows.append((fips, m, "combined_unit"))
        else:
            rows.append((fips, "", "no_acs_match"))
    xw = pd.DataFrame(rows, columns=["bea_fips", "county_fips", "match_type"])
    xw["geo_name"] = xw["bea_fips"].map(names).str.rstrip("*")
    xw["county_name"] = xw["county_fips"].map(acs_names).fillna("")
    xw["n_counties_in_unit"] = xw.groupby("bea_fips")["county_fips"].transform("size")

    mapped = xw[xw["county_fips"] != ""]
    assert not mapped.duplicated("county_fips").any(), "An ACS county maps to two BEA units"
    uncovered = sorted(set(acs_names.index) - set(mapped["county_fips"]))

    # 6. Validate and save
    assert not wide.duplicated(["bea_fips", "year"]).any()
    assert len(wide) == names.size * len(YEARS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    wide = wide[["bea_fips", "geo_name", "year", *LINES.values(), "real_gdp_missing", "bea_footnoted"]]
    wide.to_csv(OUT_DIR / "bea_cagdp1_clean.csv", index=False)
    xw.to_csv(OUT_DIR / "bea_fips_crosswalk.csv", index=False)

    # 7. Pre-2020 growth readiness (what RQ1 needs): real GDP present in both 2015 and 2019
    r = wide.pivot(index="bea_fips", columns="year", values="real_gdp_k_2017usd")
    no_growth = r[r[2015].isna() | r[2019].isna()].index
    ng = xw[xw["bea_fips"].isin(no_growth)].drop_duplicates("bea_fips")
    by_state = ng["bea_fips"].str[:2].value_counts().to_dict()
    ng_in_acs = xw[xw["bea_fips"].isin(no_growth) & (xw["county_fips"] != "")]
    unit_rows = xw[xw["match_type"] == "combined_unit"]

    lines = [
        "BEA CAGDP1 cleaning and validation",
        f"Raw checksum validation: PASS",
        f"Raw rows: {n_raw:,} (2 lines x {names.size:,} geographies x {len(YEARS)} years)",
        f"Zero values recoded to NA ('(NA)' note): {n_na:,} ({n_na // 2:,} geography-years per line)",
        f"Cleaned rows (one per geography-year): {len(wide):,}",
        f"Real GDP missing geography-years: {int(wide['real_gdp_missing'].sum()):,}",
        "",
        f"Crosswalk: {xw['match_type'].eq('direct').sum():,} direct, "
        f"{unit_rows['bea_fips'].nunique()} combined units covering {len(unit_rows)} ACS counties, "
        f"{xw['match_type'].eq('no_acs_match').sum()} BEA units with no ACS match",
        f"ACS/BLS counties (excl. PR) covered by crosswalk: {len(mapped):,} of {len(acs_names):,}",
        f"ACS/BLS counties not covered: {uncovered}",
        "",
        "Units without real GDP in 2015 or 2019 (no pre-2020 growth), by state FIPS: "
        f"{by_state}",
        f"  ...of which map to an ACS county: {ng_in_acs['county_fips'].nunique()} counties "
        f"({', '.join(sorted(ng_in_acs['geo_name'].unique()))})",
        "",
        "Notes",
        "Values are thousands of dollars (UNIT_MULT = 3); real = chained 2017 dollars.",
        "Combined units (VA cities + HI Maui/Kalawao) report one GDP for several ACS/BLS counties.",
        "Level GDP must not be copied to members; a growth rate can be, but this is a group decision.",
        "Connecticut planning regions only have real GDP for 2024; old CT counties stop at 2023.",
        "Read with dtype={'bea_fips': str, 'county_fips': str} to keep leading zeros.",
        "No imputation or outlier removal was applied.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
