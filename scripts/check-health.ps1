$ErrorActionPreference = "Stop"

Write-Host "Checking backend health..."
try {
  $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
  $health | ConvertTo-Json -Depth 5
} catch {
  Write-Host "Backend is not reachable at http://127.0.0.1:8000/health"
}

Write-Host ""
Write-Host "Checking UI root..."
try {
  $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -TimeoutSec 5
  Write-Host "UI OK, status:" $resp.StatusCode
} catch {
  Write-Host "UI is not reachable at http://127.0.0.1:8000/"
}

Write-Host ""
Write-Host "Listening ports (8000, 11434):"
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 8000, 11434 } |
  Select-Object LocalAddress, LocalPort, OwningProcess, State
