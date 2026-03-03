$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\backend\.venv")) {
  throw "backend/.venv not found. Run .\\scripts\\setup.ps1 first."
}
Push-Location .\backend
..\backend\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
Pop-Location

