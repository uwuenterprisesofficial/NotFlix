# Build the backend's Docker image and push it to the registry (Windows PowerShell).
#
#   docker login registry.mfhost.de      (once)
#   .\scripts\publish-backend.ps1
#
# Pushes registry.mfhost.de/notflix-backend:publish. Override with -Image, -Tag and -Platform
# (default linux/amd64). The image runs the database migrations when it starts.
param(
    [string]$Image = "registry.mfhost.de/notflix-backend",
    [string]$Tag = "publish",
    [string]$Platform = "linux/amd64"
)
$ErrorActionPreference = "Stop"
$backend = Resolve-Path (Join-Path $PSScriptRoot "..\backend")

Write-Host "Building ${Image}:${Tag} ($Platform) from $backend"
docker build --platform $Platform --pull -t "${Image}:${Tag}" $backend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Pushing ${Image}:${Tag}"
docker push "${Image}:${Tag}"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Published ${Image}:${Tag}"
