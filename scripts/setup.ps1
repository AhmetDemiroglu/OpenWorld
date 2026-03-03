$ErrorActionPreference = "Stop"

Write-Host "== OpenWorld setup =="

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

Assert-Command python
Assert-Command npm

$runtimeRoot = "C:\OpenWorldRuntime"
$runtimeVenv = Join-Path $runtimeRoot "venv"
$runtimePython = Join-Path $runtimeVenv "Scripts\python.exe"
$backendPython = ".\backend\.venv\Scripts\python.exe"
$backendCfg = ".\backend\.venv\pyvenv.cfg"

if (-not (Test-Path $runtimePython)) {
  Write-Host "Creating runtime virtual environment at C:\OpenWorldRuntime\venv ..."
  if (-not (Test-Path $runtimeRoot)) {
    New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
  }
  py -3.13 -m venv $runtimeVenv
}

$pythonExe = $runtimePython
if ((Test-Path $backendPython) -and (Test-Path $backendCfg)) {
  $pythonExe = $backendPython
}

Write-Host "Installing backend dependencies..."
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r .\backend\requirements.txt

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
