"""Command line: python -m barsha <command>."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, date, datetime

from . import pipeline
from .alerts import render
from .config import Settings
from .gold import TABLES, gold_key
from .source import open_source
from .storage import LocalLake, open_lake


def _date(text: str) -> date:
    return date.fromisoformat(text)


def _today() -> date:
    return datetime.now(UTC).date()


def _compact(summary: dict) -> dict:
    """Long year and file lists become counts and ranges for the terminal; _runs/ keeps them all."""
    ingest, transform = summary["ingest"], summary["transform"]
    years = summary["years_checked"]
    return {
        "run_id": summary["run_id"],
        "as_of": summary["as_of"],
        "years_checked": f"{years[0]}-{years[-1]}" if len(years) > 2 else years,
        "files_copied": len(ingest["copied"]),
        "files_unchanged": ingest["unchanged"],
        "files_vanished_upstream": ingest["vanished"],
        "years_with_no_upstream_files": ingest["empty_years"],
        "silver_years_built": len(transform["built"]),
        "silver_years_quarantined": transform["quarantined"],
        "gold_rows": summary["gold"],
        "alerts": summary["alerts"],
        "status": summary["status"],
    }


def main(argv: list[str] | None = None) -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(prog="barsha", description="Nepal monsoon rainfall lakehouse")
    parser.add_argument("--lake", default=settings.lake, help="local folder or s3://bucket/prefix")
    parser.add_argument("--source", default=settings.source, help="s3://noaa-gsod-pds or a local mirror")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="ingest, transform, gold, bulletin")
    run.add_argument("--backfill", action="store_true", help=f"check every year since {pipeline.FIRST_YEAR}")
    run.add_argument("--years", type=int, nargs="*")
    run.add_argument("--as-of", type=_date, default=None)

    rebuild = sub.add_parser("rebuild", help="rebuild silver for given years (or all raw years) and gold")
    rebuild.add_argument("--years", type=int, nargs="*")
    rebuild.add_argument("--as-of", type=_date, default=None)

    bulletin = sub.add_parser("bulletin", help="replay the bulletin for a past day")
    bulletin.add_argument("--as-of", type=_date, required=True)
    bulletin.add_argument("--json", action="store_true")

    query = sub.add_parser("query", help="SQL over the local lake (silver + gold tables) with DuckDB")
    query.add_argument("sql")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lake = open_lake(args.lake)

    if args.cmd == "run":
        as_of = args.as_of or _today()
        years = args.years or (pipeline.backfill_years(as_of) if args.backfill else pipeline.daily_years(as_of))
        summary = pipeline.run_all(open_source(args.source), lake, years, as_of)
        bulletin_text = render(summary.pop("bulletin"))
        print(json.dumps(_compact(summary), indent=2))
        print()
        print(bulletin_text)

    elif args.cmd == "rebuild":
        as_of = args.as_of or _today()
        years = args.years or sorted({int(k.split("=")[1].split("/")[0]) for k in lake.list("raw/gsod/")})
        run_id = pipeline.new_run_id()
        print(json.dumps(pipeline.run_transform(lake, years, run_id), indent=2))
        print(json.dumps(pipeline.run_gold(lake, as_of), indent=2))

    elif args.cmd == "bulletin":
        result = pipeline.replay_bulletin(lake, args.as_of)
        print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))

    elif args.cmd == "query":
        if not isinstance(lake, LocalLake):
            raise SystemExit("query runs on a local lake; on AWS use Athena (sql/athena/)")
        import duckdb

        con = duckdb.connect()
        silver = lake.uri("silver/daily_weather") + "/*/*.parquet"
        con.execute(f"create view daily_weather as select * from read_parquet('{silver}', hive_partitioning = true)")
        for table in TABLES:
            if lake.exists(gold_key(table)):
                con.execute(f"create view {table} as select * from read_parquet('{lake.uri(gold_key(table))}')")
        con.sql(args.sql).show(max_rows=60, max_width=200)


if __name__ == "__main__":
    main()
