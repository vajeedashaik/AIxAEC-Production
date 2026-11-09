# AWS demo runbook: deploy, test, destroy

Run in PowerShell from the repo root, region `eu-west-1`. The stack **bills by the hour from step 4 until step 9**, so never leave it up overnight. The budget alert only warns, it does not stop spending.

## 0. Before you start

- Start Docker Desktop and wait until it is fully running.
- Unpause the hosted Supabase project.
- Add Terraform to the path for this window:

```powershell
$env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hashicorp.Terraform_Microsoft.Winget.Source_8wekyb3d8bbwe"
```

## 1. Check nothing is left over

```powershell
aws ecs list-clusters --region eu-west-1
```

There should be no `aec-demo` cluster. If there is, run `.\infra\scripts\destroy.ps1` first.

## 2. Update your IP and the OCR setting

Your public IP changes, so regenerate the tfvars, then re-add the OCR line (the regenerate step drops it):

```powershell
.\infra\scripts\init-tfvars.ps1 -Email you@example.com -Force
Add-Content infra/terraform/terraform.tfvars 'ocr_provider = "rekognition"'
```

## 3. Build and push the images

```powershell
.\infra\scripts\build-push.ps1    # type yes at the plan prompt
```

Destroy probably removed the ECR repositories, so the images must be rebuilt. If `terraform init` fails with a registry IPv6 reset, just retry.

## 4. Deploy (billing starts here)

```powershell
.\infra\scripts\deploy.ps1        # type yes
```

Note the API URL and the two `NEXT_PUBLIC_*` lines it prints.

## 5. Confirm the SNS email

Click the confirmation link in the new AWS email. Each deploy creates a fresh subscription, and without confirming it the app's "job finished" mail will not arrive.

## 6. Smoke test

```powershell
.\infra\scripts\smoke.ps1
```

Wait about a minute after the deploy if the API is not ready yet. Expected: `Smoke test passed.` with `OCR provider: rekognition`.

## 7. The manual run

1. Paste the two `NEXT_PUBLIC_*` lines into `apps/web/.env.local`, replacing the old IP.
2. In `apps/web`, run `npm run dev` and open `http://localhost:3000`. Keep using localhost: the API allows only that origin.
3. Sign in, upload a floor plan, and wait for it to complete.
4. Check that an email arrives saying the job finished. Alarm and confirmation mails do not count.
5. Optional: try one voice command to test Whisper on Fargate. The first use downloads the model and may be slow.

## 8. Check the logs (ask Claude, or run)

```powershell
aws logs tail /aec-demo/worker --since 1h --region eu-west-1          # SQS receipt and job claim
aws logs tail /aws/lambda/aec-demo-vision --since 1h --region eu-west-1  # Rekognition OCR stage
aws ssm describe-parameters --region eu-west-1 --query "Parameters[].Name"  # 5 names under /aec-demo/
```

Then update `PROJECT_SOURCE_OF_TRUTH.md` section 17 and `docs/AWS_FACULTY_SUMMARY.md` with what actually happened.

## 9. Destroy (billing stops)

```powershell
.\infra\scripts\destroy.ps1       # type yes
aws ecs list-clusters --region eu-west-1    # confirm nothing is left
```

## What this run proves, and what it does not

| Check | Settled by |
|---|---|
| SQS receipt by the worker | Step 8, worker log |
| App's own "job finished" SNS email | Step 7.4 |
| Rekognition in the deployed app | Step 6 and Lambda log |
| Whisper on Fargate | Step 7.5 only |
| Textract, Transcribe, Bedrock | Not testable on the Free Plan (blocked) |
