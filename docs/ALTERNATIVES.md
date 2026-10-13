# Alternatives I considered

For each layer: what I chose, what else would work, and when I'd switch. Monthly costs come from `scripts/cost_model.py` (us-east-1 list prices, free tier ignored).

## Ingestion

| Option | Verdict |
|---|---|
| **Lambda listing the bucket daily, copying files whose ETag changed** (chosen) | Two `ListObjectsV2` calls a day. Simple, idempotent, and the manifest doubles as an audit of what came in when. |
| S3 event notifications or SNS from the source bucket | NOAA's bucket isn't mine, so I can't attach notifications to it. Some Open Data buckets publish an SNS topic for new objects; this one's daily rewrite of the current-year file would fire 15 events a day for the same small change anyway. |
| Kinesis Data Streams / Firehose | Built for continuous records. Upstream publishes daily files, so a stream would be a ~$29/month always-on buffer in front of a once-a-day job. Right choice if I took hourly SYNOP messages directly. |
| AWS DataSync or `aws s3 sync` on a schedule | Would copy files fine, but gives me no per-file record of what changed, and I'd still need logic to know which years to rebuild. |
| AWS Glue crawler on the source bucket | Crawlers infer schema; I want a fixed schema that fails loudly when upstream changes. |

## Storage and table format

| Option | Verdict |
|---|---|
| **Parquet on S3, one file per year partition, rebuilt whole** (chosen) | Matches the unit upstream changes in. No compaction or vacuum to run. |
| Apache Iceberg (Athena or Glue) | Gives row-level MERGE, time travel and schema evolution. Worth it when updates are row-level or partitions are large. Here every change replaces a whole year, and S3 versioning already gives me rollback. I'd switch at hourly grain or when several writers touch one table. |
| Delta Lake / Hudi | Same reasoning as Iceberg; Iceberg is the best supported of the three in Athena, so it would be my pick if I needed one. |
| CSV in silver | Athena would scan every column on every query, and types would be re-parsed every time. |

## Transformation

| Option | Monthly cost | Verdict |
|---|---:|---|
| **Lambda + pandas + DuckDB SQL** (chosen) | ~$0.01 | Under 2 seconds of work a day. Same code and SQL run locally and in tests. |
| Glue Spark ETL job | +$0.44 | Spark start-up is longer than the whole job, and I lose fast local tests. Right for hundreds of GB. |
| Glue Python shell | ~+$0.01 | A fine middle ground; it would replace Transform if I needed more than Lambda's 15 minutes. |
| Athena CTAS / INSERT for gold | pennies | Keeps everything in SQL, but each run creates new files and needs cleanup of the old ones; DuckDB lets me test the same SQL in milliseconds. If the gold SQL outgrew one machine, this is the next step. |
| dbt (dbt-athena or dbt-duckdb) | free | Good fit for the gold layer as the number of models grows: tests, docs, lineage. With five models, a folder of `.sql` files run in order is enough. |
| EMR Serverless | | Overkill below hundreds of GB. |

## Orchestration

| Option | Monthly cost | Verdict |
|---|---:|---|
| **Step Functions Standard + EventBridge Scheduler** (chosen) | ~$0.005 | Per-step retries, a failure branch, execution history. |
| One Lambda doing everything | ~$0.01 | Cheapest, but a failure in step 3 re-runs steps 1-2 and there's no per-step history. |
| Amazon MWAA (Airflow) | ~$358 | The right tool for dozens of interdependent DAGs and a team that knows Airflow. For one four-step daily job it costs ~300x everything else combined. |
| Glue Workflows | small | Ties orchestration to Glue jobs, which I'm not using. |

## Query and serving

| Option | Monthly cost | Verdict |
|---|---:|---|
| **Athena over the Glue Data Catalog** (chosen) | ~$0.02 | Pay per query, nothing idle, standard SQL, works with QuickSight and any JDBC/ODBC tool. |
| Redshift Serverless | ~$90 for an hour a day | Worth it for heavy concurrent BI with joins over large tables. Here the gold tables total ~300 KB. |
| QuickSight dashboard on Athena | per user | Nice for non-SQL users. I left it out to keep the bill near zero; it connects to the same workgroup. |
| A public API (API Gateway + Lambda) | small | Would let a newsroom or app pull `rain_daily` directly. Not needed until someone asks for it. |

## Catalog

| Option | Verdict |
|---|---|
| **Tables declared in CloudFormation, partition projection on `year`** (chosen) | Schema lives in the repo and is reviewed like code. No crawler, no `MSCK REPAIR`. |
| Glue crawler | ~$2.20/month at a 10-minute minimum per daily run, and it would happily infer a broken schema from a broken file. |
| Lake Formation permissions | The right layer for column- or row-level access across teams. Public weather data doesn't need it. |

## Data quality

| Option | Verdict |
|---|---|
| **Checks in Python, with block vs fix severities, results stored per run** (chosen) | Runs in unit tests and on a laptop. |
| AWS Glue Data Quality (DQDL) | Managed, with anomaly detection and results in the console. My rules translate one-to-one (`IsUnique`, `ColumnValues between`, `RowCount`). I'd move to it alongside a move to Glue jobs. |
| Great Expectations / Soda | Good if several pipelines share a rule library. One pipeline doesn't need the framework. |

## Alert delivery

| Option | Verdict |
|---|---|
| **SNS email, English and Nepali in one message** (chosen) | Free at this volume and needs nothing from subscribers. |
| SMS through SNS | International SMS to Nepal costs far more per message than a local Nepali SMS gateway; for SMS I'd use a local aggregator behind the same topic. |
| Slack / Teams webhooks via a Lambda subscriber | Easy to add as another SNS subscription. |
