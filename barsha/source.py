"""Read the upstream GSOD files: the public S3 bucket, or a local mirror with the same layout."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .config import NEPAL_STATION_PREFIX, SOURCE_REGION


@dataclass(frozen=True)
class SourceObject:
    key: str  # "2024/44454099999.csv"
    etag: str
    size: int

    @property
    def year(self) -> int:
        return int(self.key.split("/")[0])

    @property
    def station_id(self) -> str:
        return self.key.split("/")[1].removesuffix(".csv")


class S3Source:
    """Anonymous reads from an AWS Open Data bucket. No credentials, no cross-account role."""

    def __init__(self, bucket: str, client=None):
        if client is None:
            import boto3
            from botocore import UNSIGNED
            from botocore.config import Config

            client = boto3.client(
                "s3",
                region_name=SOURCE_REGION,
                config=Config(signature_version=UNSIGNED, retries={"max_attempts": 5, "mode": "adaptive"}),
            )
        self.bucket = bucket
        self.s3 = client

    def list(self, year: int) -> list[SourceObject]:
        out = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{year}/{NEPAL_STATION_PREFIX}"):
            for obj in page.get("Contents", []):
                out.append(SourceObject(obj["Key"], obj["ETag"].strip('"'), obj["Size"]))
        return out

    def read(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()


class LocalSource:
    """A folder laid out like the bucket (<year>/<station>.csv). Used by tests and offline runs."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def list(self, year: int) -> list[SourceObject]:
        folder = self.root / str(year)
        if not folder.is_dir():
            return []
        out = []
        for path in sorted(folder.glob(f"{NEPAL_STATION_PREFIX}*.csv")):
            data = path.read_bytes()
            out.append(SourceObject(f"{year}/{path.name}", hashlib.md5(data).hexdigest(), len(data)))
        return out

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


def open_source(location: str, client=None):
    if location.startswith("s3://"):
        return S3Source(location[5:].strip("/"), client)
    return LocalSource(location)
