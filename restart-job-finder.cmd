@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-job-finder.ps1" %*
