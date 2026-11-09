"""AWS Lambda entry point: the same pipeline as POST /v1/analyze, with files passed through S3.

The event comes from the worker (services/api/app/aws/lambda_vision.py) and only IAM-authorised callers can invoke this.
"""

import logging
from functools import lru_cache
from typing import Any
from uuid import UUID

import boto3

from app.config import get_settings
from app.errors import ServiceError
from app.pipeline.runner import run_pipeline

logging.getLogger().setLevel(get_settings().log_level)  # Lambda's root logger defaults to WARNING
log = logging.getLogger("vision.lambda")


@lru_cache
def _default_s3() -> Any:
    return boto3.client("s3")


def handler(event: dict[str, Any], _context: Any, s3: Any = None) -> dict[str, str]:
    s3 = s3 or _default_s3()
    bucket = event["bucket"]
    log.info("analyze", extra={"request_id": event.get("request_id", "-"), "floorplan_id": event["floorplan_id"]})
    data = s3.get_object(Bucket=bucket, Key=event["source_key"])["Body"].read()
    try:
        result = run_pipeline(data, event["content_type"], UUID(event["floorplan_id"]))
    except ServiceError as exc:  # undecodable input
        return {"error": exc.message or "The file could not be processed."}
    s3.put_object(Bucket=bucket, Key=event["result_key"], Body=result.model_dump_json().encode(),
                  ContentType="application/json")
    return {"result_key": event["result_key"]}
