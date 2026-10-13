# Challenges and bugs

The problems I hit building Barsha, in the order I hit them, with what each one taught me. The first eight are about the data; the rest are about my own code and infrastructure.

## 1. Four thousand zeros that were not dry days

**Symptom.** While profiling the raw files I grouped precipitation by its `PRCP_ATTRIBUTES` flag. Flag `I` had 4,599 rows, every one of them `0.00`, and not one with rain in the weather codes.

**Cause.** In GSOD, `I` means the station sent no precipitation report that day. The file still writes `0.00` in the value column. A pipeline that reads the column and ignores the flag records a dry day.

**How bad.** Kathmandu airport's June-September total, summed naively: 1999: 65.6 mm, 2000: 10.9 mm, **2001-2003: 0.0 mm**. Kathmandu normally gets well over 1,000 mm in a monsoon. Any dashboard built on that column would say the valley had no monsoon for three years.

**Fix.** `classify_precip()` turns the flag into `complete / partial / missing`, and `prcp_mm` is only filled for complete days. The raw value stays in `prcp_reported_mm`. Test: `test_flag_i_zero_is_not_a_dry_day`.

**Lesson.** Read the flag columns before the value columns. The data dictionary is part of the data.

## 2. The gaps are on the rainy days

**Symptom.** Of 2,281 days with a blank flag and `99.99`, 2,278 had rain in the weather codes. Flag `H` (480 days) is the same story: "0" reported, rain observed.

**Cause.** Missing precipitation is not random. Gauges and reports fail when it rains, which is exactly when the value matters.

**Fix.** Two rules. Seasonal totals are published only when at least 90% of June-September has complete readings; otherwise the row says `withheld: 85 of 122 days complete` instead of printing an undercount. And every season records `missing_on_rain_days`, so the gap is visible. Only **60 of 337** station-monsoons pass. That number is the honest state of this public archive, and I'd rather show it than hide it.

**Lesson.** "Drop nulls" is a modelling decision. Check whether missingness depends on the thing you're measuring before you make it.

## 3. My outlier check called the 2014 Surkhet flood a sensor error

**Symptom.** The first suspect-value rule was "more than 3x the station's own 99.9th percentile". It flagged two days: Taplejung, 19 April 2018 (404 mm), and Surkhet, 15 August 2014 (427 mm). The second one was the rain behind the August 2014 floods in Surkhet, Bardiya and Banke: a real disaster, not a broken gauge.

**Cause.** A rule that only looks at one station's history cannot tell a broken gauge from a record storm. Both are far outside the station's past.

**Fix.** A spike is only suspect if no station within 200 km had heavy rain (64.5 mm or more) the day before, the same day or the day after. Surkhet is corroborated by 142.7 mm at a neighbour and becomes a red alert; Taplejung's neighbours had 17 mm and it stays suspect. Distances are computed in SQL with the haversine formula. Test: `test_isolated_spike_is_held_as_suspect_but_corroborated_one_is_not`.

**Trade-off I accepted.** A station with no reporting neighbour that gets a real record storm is held for review instead of published. The operator still gets an alert the same morning, so the cost is a review delay, not a missed event ([FAILURE_MODES.md](FAILURE_MODES.md)).

**Lesson.** Validate a data-quality rule against known real events before trusting it. The extremes are the data this project exists for.

## 4. "Light rain", red alert

**Symptom.** A unit test with a neighbouring station built a bulletin with a red alert for 10 mm of rain.

**Cause.** In that synthetic history every wet day is 10 mm, so 10 mm *is* the station's 99.9th percentile. Real dry stations behave the same way at small scale: Jumla's 99th percentile of rainy days is about 42 mm.

**Fix.** Station-relative levels only apply from 50 mm upward. The absolute DHM/IMD categories (heavy 64.5, very heavy 115.6, extremely heavy 204.5 mm) still apply everywhere.

**Lesson.** Percentile thresholds need an absolute floor, or "rare" turns into "harmless but rare".

## 5. The alert text said things that weren't true

**Symptom.** Replaying 28 September 2024, the Bhairahawa line said its 141 mm was "above the level this station reaches on only 1 in 100 rainy days (154 mm)". 141 is below 154. Simara had the same problem. The same replay also listed Bhairahawa twice, once per day.

**Cause.** The orange level triggers on *either* the station's 99th percentile *or* the absolute 115.6 mm. The text assumed the first.

**Fix.** Each sentence is added only when its own condition holds, and the bulletin shows one line per station: its wettest day in the window.

