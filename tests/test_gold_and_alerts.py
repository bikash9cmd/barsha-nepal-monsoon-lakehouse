from datetime import date, timedelta

import pandas as pd
import pytest

from barsha.alerts import build_bulletin, ne_digits, render
from barsha.gold import build_gold_frames
from barsha.ingest import ingest
from barsha.source import LocalSource
from barsha.storage import LocalLake
from barsha.transform import build_year, load_silver

from .conftest import gsod_row, year_rows

KTM, OKH, JUM = "44454099999", "44462099999", "44424099999"


def _load(mirror, lake_dir, years):
    lake = LocalLake(lake_dir)
    ingest(LocalSource(mirror.root), lake, years)
    for y in years:
        assert not build_year(lake, y, "t").blocked
    return load_silver(lake)


@pytest.fixture
def history(mirror):
    """Ten years where every wet day is 10 mm, so each station's own extremes are known."""
    for y in range(2010, 2020):
        mirror.put(y, KTM, year_rows(KTM, y, wet_in=0.4))
        mirror.put(y, OKH, year_rows(OKH, y, wet_in=0.4))
    return list(range(2010, 2020))


def test_thresholds_use_only_earlier_years(mirror, lake_dir, history):
    # A huge 2020 day must not raise 2020's own threshold (that would hide it).
    mirror.put(2020, KTM, year_rows(KTM, 2020, {date(2020, 7, 1): 8.0}))
    mirror.put(2020, OKH, year_rows(OKH, 2020, {date(2020, 7, 1): 3.0}))  # a neighbour agrees
    silver = _load(mirror, lake_dir, history + [2020])
    rain = build_gold_frames(silver, date(2020, 12, 31))["rain_daily"]

    day = rain[(rain.station_id == KTM) & (rain.obs_date == "2020-07-01")].iloc[0]
    assert day["p99_wet_mm"] == pytest.approx(10.2, abs=0.1)
    assert day["prior_max_mm"] == pytest.approx(10.2, abs=0.1)
    assert day["alert_level"] == "red"  # 203 mm: very heavy and a station record
    assert day["is_station_record"]


def test_isolated_spike_is_held_as_suspect_but_corroborated_one_is_not(mirror, lake_dir, history):
    # Kathmandu: a 400 mm day with dry neighbours. Okhaldhunga (~130 km away) gets the same
    # in a later year, but Kathmandu has heavy rain the day before.
    mirror.put(2020, KTM, year_rows(KTM, 2020, {date(2020, 4, 19): 16.0, date(2020, 8, 14): 3.0}))
    mirror.put(2020, OKH, year_rows(OKH, 2020, {date(2020, 8, 15): 16.0}))
    silver = _load(mirror, lake_dir, history + [2020])
    rain = build_gold_frames(silver, date(2020, 12, 31))["rain_daily"]

    lonely = rain[(rain.station_id == KTM) & (rain.obs_date == "2020-04-19")].iloc[0]
    backed = rain[(rain.station_id == OKH) & (rain.obs_date == "2020-08-15")].iloc[0]
    assert lonely["alert_level"] == "suspect" and not lonely["is_station_record"]
    assert backed["alert_level"] == "red" and backed["neighbour_max_mm"] == pytest.approx(76.2)


def test_three_day_total_needs_three_complete_days(mirror, lake_dir):
    rows = year_rows(KTM, 2024, wet_every=1, wet_in=1.0)
    rows[9] = gsod_row(KTM, date(2024, 1, 10), 0.0, "I")
    mirror.put(2024, KTM, rows)
    rain = build_gold_frames(_load(mirror, lake_dir, [2024]), date(2024, 12, 31))["rain_daily"]
    by_day = rain.set_index("obs_date")["rain_3day_mm"]
    assert by_day[pd.Timestamp("2024-01-09")] == pytest.approx(76.2)
    assert pd.isna(by_day[pd.Timestamp("2024-01-11")])  # window includes the missing 10th
    assert by_day[pd.Timestamp("2024-01-13")] == pytest.approx(76.2)


def test_monsoon_total_withheld_when_too_many_days_missing(mirror, lake_dir):
    good = year_rows(KTM, 2023)
    gappy = year_rows(KTM, 2024)
    start = date(2024, 7, 1).timetuple().tm_yday - 1
    for i in range(start, start + 20):  # 20 monsoon days with no report
        d = date(2024, 1, 1) + timedelta(days=i)
        gappy[i] = gsod_row(KTM, d, 99.99, "", rain=True)
    mirror.put(2023, KTM, good)
    mirror.put(2024, KTM, gappy)
    season = build_gold_frames(_load(mirror, lake_dir, [2023, 2024]), date(2024, 12, 31))["monsoon_season"]
    s = season.set_index("year")
    assert s.loc[2023, "total_status"] == "published" and s.loc[2023, "jjas_total_mm"] > 0
    assert s.loc[2024, "total_status"] == "withheld: 102 of 122 days complete"
    assert pd.isna(s.loc[2024, "jjas_total_mm"])
    assert s.loc[2024, "missing_on_rain_days"] == 20


