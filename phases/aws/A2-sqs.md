# A2: SQS wake-up queue

**Switch:** `QUEUE_BACKEND=sqs` (default `postgres`). Needs `AWS_REGION`, `SQS_QUEUE_URL`.

**Goal:** workers wake on an SQS message instead of only polling. `processing_jobs` stays the source of truth. Claiming, heartbeats, fencing and stale recovery don't change.

**Files**
- New `services/api/app/ports.py`: `WorkQueue` protocol and the default `PollingQueue`.
- New `services/api/app/aws/sqs.py`: `SqsQueue`.
- Edit `app/container.py`, `app/worker.py`, and the two `enqueue` call sites in `app/v1.py`.

**Requirements**
- Publish **after** the database commit, and outside the upload's rollback block. A publish failure is logged and ignored, because the worker's backstop still finds the job.
- Worker loop: `receive()` (long-poll up to 20 s, or return `None` at once for polling mode), `run_once()`, then `ack()` the message only if `run_once` didn't raise. A crashing worker's message therefore returns and eventually reaches the DLQ.
- `run_once` always runs, even with no message, so publish failures and stale jobs are still recovered.
- Queue visibility timeout must exceed the longest job (Lambda timeout 300 s): use 360 s. DLQ after 3 receives (A8).

**Tests:** moto publish → receive → ack; publish failure doesn't raise; worker acks after success and doesn't ack when `run_once` raises; an upload publishes exactly once and only after the commit; `process=false` publishes nothing; polling mode behaves as before.
