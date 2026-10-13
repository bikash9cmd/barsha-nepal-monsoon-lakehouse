"""The Lambda handlers, run in Step Functions order against mocked S3 and SNS."""

from datetime import date

import boto3
import pytest
from moto import mock_aws

from .conftest import gsod_file, year_rows

KTM, OKH = "44454099999", "44462099999"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="noaa-gsod-pds", ACL="public-read")  # like the real Open Data bucket
        s3.create_bucket(Bucket="barsha-lake")
        sns = boto3.client("sns", region_name="us-east-1")
        alert = sns.create_topic(Name="barsha-rain-reports")["TopicArn"]
        ops = sns.create_topic(Name="barsha-ops")["TopicArn"]
        monkeypatch.setenv("LAKE_BUCKET", "barsha-lake")
        monkeypatch.setenv("SOURCE_BUCKET", "noaa-gsod-pds")
        monkeypatch.setenv("ALERT_TOPIC", alert)
        monkeypatch.setenv("OPS_TOPIC", ops)
        yield s3


def _put(s3, year, station, rows):
    s3.put_object(Bucket="noaa-gsod-pds", Key=f"{year}/{station}.csv", Body=gsod_file(rows), ACL="public-read")


def _run(event):
    from barsha.aws import handlers

    state = handlers.ingest_handler(event)
    if state["ingest"]["changed_years"]:
        state = handlers.transform_handler(state)
    state = handlers.gold_handler(state)
    return state, handlers.bulletin_handler(state)


def test_daily_run_end_to_end(aws):
    for y in range(2010, 2020):
        _put(aws, y, KTM, year_rows(KTM, y))
        _put(aws, y, OKH, year_rows(OKH, y))
    _put(aws, 2020, KTM, year_rows(KTM, 2020, {date(2020, 7, 1): 8.0}))
    _put(aws, 2020, OKH, year_rows(OKH, 2020, {date(2020, 7, 1): 3.0}))

    state, result = _run({"mode": "backfill", "as_of": "2020-07-01"})
    assert len(state["ingest"]["copied"]) == 22
    assert state["transform"]["quarantined"] == []
    assert result["status"] == "OK" and result["public_alerts"] == 2

    keys = [o["Key"] for o in aws.list_objects_v2(Bucket="barsha-lake")["Contents"]]
    assert "silver/daily_weather/year=2020/data.parquet" in keys
    assert "gold/rain_daily/data.parquet" in keys
    assert any(k.startswith("gold/bulletins/as_of=2020-07-01/") for k in keys)

    # The next day nothing changed upstream: nothing is copied, gold and the bulletin still run.
    state, result = _run({"mode": "daily", "as_of": "2020-07-02"})
    assert state["ingest"]["copied"] == [] and "transform" not in state
    assert result["status"] == "OK"


def test_quarantine_is_reported_as_partial(aws):
    _put(aws, 2024, KTM, year_rows(KTM, 2024))
    _run({"years": [2024], "as_of": "2024-12-31"})

    _put(aws, 2024, KTM, year_rows(KTM, 2024)[:50])  # upstream truncates the file
    state, result = _run({"years": [2024], "as_of": "2024-12-31"})
    assert result["status"] == "PARTIAL" and result["quarantined"] == [2024]


def test_stale_source_pages_operators(aws):
    _put(aws, 2025, KTM, year_rows(KTM, 2025)[:236])  # last day 2025-08-24, as upstream today
    state, result = _run({"mode": "daily", "as_of": "2026-10-13"})
    assert result["source_lag_days"] == 415
    assert result["operator_alerts"] == 1 and result["public_alerts"] == 0
