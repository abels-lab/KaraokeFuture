@echo off
rem Double-click to start the AI Karaoke Desktop App (multi-monitor projector, no autoplay blocks).
rem Options are passed on, e.g.  start-desktop.bat -NoFunnel   or   start-desktop.bat -Port 8000
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-desktop.ps1" %*
pause
