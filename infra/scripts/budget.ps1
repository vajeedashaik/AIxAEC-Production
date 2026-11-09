# Creates a $10 monthly cost budget that emails you at $5 and $10 of actual spend. Re-running it is harmless.
param([Parameter(Mandatory)][string]$Email)
. "$PSScriptRoot\common.ps1"

$account = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) { throw "aws sts failed" }

$budget = @{
    BudgetName = "aec-demo-monthly"; TimeUnit = "MONTHLY"; BudgetType = "COST"
    BudgetLimit = @{ Amount = "10"; Unit = "USD" }
} | ConvertTo-Json -Depth 5

$alerts = @(5, 10) | ForEach-Object {
    @{
        Notification = @{ NotificationType = "ACTUAL"; ComparisonOperator = "GREATER_THAN"; Threshold = $_ * 10; ThresholdType = "PERCENTAGE" }
        Subscribers  = @(@{ SubscriptionType = "EMAIL"; Address = $Email })
    }
}
$alerts = ConvertTo-Json -InputObject @($alerts) -Depth 6

$work = Join-Path $env:TEMP "aec-budget-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $work | Out-Null
try {
    [IO.File]::WriteAllText("$work\budget.json", $budget)  # no BOM, which the CLI would reject
    [IO.File]::WriteAllText("$work\alerts.json", $alerts)
    Invoke-Checked aws budgets create-budget --account-id $account --budget "file://$work\budget.json" --notifications-with-subscribers "file://$work\alerts.json"
    Write-Host "Budget created: emails go to $Email at `$5 and `$10."
} finally {
    Remove-Item -Recurse -Force $work
}
