@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-job-finder.ps1" %*
