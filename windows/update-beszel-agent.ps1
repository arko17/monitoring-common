<#
.SYNOPSIS
  Installs/updates the Beszel agent binary from GitHub releases (SHA256-verified).
  Called by install-beszel-agent.ps1 and weekly by the "Beszel agent update" task.
  Version comes from C:\ProgramData\beszel-agent\config.json ("latest" or e.g. "0.21.2").
#>
param ([switch]$NoRestart)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$cfgDir = Join-Path $env:ProgramData "beszel-agent"
$binDir = Join-Path $env:ProgramFiles "beszel-agent"
$exe = Join-Path $binDir "beszel-agent.exe"
$log = Join-Path $cfgDir "update.log"
function Log($m) { "$(Get-Date -Format s) $m" | Tee-Object -FilePath $log -Append | Write-Host }

$cfg = Get-Content "$cfgDir\config.json" -Raw | ConvertFrom-Json
$want = $cfg.Version
if (-not $want -or $want -eq "latest") {
    $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ "User-Agent" = "beszel-agent-updater" } `
        "https://api.github.com/repos/henrygd/beszel/releases/latest"
    $want = $rel.tag_name.TrimStart("v")
}

$have = ""
if (Test-Path $exe) {
    $out = (& $exe --version) 2>&1 | Out-String
    if ($out -match "(\d+\.\d+\.\d+)") { $have = $Matches[1] }
}
if ($have -eq $want) { Log "beszel-agent $have is current"; return }

$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
$file = "beszel-agent_windows_$arch.zip"
$base = "https://github.com/henrygd/beszel/releases/download/v$want"
$tmp = Join-Path $env:TEMP "beszel-$want"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

Log "updating beszel-agent '$have' -> '$want'"
Invoke-WebRequest -UseBasicParsing "$base/$file" -OutFile "$tmp\$file"
Invoke-WebRequest -UseBasicParsing "$base/beszel_${want}_checksums.txt" -OutFile "$tmp\checksums.txt"

$expected = (Select-String -Path "$tmp\checksums.txt" -Pattern ([regex]::Escape($file)) |
    Select-Object -First 1).Line.Split(" ")[0]
$actual = (Get-FileHash -Algorithm SHA256 "$tmp\$file").Hash
if (-not $expected -or $actual -ne $expected.ToUpper()) { throw "Checksum mismatch for $file" }

Expand-Archive -Force "$tmp\$file" -DestinationPath "$tmp\x"
$newExe = Get-ChildItem -Recurse "$tmp\x" -Filter beszel-agent.exe | Select-Object -First 1

if (-not $NoRestart) { Stop-ScheduledTask -TaskName "Beszel agent" -ErrorAction SilentlyContinue }
Get-Process beszel-agent -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Copy-Item -Force $newExe.FullName $exe
Remove-Item -Recurse -Force $tmp
if (-not $NoRestart) { Start-ScheduledTask -TaskName "Beszel agent" }
Log "beszel-agent $want installed"
