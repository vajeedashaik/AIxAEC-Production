# Writes infra\terraform\terraform.tfvars (gitignored) from services\api\.env, your current public IP and a fresh token.
# Only the Bedrock model is left for you to set. Nothing is printed except the file's path.
param([Parameter(Mandatory)][string]$Email, [switch]$Force)
. "$PSScriptRoot\common.ps1"

$target = "$TerraformDir\terraform.tfvars"
if ((Test-Path $target) -and -not $Force) { throw "$target exists. Pass -Force to overwrite it." }

$env = @{}
foreach ($line in Get-Content "$RepoRoot\services\api\.env") {
    if ($line -match '^\s*([A-Z0-9_]+)=(.*)$') { $env[$Matches[1]] = $Matches[2].Trim().Trim('"') }
}
foreach ($key in 'DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'CLERK_ISSUER', 'CLERK_SECRET_KEY') {
    if (-not $env[$key]) { throw "services\api\.env has no $key" }
}
if ($env['DATABASE_URL'] -notmatch ':5432/') { throw "Expected DATABASE_URL to be the Supabase session pooler on port 5432." }

function Hcl([string]$value) {  # a safe HCL string literal
    '"' + ($value.Replace('\', '\\').Replace('"', '\"').Replace('${', '$${').Replace('%{', '%%{')) + '"'
}

$ip = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
$bytes = New-Object byte[] 36
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes)  # 48 characters, over the 32 the services require

$lines = @(
    "alert_email               = $(Hcl $Email)"
    "api_ingress_cidr          = $(Hcl "$ip/32")"
    "bedrock_model_id          = `"`" # optional: empty = rules parser only, see infra\README.md"
    "database_url              = $(Hcl ($env['DATABASE_URL'] -replace ':5432/', ':6543/'))"
    "worker_database_url       = $(Hcl $env['DATABASE_URL'])"
    "supabase_url              = $(Hcl $env['SUPABASE_URL'])"
    "supabase_service_role_key = $(Hcl $env['SUPABASE_SERVICE_ROLE_KEY'])"
    "clerk_issuer              = $(Hcl $env['CLERK_ISSUER'])"
    "clerk_secret_key          = $(Hcl $env['CLERK_SECRET_KEY'])"
    "internal_service_token    = $(Hcl $token)"
)
[IO.File]::WriteAllText($target, ($lines -join "`n") + "`n")
Write-Host "Wrote $target (restricted to $ip/32). bedrock_model_id is empty: commands use the rules parser."
