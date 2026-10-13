from datetime import date

import pytest

from barsha.parse import SourceFormatError, parse_gsod

from .conftest import gsod_file, gsod_row

KTM = "44454099999"


def test_units_and_sentinels():
    df = parse_gsod(gsod_file([
        gsod_row(KTM, date(2024, 9, 28), 7.64, "G", temp_f=64.1, max_f=66.2, min_f=61.9),
        gsod_row(KTM, date(2024, 9, 29), 99.99, "", max_f=9999.9),
    ]))
    flood, missing = df.iloc[0], df.iloc[1]
    assert flood["prcp_mm"] == pytest.approx(194.1)
    assert flood["tmax_c"] == pytest.approx(19.0)
    assert flood["prcp_quality"] == "complete"
    assert missing["prcp_quality"] == "missing"
    assert missing["prcp_mm"] is None or missing["prcp_mm"] != missing["prcp_mm"]  # null
    assert missing["tmax_c"] != missing["tmax_c"]  # 9999.9 became null, not 5537 C


@pytest.mark.parametrize("flag, quality", [
    ("G", "complete"), ("D", "complete"), ("F", "complete"),
    ("A", "partial"), ("B", "partial"), ("C", "partial"), ("E", "partial"),
    ("H", "missing"), ("I", "missing"),
])
def test_precip_flags(flag, quality):
    df = parse_gsod(gsod_file([gsod_row(KTM, date(2020, 7, 1), 0.0, flag)]))
    assert df.loc[0, "prcp_quality"] == quality
    # Only complete days carry a usable prcp_mm; the reported value is always kept.
    assert (df.loc[0, "prcp_mm"] == 0.0) == (quality == "complete")
    assert df.loc[0, "prcp_reported_mm"] == 0.0


def test_flag_i_zero_is_not_a_dry_day():
    """The trap: 0.00 with flag I means 'no report', and summing it as 0 mm understates rain."""
    df = parse_gsod(gsod_file([gsod_row(KTM, date(2001, 7, 15), 0.0, "I")]))
    assert df.loc[0, "prcp_quality"] == "missing"
    assert df["prcp_mm"].isna().all()


def test_weather_flags():
    df = parse_gsod(gsod_file([gsod_row(KTM, date(2024, 9, 28), 7.64, "G", rain=True)]))
    assert bool(df.loc[0, "rain_observed"]) is True
    assert bool(df.loc[0, "thunder_observed"]) is False


def test_rejects_empty_and_changed_layout():
    with pytest.raises(SourceFormatError):
        parse_gsod(b"")
    with pytest.raises(SourceFormatError, match="PRCP"):
        parse_gsod(b'"STATION","DATE","NAME"\n"1","2024-01-01","X, NP"\n')
