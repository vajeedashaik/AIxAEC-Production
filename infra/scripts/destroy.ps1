# Removes everything (Terraform asks for confirmation), then lists anything still tagged for this project.
. "$PSScriptRoot\common.ps1"

$region = Get-Output region
Invoke-Terraform destroy

Write-Host ""
Write-Host "Still tagged project=aec-demo (just-deleted items can linger here for a few minutes):"
aws resourcegroupstaggingapi get-resources --region $region --tag-filters Key=project,Values=aec-demo --query "ResourceTagMappingList[].ResourceARN" --output table
Write-Host "Log groups left:"
aws logs describe-log-groups --region $region --log-group-name-prefix /aec-demo --query "logGroups[].logGroupName" --output table
Write-Host "Check the Billing console tomorrow to confirm charges have stopped."
