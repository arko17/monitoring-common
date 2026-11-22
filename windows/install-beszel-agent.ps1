<#
.SYNOPSIS
  One-time setup of the Beszel agent on a Windows PC (family PCs, own laptop/workstation).

.DESCRIPTION
  No WinGet/Scoop/NSSM needed:
  - Agent binary from the official GitHub release (SHA256-verified) in
    C:\Program Files\beszel-agent, config + data in C:\ProgramData\beszel-agent (Admins/SYSTEM only).
  - Runs as SYSTEM through the scheduled task "Beszel agent": at boot, and an hourly
    trigger restarts it if it ever stopped.
  - The agent connects OUTBOUND to the hub (WebSocket), so it also works when a laptop
    is away from home. No inbound firewall rule is needed.
  - The scheduled task "Beszel agent update" (weekly, SYSTEM) installs new releases.

  Run once in an elevated PowerShell (copy the folder with both .ps1 files to the PC):
    Set-ExecutionPolicy -Scope Process Bypass
    .\install-beszel-agent.ps1 -HubUrl https://beszel.mon.example.org `
        -Key "ssh-ed25519 AAAA..." -Token "<universal token>"

  Key and token: Beszel hub → "Add system" (public key) and
  Settings → Tokens & Fingerprints (universal token).

  Uninstall: .\install-beszel-agent.ps1 -Uninstall
#>
[CmdletBinding(DefaultParameterSetName = "Install")]
param (
    [Parameter(Mandatory = $true, ParameterSetName = "Install")] [string]$HubUrl,
    [Parameter(Mandatory = $true, ParameterSetName = "Install")] [string]$Key,
    [Parameter(Mandatory = $true, ParameterSetName = "Install")] [string]$Token,
    # "latest" = always follow upstream releases; or pin e.g. "0.21.2"
    [Parameter(ParameterSetName = "Install")] [string]$Version = "latest",
    [Parameter(Mandatory = $true, ParameterSetName = "Uninstall")] [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Please run this script in an elevated (Administrator) PowerShell."
}

$cfgDir = Join-Path $env:ProgramData "beszel-agent"
$binDir = Join-Path $env:ProgramFiles "beszel-agent"

if ($Uninstall) {
    foreach ($t in "Beszel agent", "Beszel agent update") {
        Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    }
    Get-Process beszel-agent -ErrorAction SilentlyContinue | Stop-Process -Force
    Remove-Item -Recurse -Force $binDir, $cfgDir -ErrorAction SilentlyContinue
    Write-Host "Beszel agent removed." -ForegroundColor Green
    return
}

# --- config directory, readable only by SYSTEM and Administrators -----------------
New-Item -ItemType Directory -Force -Path $cfgDir, "$cfgDir\data", $binDir | Out-Null
& icacls.exe $cfgDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null

@{ HubUrl = $HubUrl; Key = $Key; Token = $Token; Version = $Version } |
    ConvertTo-Json | Set-Content -Encoding UTF8 "$cfgDir\config.json"
Copy-Item -Force (Join-Path $PSScriptRoot "update-beszel-agent.ps1") "$cfgDir\update-beszel-agent.ps1"

# Runner: sets the environment from config.json and starts the agent in the foreground.
@'
$ErrorActionPreference = "Stop"
$cfgDir = Join-Path $env:ProgramData "beszel-agent"
$cfg = Get-Content "$cfgDir\config.json" -Raw | ConvertFrom-Json
$env:KEY = $cfg.Key
$env:TOKEN = $cfg.Token
$env:HUB_URL = $cfg.HubUrl
$env:DATA_DIR = "$cfgDir\data"
$env:LISTEN = "127.0.0.1:45876"
& (Join-Path $env:ProgramFiles "beszel-agent\beszel-agent.exe")
exit $LASTEXITCODE
'@ | Set-Content -Encoding UTF8 "$cfgDir\run-agent.ps1"

# --- install binary ------------------------------------------------------------------
& "$cfgDir\update-beszel-agent.ps1" -NoRestart

# --- tasks ----------------------------------------------------------------------------
$ps = "powershell.exe"
$common = @{ User = "SYSTEM"; RunLevel = "Highest"; Force = $true }

$agentAction = New-ScheduledTaskAction -Execute $ps `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$cfgDir\run-agent.ps1`""
$atBoot = New-ScheduledTaskTrigger -AtStartup
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$agentSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "Beszel agent" -Action $agentAction -Trigger $atBoot, $hourly `
    -Settings $agentSettings @common | Out-Null

$updAction = New-ScheduledTaskAction -Execute $ps `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$cfgDir\update-beszel-agent.ps1`""
$weekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 12:00
$updSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Beszel agent update" -Action $updAction -Trigger $weekly `
    -Settings $updSettings @common | Out-Null

Start-ScheduledTask -TaskName "Beszel agent"
Start-Sleep -Seconds 5
if (Get-Process beszel-agent -ErrorAction SilentlyContinue) {
    Write-Host "Done. The PC should appear in the Beszel hub within a minute." -ForegroundColor Green
} else {
    Write-Warning "Agent is not running yet. Check: Get-ScheduledTaskInfo 'Beszel agent'"
}
