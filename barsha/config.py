"""Constants and environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

# NOAA Global Surface Summary of the Day, mirrored on the AWS Open Data registry.
# One CSV per station per year: s3://noaa-gsod-pds/<year>/<station>.csv
SOURCE_BUCKET = "noaa-gsod-pds"
SOURCE_REGION = "us-east-1"

# Nepal's synoptic stations sit in WMO block 44, numbers 444xx.
NEPAL_STATION_PREFIX = "444"
FIRST_YEAR = 1976

INCH_TO_MM = 25.4

# GSOD sentinels for "no value".
PRCP_MISSING = 99.99
TEMP_MISSING = 9999.9

# GSOD precipitation flags (see docs/DATA.md).
PRCP_FLAG_COMPLETE = {"D", "F", "G"}  # a full 24 hours of reports
PRCP_FLAG_PARTIAL = {"A", "B", "C", "E"}  # fewer than 24 hours of reports: a lower bound
PRCP_FLAG_MISSING = {"H", "I"}  # a 0.00 that does not mean "no rain"

# June to September.
MONSOON_DAYS = 122
MIN_SEASON_COMPLETENESS = 0.9

# Below this, a day is not alerted however rare it is for the station.
MIN_RELATIVE_ALERT_MM = 50.0

# A single day this many times the station's own 99.9th percentile is held back as suspect.
SUSPECT_MULTIPLE = 3.0

# Source health.
STALE_AFTER_DAYS = 3
RETIRED_AFTER_DAYS = 3 * 365

# A rebuilt year that loses more than this share of rows is quarantined, not published.
MAX_ROW_DROP = 0.10


@dataclass(frozen=True)
class Settings:
    lake: str
    source: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            lake=os.environ.get("BARSHA_LAKE", "lake"),
            source=os.environ.get("BARSHA_SOURCE", f"s3://{SOURCE_BUCKET}"),
        )
