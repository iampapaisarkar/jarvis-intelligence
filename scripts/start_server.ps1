$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    Write-Error "Missing .venv. Run .\scripts\setup_windows.ps1 first."
}

if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
        $name, $value = $_.Split("=", 2)
        if ($name -and $value) {
            [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
        }
    }
}

$hostName = if ($env:JARVIS_HOST) { $env:JARVIS_HOST } else { "0.0.0.0" }
$port = if ($env:JARVIS_PORT) { $env:JARVIS_PORT } else { "8765" }

Write-Host "Starting Jarvis on ${hostName}:${port}"
& .\.venv\Scripts\python.exe -m uvicorn server.main:app --host $hostName --port $port
