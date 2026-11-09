"""Seams the AWS profile plugs into. The defaults here keep the free stack's behaviour."""

from typing import Protocol
from uuid import UUID

from aec_contracts import AnalyzeResult


class VisionAnalyzer(Protocol):
    def analyze(self, floorplan_id: UUID, data: bytes, filename: str, content_type: str) -> AnalyzeResult: ...


class WorkQueue(Protocol):
    """Only wakes workers: processing_jobs stays the source of truth."""

    def publish(self, job_id: UUID) -> None: ...  # must not raise, the worker's backstop still finds the job
    def receive(self) -> str | None: ...  # a handle for ack(), or None if nothing arrived
    def ack(self, handle: str) -> None: ...


class PollingQueue:
    def publish(self, job_id: UUID) -> None:
        pass

    def receive(self) -> str | None:
        return None

    def ack(self, handle: str) -> None:
        pass


class Notifier(Protocol):
    def job_finished(self, job_id: UUID, filename: str, status: str) -> None: ...  # must not raise


class NoNotifier:
    def job_finished(self, job_id: UUID, filename: str, status: str) -> None:
        pass
