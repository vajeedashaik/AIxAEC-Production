"""Blob storage behind a small interface. Only this module knows about Supabase Storage."""

import logging
from collections.abc import Callable, Iterator
from functools import cached_property
from typing import Protocol

import httpx
from aec_contracts import ErrorCode
from pydantic import ValidationError
from storage3.types import FileOptions
from storage3.utils import StorageException

from supabase import Client, create_client

from .config import Settings
from .errors import ServiceError

log = logging.getLogger("api.storage")

SOURCE_BUCKET = "floorplans"
ARTIFACT_BUCKET = "artifacts"
SIGNED_URL_TTL_SECONDS = 15 * 60


class BlobStore(Protocol):
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, bucket: str, key: str) -> bytes: ...
    def signed_urls(self, bucket: str, keys: list[str]) -> dict[str, str]: ...
    def delete_prefix(self, bucket: str, prefix: str) -> None: ...


def _guarded[T](action: str, fn: Callable[[], T]) -> T:
    try:
        return fn()
    except (StorageException, httpx.HTTPError, ValidationError) as exc:
        log.warning("blob %s failed", action, extra={"fields": {"error": str(exc)}})
        raise ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "File storage is unavailable.") from exc


class SupabaseBlobStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @cached_property
    def _client(self) -> Client:
        key = self._settings.supabase_service_role_key
        if key is None:
            log.error("SUPABASE_SERVICE_ROLE_KEY is not set")
            raise ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "File storage is unavailable.")
        return create_client(self._settings.supabase_url, key.get_secret_value())

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        # upsert: a retried job rewrites the same artifact key
        options: FileOptions = {"content-type": content_type, "upsert": "true"}
        _guarded("put", lambda: self._client.storage.from_(bucket).upload(key, data, options))

    def get(self, bucket: str, key: str) -> bytes:
        return _guarded("get", lambda: self._client.storage.from_(bucket).download(key))

    def signed_urls(self, bucket: str, keys: list[str]) -> dict[str, str]:
        signed = _guarded("sign", lambda: self._client.storage.from_(bucket).create_signed_urls(
            keys, SIGNED_URL_TTL_SECONDS))
        urls = {item["path"]: item["signedURL"] for item in signed if item["path"] and item["signedURL"]}
        public = self._settings.supabase_public_url
        return {k: u.replace(self._settings.supabase_url, public, 1) for k, u in urls.items()} if public else urls

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        def run() -> None:
            keys = list(self._walk(bucket, prefix.rstrip("/")))
            for start in range(0, len(keys), 500):
                self._client.storage.from_(bucket).remove(keys[start:start + 500])

        _guarded("delete", run)

    def _walk(self, bucket: str, prefix: str) -> Iterator[str]:
        offset, page = 0, 1000
        while True:
            items = self._client.storage.from_(bucket).list(prefix, {"limit": page, "offset": offset})
            for item in items:
                path = f"{prefix}/{item['name']}"
                yield from (self._walk(bucket, path) if item.get("id") is None else (path,))  # folders have no id
            if len(items) < page:
                return
            offset += page