def test_station_rename_creates_a_new_dimension_version(mirror, lake_dir):
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    renamed = [r.replace("TRIBHUVAN INTERNATIONAL, NP", "KATHMANDU TIA, NP") for r in year_rows(KTM, 2025)]
    mirror.put(2025, KTM, renamed)
    dim = build_gold_frames(_load(mirror, lake_dir, [2024, 2025]), date(2025, 12, 31))["station_dim"]
    assert list(dim["station_name"]) == ["TRIBHUVAN INTERNATIONAL, NP", "KATHMANDU TIA, NP"]
    assert list(dim["is_current"]) == [False, True]
    assert dim.iloc[0]["valid_to"] == pd.Timestamp("2024-12-31")


def test_lone_station_extreme_goes_to_review_not_public(mirror, lake_dir, history):
    """With no neighbour to confirm it, even a real record is held for a person to check."""
    mirror.put(2020, KTM, year_rows(KTM, 2020, {date(2020, 7, 1): 8.0}))
    mirror.put(2020, OKH, year_rows(OKH, 2020))  # reporting, but dry that day
    silver = _load(mirror, lake_dir, history + [2020])
    frames = build_gold_frames(silver, date(2020, 7, 1))
    b = build_bulletin(frames["rain_daily"], frames["station_health"], date(2020, 7, 1))
    assert [(a["type"], a["audience"]) for a in b["alerts"]] == [("SUSPECT_VALUE", "operator")]


def test_bulletin_flags_extreme_rain_and_stale_feed(mirror, lake_dir, history):
    mirror.put(2020, KTM, year_rows(KTM, 2020, {date(2020, 7, 1): 8.0}))
    mirror.put(2020, OKH, year_rows(OKH, 2020, {date(2020, 7, 1): 3.0}))
    silver = _load(mirror, lake_dir, history + [2020])

    on_the_day = build_gold_frames(silver, date(2020, 7, 1))
    b = build_bulletin(on_the_day["rain_daily"], on_the_day["station_health"], date(2020, 7, 1))
    assert [(a["type"], a["station_id"]) for a in b["alerts"]] == [("EXTREME_RAIN", KTM), ("EXTREME_RAIN", OKH)]
    assert "203 mm" in b["alerts"][0]["en"] and "२०३ मिमि" in b["alerts"][0]["ne"]
    assert "Wettest day in this station's record" in b["alerts"][0]["en"]

    later = date(2021, 3, 1)
    frames = build_gold_frames(silver, later)
    b = build_bulletin(frames["rain_daily"], frames["station_health"], later)
    assert [a["type"] for a in b["alerts"]] == ["SOURCE_STALE"]
    assert b["source_lag_days"] == 60


def test_stale_feed_keeps_its_lag_after_every_station_retires(mirror, lake_dir):
    """A feed that stopped long ago retires every station at once; the page must still say how long."""
    mirror.put(2020, KTM, year_rows(KTM, 2020))
    mirror.put(2020, OKH, year_rows(OKH, 2020))
    years_later = date(2024, 6, 1)
    frames = build_gold_frames(_load(mirror, lake_dir, [2020]), years_later)
    assert set(frames["station_health"]["status"]) == {"retired"}

    b = build_bulletin(frames["rain_daily"], frames["station_health"], years_later)
    assert b["source_lag_days"] == (years_later - date(2020, 12, 31)).days
    assert [a["type"] for a in b["alerts"]] == ["SOURCE_STALE"]
    assert f"for {b['source_lag_days']} days (newest day 2020-12-31)" in b["alerts"][0]["en"]
    assert "None" not in render(b)


def test_empty_lake_says_there_is_no_data(lake_dir):
    frames = build_gold_frames(load_silver(LocalLake(lake_dir)), date(2024, 9, 28))
    b = build_bulletin(frames["rain_daily"], frames["station_health"], date(2024, 9, 28))
    assert b["source_lag_days"] is None
    assert [a["type"] for a in b["alerts"]] == ["SOURCE_STALE"]
    assert "no station data" in b["alerts"][0]["en"]
    assert "None" not in render(b) and "source lag: no data" in render(b)


def test_one_station_silent_while_others_report(mirror, lake_dir):
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    mirror.put(2024, JUM, year_rows(JUM, 2024)[:300])
    frames = build_gold_frames(_load(mirror, lake_dir, [2024]), date(2024, 12, 31))
    b = build_bulletin(frames["rain_daily"], frames["station_health"], date(2024, 12, 31))
    assert [(a["type"], a["station_id"]) for a in b["alerts"]] == [("STATION_SILENT", JUM)]


def test_nepali_digits():
    assert ne_digits("2024-09-28") == "२०२४-०९-२८"
