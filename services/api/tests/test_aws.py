"""AWS profile adapters. moto stands in for S3, SQS and SNS; nothing here touches real AWS."""

import io
import json
import threading
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import boto3
import pytest
import respx
from botocore.exceptions import ClientError
from moto import mock_aws
from pydantic import ValidationError

from app.aws.lambda_vision import LambdaVisionClient
from app.aws.s3 import RoutedBlobStore, S3BlobStore
from app.aws.sns import SnsNotifier
from app.aws.sqs import SqsQueue
from app.config import Settings
from app.container import build_container
from app.errors import ServiceError
from app.jobs import Claim, fail_job
from app.ports import PollingQueue
from app.worker import run_forever

from .conftest import Api, analyze_result

REGION = "ap-south-1"
BUCKET = "aec-test"
FLOORPLAN = UUID("11111111-1111-1111-1111-111111111111")


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, environment="test", aws_region=REGION, s3_bucket=BUCKET, **overrides)  # type: ignore[call-arg]


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        yield client


# --- S3 ---

def test_s3_round_trip_uses_the_logical_bucket_as_prefix(s3: Any) -> None:
    store = S3BlobStore(settings())
    store.put("artifacts", "a/b.png", b"data", "image/png")
    assert store.get("artifacts", "a/b.png") == b"data"
    assert s3.head_object(Bucket=BUCKET, Key="artifacts/a/b.png")["ContentType"] == "image/png"


def test_s3_signed_urls_expire(s3: Any) -> None:
    url = S3BlobStore(settings()).signed_urls("artifacts", ["a/b.png"])["a/b.png"]
    assert "artifacts/a/b.png" in url and "X-Amz-Expires=900" in url
    assert url.startswith(f"https://{BUCKET}.s3.{REGION}.amazonaws.com/")  # the origin Terraform gives the web CSP


def test_s3_delete_prefix_covers_every_page_and_only_that_prefix(s3: Any) -> None:
    store = S3BlobStore(settings())
    for i in range(1001):
        s3.put_object(Bucket=BUCKET, Key=f"artifacts/p1/{i}", Body=b"")
    s3.put_object(Bucket=BUCKET, Key="artifacts/p2/keep", Body=b"")
    store.delete_prefix("artifacts", "p1/")
    assert [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]] == ["artifacts/p2/keep"]


def test_s3_delete_reports_per_key_failures(s3: Any) -> None:
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [{"Contents": [{"Key": "artifacts/p/x"}]}]
    client.delete_objects.return_value = {"Errors": [{"Key": "artifacts/p/x"}]}
    with pytest.raises(ServiceError):
        S3BlobStore(settings(), client=client).delete_prefix("artifacts", "p/")


def test_s3_missing_object_is_a_clean_error(s3: Any) -> None:
    with pytest.raises(ServiceError) as caught:
        S3BlobStore(settings()).get("artifacts", "nope")
    assert caught.value.status == 502
    assert "NoSuchKey" not in (caught.value.message or "")


def test_routing_sends_only_named_buckets_to_s3() -> None:
    default, artifacts = MagicMock(), MagicMock()
    store = RoutedBlobStore(default, {"artifacts": artifacts})
    store.put("artifacts", "k", b"", "image/png")
    store.put("floorplans", "k", b"", "image/png")
    artifacts.put.assert_called_once_with("artifacts", "k", b"", "image/png")
    default.put.assert_called_once_with("floorplans", "k", b"", "image/png")


# --- settings and wiring ---

@pytest.mark.parametrize(("overrides", "missing"), [
    ({"blob_backend": "hybrid"}, "S3_BUCKET"),
    ({"queue_backend": "sqs"}, "SQS_QUEUE_URL"),
    ({"notifier": "sns"}, "SNS_TOPIC_ARN"),
    ({"vision_mode": "lambda"}, "VISION_LAMBDA_NAME"),
])
def test_switches_refuse_to_start_without_their_settings(overrides: dict[str, str], missing: str) -> None:
    with pytest.raises(ValidationError, match=missing):
        Settings(_env_file=None, environment="test", aws_region=REGION, **overrides)  # type: ignore[arg-type]


