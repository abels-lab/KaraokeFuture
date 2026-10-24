<#
.SYNOPSIS
  Starts the karaoke server and opens it to guests' phones through Tailscale Funnel.

.DESCRIPTION
  1. Switches Tailscale Funnel on for the port (a public https://<laptop>.<tailnet>.ts.net
     address), so guests can join from mobile data too. The TV's QR code links there on its own.
  2. Runs the server in this window (Ctrl+C stops it) and opens the control panel.
  3. Switches Funnel off again when the server stops, unless -KeepFunnel is given: while it is
     on, anybody with the link can reach the guest page, so set a host PIN on the Settings page.
  Without Tailscale (or with -NoFunnel) the QR code links to the home Wi-Fi address as before.

.EXAMPLE
  .\start-karaoke.ps1                 # port 8010, Funnel on, control panel opens
  .\start-karaoke.ps1 -Port 8000 -NoFunnel -NoBrowser
#>
param(
    [int]$Port = 8010,
    [switch]$NoFunnel,
    [switch]$KeepFunnel,
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$app = Join-Path $PSScriptRoot "ai_karaoke"
$python = Join-Path $app ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No virtual environment at $python - see README.md, Setup." }

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) { throw "Port $Port is already in use (process $($busy[0].OwningProcess)). Is the karaoke already running?" }

$tailscale = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $tailscale -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) { $tailscale = "$env:ProgramFiles\Tailscale\tailscale.exe" }

$funnelOn = $false
if ($NoFunnel) {
    Write-Host "Funnel skipped: guests join over the home Wi-Fi." -ForegroundColor Yellow
} elseif (-not $tailscale) {
    Write-Host "Tailscale not found: guests join over the home Wi-Fi. (Install: https://tailscale.com/download)" -ForegroundColor Yellow
} else {
    & $tailscale funnel --bg $Port | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $funnelOn = $true
        $name = ((& $tailscale status --json | ConvertFrom-Json).Self.DNSName).TrimEnd(".")
        Write-Host "Guests online: https://$name/remote  (Tailscale Funnel)" -ForegroundColor Green
    } else {
        Write-Host "Funnel could not start (log in to Tailscale and allow Funnel for this device in the admin console)." -ForegroundColor Yellow
    }
}

$env:KARAOKE_PORT = "$Port"
$env:PYTHONUNBUFFERED = "1"
if (-not $NoBrowser) {
    # Opens once the server answers, without holding up the server's own output
    Start-Job -ArgumentList $Port {
        param($p)
        foreach ($i in 1..60) {
            try { Invoke-WebRequest "http://localhost:$p/api/auth/me" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 }
        }
        Start-Process "http://localhost:$p/tv"
    } | Out-Null
}

try {
    Push-Location $app
    & $python main.py
} finally {
    Pop-Location
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    if ($funnelOn -and -not $KeepFunnel) {
        & $tailscale funnel --https=443 off | Out-Null
        Write-Host "Tailscale Funnel switched off." -ForegroundColor Green
    }
}
