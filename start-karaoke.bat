@echo off
rem Double-click to start the karaoke (Tailscale Funnel on, control panel opens).
rem Options are passed on, e.g.  start-karaoke.bat -NoFunnel   or   start-karaoke.bat -Port 8000
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-karaoke.ps1" %*
pause
