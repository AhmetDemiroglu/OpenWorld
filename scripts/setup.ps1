$ErrorActionPreference = "Stop"

function Write-Status($message) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $message"
}

Write-Status "========================================"
Write-Status "OpenWorld Kurulum Scripti"
Write-Status "========================================"
Write-Status ""

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

Write-Status "1/7 - Python ve npm kontrol ediliyor..."
Assert-Command python
Assert-Command npm
Write-Status "   OK - Python ve npm bulundu"

$runtimeRoot = "C:\OpenWorldRuntime"
$runtimeVenv = Join-Path $runtimeRoot "venv"
$runtimePython = Join-Path $runtimeVenv "Scripts\python.exe"
$backendPython = ".\backend\.venv\Scripts\python.exe"
$backendCfg = ".\backend\.venv\pyvenv.cfg"

Write-Status "2/7 - Sanal ortam kontrol ediliyor..."
if (-not (Test-Path $runtimePython)) {
  Write-Status "   C:\OpenWorldRuntime\venv olusturuluyor..."
  if (-not (Test-Path $runtimeRoot)) {
    New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
  }
  py -3.13 -m venv $runtimeVenv
  Write-Status "   OK - Sanal ortam olusturuldu"
} else {
  Write-Status "   OK - Sanal ortam zaten var"
}

$pythonExe = $runtimePython
if ((Test-Path $backendPython) -and (Test-Path $backendCfg)) {
  $pythonExe = $backendPython
}

Write-Status "3/7 - Python paketleri yukleniyor..."
Write-Status "   - pip guncelleniyor..."
& $pythonExe -m pip install --upgrade pip --quiet
Write-Status "   - requirements.txt yukleniyor (bu biraz zaman alabilir)..."
& $pythonExe -m pip install -r .\backend\requirements.txt
Write-Status "   OK - Python paketleri yuklendi"

Write-Status "4/7 - Ortam degiskenleri ayarlaniyor..."
if (-not (Test-Path ".\backend\.env")) {
  Copy-Item .\backend\.env.example .\backend\.env
  Write-Status "   OK - .env dosyasi olusturuldu"
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
Write-Status "   OK - Ortam degiskenleri ayarlandi"

Write-Status "5/7 - Frontend bagimliliklari yukleniyor..."
Push-Location .\frontend
npm install
Pop-Location
Write-Status "   OK - Frontend bagimliliklari yuklendi"

Write-Status "6/7 - Frontend build ediliyor..."
Push-Location .\frontend
npm run build
Pop-Location
Write-Status "   OK - Frontend build edildi"

Write-Status "7/7 - Veri klasorleri olusturuluyor..."
New-Item -ItemType Directory -Force -Path ".\data\sessions" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\logs" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\planner" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\mail\drafts" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\reports" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\screenshots" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\audio" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\webcam" | Out-Null
Write-Status "   OK - Klasorler olusturuldu"

Write-Status ""
Write-Status "========================================"
Write-Status "Kurulum basariyla tamamlandi!"
Write-Status "========================================"
Write-Status ""
Write-Status "Simdi yapmaniz gerekenler:"
Write-Status "1. [Kaydet] butonuna tiklayin"
Write-Status "2. Model indirin: [Qwen3.5] veya [Model Cek]"
Write-Status "3. [Baslat] butonuna tiklayin"