**Lesson.** Generated text is output and needs the same checks as numbers. I now read the replay bulletins line by line after every rule change.

## 6. "1 in 100 rainy days" is not a "100-year" event

**Symptom.** My first Nepali text for the 99th-percentile sentence used "सय वर्षे" (hundred-year).

**Cause.** Translating the idea instead of the statistic. The 99th percentile of *rainy days* is passed about once a year at a station with ~100 rainy days a year. Calling that a 100-year event overstates it a hundredfold, and a flood bulletin that cries wolf gets ignored.

**Fix.** "यो स्टेशनमा १०० वर्षा-दिनमा १ पटक मात्र पुग्ने स्तर" (a level this station reaches only once in 100 rainy days), and the English says the same.

## 7. The feed had stopped and nothing said so

**Symptom.** A daily run "as of" today copied nothing, built nothing, raised nothing, and reported OK.

**Cause.** The public bucket has had no new data since 24 August 2025 (newest file written 12 September 2025, no `2026/` prefix at all). An incremental pipeline that only reacts to new files sees silence and calls it success. In a rainfall system, silence reads as "no rain".

**Fix.** Gold computes `days_since_last_obs` for every station. The bulletin raises `SOURCE_STALE` when no non-retired station has reported for more than 3 days, and `STATION_SILENT` when one station is quiet while others report. Lambda emits `SourceLagDays` and a CloudWatch alarm with `TreatMissingData: breaching` pages if it goes above 3 or stops being reported. Today the bulletin opens with: *"No station has reported for 415 days (newest day 2025-08-24). The upstream feed has stopped; reports are paused, not quiet."*

**Lesson.** Freshness is a first-class check. "Nothing to do" and "nothing arrived" have to be different states.

## 8. The second source was a copy of the first

**Symptom.** I planned to cross-check GSOD against NOAA's GHCN-Daily for Kathmandu. They agreed on all 6,086 days to 0.1 mm.

**Cause.** Every GHCN value for that station has source flag `S`: it was taken from GSOD. Lagging GHCN by one day dropped the correlation from 0.99999 to 0.28, which confirmed the two are aligned copies, not independent gauges.

**Fix.** I dropped GHCN rather than present it as validation. The cross-check that does work is spatial (bug #3).

**Lesson.** Check lineage before counting two datasets as two sources.

## 9. Station renamed mid-archive

**Symptom.** Bhairahawa's 2025 file says "BHAIRAHAWA GAUTAM BUDDHA"; every earlier file says "BHAIRAHAWA". A `GROUP BY station_name` split one station in two.

**Fix.** Facts join on the WMO id only. `station_dim` is a type 2 slowly changing dimension built from the facts: a new version starts on the first day the name, position or elevation changes, with `valid_from`, `valid_to` and `is_current`. Test: `test_station_rename_creates_a_new_dimension_version`.

## 10. Silver dates came out as midnight timestamps

**Symptom.** The first silver Parquet files stored `obs_date` as `TIMESTAMP(ms)`, because that is what pandas writes for a datetime column. The Glue table would have needed `timestamp`, and every Athena filter would have compared against midnight.

**Fix.** `to_arrow()` casts `obs_date` to Arrow `date32` before writing, and gold is written straight from DuckDB's Arrow output, which keeps SQL `DATE`. The Glue columns are `date`. A test asserts the Parquet type.

## 11. My CloudFormation template didn't parse

**Symptom.** `cfn-lint` failed with `mapping values are not allowed in this context`.

**Cause.** The Step Functions failure message, `States.Format('Run failed: {}', ...)`, was unquoted YAML, and the colon inside it started a new mapping. I had also used YAML anchors to share the retry block between states.

**Fix.** Quoted the intrinsic, and wrote each retry block out in full so the template doesn't depend on every tool that reads it (SAM CLI, cfn-lint, the console designer) handling anchors the same way. `cfn-lint` runs in CI.

## 12. A permission that could never be used

**Symptom.** The AWS handler tests failed with `403 Forbidden` on the source bucket in moto.

**Cause.** The ingest function reads NOAA's bucket with unsigned requests, as AWS recommends for Open Data. An unsigned request carries no identity, so it only works on a publicly readable bucket, and the test bucket wasn't public. That also meant the IAM statement I had given the function for `noaa-gsod-pds` could never take effect: an anonymous request never uses the role.

**Fix.** The test bucket is created `public-read`, like the real one, and I removed the dead IAM statement. The ingest role now only grants the lake bucket.

**Lesson.** Least privilege includes deleting permissions that do nothing; they mislead the next reader.
