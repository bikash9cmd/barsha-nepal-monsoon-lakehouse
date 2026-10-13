"""Monthly AWS cost estimate for Barsha, from explicit assumptions. Prints markdown tables.

    python scripts/cost_model.py

Prices are on-demand us-east-1 list prices (USD) as I understood them in October 2026, rounded
up. Check them in the AWS Pricing Calculator before quoting. The free tier is ignored, so the
totals are what an account pays after its first year.
"""

from __future__ import annotations

DAYS = 30

PRICE = {
    "lambda_gb_s_arm": 0.0000133334,
    "lambda_req": 0.20 / 1e6,
    "sfn_transition": 0.025 / 1000,
    "s3_gb": 0.023,
    "s3_put": 0.005 / 1000,
    "s3_get": 0.0004 / 1000,
    "athena_tb": 5.00,
    "athena_min_mb": 10,
    "logs_gb": 0.50,
    "custom_metric": 0.30,
    "alarm": 0.10,
    "ecr_gb": 0.10,
    # Alternatives
    "glue_dpu_hr": 0.44,
    "mwaa_small_hr": 0.49,
    "redshift_rpu_hr": 0.375,
    "kinesis_on_demand_stream_hr": 0.04,
}

ASSUME = {
    # Daily run, measured locally and padded for Lambda cold starts (init is billed).
    "runs": DAYS,
    "fn": {  # name: (memory GB, billed seconds per run incl. init)
        "ingest": (0.5, 8),
        "transform": (1.0, 8),
        "gold": (2.0, 8),
        "bulletin": (0.5, 5),
    },
    "transitions_per_run": 6,
    "lake_gb": 0.2,  # ~18 MB current data + 90 days of noncurrent raw versions
    "puts_per_run": 40,
    "gets_per_run": 120,  # gold reads every silver year
    "athena_queries": 300,  # an analyst's month; each is under the 10 MB minimum
    "custom_metrics": 2,  # SourceLagDays, YearsQuarantined
    "alarms": 5,
    "logs_gb": 0.05,
    "image_gb": 0.35,
}


def barsha() -> dict[str, float]:
    p, a = PRICE, ASSUME
    gb_s = sum(gb * s for gb, s in a["fn"].values()) * a["runs"]
    requests = len(a["fn"]) * a["runs"]
    return {
        "Lambda (4 functions, daily)": gb_s * p["lambda_gb_s_arm"] + requests * p["lambda_req"],
        "Step Functions (standard)": a["runs"] * a["transitions_per_run"] * p["sfn_transition"],
        "S3 storage + requests": a["lake_gb"] * p["s3_gb"]
        + a["runs"] * (a["puts_per_run"] * p["s3_put"] + a["gets_per_run"] * p["s3_get"]),
        "Athena (300 queries, 10 MB minimum each)": a["athena_queries"] * p["athena_min_mb"] / 1e6 * p["athena_tb"],
        "Glue Data Catalog (6 tables)": 0.0,  # first million objects free
        "CloudWatch custom metrics (2)": a["custom_metrics"] * p["custom_metric"],
        "CloudWatch alarms (5)": a["alarms"] * p["alarm"],
        "CloudWatch Logs": a["logs_gb"] * p["logs_gb"],
        "ECR image storage": a["image_gb"] * p["ecr_gb"],
    }


def alternatives() -> dict[str, float]:
    p, a = PRICE, ASSUME
    return {
        "Glue Spark ETL instead of the transform Lambda (2 DPU, 1 min minimum)":
            a["runs"] * 2 * p["glue_dpu_hr"] / 60,
        "Glue crawler instead of partition projection (10 min minimum, 1 DPU)":
            a["runs"] * p["glue_dpu_hr"] * 10 / 60,
        "MWAA (smallest environment, always on) instead of Step Functions": 730 * p["mwaa_small_hr"],
        "Redshift Serverless instead of Athena (8 RPU, 1 h of use a day)": a["runs"] * 8 * p["redshift_rpu_hr"],
        "Kinesis Data Streams on-demand, one stream, always on": 730 * p["kinesis_on_demand_stream_hr"],
    }


def table(rows: dict[str, float]) -> str:
    out = ["| Item | USD / month |", "|---|---:|"]
    out += [f"| {k} | {v:.3f} |" for k, v in rows.items()]
    out.append(f"| **Total** | **{sum(rows.values()):.2f}** |")
    return "\n".join(out)


if __name__ == "__main__":
    print("## Barsha as built\n")
    print(table(barsha()))
    print("\n## What the common alternatives would add\n")
    print("\n".join(["| Alternative | USD / month |", "|---|---:|"]
                    + [f"| {k} | {v:.2f} |" for k, v in alternatives().items()]))
