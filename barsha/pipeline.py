"""The four stages, wired together. The CLI and the Lambda handlers both call these."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from .alerts import build_bulletin
from .config import FIRST_YEAR
from .gold import build_gold, build_gold_frames, load_gold
from .ingest import ingest
from .storage import Lake, write_json
from .transform import build_year, load_silver

log = logging.getLogger(__name__)


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def daily_years(today: date) -> list[int]:
    """Last year is included so that corrections to December still arrive in January."""
    return [today.year - 1, today.year]


def backfill_years(today: date) -> list[int]:
    return list(range(FIRST_YEAR, today.year + 1))


def run_ingest(source, lake: Lake, years: list[int]) -> dict:
    return ingest(source, lake, years).to_dict()


def run_transform(lake: Lake, years: list[int], run_id: str) -> dict:
    reports = [build_year(lake, y, run_id) for y in years]
    return {
        "built": [r.year for r in reports if not r.blocked],
        "quarantined": [r.year for r in reports if r.blocked],
        "failed_checks": {
            str(r.year): [c.name for c in r.checks if c.severity == "error" and not c.passed]
            for r in reports if r.blocked
        },
    }


def run_gold(lake: Lake, as_of: date) -> dict:
    return build_gold(lake, as_of)


def run_bulletin(lake: Lake, as_of: date, run_id: str) -> dict:
    bulletin = build_bulletin(load_gold(lake, "rain_daily"), load_gold(lake, "station_health"), as_of)
    write_json(lake, f"gold/bulletins/as_of={as_of.isoformat()}/{run_id}.json", bulletin)
    return bulletin


def replay_bulletin(lake: Lake, as_of: date) -> dict:
    """What the bulletin would have said on a past day, using only data up to that day."""
    frames = build_gold_frames(load_silver(lake), as_of)
    return build_bulletin(frames["rain_daily"], frames["station_health"], as_of)


def run_all(source, lake: Lake, years: list[int], as_of: date) -> dict:
    run_id = new_run_id()
    summary = {"run_id": run_id, "as_of": as_of.isoformat(), "years_checked": years}
    summary["ingest"] = run_ingest(source, lake, years)
    changed = summary["ingest"]["changed_years"]
    summary["transform"] = run_transform(lake, changed, run_id) if changed else {"built": [], "quarantined": []}
    summary["gold"] = run_gold(lake, as_of)
    bulletin = run_bulletin(lake, as_of, run_id)
    summary["alerts"] = len(bulletin["alerts"])
    summary["status"] = "PARTIAL" if summary["transform"]["quarantined"] else "OK"
    write_json(lake, f"_runs/{run_id}.json", summary)
    return summary | {"bulletin": bulletin}
