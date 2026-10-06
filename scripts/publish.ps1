# Build NotFlix's server images and push them to the registry, for deploy/docker-compose.yml
# (Windows PowerShell).
#
#   docker login registry.mfhost.de      (once)
#   .\scripts\publish.ps1                the server's images: backend and frontend
#   .\scripts\publish.ps1 backend        only some of them (aniscraper too, if you want it)
#
# Pushes registry.mfhost.de/notflix-<name>:publish. Override with -Registry, -Tag and -Platform
# (default linux/amd64).
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Images = @("backend", "frontend"),
    [string]$Registry = "registry.uwuenterprises.de",
    [string]$Tag = "publish",
    [string]$Platform = "linux/amd64"
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
# Printed by the backend when it starts: shows which build a server runs.
$commit = git -C $root describe --always --dirty 2>$null
if (-not $commit) { $commit = "unknown" }
$version = "$commit $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mmZ'))"

foreach ($name in $Images) {
    if ($name -notin @("backend", "frontend", "aniscraper")) {
        Write-Error "Unknown image '$name' (backend, frontend or aniscraper)"
    }
    $image = "$Registry/notflix-${name}:$Tag"
    $build = @("build", "--platform", $Platform, "--pull", "--build-arg", "NOTFLIX_VERSION=$version", "-t", $image)
    # The frontend's optimized build, not the development server.
    if ($name -eq "frontend") { $build += @("--target", "prod") }
    Write-Host "==> Building $image ($Platform)"
    docker @build (Join-Path $root $name)
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "==> Pushing $image"
    docker push $image
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Host "Published: $($Images -join ', ') ($Registry, tag $Tag)"
