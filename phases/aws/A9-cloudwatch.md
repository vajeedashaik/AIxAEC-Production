# A9: CloudWatch

**Goal:** logs, a dashboard and alarms for following one upload through the system. Terraform only, no app code, because services already write JSON logs to stdout.

**Files:** `infra/terraform/cloudwatch.tf`.

**Requirements**
- Log groups with 7-day retention for each container (`awslogs` driver) and the Lambda function, created by Terraform so `destroy` removes them.
- One dashboard: ECS CPU and memory, SQS visible messages and age, DLQ depth, Lambda invocations, duration and errors.
- Alarms that notify the SNS topic: DLQ has messages, Lambda errors, ECS running task count below 1.
- Include a saved Logs Insights query that follows one job id across api, worker and Lambda.

**Checks:** `terraform validate`. On AWS (A10), confirm the dashboard shows data after one upload.
