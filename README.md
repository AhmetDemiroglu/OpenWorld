<div align="center">

# 🌍 OpenWorld Local Agent

**Gerçek Bir Süper Ajan - Yerel Yapay Zeka Asistanı**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Modern%20Web%20Framework-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB.svg)](https://react.dev)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange.svg)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Sadece finansal işlemler hariç - HER ŞEY serbest!*

</div>

---

## 📋 İçindekiler

1. [Özellikler Özeti](#-özellikler-özeti)
2. [Sistem Gereksinimleri](#-sistem-gereksinimleri)
3. [Ön Kurulum](#-ön-kurulum)
4. [Kurulum Adımları](#-kurulum-adımları)
5. [Süper Ajan Yetenekleri](#-süper-ajan-yetenekleri)
6. [Kullanım Örnekleri](#-kullanım-örnekleri)
7. [Sorun Giderme](#-sorun-giderme)
8. [Mimari](#-mimari)
9. [Güvenlik](#-güvenlik)

---

## ✨ Özellikler Özeti

OpenWorld, bilgisayarınızda çalışan **gerçek bir süper ajan'dır**. Sadece finansal işlemler (ödeme, kart, transfer) engellenmiştir - gerisi tamamen sizin kontrolünüzdedir!

### 🚀 70+ Yerleşik Araç

| Kategori | Araç Sayısı | Örnekler |
|----------|-------------|----------|
| **Ekran Kontrolü** | 12 | Screenshot, tıklama, yazı yazma, sürükle-bırak |
| **Ses** | 4 | Kayıt, çalma, metin-ses |
| **Webcam** | 3 | Fotoğraf, video kaydı |
| **Dosya Sistemi** | 7 | Tüm disk erişimi, silme, taşıma, arama |
| **ZIP/Arşiv** | 5 | ZIP/TAR oluşturma/çıkarma |
| **PDF** | 4 | Okuma, oluşturma, birleştirme, bölme |
| **Word** | 3 | DOCX oluşturma/okuma/düzenleme |
| **Excel** | 3 | XLSX oluşturma/okuma/düzenleme |
| **Kod Analiz** | 3 | Proje analizi, pattern arama |
| **VS Code** | 1 | Dosya/klasör açma |
| **Sistem** | 6 | CPU/RAM bilgisi, process kontrolü |
| **USB** | 2 | Cihaz listeleme, güvenli çıkarma |
| **Ağ** | 3 | Ping, network bilgisi |
| **OCR** | 2 | Ekran/görüntüden metin okuma |
| **Windows** | 5 | Pencere yönetimi, kilit, kapatma |
| **Shell** | 1 | Tam PowerShell/Bash erişimi |
| **Diyalog** | 3 | Uyarı, onay, giriş pencereleri |
| **Görev/Takvim** | 5 | Planlama araçları |
| **E-posta** | 2 | Gmail/Outlook okuma |
| **Web** | 3 | Haber, web sayfası çekme, araştırma |

**Toplam: 70+ Araç!**

---

## 💻 Sistem Gereksinimleri

### Minimum
- Windows 10/11 (64-bit)
- 8 GB RAM
- 10 GB boş disk alanı
- Python 3.11+
- Node.js 20+

### Önerilen
- Windows 11
- 16 GB+ RAM
- 20 GB+ boş disk (modeller için)
- GPU (CUDA destekli - opsiyonel ama önerilir)
- Mikrofon ve Webcam (ses/görüntü özellikleri için)

---

## ✅ Ön Kurulum

### Adım 1: Python 3.11+ Kurulumu

**İndir:** https://python.org/downloads

```
☑️ Add Python to PATH (MUTLAKA işaretleyin!)
☑️ tcl/tk and IDLE
```

**Doğrulama:**
```powershell
python --version
# Python 3.11.x veya üstü
```

### Adım 2: Node.js 20+ Kurulumu

**İndir:** https://nodejs.org (LTS sürümü)

**Doğrulama:**
```powershell
node --version
# v20.x.x
```

### Adım 3: Ollama Kurulumu

**İndir:** https://ollama.com/download

**Doğrulama:**
```powershell
ollama --version
```

### Adım 4: Tesseract OCR Kurulumu (Opsiyonel ama Önerilir)

OCR (ekrandan metin okuma) için gerekli:

**İndir:** https://github.com/UB-Mannheim/tesseract/wiki

Kurulum sırasında "Add to PATH" seçeneğini işaretleyin.

---

## 🚀 Kurulum Adımları

### 5. Repository'yi İndir

```powershell
git clone https://github.com/AhmetDemiroglu/OpenWorld.git
cd OpenWorld
```

### 6. Launcher'ı Çalıştır

```powershell
python launcher.py
```

### 7. Kurulum Butonuna Bas

```
[⚙ Kurulum] → 5-10 dakika bekleyin
```

Bu işlem şunları kurar:
- Python sanal ortamı (`.venv/`)
- 30+ Python paketi
- Node.js bağımlılıkları
- Frontend build

### 8. Model İndir

Terminal'de:
```powershell
ollama pull qwen3.5:9b-q4_K_M
```

Veya Launcher'dan: **[Model Çek]** butonu

### 9. Başlat

```
[Kaydet] → [Başlat] → [Arayüz]
```

**Web Arayüzü:** http://127.0.0.1:8000

---

## 🤖 Süper Ajan Yetenekleri

### 🖥️ 1. EKRAN KONTROLÜ (Gör ve Etkile)

Ajanınız ekranınızı görebilir ve kontrol edebilir!

**Screenshot (Ekran Görüntüsü):**
```
"Masaüstümün ekran görüntüsünü al"
"Şu web sayfasının görüntüsünü al: https://github.com"
"Ekranın sol üst köşesini (0,0,500,500) görüntüle"
```

**Görüntü Tanıma ve Tıklama:**
```
"Ekranda Chrome ikonunu bul"
"Şu koordinata (100, 200) tıkla"
"Notepad'i aç"
```

**Otomasyon:**
```
"Şunu yaz: Merhaba Dünya"
"Enter'a bas"
"Ctrl+S kısayolunu çalıştır"
"Fareyi (500, 300) konumuna götür ve sürükle"
"Sayfayı aşağı kaydır"
```

**Araçlar:**
- `screenshot_desktop` - Masaüstü görüntüsü
- `screenshot_webpage` - Web sayfası görüntüsü  
- `find_image_on_screen` - Görüntü ara
- `click_on_screen` - Tıklama
- `type_text` - Yazı yazma
- `press_key` - Tuşa basma
- `mouse_move` - Fare hareketi
- `drag_to` - Sürükle-bırak
- `scroll` - Kaydırma
- `hotkey` - Kısayol (ctrl+c, alt+tab, win+r)

---

### 🎤 2. SES KONTROLÜ (Dinle ve Konuş)

**Ses Kaydı:**
```
"10 saniye ses kaydet"
"Mikrofonu aç ve kayda başla"
"Kaydı durdur ve kaydet"
```

**Metin-Ses (TTS):**
```
"Merhaba, ben OpenWorld Assistant'ı sesli söyle"
"Bu metni sesli oku"
```

**Ses Çalma:**
```
"Şu ses dosyasını çal"
```

**Araçlar:**
- `start_audio_recording` - Kayda başla
- `stop_audio_recording` - Kaydet
- `play_audio` - Ses çal
- `text_to_speech` - Metni sese çevir

---

### 📷 3. WEBCAM KONTROLÜ

**Fotoğraf:**
```
"Webcam'den fotoğrafımı çek"
"Bir selfie çek ve kaydet"
```

**Video:**
```
"5 saniyelik video kaydet"
"Webcam'den 30 saniyelik video çek"
```

**Araçlar:**
- `list_cameras` - Kameraları listele
- `webcam_capture` - Fotoğraf çek
- `webcam_record_video` - Video kaydet

---

### 📁 4. DOSYA SİSTEMİ (Tam Erişim)

Tüm diske erişim! Sadece kritik Windows dosyaları korunur.

**Dosya İşlemleri:**
```
"C:\Users'deki tüm PDF'leri listele"
"Masaüstüne yeni bir klasör oluştur"
"C:\Temp klasörünü sil"
"Dosyayı şuradan şuraya taşı"
"Tüm diskte 'password' geçen dosyaları ara"
```

**Dosya Okuma/Yazma:**
```
"C:\log.txt dosyasını oku"
"Masaüstüne notlar.txt oluştur, içine şunu yaz..."
"Dosyanın sonuna şunu ekle..."
```

**Araçlar:**
- `list_directory` - Dizin listele (recursive)
- `read_file` - Dosya oku
- `write_file` - Dosya yaz
- `delete_file` - Sil (confirm ile)
- `copy_file` - Kopyala
- `move_file` - Taşı
- `search_files` - Ara

---

### 📦 5. ZIP / ARŞİV

**ZIP Oluşturma:**
```
"Belgeler klasörünü yedekle.zip yap"
"Şu dosyayı şifreli zip olarak kaydet"
```

**ZIP Çıkarma:**
```
"Yedekle.zip'i çıkar"
"Şifreli arşivi aç (şifre: 1234)"
```

**TAR:**
```
"Linux formatında .tar.gz oluştur"
```

**Araçlar:**
- `create_zip` - ZIP oluştur
- `extract_zip` - ZIP çıkar
- `list_zip_contents` - İçeriği listele
- `create_tar` - TAR oluştur
- `extract_tar` - TAR çıkar

---

### 📄 6. PDF YÖNETİMİ

**PDF Okuma:**
```
"Şu PDF'in içeriğini oku"
"Sadece 1-5 sayfalarını göster"
```

**PDF Oluşturma:**
```
"Bu raporu PDF olarak kaydet"
```

**PDF Birleştirme/Bölme:**
```
"3 PDF'i tek dosyada birleştir"
"PDF'i her 10 sayfada bir böl"
```

**Araçlar:**
- `read_pdf` - PDF oku
- `create_pdf` - PDF oluştur
- `merge_pdfs` - Birleştir
- `split_pdf` - Böl

---

### 📝 7. WORD (DOCX)

**Word Oluşturma:**
```
"Rapor.docx oluştur, başlık: 'Yıllık Rapor', 
 içindekiler: Giriş, Sonuç"
"Tablo içeren Word belgesi oluştur"
```

**Word Okuma:**
```
"Şu Word dosyasını oku"
"Belgelerim.docx içeriğini göster"
```

**Word Düzenleme:**
```
"Mevcut Word dosyasına yeni bölüm ekle"
```

**Araçlar:**
- `create_docx` - Word oluştur
- `read_docx` - Word oku
- `add_to_docx` - Ekleme yap

---

### 📊 8. EXCEL (XLSX)

**Excel Oluşturma:**
```
"Veriler.xlsx oluştur, sütunlar: Ad, Soyad, Yaş
 satırlar: [...]"
```

**Excel Okuma:**
```
"Şu Excel dosyasını oku"
"İlk 100 satırı göster"
```

**Excel Düzenleme:**
```
"Excel'e yeni satırlar ekle"
"Yeni sayfa oluştur"
```

**Araçlar:**
- `create_excel` - Excel oluştur
- `read_excel` - Excel oku
- `add_to_excel` - Veri ekle

---

### 💻 9. KOD ve PROJE ANALİZİ

**Kod Analizi:**
```
"main.py dosyasını analiz et (satır sayısı, fonksiyonlar)"
"Projemde 'TODO' yazan yerleri bul"
"Tüm Python dosyalarını analiz et ve raporla"
```

**Proje Analizi:**
```
"Projemin kod yapısını analiz et ve markdown raporu oluştur"
"Hangi dilde kaç satır kod var?"
```

**VS Code Açma:**
```
"Bu projeyi VS Code'da aç"
"Şu dosyayı VS Code'da aç"
"Bu klasörü VS Code'da aç"
```

**Araçlar:**
- `analyze_code` - Kod analizi
- `find_code_patterns` - Pattern arama
- `analyze_project_code` - Proje analizi
- `open_in_vscode` - VS Code'da aç
- `open_folder` - Klasör aç
- `create_folder` - Klasör oluştur

---

### 🖥️ 10. SİSTEM YÖNETİMİ

**Sistem Bilgisi:**
```
"CPU ve RAM kullanımını göster"
"Disk doluluk oranını kontrol et"
"Sistem bilgilerini getir"
```

**Process Yönetimi:**
```
"Çalışan uygulamaları listele"
"Chrome process'lerini sonlandır"
"PID 1234 olan uygulamayı kapat"
```

**Güç Yönetimi:**
```
"Bilgisayarı 1 saat sonra kapat"
"Yeniden başlat"
"Ekranı kilitle"
```

**Araçlar:**
- `get_system_info` - Sistem bilgisi
- `list_processes` - Process listele
- `kill_process` - Process sonlandır
- `shutdown_system` - Kapat/yeniden başlat
- `lock_workstation` - Ekran kilidi

---

### 🪟 11. PENCERE YÖNETİMİ (Windows)

**Pencere Kontrolü:**
```
"Açık pencereleri listele"
"Chrome penceresini öne getir"
"Tüm pencereleri simge durumuna küçült"
"Notepad penceresini aktif et"
```

**Araçlar:**
- `get_window_list` - Pencereleri listele
- `activate_window` - Öne getir
- `minimize_all_windows` - Hepsini küçült

---

### 🔌 12. USB YÖNETİMİ

**USB Kontrolü:**
```
"Bağlı USB cihazlarını listele"
"E: sürücüsünü güvenli çıkar"
```

**Araçlar:**
- `list_usb_devices` - Listele
- `eject_usb_drive` - Güvenli çıkar

---

### 👁️ 13. OCR (METİN TANIMA)

**Ekrandan Metin Okuma:**
```
"Ekrandaki şu bölgedeki metni oku"
"Şu görüntüdeki yazıyı çıkar"
"Ekran görüntüsündeki metni kopyala"
```

**Araçlar:**
- `ocr_screenshot` - Ekrandan oku
- `ocr_image` - Görüntüden oku

---

### 💬 14. DİYALOG PENCERELERİ

**Kullanıcı Etkileşimi:**
```
"Kullanıcıya uyarı göster: 'İşlem tamamlandı'"
"Onay iste: 'Silmek istiyor musunuz?'"
"Giriş iste: 'Adınız nedir?'"
```

**Araçlar:**
- `alert` - Uyarı göster
- `confirm` - Onay al (Evet/Hayır)
- `prompt` - Girdi al

---

### 🐚 15. TAM SHELL ERİŞİMİ

**PowerShell/Bash:**
```
"ipconfig komutunu çalıştır"
"Get-Process | Select-Object -First 10"
"format D: /FS:NTFS /Q"
"regedit /s ayarlar.reg"
"Tüm PowerShell komutları serbest!"
```

**Not:** Sadece finansal komutlar engellenir. Gerisi serbest!

**Araçlar:**
- `execute_command` - Komut çalıştır
- `run_shell` - Alternatif

---

### 📅 16. GÖREV ve TAKVİM

**Görev Yönetimi:**
```
"Yeni görev ekle: Yarın saat 14:00'te toplantı"
"Tüm görevleri listele"
"Görev #123'i tamamlandı olarak işaretle"
```

**Takvim:**
```
"15 Mart için doğum günü etkinliği ekle"
"Yaklaşan etkinlikleri göster"
```

**Araçlar:**
- `add_task` - Görev ekle
- `list_tasks` - Listele
- `complete_task` - Tamamla
- `add_calendar_event` - Etkinlik ekle
- `list_calendar_events` - Göster

---

### 📧 17. E-POSTA

**Gmail/Outlook:**
```
"Gmail'deki son 5 okunmamış maili özetle"
"Outlook gelen kutusunu kontrol et"
```

**Araçlar:**
- `check_gmail_messages` - Gmail oku
- `check_outlook_messages` - Outlook oku

---

### 🌐 18. WEB ve ARAŞTIRMA

**Web:**
```
"Bugünün haberlerini getir"
"Şu web sayfasının içeriğini çek"
"Yapay zeka trendleri hakkında araştırma yap ve rapor yaz"
```

**Araçlar:**
- `search_news` - Haber ara
- `fetch_web_page` - Sayfa çek
- `research_and_report` - Araştırma
- `create_email_draft` - E-posta taslağı

---

## 💡 Kullanım Örnekleri

### Karmaşık Görevler

**Örnek 1: Otomatik Rapor Hazırlama**
```
"1. Ekran görüntüsü al
 2. Webcam'den fotoğraf çek
 3. Sistem bilgilerini topla
 4. Tüm bunları Word belgesinde birleştir
 5. Word'ü PDF'e çevir
 6. PDF'i zip'le ve masaüstüne kaydet"
```

**Örnek 2: Proje Analizi**
```
"1. C:\Projem klasörünü analiz et
 2. Hangi dilde kaç satır kod var bul
 3. Sonuçları Excel'e yaz
 4. Excel'i aç"
```

**Örnek 3: Dosya Yönetimi**
```
"1. Masaüstündeki tüm PDF'leri bul
 2. Hepsini birleştir
 3. Birleşik dosyayı zip'le
 4. ZIP'i şifrele"
```

**Örnek 4: Otomasyon**
```
"1. Notepad aç
 2. 'Merhaba Dünya' yaz
 3. Ctrl+S ile kaydet
 4. Dosyayı kapat"
```

---

## 🔧 Sorun Giderme

### "Python bulunamadı"
Python kurulumunda "Add to PATH" işaretlememişsiniz. Yeniden kurun.

### "Tesseract not found"
OCR kullanmak için Tesseract kurulu olmalı: https://github.com/UB-Mannheim/tesseract/wiki

### "ChromeDriver hatası"
Web screenshot için Chrome tarayıcısı kurulu olmalı.

### "Mikrofon/Webcam erişim yok"
Windows Gizlilik ayarlarından mikrofon ve kamera izinlerini verin.

### "DLL Load Failed" (PyAudio)
Windows'ta PyAudio kurulumu sorunlu olabilir:
```powershell
pip install pipwin
pipwin install pyaudio
```

---

## 🏗️ Mimari

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenWorld Super Agent                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Web UI     │    │  Telegram    │    │   REST API   │  │
│  │   (React)    │◄──►│    Bot       │◄──►│  (FastAPI)   │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                 │           │
│                         ┌───────────────────────┘           │
│                         ▼                                   │
│                ┌──────────────────┐                        │
│                │   Agent Core     │                        │
│                └────────┬─────────┘                        │
│                         │                                   │
│     ┌───────────────────┼───────────────────┐              │
│     ▼                   ▼                   ▼              │
│  ┌───────┐        ┌──────────┐       ┌──────────┐        │
│  │  LLM  │        │  Memory  │       │  Tools   │        │
│  │Ollama │        │(Session) │       │ (70+ Adt)│        │
│  └───────┘        └──────────┘       └──────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔒 Güvenlik

### Tek Yasak: Finansal İşlemler

**Engellenen:**
- ❌ Kredi kartı işlemleri
- ❌ Para transferi (havale, EFT, wire)
- ❌ Ödeme yapma/alma
- ❌ Satın alma (online checkout)
- ❌ Bitcoin/kripto transferi

### Serbest Bölge (TAMAMEN AÇIK)

**Serbest:**
- ✅ Dosya silme/formatlama
- ✅ Sistem dosyalarını düzenleme
- ✅ Kayıt defteri değişikliği
- ✅ Uygulama kapatma
- ✅ Bilgisayarı kapatma/yeniden başlatma
- ✅ Tüm PowerShell/Bash komutları
- ✅ Ekran/webcam erişimi
- ✅ Ses kaydı
- ✅ USB yönetimi

**Prensip:** Kullanıcı kendi bilgisayarında ne isterse yapabilir. Ajan sorgusuz sualsiz yerine getirir.

---

## 📦 Yeni Paketler (70+ Araç İçin)

```txt
# Ekran/Otomasyon
pillow, selenium, webdriver-manager, playwright, pyautogui

# Ses
pyaudio, sounddevice, scipy

# Webcam
opencv-python

# USB
pyusb

# OCR
pytesseract

# PDF
PyPDF2, reportlab

# Word/Excel
python-docx, openpyxl

# Sistem
psutil, numpy
```

---

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun
3. Değişikliklerinizi commit edin
4. Push edin
5. Pull Request açın

---

## 📜 Lisans

MIT License
