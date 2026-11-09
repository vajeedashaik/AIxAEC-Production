# A7: SNS job notifications

**Switch:** `NOTIFIER=sns` (default `none`). Needs `AWS_REGION`, `SNS_TOPIC_ARN`.

**Goal:** an email goes out when a processing job finishes or fails.

**Files**
- Edit `services/api/app/ports.py` (`Notifier` protocol, `NoNotifier`), `app/container.py`, and `app/jobs.py` (only the end of `_complete` and `fail_job`).
- New `services/api/app/aws/sns.py`: `SnsNotifier`.

**Requirements**
- Notify only **after** the commit and only when this worker still owned the job, so a stale worker never sends a second email.
- A notification failure is logged and never affects the job.
- The filename is user input: it may appear in the message body only, never in the `Subject` (ASCII, under 100 characters, no newlines). Never include file contents, keys or URLs.

**Tests:** moto publish succeeds and a failure doesn't raise; a completed job notifies `COMPLETED` once; a failed job notifies `FAILED` once; a lost job notifies nothing.

**Known limit:** one shared topic, so this is an owner alert and not per-user email.
