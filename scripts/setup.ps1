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

function Invoke-CheckedCommand([string]$exe, [string[]]$commandArgs, [string]$label) {
  & $exe @commandArgs
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    throw "$label basarisiz (exit code: $code)"
  }
}

function Test-HealthyVenv($venvPath) {
  $py = Join-Path $venvPath "Scripts\python.exe"
  $cfg = Join-Path $venvPath "pyvenv.cfg"
  if (-not (Test-Path $py) -or -not (Test-Path $cfg)) {
    return $false
  }
  try {
    & $py -c "import sys; print(sys.executable)" | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

Write-Status "1/7 - Python ve npm kontrol ediliyor..."
Assert-Command python
Assert-Command npm
Write-Status "   OK - Python ve npm bulundu"

$backendVenv = ".\backend\.venv"
$backendPython = ".\backend\.venv\Scripts\python.exe"

Write-Status "2/7 - Sanal ortam kontrol ediliyor..."
if (-not (Test-HealthyVenv $backendVenv)) {
  if (Test-Path $backendVenv) {
    Write-Status "   Bozuk venv tespit edildi, temizleniyor..."
    Remove-Item -Recurse -Force $backendVenv
  }
  Write-Status "   backend/.venv olusturuluyor..."
  $venvCreator = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
  try {
    if ($venvCreator -eq "py") {
      Invoke-CheckedCommand -exe "py" -commandArgs @("-3.13", "-m", "venv", $backendVenv) -label "Python 3.13 venv olusturma"
    } else {
      throw "py launcher bulunamadi"
    }
  } catch {
    Write-Status "   Python 3.13 bulunamadi, varsayilan Python ile yeniden deneniyor..."
    if ($venvCreator -eq "py") {
      Invoke-CheckedCommand -exe "py" -commandArgs @("-3", "-m", "venv", $backendVenv) -label "Varsayilan Python venv olusturma"
    } else {
      Invoke-CheckedCommand -exe "python" -commandArgs @("-m", "venv", $backendVenv) -label "Varsayilan Python venv olusturma"
    }
  }
  if (-not (Test-HealthyVenv $backendVenv)) {
    throw "backend/.venv olusturuldu ama saglik kontrolunu gecemedi."
  }
  Write-Status "   OK - Sanal ortam olusturuldu"
} else {
  Write-Status "   OK - Sanal ortam zaten var"
}

$pythonExe = $backendPython
Write-Status "   Not: Kurulum paketleri backend/.venv'e kurulacak: $pythonExe"

Write-Status "3/7 - Python paketleri yukleniyor..."
Write-Status "   - pip guncelleniyor..."
Invoke-CheckedCommand -exe $pythonExe -commandArgs @("-m", "pip", "install", "--upgrade", "pip", "--quiet") -label "pip guncelleme"
Write-Status "   - requirements.txt yukleniyor (bu biraz zaman alabilir)..."
Invoke-CheckedCommand -exe $pythonExe -commandArgs @("-m", "pip", "install", "-r", ".\backend\requirements.txt") -label "requirements kurulumu"
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
if (Test-Path ".\package-lock.json") {
  npm ci --no-fund --loglevel=error
} else {
  npm install --no-fund --loglevel=error
}
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
