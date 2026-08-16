@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-job-finder.ps1" %*
