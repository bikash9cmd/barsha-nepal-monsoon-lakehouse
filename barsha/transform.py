"""Silver: rebuild one year partition from every raw station file for that year.

The unit of work is the year, not the row. Upstream replaces a whole station-year file when
anything changes, so rebuilding the partition from its raw files is idempotent and needs no
MERGE. A year that fails the quality gate keeps its last good silver file; its raw files are
copied to quarantine/ for a person to look at.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from .parse import SILVER_SCHEMA, SourceFormatError, parse_gsod
from .quality import Check, QualityReport, run_checks
from .storage import Lake, read_arrow, read_json, write_arrow, write_json

log = logging.getLogger(__name__)

SILVER_ROWS_KEY = "_state/silver_rows.json"


def silver_key(year: int) -> str:
    return f"silver/daily_weather/year={year}/data.parquet"


def build_year(lake: Lake, year: int, run_id: str) -> QualityReport:
    raw_keys = [k for k in lake.list(f"raw/gsod/year={year}/") if k.endswith(".csv")]
    frames, unreadable = [], []
    for key in raw_keys:
        try:
            frame = parse_gsod(lake.read_bytes(key))
            frame["source_file"] = key
            frames.append(frame)
        except SourceFormatError as exc:
            unreadable.append(f"{key}: {exc}")

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(SILVER_SCHEMA))
    row_counts = read_json(lake, SILVER_ROWS_KEY, default={})
    clean, report = run_checks(df, year, row_counts.get(str(year)))
    report.checks.insert(0, Check("raw_files_parse", "error", len(unreadable), "; ".join(unreadable)))

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    write_json(lake, f"quality/run={run_id}/year={year}.json", report.to_dict())

    if report.blocked:
        for key in raw_keys:
            lake.write_bytes(f"quarantine/{stamp}/{key}", lake.read_bytes(key))
        log.warning("year %s quarantined: %s", year, [c.name for c in report.checks if not c.passed])
        return report

    clean = clean.sort_values(["station_id", "obs_date"]).reset_index(drop=True)
    write_arrow(lake, silver_key(year), to_arrow(clean))
    row_counts[str(year)] = len(clean)
    write_json(lake, SILVER_ROWS_KEY, row_counts)
    return report


def to_arrow(df: pd.DataFrame) -> pa.Table:
    """Parquet types Athena reads cleanly: obs_date as DATE, not a midnight TIMESTAMP."""
    table = pa.Table.from_pandas(df, preserve_index=False)
    i = table.schema.get_field_index("obs_date")
    return table.set_column(i, "obs_date", pc.cast(table["obs_date"], pa.date32()))


def load_silver(lake: Lake) -> pa.Table:
    keys = [k for k in lake.list("silver/daily_weather/") if k.endswith(".parquet")]
    if not keys:
        empty = pd.DataFrame({c: pd.Series(dtype=t) for c, t in SILVER_SCHEMA.items()})
        return to_arrow(empty)
    return pa.concat_tables([read_arrow(lake, k) for k in keys], promote_options="default")

