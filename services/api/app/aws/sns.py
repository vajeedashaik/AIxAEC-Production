"""Job-finished email through SNS."""

import logging
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ..config import Settings

log = logging.getLogger("api.aws.sns")


class SnsNotifier:
    """shortcut: one shared topic, so this is an owner alert; per-user email needs a subscription per user."""

    def __init__(self, settings: Settings, client: Any = None) -> None:
        assert settings.sns_topic_arn  # Settings refuses the switch without it
        self._topic = settings.sns_topic_arn
        self._client = client or boto3.client("sns", region_name=settings.aws_region)

    def job_finished(self, job_id: UUID, filename: str, status: str) -> None:
        try:
            # The filename is user input, and an SNS subject must be short plain ASCII, so it stays in the body.
            self._client.publish(TopicArn=self._topic, Subject=f"Floor plan processing {status}",
                                 Message=f"Status: {status}\nFile: {filename}\nJob: {job_id}")
        except (BotoCoreError, ClientError) as exc:
            log.warning("sns publish failed", extra={"fields": {"job_id": str(job_id), "error": str(exc)}})
