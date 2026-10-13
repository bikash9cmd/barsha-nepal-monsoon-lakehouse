"""Turn one raw GSOD CSV into typed rows in metric units, keeping what the source flags mean."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .config import (
    INCH_TO_MM,
    PRCP_FLAG_COMPLETE,
    PRCP_FLAG_MISSING,
    PRCP_FLAG_PARTIAL,
    PRCP_MISSING,
    TEMP_MISSING,
)

SOURCE_COLUMNS = [
    "STATION", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION", "NAME",
    "TEMP", "MAX", "MIN", "PRCP", "PRCP_ATTRIBUTES", "FRSHTT",
]

SILVER_SCHEMA = {
    "station_id": "string",
    "obs_date": "datetime64[ms]",
    "station_name": "string",
    "latitude": "float64",
    "longitude": "float64",
    "elevation_m": "float64",
    "tavg_c": "float64",
    "tmax_c": "float64",
    "tmin_c": "float64",
    "prcp_reported_mm": "float64",
    "prcp_mm": "float64",
    "prcp_flag": "string",
    "prcp_quality": "string",
    "rain_observed": "boolean",
    "thunder_observed": "boolean",
}


class SourceFormatError(ValueError):
    pass


def _number(series: pd.Series, missing: float) -> pd.Series:
    values = pd.to_numeric(series.str.strip(), errors="coerce")
    return values.mask(np.isclose(values, missing))


def _f_to_c(series: pd.Series) -> pd.Series:
    return ((series - 32.0) * 5.0 / 9.0).round(2)


def classify_precip(flag: pd.Series, value_in: pd.Series) -> pd.Series:
    """complete / partial / missing for each day's precipitation.

    A 0.00 with flag I (no precipitation report at all) or H (rain seen, amount not
    reported) is not a dry day. Treating it as one silently lowers every total.
    """
    flag = flag.fillna("").str.strip()
    quality = pd.Series("missing", index=flag.index, dtype="string")
    quality[flag.isin(PRCP_FLAG_COMPLETE)] = "complete"
    quality[flag.isin(PRCP_FLAG_PARTIAL)] = "partial"
    quality[flag.isin(PRCP_FLAG_MISSING) | value_in.isna()] = "missing"
    return quality


def parse_gsod(data: bytes) -> pd.DataFrame:
    if not data.strip():
        raise SourceFormatError("empty file")
    raw = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    missing = [c for c in SOURCE_COLUMNS if c not in raw.columns]
    if missing:
        raise SourceFormatError(f"missing columns: {missing}")

    prcp_in = _number(raw["PRCP"], PRCP_MISSING)
    flag = raw["PRCP_ATTRIBUTES"].str.strip()
    quality = classify_precip(flag, prcp_in)
    frshtt = raw["FRSHTT"].str.strip().str.zfill(6)

    out = pd.DataFrame(
        {
            "station_id": raw["STATION"].str.strip(),
            "obs_date": pd.to_datetime(raw["DATE"].str.strip(), format="%Y-%m-%d", errors="coerce"),
            "station_name": raw["NAME"].str.strip(),
            "latitude": pd.to_numeric(raw["LATITUDE"], errors="coerce"),
            "longitude": pd.to_numeric(raw["LONGITUDE"], errors="coerce"),
            "elevation_m": pd.to_numeric(raw["ELEVATION"], errors="coerce"),
            "tavg_c": _f_to_c(_number(raw["TEMP"], TEMP_MISSING)),
            "tmax_c": _f_to_c(_number(raw["MAX"], TEMP_MISSING)),
            "tmin_c": _f_to_c(_number(raw["MIN"], TEMP_MISSING)),
            "prcp_reported_mm": (prcp_in * INCH_TO_MM).round(1),
            "prcp_flag": flag.replace("", pd.NA),
            "prcp_quality": quality,
            "rain_observed": frshtt.str[1] == "1",
            "thunder_observed": frshtt.str[4] == "1",
        }
    )
    out["prcp_mm"] = out["prcp_reported_mm"].where(out["prcp_quality"] == "complete")
    return out[list(SILVER_SCHEMA)].astype(SILVER_SCHEMA)
