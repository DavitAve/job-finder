@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0status-job-finder.ps1" %*
