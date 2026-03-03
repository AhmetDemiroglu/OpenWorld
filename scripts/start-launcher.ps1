$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".\backend\.venv\Scripts\python.exe")) {
  Write-Host "Ilk kurulum yapiliyor..."
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\setup.ps1
}

.\backend\.venv\Scripts\python.exe .\launcher.py

