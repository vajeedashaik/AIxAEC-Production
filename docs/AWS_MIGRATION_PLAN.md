# AWS Migration Plan

Status (2026-11-09): **M1–M6 (prompts A1–A7) tested offline. M7 (A8–A9) written; `terraform validate` and a read-only `plan` pass (41 resources). Nothing has been applied or run on real AWS.** M8–M9 (A10) NOT_STARTED. Written from commit `a1de848`. Per-service prompts: `phases/aws/`.

**Update (2026-11-09, run on real AWS by Claude with the owner's permission):** `build-push` and `deploy` ran; `smoke.ps1` passed (API health, Lambda vision pipeline 8/8 stages, S3 artifacts). **Textract is blocked by the Free Plan** (`SubscriptionRequiredException`), so the Lambda runs Tesseract (Debian image, `OCR_PROVIDER=tesseract`) and the stack has **8 services**. Seen working on AWS: ECR, S3, Lambda, Fargate (API healthy). Deployed but not exercised: SQS/worker path, SNS email, CloudWatch alarms, Transcribe. Fargate is still running until `destroy.ps1`.

**Second AWS run (2026-11-09):** by direct CLI call on this account, **Textract, Transcribe, Comprehend and Translate all return `SubscriptionRequiredException`** (Free Plan); Polly and Rekognition are not in the IAM policy. Seen working: SQS (message accepted, queue drained by the running worker, receipt not proven in logs), CloudWatch (dashboard and 3 alarms exist; `no-running-task` showed ALARM only because a new service has no CPU datapoints yet), Fargate (API `readyz` ok, worker started). SNS: subscription confirmed and a manual `aws sns publish` test mail ("hello") arrived (owner-confirmed). The app's own "job finished" notification has not been triggered. Voice now defaults to Whisper (`stt_provider = "whisper"` variable; Whisper in the Fargate container is untested).

Where things stand: region is `eu-west-1` (Ireland, matching Supabase). The account (`615371646456`, IAM user `aec-dev`) is on the AWS Free Plan, which blocks Bedrock (`Operation not allowed`), so **the AWS stack runs 9 services with the rules parser**; the Bedrock code is tested but off (`bedrock_model_id = ""`). Done: inline IAM policy `aec-demo-deploy` applied, $5/$10 budget alert created, `infra/terraform/terraform.tfvars` generated (gitignored, holds secrets). **Next:** run `infra\scripts\build-push.ps1` (the owner types `yes`), then `deploy.ps1`, `smoke.ps1`, `destroy.ps1`. Textract, Transcribe, Lambda and Fargate are untested on this account and may hit the same Free Plan wall. All work is uncommitted on branch `aws-profile`.

## 1. Goal and scope

Add an **AWS deployment profile** to the platform, using these 10 services, each doing a real job:

| # | Service | Job in this project |
|---|---|---|
| 1 | **S3** | Vision artifacts, plus temporary hand-off files for Lambda and Transcribe |
| 2 | **SQS** (+ dead-letter queue) | Tells workers a processing job is waiting |
| 3 | **Lambda** | Runs the vision pipeline (container image) |
| 4 | **ECR** | Stores the container images |
| 5 | **ECS Fargate** | Runs api, worker, geometry and language |
| 6 | **Textract** | OCR for floor-plan labels |
| 7 | **Transcribe** | Speech-to-text for voice commands |
| 8 | **Bedrock** | LLM that parses text commands |
| 9 | **SNS** | "Job finished or failed" email |
| 10 | **CloudWatch** | Logs, dashboard, alarms |

**Stays as it is:** Clerk (auth), Supabase (Postgres, plus Storage for source uploads), Docker Compose local mode, all contracts.
**Out of scope:** hosting the web app on AWS (it runs locally against the AWS-hosted API), Cognito, RDS, NAT.

## 2. Principles (the "no mess" rules)

1. **Additive, not a rewrite.** The free local stack stays the default and keeps working. AWS is switched on by env vars. Rolling back means unsetting them.
2. **Use the seams that already exist.** `BlobStore`, `OCRService`, `SpeechService` and `LlmClient` already isolate each provider. We add implementations and change no callers.
3. **Contracts stay frozen, with one additive exception.** Anything AWS-specific (Lambda payloads, S3 keys) stays inside the owning service. The only change is adding `"transcribe"` to `TranscribeResult.provider`, because reporting `whisper` for a Transcribe result would be false.
4. **Postgres stays the source of truth for job state.** SQS is only a wake-up signal. The existing claim, heartbeat, fencing-token and stale-recovery logic in `jobs.py` is untouched.
5. **No credentials in code or env.** ECS and Lambda use IAM roles. Developers use an AWS SSO or CLI profile.
6. **Build and test offline first.** Milestones M1–M6 need no AWS account and no spend (tested with stubs). Only M7–M8 touch real AWS.
7. **Everything in `infra/`, one command to create and one to destroy.** No console clicking, no leftover resources.
8. **Honest status labels.** Only a human run on real AWS earns `VERIFIED`.

## 3. Target architecture

```
Browser (local web :3000, Clerk)
   │  HTTPS-less demo: http://<task-public-ip>:8000   (see D2)
   ▼
┌──────────────── ECS Fargate: ONE task, 4 containers sharing localhost ────────────────┐
│ api :8000 ── worker ── geometry :8002 ── language :8003                               │
└──┬───────────┬──────────────────────────────────────────┬────────────────────┬────────┘
   │           │ long-poll                                │ Bedrock (Converse)  │ Transcribe
   │ publish   ▼                                          ▼                    ▼ (via S3 tmp/)
   │        SQS queue ──(3 failures)──► DLQ         Amazon Bedrock       Amazon Transcribe
   │           │
   │           │ worker: claim job in Postgres → copy source to S3 tmp/ → invoke
   │           ▼
   │      Lambda (vision image from ECR) ── Textract (OCR)
   │           │ writes result JSON + artifacts to S3, returns the keys
   ▼           ▼
 SNS topic   S3 bucket (artifacts, tmp/ with 1-day expiry)
 (email)
        Supabase (hosted): Postgres (jobs, versions) + Storage (floorplans) ◄── api + worker via the pooler
        Clerk: JWT verified by the api via JWKS (unchanged)
        CloudWatch: container + Lambda logs, dashboard, alarms
```

## 4. Key design decisions

| ID | Decision | Why | Status |
|---|---|---|---|
| D1 | **Lambda gets an S3 key, not the file.** The worker copies the source to `s3://…/tmp/`, invokes Lambda, and Lambda writes the result to S3 and returns only the key. | Sync Lambda payloads are capped at about 6 MB, and uploads can reach 25 MB. Passing keys avoids the limit and avoids any contract change. | Proposed |
| D2 | **No load balancer.** The task gets a public IP, and the web app runs locally against `http://<ip>:8000`. | An ALB is an 11th service plus a domain and certificate for HTTPS. A localhost page may call an HTTP API. The IP changes each deploy, so the web API URL env var is set per run. | **Needs your OK**, see §10 |
| D3 | **One Fargate task, four containers** (api, worker, geometry, language) on `localhost`. | No service discovery or internal networking needed. Existing `*_URL` env vars just point at `127.0.0.1`. | Proposed |
| D4 | **Small Terraform-managed VPC, public subnets, no NAT.** Security group allows only :8000 from one IP (`api_ingress_cidr`). | The account has no default VPC, and a VPC is free. The NAT Gateway is the biggest avoidable cost. The API is plain HTTP, so only the owner's IP may reach it. | Decided |
| D5 | **Supabase via its pooler** (IPv4). The worker uses the session-mode URL (`WORKER_DATABASE_URL` already exists) because it relies on `FOR UPDATE SKIP LOCKED`. | Fargate in public subnets may lack IPv6. Hosted Supabase direct connections are IPv6-first. | To verify in M8 |
| D6 | **Hybrid storage.** `floorplans` stay in Supabase Storage, `artifacts` move to S3. | Keeps the upload path and signed-URL flow untouched, and S3 still has a real job. | Proposed |
| D7 | **Transcribe is asynchronous** (upload to S3, start job, poll, read transcript, clean up). | Simplest SDK path. Latency is likely several seconds, which is worse than local Whisper. `STT_PROVIDER` can stay `whisper` if the demo feels slow. | Proposed |
| D8 | **Bedrock via boto3 `converse`**, optional (off on a Free Plan account: Bedrock returns `Operation not allowed`, so `bedrock_model_id` is empty and the rules parser answers). | The current client targets an OpenAI-compatible URL. Converse has no `response_format`, so JSON mode is prompt-only. Model access must be enabled per account and region. | To verify in M5 |
| D9 | **Terraform** for infrastructure, local state. | `plan` and `destroy` are clear for a live demo, and local state avoids creating a state bucket first. CDK is the alternative if you prefer Python. | **Needs your OK**, see §10 |
| D10 | **Secrets as Terraform sensitive variables** put into the task definition. | Secrets Manager and SSM are not in the 10 services. Acceptable because the stack is short-lived and destroyed afterwards. Upgrade path is Secrets Manager. | Known limitation |
| D11 | **Region `eu-west-1` (Ireland)**, the same region as the hosted Supabase project, to keep database round trips short. Textract, Transcribe, Lambda, ECS, ECR, SQS, SNS and S3 are all offered there. | Decided |

## 5. Configuration switches

All default to today's behaviour.

| Service | Env var | Values (new ones in bold) |
|---|---|---|
| api | `BLOB_BACKEND` | `supabase` (default), **`hybrid`** (floorplans in Supabase, artifacts in S3) |
| api | `QUEUE_BACKEND` | `postgres` (default), **`sqs`** |
| api | `VISION_MODE` | `http` (default), **`lambda`** |
| api | `NOTIFIER` | `none` (default), **`sns`** |
| api | `AWS_REGION`, `S3_BUCKET`, `SQS_QUEUE_URL`, `SNS_TOPIC_ARN`, `VISION_LAMBDA_NAME` | only read when the matching switch is on |
| vision | `OCR_PROVIDER` | `auto`, `stub`, `tesseract`, **`textract`** |
| language | `STT_PROVIDER` | `whisper`, `stub`, **`transcribe`** |
| language | `LLM_PROVIDER` | `openai` (default, OmniRoute), **`bedrock`** |

## 6. Code changes by milestone

New dependency: `boto3` in `services/api`, `services/vision` and `services/language`. Everything else is new files plus small edits to the files listed.

### M1: S3 for artifacts (`BLOB_BACKEND=hybrid`)
- **New** `services/api/app/aws/s3.py`: `S3BlobStore` implementing the existing `BlobStore` protocol (`put`, `get`, `signed_urls` → presigned URLs, `delete_prefix`).
- **New** `RoutedBlobStore` (same package): sends the `artifacts` bucket to S3 and `floorplans` to `SupabaseBlobStore`.
- **Edit** `config.py` (new settings and a validator that requires the S3 settings when the switch is on), `container.py` (choose the store).
- `jobs.py` is unchanged, because it already calls `c.blobs.put(ARTIFACT_BUCKET, …)`.

### M2: SQS as the wake-up signal (`QUEUE_BACKEND=sqs`)
- **New** `aws/sqs.py`: `publish(job_id)` and `wait_for_message(timeout)`.
- **Edit** where jobs are enqueued (after the commit): publish a message. A publish failure is logged and ignored, because the polling backstop still picks the job up.
- **Edit** `worker.py`: long-poll SQS (20 s), then run the existing `run_once()`, then delete the message. Keep a slow Postgres poll as a backstop so stale-job recovery still works.
- Queue settings: visibility timeout 360 s (longer than the 300 s Lambda timeout), DLQ after 3 receives.

### M3: Textract OCR (`OCR_PROVIDER=textract`)
- **New** `services/vision/app/ocr/textract.py`: `TextractOCR` implementing `OCRService.recognize(gray) -> list[OcrWord]`. Encode the image as PNG, call `DetectDocumentText`, convert relative boxes to pixels, convert confidence 0–100 to 0–1.
- **Edit** `ocr/factory.py` and `config.py` (add the literal).
- To verify: the 5 MB inline image limit at `image_max_dimension` 2400, and that `recognize` is called once per plan (it is: `pipeline/stages.py:99`).

### M4: Vision on Lambda (`VISION_MODE=lambda`)
- **New** `services/vision/app/lambda_handler.py`: reads the source from S3, calls the existing pipeline directly (no HTTP), writes `AnalyzeResult` JSON to S3, returns `{result_key}`.
- **New** `services/vision/Dockerfile.lambda`: the Lambda base image, same dependencies.
- **New** `services/api/app/aws/lambda_vision.py`: `LambdaVisionClient` with the same `analyze(floorplan_id, source, filename, content_type)` signature as `VisionClient`, so `jobs.py` stays unchanged. It copies the source to `tmp/`, invokes, reads the result, deletes the temp objects.
- **Edit** `container.py` (choose the client).
- To verify: memory limit (new accounts may cap at 3008 MB), a cold start with OpenCV, and the 15-minute ceiling against a large PDF.

### M5: Transcribe and Bedrock
- **New** `services/language/app/speech_transcribe.py`: `TranscribeSpeech` implementing `SpeechService`. Keep the existing audio decoding and duration checks before uploading.
- **New** `services/language/app/llm_bedrock.py`: a Bedrock client with the same `complete(messages, *, deadline, json_mode) -> (content, model)` and `probe()` surface as `LlmClient`. The circuit breaker and retry code should be shared, not copied. This means a small refactor in `llm.py`, and botocore errors must map to `LlmUnavailable`.
- **Edit** `config.py`, `speech.py` (`build_speech`) and `parsers.py` (`build_llm_client`).

### M6: SNS notifications (`NOTIFIER=sns`)
- **New** `aws/sns.py` plus a no-op notifier. Add a `Notifier` to the `Container`.
- **Edit** `jobs.py` in two places only: after `_complete` and after `fail_job`, call `c.notifier.job_finished(...)`. Failures are swallowed and logged. The message contains status, plan name and job id, never file contents.

### M7: Infrastructure (`infra/terraform/`)
New folder, no existing files touched.

```
infra/
  README.md              how to deploy, test, destroy
  terraform/
    versions.tf  variables.tf  outputs.tf
    s3.tf        sqs.tf        sns.tf       lambda.tf
    ecr.tf       ecs.tf        iam.tf       cloudwatch.tf
  scripts/
    build-push.ps1       build the 4 images + Lambda image, push to ECR
    deploy.ps1           terraform apply, print the API URL
    smoke.ps1            upload a fixture plan, wait for COMPLETED
    destroy.ps1          terraform destroy, then list leftovers
```

| Resource | Notes |
|---|---|
| S3 bucket | Private, public access blocked, `tmp/` lifecycle expiry of 1 day |
| SQS queue + DLQ | Visibility timeout 360 s, `maxReceiveCount` 3 |
| SNS topic | Email subscription (needs a manual confirm click) |
| ECR repos | api, geometry, language, vision-lambda |
| Lambda | Container image, timeout 300 s, memory per M4 findings, env `OCR_PROVIDER=textract` |
| ECS | Cluster, one task definition (4 containers), one service, `awslogs` log driver |
| IAM | Task role: S3 (the bucket only), SQS, SNS publish, Bedrock invoke, Transcribe, Lambda invoke. Lambda role: S3, Textract. No wildcard resources where a name or ARN is known. |
| CloudWatch | Log groups with 7-day retention, a dashboard (ECS CPU and memory, SQS depth, Lambda duration and errors), alarms: DLQ not empty, Lambda errors, ECS task count 0 |

### M8: Deploy, test, tear down
1. Build and push images, `terraform apply`, confirm the SNS email.
2. Run the smoke script, then the existing Playwright e2e against the AWS API URL (the e2e suite already takes `E2E_API_URL`).
3. Check the CloudWatch dashboard, the DLQ and the Billing console.
4. `terraform destroy`, then check for leftovers (log groups, ECR images, S3 objects).

### M9: Docs and demo
Update `docs/ARCHITECTURE.md` and this file's status labels, add an architecture diagram, and write a short runbook with the demo script (follow one upload through S3 → SQS → Lambda → Textract → SNS → CloudWatch).

## 7. Order of work

```
M0 decisions + guardrails ─► M1 S3 ─► M2 SQS ─► M3 Textract ─► M4 Lambda ─► M5 Transcribe+Bedrock ─► M6 SNS
        (no AWS spend, all tested offline)                                                               │
                                                                                                         ▼
                                                                      M7 Terraform ─► M8 deploy/test/destroy ─► M9 docs
                                                                              (first real AWS spend)
```

M0 is the only milestone that starts with a manual step. Each of M1–M6 is its own commit, and the app still works on the free stack after each one.

### M0: before any code
- You approve the open decisions in §10.
- Amend the "no AWS" rule in `CLAUDE.md` and `phases/shared/ARCHITECTURE.md` so it reads "no AWS in the default profile; AWS allowed in the `aws` profile under `infra/`". Add a **P8** row to `phases/shared/OWNERSHIP.md` covering `infra/**`, the new `aws*` files above and the listed small edits.
- Work on a branch, `aws-profile`. Stage only owned paths, never `git add -A`, and don't push unless you ask.
- Create the AWS account guardrails: a budget with alerts at $5 and $10, an IAM Identity Center user or a scoped IAM user (no root keys), and confirm which regions offer Textract, Transcribe and a Bedrock model you can enable.

## 8. Testing strategy

| Level | How | Needs AWS? |
|---|---|---|
| Unit (S3, SQS, SNS) | `moto` mocks (verify it covers the calls we use) | No |
| Unit (Textract, Transcribe, Bedrock, Lambda) | botocore `Stubber` with recorded response shapes | No |
| Existing suites | Must stay green with all switches at defaults: pytest, ruff and mypy strict per service, plus Vitest | No |
| Contract conformance | Unchanged, because contracts don't change | No |
| Lambda image | Run locally with the Lambda Runtime Interface Emulator against a fixture plan | No |
| Smoke and e2e | `smoke.ps1`, then Playwright against the deployed API | Yes (M8) |

No automated CI job touches real AWS. Real-AWS checks are manual and labelled `VERIFIED` only after you have seen them work.

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Stack left running | Fargate and Lambda charges continue | `destroy.ps1`, budget alerts, tag everything `project=aec-demo`, check Billing the next day |
| Bedrock model not available in the region or not enabled | Command parsing falls back to the rules parser | The hybrid parser already degrades to rules. Check in M0. |
| Textract accuracy or cost on plans | Worse labels, a few cents per plan | Keep `tesseract` selectable, compare on the fixture plans in M3 |
| Lambda memory or cold-start limits | Slow or failed analysis | Measure in M4, set timeout and memory from the results |
| Supabase pooler or IPv4 issues from Fargate | Worker cannot reach the database | Test early in M8 with a one-container deploy. The session-mode URL setting already exists. |
| Supabase free project paused | Everything fails | Unpause the day before and again before the review |
| Clerk development keys and the API's public IP | Sign-in may behave differently away from localhost | Keep the web app on `localhost:3000`, set `CLERK_AUTHORIZED_PARTIES` and `CORS_ORIGINS` explicitly, and test in M8 |
| Transcribe latency | Voice commands feel slow | `STT_PROVIDER=whisper` remains available |
| Secrets in the task definition | Visible to anyone with ECS read access in that account | Single-owner demo account, short-lived, destroyed after |
| API port open to the internet | Anyone can reach it | Clerk JWT required on `/v1`, per-user rate limiting exists, only `:8000` is open |

## 10. Decisions

Settled by the owner on 2026-11-09:

1. The "no AWS" rule is replaced by the AWS profile rule (`CLAUDE.md`).
2. No load balancer (D2).
3. Terraform (D9).
4. Build order M1 → M2 → M3 first.

Still open: the region and Bedrock model (D11), to confirm on the real AWS account before A8.

## 11. Definition of done

- With all switches at defaults, all existing tests pass unchanged.
- With the `aws` profile on, one uploaded plan goes through SQS, Lambda and Textract, ends `COMPLETED` in the UI, stores artifacts in S3, sends an SNS email, and shows up in the CloudWatch dashboard.
- Voice and text commands work through Transcribe and Bedrock, or fall back cleanly.
- `terraform destroy` leaves no billable resources.
- Status labels in `phases/STATUS.md` are updated honestly.
