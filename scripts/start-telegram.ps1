$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\backend\.venv")) {
  throw "backend/.venv not found. Run .\\scripts\\setup.ps1 first."
}
Push-Location .\backend
..\backend\.venv\Scripts\python -m app.telegram_bridge
Pop-Location

