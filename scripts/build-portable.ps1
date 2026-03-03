# OpenWorld Portable Build Script
# Bu script, dagitim icin portable ZIP olusturur
# Kullanici sadece ZIP'i acip OpenWorld-Launcher.bat'i calistirir

param(
    [string]$Version = "1.0.0",
    [switch]$IncludePython,
    [switch]$IncludeNode
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BuildDir = "$Root\build\OpenWorld-Portable-$Version"
$OutputZip = "$Root\build\OpenWorld-Portable-$Version.zip"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenWorld Portable Build Script" -ForegroundColor Cyan
Write-Host "Version: $Version" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Temizlik
Write-Host "[1/6] Build dizini temizleniyor..." -ForegroundColor Yellow
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
if (Test-Path $OutputZip) {
    Remove-Item -Force $OutputZip
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# Kaynak dosyalari kopyala
Write-Host "[2/6] Kaynak dosyalar kopyalaniyor..." -ForegroundColor Yellow
$ExcludeList = @(
    '.git', '__pycache__', '.venv', 'venv', 'node_modules', 
    'dist', 'build', '*.gguf', '*.bin', '*.log',
    'data\sessions', 'data\logs', 'data\mail\drafts', 'data\reports'
)

Get-ChildItem -Path $Root | Where-Object { 
    $item = $_
    $exclude = $false
    foreach ($ex in $ExcludeList) {
        if ($item.Name -like $ex -or $item.FullName -like "*$ex*") {
            $exclude = $true
            break
        }
    }
    -not $exclude
} | ForEach-Object {
    $dest = "$BuildDir\$($_.Name)"
    if ($_.PSIsContainer) {
        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
    } else {
        Copy-Item -Path $_.FullName -Destination $dest -Force
    }
}

# Gerekli klasorleri olustur
Write-Host "[3/6] Veri klasorleri olusturuluyor..." -ForegroundColor Yellow
@('data\sessions', 'data\logs', 'data\planner', 'data\mail\drafts', 'data\reports', 'models') | ForEach-Object {
    New-Item -ItemType Directory -Force -Path "$BuildDir\$_" | Out-Null
}

# README ekle
Write-Host "[4/6] Kullanim kilavuzu ekleniyor..." -ForegroundColor Yellow
$Readme = @"
# OpenWorld Portable v$Version

## Hizli Baslangic

1. **OpenWorld-Launcher.bat** dosyasina cift tiklayin
2. Launcher acilinca **"Kurulum"** butonuna basin
3. **"Qwen3.5"** veya **"Model Cek"** ile model indirin
4. **"Kaydet"** > **"Baslat"** > **"Arayuz"**

Hepsi bu kadar!

## Telegram Botu (Istege Bagli)

1. @BotFather'dan bot tokeni alin
2. @userinfobot'dan kullanici ID'nizi ogrenin
3. Launcher'daki Telegram bolumune girin
4. Token ve ID'yi yazip Kaydet'e basin

## E-posta (Istege Bagli)

- Gmail: Google Cloud Console'dan OAuth Client ID alin
- Outlook: Azure Portal'dan App Registration yapin

Detayli bilgi icin: https://github.com/kullaniciadi/OpenWorld

## Notlar

- Ilk kurulum internet baglantisi gerektirir (model indirme)
- Ollama kurulu olmalidir: https://ollama.com/download
- Port 8000 ve 11434 bos olmalidir

---
OpenWorld Local Agent v$Version
"@

$Readme | Out-File -FilePath "$BuildDir\KULLANIM_KILAVUZU.txt" -Encoding UTF8

# Kurulum scripti olustur (otomatik setup)
Write-Host "[5/6] Otomatik kurulum scripti olusturuluyor..." -ForegroundColor Yellow
$AutoSetup = @'
@echo off
chcp 65001 >nul
title OpenWorld - Otomatik Kurulum
echo.
echo ========================================
echo   OpenWorld - Otomatik Kurulum
echo ========================================
echo.

REM Python kontrol
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python kurulu degil!
    echo Lutfen Python 3.11+ indirin: https://python.org
    pause
    exit /b 1
)

REM Node.js kontrol
node --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Node.js kurulu degil!
    echo Lutfen Node.js 20+ indirin: https://nodejs.org
    pause
    exit /b 1
)

REM Ollama kontrol
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [UYARI] Ollama bulunamadi!
    echo Model kullanabilmek icin Ollama kurun: https://ollama.com/download
    echo.
)

echo [1/4] Python sanal ortam olusturuluyor...
cd backend
if exist .venv (
    echo Sanal ortam zaten var, atlaniyor...
) else (
    python -m venv .venv
)

echo [2/4] Python paketleri yukleniyor...
call .venv\Scripts\activate.bat
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo [3/4] Frontend build ediliyor...
cd ..\frontend
if exist node_modules (
    echo Node modules zaten var, atlaniyor...
) else (
    call npm install
)
call npm run build

echo [4/4] Ayarlar hazirlaniyor...
cd ..
if not exist backend\.env (
    copy backend\.env.example backend\.env 2>nul || (
        echo # OpenWorld Environment > backend\.env
    )
)

echo.
echo ========================================
echo   Kurulum Tamamlandi!
echo ========================================
echo.
echo Simdi OpenWorld-Launcher.bat'i calistirabilirsiniz.
echo.
pause
'@

$AutoSetup | Out-File -FilePath "$BuildDir\KURULUM.bat" -Encoding ASCII

# ZIP olustur
Write-Host "[6/6] ZIP arsivi olusturuluyor..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $OutputZip -Force

# Sonuc
$ZipSize = (Get-Item $OutputZip).Length / 1MB
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Build Tamamlandi!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Cikti: $OutputZip" -ForegroundColor White
Write-Host "Boyut: $([math]::Round($ZipSize, 2)) MB" -ForegroundColor White
Write-Host ""
Write-Host "Kullanim:" -ForegroundColor Yellow
Write-Host "  1. ZIP'i istediginiz yere acin" -ForegroundColor Gray
Write-Host "  2. KURULUM.bat'i calistirin (ilk sefer icin)" -ForegroundColor Gray
Write-Host "  3. OpenWorld-Launcher.bat'i calistirin" -ForegroundColor Gray
Write-Host ""
