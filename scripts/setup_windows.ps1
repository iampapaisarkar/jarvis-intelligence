# Requires Python 3.11, 3.12, or 3.13 on PATH.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python is not on PATH. Install Python 3.11-3.13 from python.org and enable 'Add python.exe to PATH'."
}

$versionOutput = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$major, $minor = $versionOutput.Split(".")
if ([int]$major -ne 3 -or [int]$minor -lt 11 -or [int]$minor -gt 13) {
    Write-Warning "Detected Python $versionOutput. llama-cpp-python wheels are most reliable on 3.11-3.13."
}

Write-Host "Creating virtual environment at .venv"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example - edit JARVIS_AUTH_TOKEN before exposing this on a LAN."
}

New-Item -ItemType Directory -Force -Path models\llm, models\stt, models\tts, logs | Out-Null

Write-Host ""
Write-Host "Next:"
Write-Host "  1. .\.venv\Scripts\Activate.ps1"
Write-Host "  2. python scripts\download_model.py"
Write-Host "  3. python scripts\download_model.py --stt"
Write-Host "  4. python scripts\download_model.py --tts"
Write-Host "  5. .\scripts\start_server.ps1"
