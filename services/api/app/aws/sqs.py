"""SQS as the worker wake-up signal. Postgres still decides which job runs."""

import json
import logging
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ..config import Settings

log = logging.getLogger("api.aws.sqs")

LONG_POLL_SECONDS = 20


class SqsQueue:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        assert settings.sqs_queue_url  # Settings refuses the switch without it
        self._url = settings.sqs_queue_url
        self._client = client or boto3.client("sqs", region_name=settings.aws_region)

    def publish(self, job_id: UUID) -> None:
        try:
            self._client.send_message(QueueUrl=self._url, MessageBody=json.dumps({"job_id": str(job_id)}))
        except (BotoCoreError, ClientError) as exc:
            log.warning("sqs publish failed", extra={"fields": {"job_id": str(job_id), "error": str(exc)}})

    def receive(self) -> str | None:
        messages = self._client.receive_message(QueueUrl=self._url, MaxNumberOfMessages=1,
                                                WaitTimeSeconds=LONG_POLL_SECONDS).get("Messages")
        return str(messages[0]["ReceiptHandle"]) if messages else None

    def ack(self, handle: str) -> None:
        self._client.delete_message(QueueUrl=self._url, ReceiptHandle=handle)
