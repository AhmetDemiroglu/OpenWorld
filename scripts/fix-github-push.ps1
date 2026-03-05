# OpenWorld GitHub Push Fix Script
# 5GB model dosyasini Git history'den temizler ve yeniden push eder

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Red
Write-Host "GitHub Push Sorunu Cozucu" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""
Write-Host "Sorun: 5GB model dosyasi GitHub'a gitmis" -ForegroundColor Yellow
Write-Host "Cozum: Model dosyasini history'den silecegiz" -ForegroundColor Yellow
Write-Host ""

# Kontroller
$ModelPath = "models/Qwen3.5-9B-Q4_K_M.gguf"
if (Test-Path $ModelPath) {
    $Size = (Get-Item $ModelPath).Length / 1GB
    Write-Host "[!] Model dosyasi bulundu: $([math]::Round($Size, 2)) GB" -ForegroundColor Red
    Write-Host "[!] Bu dosya GitHub'a GITMEMELI (max 100MB)" -ForegroundColor Red
    Write-Host ""
}

Write-Host "ADIM 1: Model dosyasi Git tracking'den cikariliyor..." -ForegroundColor Cyan
git rm --cached $ModelPath 2>$null
Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 2: Gitignore guncelleniyor..." -ForegroundColor Cyan
@"
# Models
models/*.gguf
models/*.bin
models/*.safetensors
*.gguf
*.bin
"@ | Out-File -Append -FilePath .gitignore -Encoding UTF8
Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 3: BFG Repo-Cleaner indiriliyor..." -ForegroundColor Cyan
$BfgUrl = "https://repo1.maven.org/maven2/com/madgag/bfg/1.14.0/bfg-1.14.0.jar"
$BfgPath = "$env:TEMP\bfg.jar"
if (-not (Test-Path $BfgPath)) {
    Invoke-WebRequest -Uri $BfgUrl -OutFile $BfgPath
}
Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 4: Git history'den buyuk dosyalar temizleniyor..." -ForegroundColor Cyan
Write-Host "(Bu islem biraz zaman alabilir...)" -ForegroundColor Gray

# Git repository'i clone'la (mirror)
$MirrorDir = "$env:TEMP\openworld-mirror"
if (Test-Path $MirrorDir) {
    Remove-Item -Recurse -Force $MirrorDir
}

$RemoteUrl = git remote get-url origin
Write-Host "Mirror clonlaniyor: $RemoteUrl" -ForegroundColor Gray

# Java ile BFG calistir
java -jar $BfgPath --strip-blobs-bigger-than 100M .

Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 5: Git reflog temizleniyor..." -ForegroundColor Cyan
git reflog expire --expire=now --all
Write-Host "OK" -ForegroundColor Green

Write-Host ""
WriteHost "ADIM 6: Git garbage collection..." -ForegroundColor Cyan
git gc --prune=now --aggressive
Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 7: Degisiklikler commit ediliyor..." -ForegroundColor Cyan
git add .gitignore
git commit -m "Remove large model files from history"
Write-Host "OK" -ForegroundColor Green

Write-Host ""
Write-Host "ADIM 8: GitHub'a force push..." -ForegroundColor Cyan
Write-Host "(Bu adim varolan GitHub history'sini silecek!)" -ForegroundColor Red
$Confirm = Read-Host "Devam etmek istiyor musunuz (E/H)"

if ($Confirm -eq "E" -or $Confirm -eq "e") {
    git push origin main --force
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "BASARILI! GitHub'a gonderildi." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "GitHub'da kontrol edin:" -ForegroundColor Cyan
    Write-Host $RemoteUrl -ForegroundColor White
} else {
    Write-Host "Islem iptal edildi." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "NOT: Model dosyanizi saklamayi unutmayin!" -ForegroundColor Yellow
Write-Host "Yerel kopyaniz: $ModelPath" -ForegroundColor Gray
