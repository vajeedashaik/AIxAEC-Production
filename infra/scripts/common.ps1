# Shared by the other scripts. Windows PowerShell 5.1 doesn't stop on a failed native command, so Invoke-Checked does.
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$TerraformDir = "$RepoRoot\infra\terraform"

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$Command, [Parameter(ValueFromRemainingArguments)][string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

function Invoke-Terraform {
    Invoke-Checked terraform "-chdir=$TerraformDir" @args
}

function Get-Output([string]$Name) {
    $value = & terraform "-chdir=$TerraformDir" output -raw $Name
    if ($LASTEXITCODE -ne 0) { throw "terraform output $Name failed. Has deploy.ps1 run?" }
    return $value
}

function Get-ApiUrl {
    $region, $cluster = (Get-Output region), (Get-Output cluster)
    $task = aws ecs list-tasks --region $region --cluster $cluster --desired-status RUNNING --query "taskArns[0]" --output text
    if (-not $task -or $task -eq "None") { throw "No running task yet." }
    $eni = aws ecs describe-tasks --region $region --cluster $cluster --tasks $task --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" --output text
    $ip = aws ec2 describe-network-interfaces --region $region --network-interface-ids $eni --query "NetworkInterfaces[0].Association.PublicIp" --output text
    return "http://${ip}:8000"
}
