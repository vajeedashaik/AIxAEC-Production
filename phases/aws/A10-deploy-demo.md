# A10: Deploy, test, destroy, demo

**This prompt spends real money. Run it only when the owner asks, and confirm before each `apply` and `destroy`.**

**Before starting (owner)**
- AWS account with a budget alert at $5 and $10, and a non-root SSO or IAM profile.
- Region chosen, with Textract, Transcribe and a Bedrock model confirmed available and enabled.
- Hosted Supabase unpaused. Terraform, AWS CLI and Docker installed and running.

**Steps**
1. `build-push.ps1`, then `deploy.ps1`. Confirm the SNS subscription email.
2. `smoke.ps1`: upload a fixture plan and wait for `COMPLETED`.
3. Point the local web app at the printed API URL. Run Playwright with `E2E_API_URL` set. Test sign-in early, since Clerk dev keys and CORS are the likeliest surprises.
4. Check the S3 artifacts, the SNS email, the CloudWatch dashboard, an empty DLQ and the Billing console.
5. `destroy.ps1`, then confirm no billable resources remain.

**Finish**
- Update `docs/ARCHITECTURE.md`, add a diagram, write a short demo runbook (follow one upload: SQS → Lambda → Textract → S3 → SNS → CloudWatch).
- Describe the system honestly: AWS for compute, queueing, AI and monitoring, with Clerk for auth and Supabase for data.
- Mark items `VERIFIED` in `phases/STATUS.md` only after the owner has seen them work on AWS.
