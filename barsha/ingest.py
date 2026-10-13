"""Bronze: copy new or changed upstream files into the lake, exactly as received.

The manifest maps each upstream key to the ETag we last copied. A file whose ETag has not
changed is skipped, so a daily run reads two directory listings and usually copies only
the current year's files. Running the same ingest twice changes nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .storage import Lake, read_json, write_json

log = logging.getLogger(__name__)

MANIFEST_KEY = "_state/manifest.json"


def raw_key(year: int, station_id: str) -> str:
    return f"raw/gsod/year={year}/{station_id}.csv"


@dataclass
class IngestResult:
    copied: list[str] = field(default_factory=list)
    unchanged: int = 0
    vanished: list[str] = field(default_factory=list)
    empty_years: list[int] = field(default_factory=list)

    @property
    def changed_years(self) -> list[int]:
        return sorted({int(k.split("/")[0]) for k in self.copied})

    def to_dict(self) -> dict:
        return {
            "copied": self.copied,
            "unchanged": self.unchanged,
            "vanished": self.vanished,
            "empty_years": self.empty_years,
            "changed_years": self.changed_years,
        }


def ingest(source, lake: Lake, years: list[int], now: datetime | None = None) -> IngestResult:
    now = now or datetime.now(UTC)
    manifest: dict = read_json(lake, MANIFEST_KEY, default={})
    result = IngestResult()

    for year in years:
        objects = source.list(year)
        if not objects:
            result.empty_years.append(year)
        listed = {o.key for o in objects}

        for obj in objects:
            prev = manifest.get(obj.key)
            if prev and prev["etag"] == obj.etag:
                result.unchanged += 1
                continue
            data = source.read(obj.key)
            lake.write_bytes(raw_key(obj.year, obj.station_id), data)
            manifest[obj.key] = {
                "etag": obj.etag,
                "size": obj.size,
                "ingested_at": now.isoformat(timespec="seconds"),
            }
            result.copied.append(obj.key)

        # Upstream deleted a file we already hold. Keep our copy and report it.
        for key in sorted(manifest):
            if key.startswith(f"{year}/") and key not in listed:
                result.vanished.append(key)

    # Written last: a crash before this line means the next run copies the same files again,
    # which is harmless because raw keys are fixed per station-year.
    write_json(lake, MANIFEST_KEY, manifest)
    log.info("ingest: copied %d, unchanged %d", len(result.copied), result.unchanged)
    return result
