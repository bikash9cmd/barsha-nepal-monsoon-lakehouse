"""Data-quality gate for one rebuilt silver year.

Each rule returns how many rows it caught and whether that blocks publishing. Errors stop
the year from replacing the last good version; warnings are fixed in place and recorded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .config import MAX_ROW_DROP


@dataclass
class Check:
    name: str
    severity: str  # "error" blocks the year, "warn" is fixed and recorded
    failed_rows: int
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.failed_rows == 0


@dataclass
class QualityReport:
    year: int
    rows: int
    checks: list[Check]

    @property
    def blocked(self) -> bool:
        return any(c.severity == "error" and not c.passed for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "rows": self.rows,
            "blocked": self.blocked,
            "checks": [asdict(c) | {"passed": c.passed} for c in self.checks],
        }


def run_checks(df: pd.DataFrame, year: int, previous_rows: int | None) -> tuple[pd.DataFrame, QualityReport]:
    """Returns the cleaned frame and the report. The input frame is not modified."""
    df = df.copy()
    checks: list[Check] = []

    bad_date = df["obs_date"].isna() | (df["obs_date"].dt.year != year)
    checks.append(Check("obs_date_in_partition_year", "error", int(bad_date.sum())))

    dupes = df.duplicated(["station_id", "obs_date"], keep=False)
    checks.append(Check("unique_station_day", "error", int(dupes.sum())))

    foreign = ~df["station_name"].fillna("").str.endswith(", NP")
    checks.append(Check("station_in_nepal", "error", int(foreign.sum())))

    if previous_rows:
        drop = 1 - len(df) / previous_rows
        lost = max(previous_rows - len(df), 0)
        checks.append(
            Check(
                "row_count_not_shrunk",
                "error",
                lost if drop > MAX_ROW_DROP else 0,
                f"{previous_rows} -> {len(df)} rows",
            )
        )

    # Warnings: impossible values are nulled, never guessed.
    for col in ("tavg_c", "tmax_c", "tmin_c"):
        out_of_range = df[col].notna() & ~df[col].between(-45, 50)
        checks.append(Check(f"{col}_in_range", "warn", int(out_of_range.sum())))
        df.loc[out_of_range, col] = pd.NA

    inverted = df["tmax_c"].notna() & df["tmin_c"].notna() & (df["tmax_c"] < df["tmin_c"])
    checks.append(Check("tmax_not_below_tmin", "warn", int(inverted.sum())))
    df.loc[inverted, ["tmax_c", "tmin_c"]] = pd.NA

    bad_prcp = df["prcp_mm"].notna() & ~df["prcp_mm"].between(0, 1000)
    checks.append(Check("prcp_in_range", "warn", int(bad_prcp.sum())))
    df.loc[bad_prcp, "prcp_mm"] = pd.NA
    df.loc[bad_prcp, "prcp_quality"] = "missing"

    # Recorded, not fixed: how often "missing" rain falls on days the station saw rain.
    hidden = (df["prcp_quality"] == "missing") & df["rain_observed"].fillna(False)
    checks.append(Check("prcp_missing_on_rain_day", "warn", int(hidden.sum()), "kept as missing"))

    return df, QualityReport(year, len(df), checks)
