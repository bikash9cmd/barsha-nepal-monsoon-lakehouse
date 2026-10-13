"""AWS Lambda entry points. Same pipeline code as the CLI; only the lake location differs.

Step Functions calls them in order and passes one growing state document between them:

  ingest_handler     upstream S3 (anonymous) -> raw/ in the lake, manifest of ETags
  transform_handler  raw/ -> silver/ for the years that changed, behind the quality gate
  gold_handler       silver/ -> gold/ tables (DuckDB), queried through Athena
  bulletin_handler   gold/ -> bulletin JSON + SNS (public alerts and operator alerts)

Environment variables are set by infra/template.yaml.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, date, datetime

import boto3

from barsha import pipeline
from barsha.alerts import render
from barsha.config import SOURCE_BUCKET
from barsha.source import S3Source
from barsha.storage import S3Lake

log = logging.getLogger()
log.setLevel(logging.INFO)


def _lake() -> S3Lake:
    return S3Lake(os.environ["LAKE_BUCKET"])


def _as_of(event: dict) -> date:
    if event.get("as_of"):
        return date.fromisoformat(event["as_of"])
    return datetime.now(UTC).date()


def _metric(name: str, value: float, unit: str = "Count") -> None:
    """CloudWatch Embedded Metric Format: a log line becomes a metric, with no PutMetricData call.

    Only metrics that an alarm watches are emitted. Each custom metric costs $0.30 a month,
    which makes metrics the largest line on this project's bill (docs/COST.md); everything
    else goes to the logs, where Logs Insights can still query it.
    """
    print(json.dumps({
        "_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [{
            "Namespace": "Barsha", "Dimensions": [[]], "Metrics": [{"Name": name, "Unit": unit}]}]},
        name: value,
    }))


def ingest_handler(event: dict, context=None) -> dict:
    as_of = _as_of(event)
    if event.get("years"):
        years = [int(y) for y in event["years"]]
    elif event.get("mode") == "backfill":
        years = pipeline.backfill_years(as_of)
    else:
        years = pipeline.daily_years(as_of)

    source = S3Source(os.environ.get("SOURCE_BUCKET", SOURCE_BUCKET))
    result = pipeline.run_ingest(source, _lake(), years)
    log.info("ingest copied=%d unchanged=%d vanished=%s empty_years=%s", len(result["copied"]),
             result["unchanged"], result["vanished"], result["empty_years"])
    return {
        "run_id": event.get("run_id") or pipeline.new_run_id(),
        "as_of": as_of.isoformat(),
        "years": years,
        "ingest": result,
    }


def transform_handler(event: dict, context=None) -> dict:
    years = event["ingest"]["changed_years"]
    result = pipeline.run_transform(_lake(), years, event["run_id"])
    _metric("YearsQuarantined", len(result["quarantined"]))
    return event | {"transform": result}


def gold_handler(event: dict, context=None) -> dict:
    counts = pipeline.run_gold(_lake(), _as_of(event))
    return event | {"gold": counts}


def bulletin_handler(event: dict, context=None) -> dict:
    as_of = _as_of(event)
    bulletin = pipeline.run_bulletin(_lake(), as_of, event["run_id"])
    if bulletin["source_lag_days"] is not None:
        _metric("SourceLagDays", bulletin["source_lag_days"], "None")

    sns = boto3.client("sns")
    public = [a for a in bulletin["alerts"] if a["audience"] == "public"]
    operator = [a for a in bulletin["alerts"] if a["audience"] == "operator"]
    if public and os.environ.get("ALERT_TOPIC"):
        sns.publish(
            TopicArn=os.environ["ALERT_TOPIC"],
            Subject=f"Barsha: extreme rain at {len(public)} station(s), {as_of}",
            Message=render(bulletin | {"alerts": public}),
        )
    if operator and os.environ.get("OPS_TOPIC"):
        sns.publish(
            TopicArn=os.environ["OPS_TOPIC"],
            Subject=f"Barsha ops: {len(operator)} issue(s), {as_of}",
            Message=render(bulletin | {"alerts": operator}),
        )

    quarantined = event.get("transform", {}).get("quarantined", [])
    return {
        "run_id": event["run_id"],
        "as_of": as_of.isoformat(),
        "status": "PARTIAL" if quarantined else "OK",
        "quarantined": quarantined,
        "public_alerts": len(public),
        "operator_alerts": len(operator),
        "source_lag_days": bulletin["source_lag_days"],
    }
