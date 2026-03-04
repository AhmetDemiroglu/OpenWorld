# Kurulum Rehberi

## Sistem Gereksinimleri

### Minimum
- Windows 10/11 (64-bit)
- 8 GB RAM
- 10 GB boş disk alanı
- Python 3.11+
- Node.js 20+

### Önerilen
- Windows 11
- 16 GB+ RAM
- 20 GB+ boş disk
- GPU (CUDA destekli)
- Mikrofon ve Webcam

## Adım Adım Kurulum

### 1. Python Kurulumu

1. [python.org](https://python.org) adresinden Python 3.11+ indirin
2. Kurulum sırasında **"Add Python to PATH"** seçeneğini işaretleyin
3. Kurulumu doğrulayın:
   ```powershell
   python --version
   ```

### 2. Node.js Kurulumu

1. [nodejs.org](https://nodejs.org) adresinden LTS sürümünü indirin
2. Kurulumu doğrulayın:
   ```powershell
   node --version
   ```

### 3. Ollama Kurulumu

1. [ollama.com/download](https://ollama.com/download) adresinden indirin
2. Model indirin:
   ```powershell
   ollama pull qwen3.5:9b-q4_K_M
   ```

### 4. OpenWorld Kurulumu

```powershell
# Repo'yu klonla
git clone https://github.com/AhmetDemiroglu/OpenWorld.git
cd OpenWorld

# Launcher'ı çalıştır
python launcher.py
```

Launcher'da:
1. **[Kurulum]** butonuna tıklayın
2. Kurulum tamamlanana kadar bekleyin (5-10 dk)
3. **[Kaydet]** ve **[Başlat]** yapın

### 5. Doğrulama

Web arayüzüne gidin: http://127.0.0.1:8000

## Sorun Giderme

### "Python bulunamadı"
Python PATH'e eklenmemiş. Yeniden kurun ve "Add to PATH" işaretleyin.

### "Tesseract not found"
OCR için Tesseract kurun: https://github.com/UB-Mannheim/tesseract/wiki

### "DLL Load Failed" (PyAudio)
```powershell
pip install pipwin
pipwin install pyaudio
```
