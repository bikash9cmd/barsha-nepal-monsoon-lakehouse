"""The lake: one key space, backed by a local folder or an S3 prefix.

Every stage reads and writes through this interface, so the pipeline that runs on a laptop
is the same code that runs in Lambda.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Protocol

import pyarrow as pa
import pyarrow.parquet as pq


class Lake(Protocol):
    def read_bytes(self, key: str) -> bytes: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def list(self, prefix: str) -> list[str]: ...
    def exists(self, key: str) -> bool: ...
    def uri(self, key: str) -> str: ...


class LocalLake:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on one filesystem, like an S3 PUT

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        folder = base if base.is_dir() else base.parent
        if not folder.exists():
            return []
        keys = (p.relative_to(self.root).as_posix() for p in folder.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix) and not k.endswith(".tmp"))

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def uri(self, key: str) -> str:
        return str(self._path(key))


class S3Lake:
    def __init__(self, bucket: str, prefix: str = "", client=None):
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.s3 = client or boto3.client("s3")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def read_bytes(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()

    def write_bytes(self, key: str, data: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)

    def list(self, prefix: str) -> list[str]:
        keys = []
        strip = len(self.prefix) + 1 if self.prefix else 0
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            keys.extend(obj["Key"][strip:] for obj in page.get("Contents", []))
        return sorted(keys)

    def exists(self, key: str) -> bool:
        resp = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=self._key(key), MaxKeys=1)
        return any(obj["Key"] == self._key(key) for obj in resp.get("Contents", []))

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{self._key(key)}"


def open_lake(location: str, client=None) -> Lake:
    if location.startswith("s3://"):
        bucket, _, prefix = location[5:].partition("/")
        return S3Lake(bucket, prefix, client)
    return LocalLake(location)


def read_arrow(lake: Lake, key: str) -> pa.Table:
    return pq.read_table(io.BytesIO(lake.read_bytes(key)))


def write_arrow(lake: Lake, key: str, table: pa.Table) -> None:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    lake.write_bytes(key, buf.getvalue())


def read_json(lake: Lake, key: str, default=None):
    if not lake.exists(key):
        return default
    return json.loads(lake.read_bytes(key))


def write_json(lake: Lake, key: str, obj) -> None:
    lake.write_bytes(key, json.dumps(obj, indent=2, sort_keys=True, default=str).encode())
