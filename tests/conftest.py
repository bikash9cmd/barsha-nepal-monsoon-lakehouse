"""Helpers that write files in the exact GSOD CSV layout, so tests never touch the network."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

HEADER = (
    '"STATION","DATE","LATITUDE","LONGITUDE","ELEVATION","NAME","TEMP","TEMP_ATTRIBUTES",'
    '"DEWP","DEWP_ATTRIBUTES","SLP","SLP_ATTRIBUTES","STP","STP_ATTRIBUTES","VISIB",'
    '"VISIB_ATTRIBUTES","WDSP","WDSP_ATTRIBUTES","MXSPD","GUST","MAX","MAX_ATTRIBUTES",'
    '"MIN","MIN_ATTRIBUTES","PRCP","PRCP_ATTRIBUTES","SNDP","FRSHTT"'
)

STATIONS = {
    # id: (name, lat, lon)
    "44454099999": ("TRIBHUVAN INTERNATIONAL, NP", 27.696592, 85.359192),
    "44462099999": ("OKHALDHUNGA, NP", 27.3, 86.5),
    "44424099999": ("JUMLA, NP", 29.2833333, 82.1666667),
}


def gsod_row(station: str, day: date, prcp_in: float = 0.0, flag: str = "G", *,
             temp_f: float = 68.0, max_f: float = 77.0, min_f: float = 59.0,
             rain: bool | None = None, name: str | None = None) -> str:
    st_name, lat, lon = STATIONS.get(station, ("SOMEWHERE, NP", 27.0, 85.0))
    rain = (prcp_in > 0 and prcp_in != 99.99) if rain is None else rain
    frshtt = f"0{int(rain)}0000"
    return (
        f'"{station}","{day.isoformat()}","{lat}","{lon}","1338.07","{name or st_name}",'
        f'"{temp_f:6.1f}","24","  45.4","24","9999.9"," 0","999.9"," 0","  4.4","24",'
        f'"  3.5","24","  8.9","999.9","{max_f:6.1f}","*","{min_f:6.1f}","*",'
        f'"{prcp_in:5.2f}","{flag}","999.9","{frshtt}"'
    )


def gsod_file(rows: list[str]) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def year_rows(station: str, year: int, rain_by_date: dict[date, float] | None = None,
              wet_every: int = 3, wet_in: float = 0.4) -> list[str]:
    """A full year: a modest wet day every few days, plus any specific days given."""
    rain_by_date = rain_by_date or {}
    rows, day = [], date(year, 1, 1)
    while day.year == year:
        prcp = rain_by_date.get(day, wet_in if day.timetuple().tm_yday % wet_every == 0 else 0.0)
        rows.append(gsod_row(station, day, prcp))
        day += timedelta(days=1)
    return rows


class Mirror:
    """A local folder laid out like s3://noaa-gsod-pds."""

    def __init__(self, root: Path):
        self.root = root

    def put(self, year: int, station: str, rows: list[str]) -> None:
        folder = self.root / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{station}.csv").write_bytes(gsod_file(rows))


@pytest.fixture
def mirror(tmp_path) -> Mirror:
    return Mirror(tmp_path / "mirror")


@pytest.fixture
def lake_dir(tmp_path) -> Path:
    return tmp_path / "lake"
