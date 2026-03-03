$ErrorActionPreference = "Stop"

Write-Host "== OpenWorld setup =="

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

Assert-Command python
Assert-Command npm

if (-not (Test-Path ".\backend\.venv")) {
  Write-Host "Creating Python virtual environment..."
  python -m venv .\backend\.venv
}

Write-Host "Installing backend dependencies..."
.\backend\.venv\Scripts\python -m pip install --upgrade pip
.\backend\.venv\Scripts\python -m pip install -r .\backend\requirements.txt

if (-not (Test-Path ".\backend\.env")) {
  Copy-Item .\backend\.env.example .\backend\.env
  Write-Host "Created backend/.env from example"
}

function Ensure-EnvKey($key, $defaultValue) {
  $path = ".\backend\.env"
  $raw = Get-Content $path -Raw
  if ($raw -notmatch "(?m)^$([regex]::Escape($key))=") {
    Add-Content -Path $path -Value "$key=$defaultValue"
  }
}

Ensure-EnvKey "WEB_ALLOWED_DOMAINS" ""
Ensure-EnvKey "WEB_BLOCK_PRIVATE_HOSTS" "true"
Ensure-EnvKey "GMAIL_ACCESS_TOKEN" ""
Ensure-EnvKey "GMAIL_ACCESS_TOKEN_ENC" ""
Ensure-EnvKey "GMAIL_REFRESH_TOKEN" ""
Ensure-EnvKey "GMAIL_REFRESH_TOKEN_ENC" ""
Ensure-EnvKey "GMAIL_CLIENT_ID" ""
Ensure-EnvKey "GMAIL_CLIENT_SECRET" ""
Ensure-EnvKey "GMAIL_CLIENT_SECRET_ENC" ""
Ensure-EnvKey "OUTLOOK_ACCESS_TOKEN" ""
Ensure-EnvKey "OUTLOOK_ACCESS_TOKEN_ENC" ""
Ensure-EnvKey "OUTLOOK_REFRESH_TOKEN" ""
Ensure-EnvKey "OUTLOOK_REFRESH_TOKEN_ENC" ""
Ensure-EnvKey "OUTLOOK_CLIENT_ID" ""
Ensure-EnvKey "OUTLOOK_TENANT_ID" "common"

Write-Host "Installing frontend dependencies..."
Push-Location .\frontend
npm install
Pop-Location

Write-Host "Setup complete."
