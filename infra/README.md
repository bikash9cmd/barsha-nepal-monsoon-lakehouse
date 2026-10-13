# Deploying to AWS

Everything is defined in [`template.yaml`](template.yaml) (AWS SAM). Region: **us-east-1**, next to the NOAA source bucket (see ADR-007 in [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)).

## Prerequisites

- An AWS account and credentials (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and Docker (the image is built for arm64)

## Deploy

```bash
sam build --template-file infra/template.yaml
sam deploy --guided --region us-east-1      # stack name e.g. barsha; set OpsEmail to get alarms
```

`sam deploy --guided` creates an ECR repository for the image and saves your answers in `samconfig.toml`.

## First load

The stack starts empty. Run one backfill through the state machine; it copies every Nepal file since 1976 (~410 files, 16 MB):

```bash
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn from the outputs> \
  --input '{"mode": "backfill"}'
```

From then on the schedule runs daily at 01:30 UTC (07:15 Nepal time).

## Query

In the Athena console, pick the `barsha` workgroup and the `barsha` database, then try the files in [`sql/athena/`](../sql/athena/). Or from the CLI:

```bash
aws athena start-query-execution --work-group barsha \
  --query-string "SELECT * FROM barsha.station_health"
```

## Replay a past day

```bash
aws stepfunctions start-execution --state-machine-arn <arn> \
  --input '{"years": [2024], "as_of": "2024-09-28"}'
```

This rebuilds gold as of that date and publishes that day's bulletin to SNS, so subscribe a test email first. Gold stays as of that date until the next scheduled run rebuilds it for today; for side-effect-free replays, use `python -m barsha bulletin --as-of 2024-09-28` locally.

## Rebuild after a bad deploy

Every stage is idempotent. To rebuild silver from raw for some years without touching the source, invoke the transform function with `{"run_id": "manual", "ingest": {"changed_years": [2024, 2025]}}`, then the gold function. Locally, `make rebuild LAKE=s3://<bucket>` does the same.

## Tear down

```bash
sam delete
```

The lake bucket is versioned, so empty it first, including old versions (`aws s3api delete-objects` over `list-object-versions`, or the console's "Empty" button).

## What's verified and what isn't

- `cfn-lint infra/template.yaml` passes, and CI runs it.
- The four handlers run in Step Functions order against mocked S3 and SNS in `tests/test_aws_handlers.py`.
- The ingest code has run against the real `s3://noaa-gsod-pds` bucket (anonymous reads), and the full pipeline has run end to end on that data locally.
- The stack itself has **not** been deployed to an AWS account yet, so expect small fixes on a first deploy (IAM edge cases, the arm64 image build).
