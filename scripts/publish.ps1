# Build NotFlix's server images and push them to the registry, for deploy/docker-compose.yml
# (Windows PowerShell).
#
#   docker login registry.uwuenterprises.de      (once)
#   .\scripts\publish.ps1                the server's image: backend
#   .\scripts\publish.ps1 backend frontend   others too (the web app, aniscraper)
#
# The backend's image includes the desktop app's latest build (desktop/dist, made with npm run
# dist there first): servers hand it out as the app's auto-update.
#
# Pushes registry.uwuenterprises.de/notflix-<name>:latest. Override with -Registry, -Tag and -Platform
# (default linux/amd64).
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Images = @("backend"),
    [string]$Registry = "registry.uwuenterprises.de",
    [string]$Tag = "latest",
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
    if ($name -eq "backend") {
        # The desktop app's latest build goes into the image: the server hands it out as the
        # app's update (see backend/app/api/updates.py).
        node (Join-Path $root "scripts/copy-release.mjs")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
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
