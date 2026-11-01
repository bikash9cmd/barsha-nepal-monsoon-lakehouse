# What breaks, and what happens then

Each row is something that will go wrong eventually, what Barsha does about it, and how it was checked.

| What breaks | What the user sees | What the system does | Checked by |
|---|---|---|---|
| **Upstream stops publishing** (happening now: nothing since 24 Aug 2025) | Operators get *"No station has reported for 415 days … reports are paused, not quiet."* No public alerts. | `SOURCE_STALE` in the bulletin; `SourceLagDays` metric; `SourceStaleAlarm` (also fires if the metric stops arriving). | `test_stale_source_pages_operators`, `test_stale_feed_keeps_its_lag_after_every_station_retires`, and a real run against the bucket |
| **One station goes silent** | Operators: *"Jumla has not reported since …; other stations have."* | `STATION_SILENT` only when others are reporting, so a network-wide gap gives one alert, not fifteen. Stations silent for 3+ years are `retired` and ignored. | `test_one_station_silent_while_others_report` |
| **Upstream publishes a truncated or corrupt file** | Nothing changes for users: yesterday's silver stays. Operators see `YearsQuarantined`. | Gate blocks the year (row count down >10%, unparseable file, duplicate days, a non-Nepal station). Raw copied to `quarantine/`, run status `PARTIAL`. | `test_truncated_upstream_file_is_quarantined_and_last_good_kept`, `test_duplicate_days_and_foreign_stations_block_the_year`, `test_quarantine_is_reported_as_partial` |
| **Upstream changes the CSV layout** | Same as above. | `parse_gsod` checks for required columns and raises `SourceFormatError`; the year is quarantined. | `test_rejects_empty_and_changed_layout` |
| **A broken gauge reports a huge value** | Not published. Operators get a review alert the same morning. | `is_suspect` when >3x the station's 99.9th percentile *and* no station within 200 km had heavy rain on the day before, the day, or the day after. Kept in the lake, excluded from records and thresholds. | Taplejung 19 Apr 2018 in the real data; `test_isolated_spike_is_held_as_suspect_but_corroborated_one_is_not` |
| **A real record storm hits a station with no reporting neighbour** | Held for review instead of published: the false-hold case of the rule above. | Same review alert to operators; a person releases it. I accepted this: a delayed true alert is better than publishing every broken gauge. | `test_lone_station_extreme_goes_to_review_not_public` |
| **Upstream deletes a file we already hold** | Nothing; our copy stays in silver. | Reported as `vanished` in the run summary. | `test_ingest_reports_empty_years_and_vanished_files` |
| **Upstream revises an old year** | The revised numbers appear next run (for this year and last). Older revisions need a backfill. | Daily runs check this year and last; `{"mode": "backfill"}` re-checks every year by ETag and copies only what changed. | `test_ingest_is_incremental_and_idempotent` |
| **A Lambda step throws** | Nothing published that day; next day catches up (ETags still differ). | Step Functions retries service errors 3 times with jittered backoff, then publishes the error to the ops topic. `PipelineFailedAlarm`. | `cfn-lint`; the retry and catch are in `template.yaml` |
| **The schedule is disabled or broken** | No bulletin. | `PipelineNotRunningAlarm` on zero executions for two days, with missing data treated as breaching. Scheduler retries twice, then the DLQ alarm fires. | `template.yaml` |
| **A run is retried or started twice** | Same lake contents. | Every stage is idempotent: ETag-diffed copies, fixed raw keys, whole-partition rewrites, full gold rebuild. | `test_silver_year_rebuild` (rebuild twice, same rows) |
| **Someone writes a runaway Athena query** | Query cancelled. | Workgroup `BytesScannedCutoffPerQuery` = 1 GB (the whole lake is ~18 MB). | `template.yaml` |
| **A bad deploy corrupts silver or gold** | Wrong numbers until fixed. | Bucket versioning keeps 30 days of noncurrent silver and gold versions; raw keeps 90. `make rebuild` regenerates silver and gold from raw. | Manual |
| **The monthly bill drifts** | Email at 80% of $5. | AWS Budget with actual and forecast notifications. | `template.yaml` |

## What isn't handled

- **Rain that GSOD never received.** On 10 and 12 August 2017, at the height of that year's Terai floods, only one station has a row. No pipeline can recover a day the archive doesn't have. Barsha reports it as missing; it can't fill it.
- **Partial days.** Days built from one to three 6-hour reports are kept as `partial` and excluded from totals and alerts. A storm that falls between reports is undercounted, not flagged.
- **Station moves.** GSOD restates the current coordinates in every old file, so a station move in the past is invisible. `station_dim` would version it if the coordinates ever changed in a new file.
