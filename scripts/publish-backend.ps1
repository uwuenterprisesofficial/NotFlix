# Only the backend's image; see publish.ps1.
& (Join-Path $PSScriptRoot "publish.ps1") backend @args
exit $LASTEXITCODE
