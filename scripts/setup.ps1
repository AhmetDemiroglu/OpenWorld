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
Write-Status "   ✓ Python ve npm bulundu"

$runtimeRoot = "C:\OpenWorldRuntime"
$runtimeVenv = Join-Path $runtimeRoot "venv"
$runtimePython = Join-Path $runtimeVenv "Scripts\python.exe"
$backendPython = ".\backend\.venv\Scripts\python.exe"
$backendCfg = ".\backend\.venv\pyvenv.cfg"

Write-Status "2/7 - Sanal ortam kontrol ediliyor..."
if (-not (Test-Path $runtimePython)) {
  Write-Status "   C:\OpenWorldRuntime\venv oluşturuluyor..."
  if (-not (Test-Path $runtimeRoot)) {
    New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
  }
  py -3.13 -m venv $runtimeVenv
  Write-Status "   ✓ Sanal ortam oluşturuldu"
} else {
  Write-Status "   ✓ Sanal ortam zaten var"
}

$pythonExe = $runtimePython
if ((Test-Path $backendPython) -and (Test-Path $backendCfg)) {
  $pythonExe = $backendPython
}

Write-Status "3/7 - Python paketleri yükleniyor..."
Write-Status "   - pip güncelleniyor..."
& $pythonExe -m pip install --upgrade pip --quiet
Write-Status "   - requirements.txt yükleniyor (bu biraz zaman alabilir)..."
& $pythonExe -m pip install -r .\backend\requirements.txt
Write-Status "   ✓ Python paketleri yüklendi"

Write-Status "4/7 - Ortam değişkenleri ayarlanıyor..."
if (-not (Test-Path ".\backend\.env")) {
  Copy-Item .\backend\.env.example .\backend\.env
  Write-Status "   ✓ .env dosyası oluşturuldu"
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
Write-Status "   ✓ Ortam değişkenleri ayarlandı"

Write-Status "5/7 - Frontend bağımlılıkları yükleniyor..."
Push-Location .\frontend
npm install
Pop-Location
Write-Status "   ✓ Frontend bağımlılıkları yüklendi"

Write-Status "6/7 - Frontend build ediliyor..."
Push-Location .\frontend
npm run build
Pop-Location
Write-Status "   ✓ Frontend build edildi"

Write-Status "7/7 - Veri klasörleri oluşturuluyor..."
New-Item -ItemType Directory -Force -Path ".\data\sessions" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\logs" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\planner" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\mail\drafts" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\reports" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\screenshots" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\audio" | Out-Null
New-Item -ItemType Directory -Force -Path ".\data\webcam" | Out-Null
Write-Status "   ✓ Klasörler oluşturuldu"

Write-Status ""
Write-Status "========================================"
Write-Status "Kurulum başarıyla tamamlandı!"
Write-Status "========================================"
Write-Status ""
Write-Status "Şimdi yapmanız gerekenler:"
Write-Status "1. [Kaydet] butonuna tıklayın"
Write-Status "2. Model indirin: [Qwen3.5] veya [Model Çek]"
Write-Status "3. [Başlat] butonuna tıklayın"
