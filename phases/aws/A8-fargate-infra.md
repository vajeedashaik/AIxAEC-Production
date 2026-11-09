# A8: ECS Fargate and Terraform

**Goal:** one command creates every AWS resource and one command removes them.

**Files:** `infra/terraform/*.tf`, `infra/scripts/{build-push,deploy,smoke,destroy}.ps1`, `infra/README.md`. Nothing outside `infra/`.

**Requirements**
- Terraform with local state. A small Terraform-managed VPC (the account has no default VPC), public subnets, no NAT, no load balancer. Security group opens only `:8000`, and only to `api_ingress_cidr`, because the API is plain HTTP.
- **ECR:** repos for api, geometry, language, vision-lambda.
- **ECS:** one Fargate task with four containers (api, worker, geometry, language) talking over `127.0.0.1`, a public IP, and `stopTimeout` at the 120 s maximum.
- **S3:** private, all public access blocked, 1-day expiry on `tmp/`, CORS for the web origin if the browser needs it.
- **SQS:** visibility 360 s, DLQ after 3 receives.
- **SNS:** topic plus an email subscription (needs one manual confirm click).
- **Lambda:** image from ECR, timeout 300 s, `OCR_PROVIDER=textract`.
- **IAM:** separate task and Lambda roles scoped to named resources. Task role: S3 bucket, SQS, SNS publish, Lambda invoke, Transcribe, Bedrock invoke. Lambda role: S3 bucket, Textract, logs. `textract:*` and `transcribe:*` calls that AWS doesn't scope by resource use `*` on the specific actions only.
- Env vars set the AWS switches. Supabase and Clerk secrets arrive as Terraform `sensitive` variables, from a gitignored `terraform.tfvars` (D10).
- Tag everything `project = aec-demo`.

**Checks:** `terraform fmt -check` and `terraform validate` (Terraform must be installed). `terraform plan` needs AWS credentials.