def test_defaults_use_no_aws() -> None:
    c = build_container(Settings(_env_file=None, environment="test"), blobs=MagicMock())  # type: ignore[call-arg]
    assert isinstance(c.queue, PollingQueue)
    assert type(c.vision).__name__ == "VisionClient"


def test_all_switches_on_build_the_aws_adapters(s3: Any) -> None:
    c = build_container(settings(blob_backend="hybrid", queue_backend="sqs", vision_mode="lambda", notifier="sns",
                                 sqs_queue_url="https://q", sns_topic_arn="arn:t", vision_lambda_name="vision"))
    assert isinstance(c.blobs, RoutedBlobStore)
    assert isinstance(c.queue, SqsQueue)
    assert isinstance(c.vision, LambdaVisionClient)
    assert isinstance(c.notifier, SnsNotifier)


# --- SQS and the worker loop ---

@pytest.fixture
def queue_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION).create_queue(QueueName="jobs")["QueueUrl"]


def test_sqs_publish_receive_ack(queue_url: str) -> None:
    queue = SqsQueue(settings(sqs_queue_url=queue_url))
    queue.publish(FLOORPLAN)
    handle = queue.receive()
    assert handle is not None
    queue.ack(handle)
    attributes = boto3.client("sqs", region_name=REGION).get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])
    assert set(attributes["Attributes"].values()) == {"0"}


def test_sqs_publish_failure_is_swallowed(queue_url: str) -> None:
    SqsQueue(settings(sqs_queue_url=f"{queue_url}-missing")).publish(FLOORPLAN)


def loop_once(monkeypatch: pytest.MonkeyPatch, handle: str | None, error: Exception | None = None) -> MagicMock:
    """One pass of the real worker loop with a fake queue."""
    stop = threading.Event()

    def fake_run_once(_: Any) -> bool:
        stop.set()
        if error:
            raise error
        return True

    queue = MagicMock()
    queue.receive.return_value = handle
    monkeypatch.setattr("app.worker.run_once", fake_run_once)
    run_forever(SimpleNamespace(queue=queue, settings=SimpleNamespace(worker_poll_seconds=0)), stop)  # type: ignore[arg-type]
    return queue


def test_worker_acks_after_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    loop_once(monkeypatch, "h1").ack.assert_called_once_with("h1")


def test_worker_leaves_the_message_when_run_once_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    loop_once(monkeypatch, "h1", RuntimeError("db away")).ack.assert_not_called()


def test_worker_without_a_message_acks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    loop_once(monkeypatch, None).ack.assert_not_called()


# --- enqueue and finish hooks (real Postgres, like the other route tests) ---

def recorders(api: Api) -> tuple[MagicMock, MagicMock]:
    api.c.queue, api.c.notifier = MagicMock(), MagicMock()
    api.c.queue.receive.return_value = None
    return api.c.queue, api.c.notifier  # type: ignore[return-value]


def test_upload_publishes_once(api: Api) -> None:
    queue, _ = recorders(api)
    floorplan = api.upload(api.project())
    queue.publish.assert_called_once()
    job = api.request("GET", f"/v1/floorplans/{floorplan['id']}/job").json()
    assert str(queue.publish.call_args.args[0]) == job["id"]


def test_upload_without_processing_publishes_nothing(api: Api) -> None:
    queue, _ = recorders(api)
    api.upload(api.project(), process=False)
    queue.publish.assert_not_called()


def test_reprocess_publishes(api: Api) -> None:
    queue, _ = recorders(api)
    floorplan = api.upload(api.project(), process=False)
    assert api.request("POST", f"/v1/floorplans/{floorplan['id']}/process").status_code == 202
    queue.publish.assert_called_once()


def test_completed_job_notifies_once(api: Api, upstream: respx.MockRouter) -> None:
    _, notifier = recorders(api)
    api.upload(api.project())
    api.run_worker()
    notifier.job_finished.assert_called_once()
    assert notifier.job_finished.call_args.args[1:] == ("plan.png", "COMPLETED")


