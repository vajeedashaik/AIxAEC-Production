# Checks the API is up, then runs a real fixture through Lambda and Textract. No sign-in needed.
. "$PSScriptRoot\common.ps1"

$api = Get-ApiUrl
Write-Host "healthz: $((Invoke-RestMethod "$api/healthz").status)"
Write-Host "readyz:  $((Invoke-RestMethod "$api/readyz").status)"

$region, $bucket, $function = (Get-Output region), (Get-Output bucket), (Get-Output vision_lambda)
$prefix = "tmp/smoke-$([guid]::NewGuid())"
$work = Join-Path $env:TEMP "aec-smoke-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $work | Out-Null
try {
    Invoke-Checked aws s3 cp "$RepoRoot\e2e\fixtures\two_room.png" "s3://$bucket/$prefix/source" --region $region --only-show-errors

    $event = @{
        bucket = $bucket; source_key = "$prefix/source"; result_key = "$prefix/result.json"
        content_type = "image/png"; floorplan_id = [guid]::NewGuid().ToString(); request_id = "smoke"
    } | ConvertTo-Json
    [IO.File]::WriteAllText("$work\event.json", $event)  # no BOM, which the CLI would reject

    Write-Host "Invoking Lambda (a cold start can take a minute)..."
    Invoke-Checked aws lambda invoke --region $region --function-name $function --cli-read-timeout 330 `
        --payload "fileb://$work\event.json" "$work\reply.json" --output text --query FunctionError
    $reply = Get-Content "$work\reply.json" -Raw | ConvertFrom-Json
    if (-not $reply.result_key) { throw "Lambda did not return a result: $(Get-Content "$work\reply.json" -Raw)" }

    Invoke-Checked aws s3 cp "s3://$bucket/$($reply.result_key)" "$work\result.json" --region $region --only-show-errors
    $result = Get-Content "$work\result.json" -Raw | ConvertFrom-Json
    Write-Host "Result: $($result.status)"
    $result.stages | ForEach-Object { Write-Host ("  {0,-18} {1}" -f $_.name, $_.status) }
    $ocr = $result.stages | Where-Object { $_.name -eq "ocr" }
    Write-Host "OCR provider: $($ocr.detail.provider), words: $($ocr.detail.words)"
    if ($result.status -ne "COMPLETED" -or $ocr.detail.provider -notin @("textract", "tesseract", "rekognition")) { throw "Smoke test failed." }
    Write-Host "Smoke test passed."
} finally {
    aws s3 rm "s3://$bucket/$prefix" --recursive --region $region --only-show-errors
    Remove-Item -Recurse -Force $work
}
