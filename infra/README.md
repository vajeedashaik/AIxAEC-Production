# AWS deployment

Deploys the AWS profile described in [docs/AWS_MIGRATION_PLAN.md](../docs/AWS_MIGRATION_PLAN.md). **Everything here costs money while it exists.** Fargate bills by the hour, so destroy the stack as soon as you finish.

## Before the first deploy

1. Give the deploying IAM user the permissions it lacks. It's an inline policy because a user can have only 10 managed ones:
   `aws iam put-user-policy --user-name aec-dev --policy-name aec-demo-deploy --policy-document file://infra/deployer-policy.json`
2. Set the budget alert: `.\infra\scripts\budget.ps1 -Email you@example.com`. If AWS says access is denied, the account root user must first turn on
   "IAM user and role access to Billing information" (Account settings), or create the budget in the console.
3. Bedrock is optional. AWS Free Plan accounts get `Operation not allowed` from it, so `bedrock_model_id` stays empty and commands use the
   offline rules parser. Upgrading the account plan would allow it: then set `bedrock_model_id` (for example `eu.amazon.nova-2-lite-v1:0`).
4. Unpause the hosted Supabase project. Start Docker.
5. `.\infra\scripts\init-tfvars.ps1 -Email you@example.com` writes `terraform/terraform.tfvars` (gitignored) from `services/api/.env`
   and your current public IP. Your IP changes, so re-run with `-Force` if it does.

## Deploy, test, destroy

Run from the repo root. Each script shows a Terraform plan and waits for your `yes`.

```powershell
.\infra\scripts\build-push.ps1   # ECR repositories, then build and push all images
.\infra\scripts\deploy.ps1       # everything else; prints the API URL and web settings
.\infra\scripts\smoke.ps1        # API health, then a real plan through Lambda and Textract
.\infra\scripts\destroy.ps1      # removes everything and lists leftovers
```

After `deploy.ps1`:

1. Click the confirmation link in the SNS email.
2. Put the two printed `NEXT_PUBLIC_*` lines in `apps/web/.env.local` and run `npm run dev` in `apps/web`.
3. Open `http://localhost:3000`. Keep using localhost: the API allows only that origin.

The API's public IP changes on every deploy, so repeat step 2 each time.

## Known limits

- **Plain HTTP.** With no load balancer, Clerk tokens travel unencrypted to the API. That's why ingress is limited to one IP. Add an ALB with a certificate before anything longer-lived.
- **Secrets are in the ECS task definition**, visible to anyone with read access to ECS in the account. Move them to Secrets Manager beyond a short-lived demo.
- **One Fargate task, four containers.** No scaling or redundancy.
- **Local Terraform state.** It's gitignored and holds the secrets above, so don't share it. If you lose it, delete resources by hand using the `project=aec-demo` tag.
