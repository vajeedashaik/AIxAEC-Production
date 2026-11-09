# AWS Deployment: Summary for Faculty Review

Status as of 2026-11-09. Region `eu-west-1`. Source: `docs/AWS_MIGRATION_PLAN.md`.

## What was done

The platform (floor plan upload → computer vision → versioned Building Model → edits by text/voice/click) was given an optional AWS deployment profile. The free local stack remains the default; each AWS feature is switched on by an environment variable, and all infrastructure is Terraform code in `infra/`. The stack was deployed to real AWS **twice** (build, deploy, smoke test, destroy). Both times it was fully destroyed, so nothing is running or billing.

## Status of the 10 target services

Labels: **Seen working** = observed running on real AWS. **Blocked** = AWS refused the call on this account (Free Plan: `SubscriptionRequiredException`), so a substitute is used. Nothing is marked VERIFIED, which requires a human check of the full flow.

| # | Service | Status | Evidence / note |
|---|---|---|---|
| 1 | S3 | Seen working | Vision artifacts written and read during the smoke test |
| 2 | SQS (+ DLQ) | Partly seen | Message accepted and queue drained by the worker; the worker's receipt is not proven in logs |
| 3 | Lambda | Seen working | Vision pipeline ran 8/8 stages (Debian container image, Tesseract OCR) |
| 4 | ECR | Seen working | All images built and pushed |
| 5 | ECS Fargate | Seen working | API `readyz` ok, worker started |
| 6 | Textract | **Blocked** | Free Plan. Substitute: Tesseract OCR |
| 7 | Transcribe | **Blocked** | Free Plan. Substitute: Whisper (`stt_provider`, default `whisper`); not yet run on Fargate |
| 8 | Bedrock | **Blocked** | Free Plan. Substitute: offline rules parser for commands. Bedrock code is tested offline only |
| 9 | SNS | Seen working | Manual test email arrived; the app's own "job finished" email not yet triggered |
| 10 | CloudWatch | Seen working | Dashboard and 3 alarms exist |

Also blocked by the Free Plan: Comprehend and Translate. Polly and Rekognition were not tested (not in the IAM policy).

**Net result: 6 of the 10 target services were seen working on AWS, SQS partly (7th), and 3 are blocked by the account plan and replaced by free equivalents.**

## Not yet exercised

- Full web upload → SQS → worker → Lambda → app "job finished" SNS email
- Whisper's first-use model download on Fargate

## Known limits (by design, for a short-lived demo)

- Plain HTTP API restricted to one IP; no load balancer
- Secrets sit in the ECS task definition (Secrets Manager is the upgrade path)
- One Fargate task, local Terraform state

## Options for the blocked services

Upgrading the AWS plan would unlock Textract, Transcribe and Bedrock. The code paths for all three already exist behind env switches, so enabling them means changing variables, not code.
