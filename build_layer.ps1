# ---------------------------------------------------------------------------
# build_layer.ps1
# Builds the pandas Lambda Layer for linux/x86_64 (Python 3.12).
# Run this script from the repo root before running terraform plan/apply.
#
# Usage:
#   .\build_layer.ps1
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$layerDir  = ".build\layer\python"
$buildDir  = ".build\layer"

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
}

Write-Host "==> Creating layer directory: $layerDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $layerDir | Out-Null

Write-Host "==> Installing pandas 2.2.2 for linux/x86_64 (Python 3.12)..." -ForegroundColor Cyan
py -m pip install pandas==2.2.2 `
    --target $layerDir `
    --platform manylinux2014_x86_64 `
    --python-version 3.12 `
    --only-binary=:all: `
    --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed. Make sure pip is installed and accessible."
    exit 1
}

Write-Host ""
Write-Host "==> Layer built successfully at: $buildDir" -ForegroundColor Green
Write-Host "    You can now run: terraform plan" -ForegroundColor Green
