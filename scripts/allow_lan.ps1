# Run once as Administrator. Opens LAN ports so the Mac body can find and talk to the brain.
# Private profile only. Do not port-forward these on your router.

$ErrorActionPreference = "Stop"

$rules = @(
    @{ Name = "Jarvis brain WS"; Protocol = "TCP"; Port = 8765 },
    @{ Name = "Jarvis brain discover"; Protocol = "UDP"; Port = 8766 }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Already present: $($rule.Name)"
        continue
    }
    New-NetFirewallRule `
        -DisplayName $rule.Name `
        -Direction Inbound `
        -Protocol $rule.Protocol `
        -LocalPort $rule.Port `
        -Action Allow `
        -Profile Private | Out-Null
    Write-Host "Allowed inbound $($rule.Protocol) $($rule.Port) ($($rule.Name))"
}

Write-Host "Done. Start the brain with .\scripts\start_server.ps1 — the Mac client does not need the Windows IP."
