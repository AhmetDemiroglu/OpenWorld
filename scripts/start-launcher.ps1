$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$runtimePython = "C:\OpenWorldRuntime\venv\Scripts\python.exe"
$backendPython = ".\backend\.venv\Scripts\python.exe"
$backendCfg = ".\backend\.venv\pyvenv.cfg"

if ((-not (Test-Path $runtimePython)) -and ((-not (Test-Path $backendPython)) -or (-not (Test-Path $backendCfg)))) {
  Write-Host "Ilk kurulum yapiliyor..."
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\setup.ps1
}

if (Test-Path $runtimePython) {
  & $runtimePython .\launcher.py
} else {
  & $backendPython .\launcher.py
}
