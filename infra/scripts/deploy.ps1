# Creates everything else (Terraform asks for confirmation), waits for the task and prints what the web app needs.
. "$PSScriptRoot\common.ps1"

Invoke-Terraform apply

$region, $cluster, $service = (Get-Output region), (Get-Output cluster), (Get-Output service)
Write-Host "Waiting for the ECS service to become stable..."
Invoke-Checked aws ecs wait services-stable --region $region --cluster $cluster --services $service

$api = Get-ApiUrl
Write-Host ""
Write-Host "API:       $api"
Write-Host "Dashboard: $(Get-Output dashboard_url)"
Write-Host ""
Write-Host "Put these in apps\web\.env.local, then restart npm run dev:"
Write-Host "NEXT_PUBLIC_API_URL=$api"
Write-Host "NEXT_PUBLIC_ARTIFACT_ORIGIN=$(Get-Output artifact_origin)"
Write-Host ""
Write-Host "Confirm the SNS subscription email, then run infra\scripts\smoke.ps1"
Write-Host "REMEMBER: this is billing by the hour until infra\scripts\destroy.ps1 runs."
