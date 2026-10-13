from datetime import date

from barsha.ingest import MANIFEST_KEY, ingest, raw_key
from barsha.source import LocalSource
from barsha.storage import LocalLake, read_arrow, read_json
from barsha.transform import build_year, silver_key

from .conftest import gsod_row, year_rows

KTM, OKH = "44454099999", "44462099999"


def test_ingest_is_incremental_and_idempotent(mirror, lake_dir):
    mirror.put(2023, KTM, year_rows(KTM, 2023))
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    source, lake = LocalSource(mirror.root), LocalLake(lake_dir)

    first = ingest(source, lake, [2023, 2024])
    assert first.changed_years == [2023, 2024]

    again = ingest(source, lake, [2023, 2024])
    assert again.copied == [] and again.unchanged == 2

    # Upstream rewrites the 2024 file (a new day appended): only 2024 is copied.
    mirror.put(2024, KTM, year_rows(KTM, 2024)[:-1] + [gsod_row(KTM, date(2024, 12, 31), 1.0)])
    third = ingest(source, lake, [2023, 2024])
    assert third.copied == [f"2024/{KTM}.csv"]
    assert lake.exists(raw_key(2024, KTM))


def test_ingest_reports_empty_years_and_vanished_files(mirror, lake_dir):
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    mirror.put(2024, OKH, year_rows(OKH, 2024))
    source, lake = LocalSource(mirror.root), LocalLake(lake_dir)
    ingest(source, lake, [2024])

    (mirror.root / "2024" / f"{OKH}.csv").unlink()
    result = ingest(source, lake, [2024, 2025])
    assert result.vanished == [f"2024/{OKH}.csv"]
    assert result.empty_years == [2025]
    assert lake.exists(raw_key(2024, OKH))  # our copy is kept
    assert f"2024/{OKH}.csv" in read_json(lake, MANIFEST_KEY)


def test_silver_year_rebuild(mirror, lake_dir):
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    mirror.put(2024, OKH, year_rows(OKH, 2024))
    lake = LocalLake(lake_dir)
    ingest(LocalSource(mirror.root), lake, [2024])

    report = build_year(lake, 2024, "t1")
    assert not report.blocked
    silver = read_arrow(lake, silver_key(2024))
    assert silver.num_rows == 366 * 2
    assert str(silver.schema.field("obs_date").type) == "date32[day]"

    # Rebuilding the same year gives the same rows: no duplicates, no MERGE needed.
    build_year(lake, 2024, "t2")
    assert read_arrow(lake, silver_key(2024)).num_rows == 366 * 2


def test_truncated_upstream_file_is_quarantined_and_last_good_kept(mirror, lake_dir):
    mirror.put(2024, KTM, year_rows(KTM, 2024))
    lake = LocalLake(lake_dir)
    source = LocalSource(mirror.root)
    ingest(source, lake, [2024])
    build_year(lake, 2024, "good")

    mirror.put(2024, KTM, year_rows(KTM, 2024)[:100])  # upstream publishes a cut-off file
    ingest(source, lake, [2024])
    report = build_year(lake, 2024, "bad")

    assert report.blocked
    assert [c.name for c in report.checks if not c.passed and c.severity == "error"] == ["row_count_not_shrunk"]
    assert read_arrow(lake, silver_key(2024)).num_rows == 366  # last good version still served
    assert any(k.startswith("quarantine/") for k in lake.list("quarantine/"))


def test_duplicate_days_and_foreign_stations_block_the_year(mirror, lake_dir):
    rows = year_rows(KTM, 2024)
    rows.append(rows[10])
    rows.append(gsod_row("44401099999", date(2024, 1, 1), name="SOMEWHERE ELSE, IN"))
    mirror.put(2024, KTM, rows)
    lake = LocalLake(lake_dir)
    ingest(LocalSource(mirror.root), lake, [2024])

    report = build_year(lake, 2024, "t")
    failed = {c.name for c in report.checks if not c.passed and c.severity == "error"}
    assert failed == {"unique_station_day", "station_in_nepal"}
    assert not lake.exists(silver_key(2024))


def test_impossible_temperatures_are_nulled_not_published(mirror, lake_dir):
    rows = year_rows(KTM, 2024)
    rows[0] = gsod_row(KTM, date(2024, 1, 1), max_f=50.0, min_f=60.0)  # max below min
    mirror.put(2024, KTM, rows)
    lake = LocalLake(lake_dir)
    ingest(LocalSource(mirror.root), lake, [2024])

    report = build_year(lake, 2024, "t")
    assert not report.blocked
    check = next(c for c in report.checks if c.name == "tmax_not_below_tmin")
    assert check.failed_rows == 1
    first = read_arrow(lake, silver_key(2024)).to_pandas().iloc[0]
    assert first["tmax_c"] != first["tmax_c"] and first["tmin_c"] != first["tmin_c"]