def test_failed_job_notifies_once(api: Api, upstream: respx.MockRouter) -> None:
    _, notifier = recorders(api)
    upstream.routes["analyze"].mock(return_value=respx.MockResponse(422, json={}))
    api.upload(api.project())
    api.run_worker()
    notifier.job_finished.assert_called_once()
    assert notifier.job_finished.call_args.args[2] == "FAILED"


def test_lost_job_notifies_nothing(api: Api) -> None:
    _, notifier = recorders(api)
    floorplan = api.upload(api.project())
    job = api.request("GET", f"/v1/floorplans/{floorplan['id']}/job").json()
    fail_job(api.c, Claim(UUID(job["id"]), UUID(floorplan["id"]), attempts=99), "too late")
    notifier.job_finished.assert_not_called()


def test_sns_keeps_the_filename_out_of_the_subject() -> None:
    client = MagicMock()
    SnsNotifier(settings(sns_topic_arn="arn:t"), client=client).job_finished(FLOORPLAN, "evil\nname.png", "COMPLETED")
    sent = client.publish.call_args.kwargs
    assert sent["Subject"] == "Floor plan processing COMPLETED"
    assert "evil" in sent["Message"]


def test_sns_failure_is_swallowed() -> None:
    client = MagicMock()
    client.publish.side_effect = ClientError({"Error": {"Code": "Throttled", "Message": "x"}}, "Publish")
    SnsNotifier(settings(sns_topic_arn="arn:t"), client=client).job_finished(FLOORPLAN, "a.png", "FAILED")


# --- vision on Lambda ---

class FakeLambda:
    def __init__(self, s3: Any, reply: dict[str, str] | None = None, function_error: str | None = None,
                 body: str | None = None) -> None:
        self.s3, self.reply, self.function_error, self.body = s3, reply, function_error, body
        self.event: dict[str, str] = {}

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.event = json.loads(kwargs["Payload"])
        assert self.s3.get_object(Bucket=BUCKET, Key=self.event["source_key"])["Body"].read() == b"plan"
        body = self.body if self.body is not None else json.dumps(analyze_result(str(FLOORPLAN)))
        self.s3.put_object(Bucket=BUCKET, Key=self.event["result_key"], Body=body.encode())
        reply = self.reply if self.reply is not None else {"result_key": self.event["result_key"]}
        response: dict[str, Any] = {"Payload": io.BytesIO(json.dumps(reply).encode())}
        if self.function_error:
            response["FunctionError"] = self.function_error
        return response


def vision_client(s3: Any, fake: Any) -> LambdaVisionClient:
    return LambdaVisionClient(settings(vision_lambda_name="vision"), s3=s3, lambda_client=fake)


def no_temp_files(s3: Any) -> bool:
    return s3.list_objects_v2(Bucket=BUCKET, Prefix="tmp/")["KeyCount"] == 0


def test_lambda_returns_the_result_and_cleans_up(s3: Any) -> None:
    fake = FakeLambda(s3)
    result = vision_client(s3, fake).analyze(FLOORPLAN, b"plan", "plan.png", "image/png")
    assert result.status == "COMPLETED"
    assert fake.event["floorplan_id"] == str(FLOORPLAN)
    assert no_temp_files(s3)


@pytest.mark.parametrize("kwargs", [{"function_error": "Unhandled"}, {"reply": {"error": "bad file"}},
                                    {"body": "not json"}, {"body": "{}"}])
def test_lambda_failures_become_a_clean_error_and_clean_up(s3: Any, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ServiceError) as caught:
        vision_client(s3, FakeLambda(s3, **kwargs)).analyze(FLOORPLAN, b"plan", "plan.png", "image/png")
    assert caught.value.status == 502
    assert no_temp_files(s3)


def test_lambda_client_never_retries(s3: Any) -> None:
    client = LambdaVisionClient(settings(vision_lambda_name=f"v{uuid4().hex}"), s3=s3)
    assert client._lambda.meta.config.retries["total_max_attempts"] == 1
    assert client._lambda.meta.config.read_timeout > 300
