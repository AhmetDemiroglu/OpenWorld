# OpenWorld EXE Build Script
# Bu script OpenWorld icin calistirilabilir dosyalar olusturur

param(
    [string]$Version = "1.0.0",
    [string]$Type = "installer"  # installer, portable, veya launcher
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BuildDir = "$Root\build"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OpenWorld EXE Build Script" -ForegroundColor Cyan
Write-Host "Version: $Version" -ForegroundColor Cyan
Write-Host "Type: $Type" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

switch ($Type) {
    "installer" {
        Build-Installer
    }
    "portable" {
        Build-Portable
    }
    "launcher" {
        Build-LauncherExe
    }
    default {
        Write-Host "Bilinmeyen type: $Type" -ForegroundColor Red
        Write-Host "Kullanim: .\build-exe.ps1 -Version '1.0.0' -Type [installer|portable|launcher]" -ForegroundColor Yellow
    }
}

function Build-Installer {
    Write-Host "[Inno Setup Installer]" -ForegroundColor Green
    Write-Host ""
    
    # Inno Setup kontrol
    $InnoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $InnoPath)) {
        $InnoPath = "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    }
    
    if (-not (Test-Path $InnoPath)) {
        Write-Host "HATA: Inno Setup bulunamadi!" -ForegroundColor Red
        Write-Host "Lutfen indirin: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Kurulumdan sonra tekrar deneyin." -ForegroundColor Gray
        return
    }
    
    Write-Host "Inno Setup bulundu: $InnoPath" -ForegroundColor Green
    Write-Host "Installer derleniyor..." -ForegroundColor Yellow
    
    # ISS dosyasini guncelle
    $IssContent = Get-Content "$PSScriptRoot\OpenWorld-Setup.iss" -Raw
    $IssContent = $IssContent -replace '#define MyAppVersion "1.0.0"', "#define MyAppVersion `"$Version`""
    $IssContent | Out-File "$PSScriptRoot\OpenWorld-Setup.iss" -Encoding UTF8
    
    # Derle
    & $InnoPath "$PSScriptRoot\OpenWorld-Setup.iss"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "BASARILI!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "Cikti: $BuildDir\OpenWorld-Setup-v$Version.exe" -ForegroundColor White
        Write-Host ""
        Write-Host "Kullanim:" -ForegroundColor Yellow
        Write-Host "  1. EXE'yi dagitin" -ForegroundColor Gray
        Write-Host "  2. Kullanici kurulum yapsin" -ForegroundColor Gray
        Write-Host "  3. Masaustunden calistirsin" -ForegroundColor Gray
    } else {
        Write-Host "HATA: Derleme basarisiz!" -ForegroundColor Red
    }
}

function Build-Portable {
    Write-Host "[Portable ZIP]" -ForegroundColor Green
    Write-Host ""
    
    # Zaten var olan portable scripti calistir
    & "$PSScriptRoot\build-portable.ps1" -Version $Version
    
    # Bat to Exe (varsa)
    $BatToExe = "$env:ProgramFiles\Bat_To_Exe_Converter\Bat_To_Exe.exe"
    if (Test-Path $BatToExe) {
        Write-Host "Bat to Exe bulundu, launcher.exe olusturuluyor..." -ForegroundColor Yellow
        # Bu kisim istege bagli
    }
}

function Build-LauncherExe {
    Write-Host "[Launcher Only EXE]" -ForegroundColor Green
    Write-Host ""
    
    # PyInstaller kontrol
    $PyInstaller = & python -m pip show pyinstaller 2>$null
    if (-not $PyInstaller) {
        Write-Host "PyInstaller kuruluyor..." -ForegroundColor Yellow
        & python -m pip install pyinstaller
    }
    
    # Launcher'i exe yap
    $LauncherDir = "$BuildDir\launcher-exe"
    New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null
    
    & python -m PyInstaller `
        --noconfirm `
        --onefile `
        --windowed `
        --name "OpenWorld" `
        --distpath "$LauncherDir" `
        --workpath "$BuildDir\temp" `
        --specpath "$BuildDir\temp" `
        "$Root\launcher.py"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Launcher EXE olusturuldu: $LauncherDir\OpenWorld.exe" -ForegroundColor Green
        Write-Host "NOT: Bu exe sadece launcher.py'yi calistirir." -ForegroundColor Yellow
        Write-Host "Python ve diger bagimliliklar hala gerekli!" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Build tamamlandi." -ForegroundColor Cyan
