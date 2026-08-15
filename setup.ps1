<#
.SYNOPSIS
    One-click environment initializer for BioNexus Plugin (PowerShell).
.DESCRIPTION
    Creates a local virtual environment (.venv) and runs hardware-optimized package installation.
#>

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " 🧬 BioNexus Plugin: Windows PowerShell One-Click Setup" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python was not found in PATH. Please install Python 3.10+." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] Creating Python virtual environment in .venv ..." -ForegroundColor Green
    python -m venv .venv
}

Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Green
& ".\.venv\Scripts\Activate.ps1"

python scripts\setup_env.py $args

Write-Host "`n[DONE] Setup complete! Activate anytime via: .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
