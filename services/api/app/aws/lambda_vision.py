"""Runs the vision pipeline on Lambda. Files travel through S3 because sync payloads are capped near 6 MB."""

import json
import logging
from typing import Any
from uuid import UUID, uuid4

import boto3
from aec_contracts import AnalyzeResult, ErrorCode
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import Settings
from ..errors import ServiceError
from ..observability import request_id_var

log = logging.getLogger("api.aws.lambda")

READ_TIMEOUT_SECONDS = 330  # longer than the function's 300 s timeout


def _unavailable() -> ServiceError:
    return ServiceError(502, ErrorCode.UPSTREAM_UNAVAILABLE, "The vision service is unavailable.")


class LambdaVisionClient:
    def __init__(self, settings: Settings, s3: Any = None, lambda_client: Any = None) -> None:
        assert settings.s3_bucket and settings.vision_lambda_name  # Settings refuses the switch without them
        self._bucket = settings.s3_bucket
        self._function = settings.vision_lambda_name
        self._s3 = s3 or boto3.client("s3", region_name=settings.aws_region)
        # One attempt only: an automatic retry after a read timeout would run a slow job twice.
        self._lambda = lambda_client or boto3.client(
            "lambda", region_name=settings.aws_region,
            config=Config(read_timeout=READ_TIMEOUT_SECONDS, retries={"total_max_attempts": 1}))

    def analyze(self, floorplan_id: UUID, data: bytes, filename: str, content_type: str) -> AnalyzeResult:
        prefix = f"tmp/{floorplan_id}/{uuid4().hex}"
        source_key, result_key = f"{prefix}/source", f"{prefix}/result.json"
        event = {"bucket": self._bucket, "source_key": source_key, "result_key": result_key,
                 "content_type": content_type, "floorplan_id": str(floorplan_id), "request_id": request_id_var.get()}
        try:
            self._s3.put_object(Bucket=self._bucket, Key=source_key, Body=data, ContentType=content_type)
            response = self._lambda.invoke(FunctionName=self._function, InvocationType="RequestResponse",
                                           Payload=json.dumps(event))
            reply = json.loads(response["Payload"].read())
            if response.get("FunctionError") or reply.get("error"):
                log.warning("vision lambda failed", extra={"fields": {
                    "function_error": response.get("FunctionError"), "error": reply.get("error")}})
                raise _unavailable()
            body = self._s3.get_object(Bucket=self._bucket, Key=result_key)["Body"].read()
            return AnalyzeResult.model_validate_json(body)
        except (BotoCoreError, ClientError, ValueError) as exc:  # ValueError covers bad JSON and pydantic errors
            log.warning("vision lambda call failed", extra={"fields": {"error": type(exc).__name__}})
            raise _unavailable() from exc
        finally:
            self._clean_up(source_key, result_key)

    def _clean_up(self, *keys: str) -> None:
        try:
            self._s3.delete_objects(Bucket=self._bucket,
                                    Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True})
        except (BotoCoreError, ClientError):
            log.warning("could not delete vision temp files")  # the bucket's 1-day tmp/ expiry is the backstop
