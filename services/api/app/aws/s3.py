"""S3 behind BlobStore. One real bucket: the logical bucket name becomes a key prefix."""

import logging
from collections.abc import Callable
from typing import Any

import boto3
from aec_contracts import ErrorCode
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import Settings
from ..errors import ServiceError
from ..storage import SIGNED_URL_TTL_SECONDS, BlobStore

log = logging.getLogger("api.aws.s3")


def _unavailable() -> ServiceError:
    return ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "File storage is unavailable.")


def _guarded[T](action: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except (BotoCoreError, ClientError) as exc:
        log.warning("s3 %s failed", action, extra={"fields": {"error": str(exc)}})
        raise _unavailable() from exc


class S3BlobStore:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        assert settings.s3_bucket  # Settings refuses the switch without it
        self._bucket = settings.s3_bucket
        # Virtual addressing gives regional URLs: the global host can redirect on new buckets, and the CSP allows one.
        self._client = client or boto3.client("s3", region_name=settings.aws_region, config=Config(
            signature_version="s3v4", s3={"addressing_style": "virtual"}))

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        _guarded("put", lambda: self._client.put_object(Bucket=self._bucket, Key=f"{bucket}/{key}", Body=data,
                                                        ContentType=content_type))

    def get(self, bucket: str, key: str) -> bytes:
        def read() -> bytes:
            body: bytes = self._client.get_object(Bucket=self._bucket, Key=f"{bucket}/{key}")["Body"].read()
            return body

        return _guarded("get", read)

    def signed_urls(self, bucket: str, keys: list[str]) -> dict[str, str]:
        def sign(key: str) -> str:
            url: str = self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": f"{bucket}/{key}"},
                ExpiresIn=SIGNED_URL_TTL_SECONDS)
            return url

        return _guarded("sign", lambda: {key: sign(key) for key in keys})

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        def run() -> None:
            pages = self._client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket,
                                                                           Prefix=f"{bucket}/{prefix}")
            for page in pages:
                keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if not keys:
                    continue
                result = self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": keys, "Quiet": True})
                if result.get("Errors"):  # delete_objects reports per-key failures without raising
                    log.warning("s3 delete left objects behind", extra={"fields": {"count": len(result["Errors"])}})
                    raise _unavailable()

        _guarded("delete", run)


class RoutedBlobStore:
    """Sends named logical buckets to their own store and everything else to the default."""

    def __init__(self, default: BlobStore, routes: dict[str, BlobStore]) -> None:
        self._default = default
        self._routes = routes

    def _for(self, bucket: str) -> BlobStore:
        return self._routes.get(bucket, self._default)

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self._for(bucket).put(bucket, key, data, content_type)

    def get(self, bucket: str, key: str) -> bytes:
        return self._for(bucket).get(bucket, key)

    def signed_urls(self, bucket: str, keys: list[str]) -> dict[str, str]:
        return self._for(bucket).signed_urls(bucket, keys)

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        self._for(bucket).delete_prefix(bucket, prefix)
