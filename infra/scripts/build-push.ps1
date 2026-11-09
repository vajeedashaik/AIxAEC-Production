# Creates the ECR repositories, then builds and pushes every image under a new tag. Lambda and ECS need these first.
. "$PSScriptRoot\common.ps1"

Invoke-Terraform init -input=false
Invoke-Terraform apply "-target=aws_ecr_repository.images" "-target=data.aws_caller_identity.current"

$registry = Get-Output registry
# A targeted apply doesn't save the plain `region` output, so read it from the registry host.
$region = $registry.Split(".")[3]
$tag = Get-Date -Format "yyyyMMdd-HHmmss"

aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw "docker login failed" }

$images = @{
    "api"           = "services/api/Dockerfile"
    "geometry"      = "services/geometry/Dockerfile"
    "language"      = "services/language/Dockerfile"
    "vision-lambda" = "services/vision/Dockerfile.lambda"
}

Push-Location $RepoRoot
try {
    foreach ($name in $images.Keys) {
        $uri = "$registry/aec-demo/${name}:$tag"
        Write-Host "== $name"
        # --provenance=false: Lambda rejects the multi-manifest image that attestations create.
        Invoke-Checked docker build --provenance=false --platform linux/amd64 -t $uri -f $images[$name] .
        Invoke-Checked docker push $uri
    }
} finally {
    Pop-Location
}

Set-Content -Path "$TerraformDir\image.auto.tfvars" -Encoding Ascii -Value "image_tag = `"$tag`""
Write-Host "Pushed tag $tag. Next: infra\scripts\deploy.ps1"
