$ErrorActionPreference = "Stop"
if (-not (Test-Path ".\backend\.venv")) {
  throw "backend/.venv not found. Run .\\scripts\\setup.ps1 first."
}
Push-Location .\backend
# main_v2 includes scheduler/background services (email monitor + smart assistant)
..\backend\.venv\Scripts\python -m uvicorn app.main_v2:app --host 127.0.0.1 --port 8000 --reload
Pop-Location
