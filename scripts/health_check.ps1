$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
        $name, $value = $_.Split("=", 2)
        if ($name -and $value) {
            [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
        }
    }
}

$port = if ($env:JARVIS_PORT) { $env:JARVIS_PORT } else { "8765" }
$url = "http://127.0.0.1:${port}/health"
Write-Host "GET $url"
Invoke-RestMethod -Uri $url | ConvertTo-Json -Depth 6
