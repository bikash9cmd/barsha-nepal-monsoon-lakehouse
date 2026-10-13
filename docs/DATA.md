# Data

## Source

[NOAA Global Surface Summary of the Day (GSOD)](https://registry.opendata.aws/noaa-gsod/), mirrored on the AWS Open Data registry as `s3://noaa-gsod-pds`. One CSV per station per year (`<year>/<station>.csv`), public, readable with anonymous requests. GSOD is derived from the synoptic weather messages each station sends every few hours over the WMO network, summarised into one row per day.

Nepal's stations are WMO block 44, numbers 444xx. The bucket has 16 of them:

| Station | WMO id | First day | Days in archive |
|---|---|---|---:|
| Kathmandu (Tribhuvan Intl. Airport) | 44454 | 1976-04-19 | 13,732 |
| Dhankuta | 44477 | 1976-11-05 | 5,782 |
| Surkhet | 44416 | 1976-11-08 | 6,039 |
| Bhairahawa | 44438 | 1977-05-27 | 5,453 |
| Okhaldhunga | 44462 | 1976-11-05 | 3,489 |
| Dadeldhura | 44404 | 1978-08-13 | 3,482 |
| Pokhara | 44434 | 1989-09-04 | 3,476 |
| Simara | 44449 | 1980-05-24 | 3,395 |
| Jumla | 44424 | 1990-12-08 | 3,388 |
| Dhangadhi | 44409 | 2012-08-08 | 3,281 |
| Biratnagar | 44478 | 1990-09-03 | 3,257 |
| Taplejung | 44474 | 1978-09-04 | 3,181 |
| Nepalgunj | 44418 | 2012-08-28 | 3,162 |
| Dipayal | 44406 | 2012-09-25 | 3,085 |
| Dang | 44429 | 2012-08-19 | 2,935 |
| Syangboche (retired 1979) | 44461 | 1976-11-05 | 78 |

In total: 409 station-year files, 16 MB, 67,215 station-days, 1976 to 24 August 2025.

**Nothing newer exists in the bucket.** As of October 2026 the newest row is 24 August 2025, the newest file was written on 12 September 2025, and there is no `2026/` prefix. I found this while building the pipeline; it is why the bulletin and the `SourceStaleAlarm` treat "no new data" as an incident rather than as dry weather ([bug #7](CHALLENGES_AND_BUGS.md#7-the-feed-had-stopped-and-nothing-said-so)).

## Format

```text
"STATION","DATE",...,"MAX","MAX_ATTRIBUTES","MIN","MIN_ATTRIBUTES","PRCP","PRCP_ATTRIBUTES","SNDP","FRSHTT"
"44454099999","2024-09-28",...,"  66.2"," ","  61.9"," "," 7.64","G","999.9","010010"
```

- Temperatures in °F, precipitation in inches, every number left-padded with spaces inside the quotes.
- Missing values are sentinels: `9999.9` for temperatures, `99.99` for precipitation.
- `FRSHTT` is six 0/1 flags: fog, rain, snow, hail, thunder, tornado. They come from the hourly weather codes, independently of the rain gauge.
- `PRCP_ATTRIBUTES` says how the day's precipitation was put together, and it matters more than any other column.

## What the precipitation flag means, and what I do with it

| Flag | GSOD meaning | Days | Rain seen that day | Barsha `prcp_quality` |
|---|---|---:|---:|---|
| G | one 24-hour report | 52,504 | 11,813 | complete |
| D, F | four 6-hour or two 12-hour reports | 34 | 1 | complete |
| A, B, C, E | one to three 6-hour reports, or one 12-hour report | 7,317 | 19 | partial (a lower bound) |
| H | reported 0, but rain was seen in the hourly reports | 480 | 476 | missing |
| I | no precipitation report at all; value written as 0.00 | 4,599 | 0 | missing |
| blank | value 99.99 | 2,281 | 2,278 | missing |

`prcp_mm` is only filled for complete days. `prcp_reported_mm` keeps what the file said, converted to mm, for anyone who wants to make a different call.

Two things in this table shaped the whole design:

1. **4,599 zeros are not zeros.** Flag I means "nothing was reported". A pipeline that reads the number and ignores the flag records those as dry days. For Kathmandu, that turns the 2001, 2002 and 2003 monsoons into **0.0 mm** each ([bug #1](CHALLENGES_AND_BUGS.md#1-four-thousand-zeros-that-were-not-dry-days)).
2. **Missing amounts cluster on rainy days.** Of the 2,281 blank days, 2,278 had rain in the weather codes; so did 476 of the 480 H days. Gaps are not random, so dropping them biases every total downwards. A seasonal total is only published when 90% of the season is complete ([bug #2](CHALLENGES_AND_BUGS.md#2-the-gaps-are-on-the-rainy-days)).

## Other things the archive does

- **Whole days missing across the network.** On 10 and 12 August 2017, the peak of that year's Terai floods, one station has a row; on the 11th and 13th, fourteen do. 2024 has 162 days on which two or fewer stations report. Health checks distinguish "one station silent" from "the archive is missing the day".
- **Metadata is restated, not historical.** Bhairahawa's 2025 file calls it "BHAIRAHAWA GAUTAM BUDDHA" (the new international airport); earlier files say "BHAIRAHAWA". Coordinates are identical in every year, so older files carry today's position. `station_dim` versions the name as a type 2 dimension.
- **One isolated spike.** Taplejung, 19 April 2018: 404 mm, while no other station got more than 23 mm and Taplejung's previous highest day was 137 mm. It is held as `suspect`, not deleted.

## Is GHCN-Daily a second source?

NOAA's GHCN-Daily (`s3://noaa-ghcn-pds`) has Kathmandu and Dhankuta. I meant to use it to cross-check GSOD. For Kathmandu, every one of its 6,086 precipitation values carries source flag `S`, which means "taken from GSOD", and all 6,086 match GSOD to 0.1 mm. Agreement between a copy and its original proves nothing, so I left it out ([bug #8](CHALLENGES_AND_BUGS.md#8-the-second-source-was-a-copy-of-the-first)).

## Reproducing the numbers

```bash
make backfill                          # ~1 minute, anonymous reads from s3://noaa-gsod-pds
python -m barsha query "select * from quality_summary"
```
