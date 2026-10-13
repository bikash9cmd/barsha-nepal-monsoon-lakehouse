"""Gold: analyst-facing tables, rebuilt in full from silver with DuckDB SQL.

At about 70,000 station-days a full rebuild takes a couple of seconds and is always
consistent, so there is no incremental gold logic to get wrong.
"""

from __future__ import annotations

import logging
from datetime import date
from importlib import resources

import duckdb
import pandas as pd
import pyarrow as pa

from . import config
from .storage import Lake, read_arrow, write_arrow
from .transform import load_silver

log = logging.getLogger(__name__)

# Built in this order; each later query can read the tables before it.
TABLES = ["station_dim", "rain_daily", "monsoon_season", "station_health", "quality_summary"]


def gold_key(table: str) -> str:
    return f"gold/{table}/data.parquet"


def _sql(name: str) -> str:
    return resources.files("barsha.sql").joinpath(f"{name}.sql").read_text()


def _params(sql: str, as_of: date) -> dict:
    values = {
        "as_of": as_of,
        "suspect_multiple": config.SUSPECT_MULTIPLE,
        "min_relative_mm": config.MIN_RELATIVE_ALERT_MM,
        "monsoon_days": config.MONSOON_DAYS,
        "min_completeness": config.MIN_SEASON_COMPLETENESS,
        "stale_after_days": config.STALE_AFTER_DAYS,
        "retired_after_days": config.RETIRED_AFTER_DAYS,
    }
    return {k: v for k, v in values.items() if f"${k}" in sql}


def build_gold_tables(silver: pa.Table, as_of: date) -> dict[str, pa.Table]:
    con = duckdb.connect()
    con.register("silver", silver)
    out = {}
    for table in TABLES:
        sql = _sql(table)
        out[table] = con.execute(sql, _params(sql, as_of)).to_arrow_table()
        con.register(table, out[table])
    con.close()
    return out


def to_pandas(table: pa.Table) -> pd.DataFrame:
    return table.to_pandas(date_as_object=False)


def build_gold_frames(silver: pa.Table, as_of: date) -> dict[str, pd.DataFrame]:
    return {name: to_pandas(t) for name, t in build_gold_tables(silver, as_of).items()}


def build_gold(lake: Lake, as_of: date) -> dict[str, int]:
    tables = build_gold_tables(load_silver(lake), as_of)
    for name, table in tables.items():
        write_arrow(lake, gold_key(name), table)
    counts = {name: table.num_rows for name, table in tables.items()}
    log.info("gold: %s", counts)
    return counts


def load_gold(lake: Lake, table: str) -> pd.DataFrame:
    return to_pandas(read_arrow(lake, gold_key(table)))
