# P8: AWS profile prompts

One prompt per AWS service. Full design and rationale: [docs/AWS_MIGRATION_PLAN.md](../../docs/AWS_MIGRATION_PLAN.md).

| Prompt | Service | Needs real AWS? | Status |
|---|---|---|---|
| [A1](A1-s3.md) | S3 (artifacts) | No | see `phases/STATUS.md` |
| [A2](A2-sqs.md) | SQS + dead-letter queue | No | |
| [A3](A3-textract.md) | Textract | No | |
| [A4](A4-lambda-ecr.md) | Lambda + ECR (vision) | No | |
| [A5](A5-transcribe.md) | Transcribe | No | |
| [A6](A6-bedrock.md) | Bedrock | No | |
| [A7](A7-sns.md) | SNS | No | |
| [A8](A8-fargate-infra.md) | ECS Fargate + Terraform | Only to apply | |
| [A9](A9-cloudwatch.md) | CloudWatch | Only to apply | |
| [A10](A10-deploy-demo.md) | Deploy, test, destroy, demo | **Yes, this spends money** | |

## Rules for every prompt

1. Read the plan, then the code the prompt names. Look up library APIs with context7 or the installed `botocore` service models. Don't rely on memory.
2. Additive only. Every feature sits behind an env switch whose default keeps today's free-stack behaviour. With defaults, all existing tests must pass unchanged.
3. Use the existing seams (`BlobStore`, `OCRService`, `SpeechService`, `LlmClient`, the `Container`). Don't change callers beyond the listed wiring.
4. Build boto3 clients at startup, not lazily from request threads, because creating clients from the default session isn't thread-safe. Credentials come from IAM roles or an AWS profile, never from code or `.env` values.
5. Convert every botocore error at the boundary: into `ServiceError`, `LlmUnavailable` or a logged no-op, as the prompt says. Error text shown to users stays generic.
6. Tests use `moto` (S3, SQS, SNS) or botocore `Stubber`/hand-written fakes. No test or CI job touches real AWS.
7. Before handing off, run the service's `uv run pytest`, `uv run ruff check .` and `uv run mypy app`, and update `phases/STATUS.md` with honest labels. Only a human run on real AWS earns `VERIFIED`.
8. Never `git add -A`. The owner stages, commits and pushes personally.
