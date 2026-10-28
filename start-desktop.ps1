<#
.SYNOPSIS
  Starts the AI Karaoke Electron multi-monitor desktop application.

.DESCRIPTION
  1. Optionally activates Tailscale Funnel for the port (public HTTPS join link for mobile phones).
  2. Ensures desktop dependencies (electron) are installed in desktop/ (runs npm install if needed).
  3. Launches Electron, which boots the Python backend (if not already running), opens the Control Panel (/tv),
     and provides native multi-monitor projector handling (/screen).
  4. Cleans up Tailscale Funnel when the desktop application closes.
#>
param(
    [int]$Port = 8010,
    [switch]$NoFunnel,
    [switch]$KeepFunnel,
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$desktopDir = Join-Path $repoRoot "desktop"

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
if ($Dev) {
    $env:KARAOKE_DEV = "1"
}

try {
    # Check if desktop/node_modules exists; if not, install dependencies
    $nodeModules = Join-Path $desktopDir "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Host "Installing desktop app dependencies (electron)..." -ForegroundColor Cyan
        Push-Location $desktopDir
        npm install
        Pop-Location
    }

    Write-Host "Starting AI Karaoke Desktop..." -ForegroundColor Green
    Push-Location $desktopDir
    npx electron .
} finally {
    Pop-Location
    if ($funnelOn -and -not $KeepFunnel) {
        & $tailscale funnel --https=443 off | Out-Null
        Write-Host "Tailscale Funnel switched off." -ForegroundColor Green
    }
}
