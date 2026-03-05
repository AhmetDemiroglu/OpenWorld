<div align="center">

# OpenWorld Local Agent

**Gerçek Bir Süper Ajan - Yerel Yapay Zeka Asistanı**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Modern%20Web%20Framework-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB.svg)](https://react.dev)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange.svg)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Yerel yapay zeka asistanınız - 4 katmanlı güvenlik ile*

</div>

---

## İçindekiler

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

OpenWorld, bilgisayarınızda çalışan **gerçek bir süper ajandır**. 4 katmanlı güvenlik sistemi ile tehlikeli işlemler kontrol altında, günlük görevleriniz tamamen serbesttir.

### 95+ Yerleşik Araç + Akıllı Tool Seçimi

| Kategori | Araç Sayısı | Örnekler |
|----------|-------------|----------|
| **Ekran Kontrolü** | 21 | Screenshot, tıklama, yazı yazma, sürükle-bırak, OCR, pencere yönetimi |
| **Ses** | 4 | Kayıt, çalma, metin-ses dönüşümü |
| **Webcam** | 3 | Fotoğraf, video kaydı, kamera listeleme |
| **Dosya Sistemi** | 7 | Okuma, yazma, silme, taşıma, arama, klasör işlemleri |
| **ZIP/Arşiv** | 5 | ZIP/TAR oluşturma/çıkarma, şifreleme |
| **PDF** | 4 | Okuma, oluşturma, birleştirme, bölme |
| **Word/Excel** | 6 | DOCX/XLSX oluşturma/okuma/düzenleme |
| **Kod & Git** | 11 | Git işlemleri, kod analizi, VS Code entegrasyonu, test çalıştırma |
| **Sistem** | 6 | CPU/RAM bilgisi, process kontrolü, ağ, shell erişimi |
| **USB** | 2 | Cihaz listeleme, güvenli çıkarma |
| **Görev/Takvim** | 5 | Planlama, görev takibi, takvim yönetimi |
| **E-posta** | 3 | Gmail/Outlook okuma, taslak oluşturma |
| **Web & Araştırma** | 5 | Haber arama, web sayfası çekme, detaylı araştırma raporu |
| **Not Defteri** | 6 | Karmaşık görevleri adımlara bölme, checkpoint'lerle devam etme |
| **Hafıza** | 3 | Uzun süreli hafıza, kullanıcı tercihleri hatırlama |
| **Arka Plan Servisleri** | 5 | Email monitör, hava durumu, GitHub trending, teknoloji haberleri, özel uyarılar |

**Toplam: 100+ Araç** (her istekte en fazla 20 tanesi akıllı seçimle gönderilir)

### Medya Otomatik Teslimi

Ekran görüntüleri, ses kayıtları, webcam fotoğrafları ve videolar **otomatik olarak teslim edilir**:

- Web arayüzünde: Chat'te direkt preview + indirme linki
- Telegram'da: Medya dosyaları otomatik olarak gönderilir
- Tüm medya `data/media/` klasöründe tek yerde saklanır

### Akıllı Tool Seçimi (NLP Semantic Routing)

95+ aracın tamamı her istekte modele gönderilmez. Kullanıcı mesajı `sentence-transformers` (all-MiniLM-L6-v2) kullanılarak vektörlere dönüştürülür ve cosine similarity ile **en ilgili maksimum 15-20 araç** dinamik olarak seçilir:

- "ekran görüntüsünü OCR ile oku" → `screenshot_desktop`, `ocr_image` vb. anlamsal olarak yüksek puan alan araçlar LLM'e sunulur.
- Vektör tabanlı bu NLP Intent Filtering sayesinde LLM context penceresi şişmez ve token tasarrufu sağlanır.

### ⚡ Hızlı Mod (Düşünme Yok)

Screenshot, webcam gibi basit işlemlerde **düşünme aşaması atlanır**:
- Ekran görüntüsü: Direkt çalıştırılır (~1 saniye)
- Webcam fotoğraf: Anında çekilir
- Sistem bilgisi: Hemen döndürülür

### Not Defteri Sistemi (Checkpoint'ler)

Karmaşık görevler için **otomatik görev parçalama**:
- Uzun araştırmalar adımlara bölünür
- Her adım tamamlandığında checkpoint kaydedilir
- Timeout veya kesinti olursa **"devam et"** yazarak kaldığınız yerden devam edilir

---

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

OCR (ekrandan metin okuma) için gerekli. Vision özelliği olmayan modellerde bu adım zorunludur.

**İndir:** https://github.com/UB-Mannheim/tesseract/wiki

**Kurulum dosyası (önerilen):**
`C:\Program Files\Tesseract-OCR\tesseract.exe`

**PATH'e eklenecek dizin (tam olarak):**
`C:\Program Files\Tesseract-OCR`

**Launcher ayarı:**
Launcher > `OCR / Tesseract` alanındaki `Tesseract Yolu` değerini
`C:\Program Files\Tesseract-OCR\tesseract.exe` yapıp `Kaydet` düğmesine basın.

**OCR gereken başlıca işlemler:**
- Görselden metin okuma
- IDE onay penceresi izleme / kabul etme
- Ekran üstündeki metinleri analiz etme

**Doğrulama:**
```powershell
tesseract --version
```

---

## Kurulum Adımları

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
- Python sanal ortamı (`backend/.venv/`)
- 30+ Python paketi
- Node.js bağımlılıkları
- Frontend build

### 8. Model İndir

Terminal'de:
```powershell
ollama pull qwen3.5:9b-q4_K_M
```

Veya Launcher'dan: **[Model Çek]** butonu

Not: Bu sürümde LLM motoru yalnızca `ollama` olarak çalışır.

### 9. Başlat

```
[Kaydet] → [Başlat] → [Arayüz]
```

**Web Arayüzü:** http://127.0.0.1:8000

---

## Süper Ajan Yetenekleri

### 1. EKRAN KONTROLÜ (Gör ve Etkile)

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

**OCR (Metin Tanıma):**
```
"Ekrandaki şu bölgedeki metni oku"
"Şu görüntüdeki yazıyı çıkar"
```

**Araçlar:**
- `screenshot_desktop` - Masaüstü görüntüsü
- `screenshot_webpage` - Web sayfası görüntüsü 
- `ocr_screenshot` - Ekrandan metin oku
- `ocr_image` - Görüntüden metin oku
- `find_image_on_screen` - Görüntü ara
- `click_on_screen` - Tıklama
- `type_text` - Yazı yazma
- `press_key` - Tuşa basma
- `mouse_move` - Fare hareketi
- `drag_to` - Sürükle-bırak
- `scroll` - Kaydırma
- `hotkey` - Kısayol (ctrl+c, alt+tab, win+r)
- `get_window_list` - Pencereleri listele
- `activate_window` - Pencere öne getir
- `minimize_all_windows` - Tüm pencereleri küçült
- `lock_workstation` - Ekran kilidi
- `shutdown_system` - Bilgisayarı kapat/yeniden başlat

---

### 2. SES KONTROLÜ (Dinle ve Konuş)

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

### 3. WEBCAM KONTROLÜ

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

### 4. DOSYA SİSTEMİ

Dosya okuma, yazma, silme, taşıma ve arama. Silme işlemleri onay gerektirir.

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

### 5. ZIP / ARŞİV

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

### 6. PDF YÖNETİMİ

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

### 7. WORD (DOCX)

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

### 8. EXCEL (XLSX)

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

### 9. KOD ve PROJE ANALİZİ (Git + Uzaktan AI Kodlama)

**Git İşlemleri:**
```
"Git status kontrol et"
"Son commit'leri göster"
"Değişiklikleri diff'le"
"Yeni branch oluştur"
"Commit yap: 'Bug fix'"
```

**Kod Analizi:**
```
"main.py dosyasını analiz et (satır sayısı, fonksiyonlar)"
"Projemde 'TODO' yazan yerleri bul"
"Tüm Python dosyalarını analiz et ve raporla"
```

**VS Code Açma:**
```
"Bu projeyi VS Code'da aç"
"Şu dosyayı VS Code'da aç"
```

**Test Çalıştırma:**
```
"Testleri çalıştır"
"pytest ile testleri koş"
```

#### Uzaktan AI Kodlama (Remote AI Coding)

OpenWorld'ün en güçlü özelliklerinden biri: **dışarıdayken bile bilgisayarınızdaki VS Code'u açıp, AI kod asistanlarını (KimiCode, Claude Code, Codex, Copilot) uzaktan komutlandırabilirsiniz.**

**Nasıl Çalışır?**

Telegram'dan tek bir mesajla:
1. VS Code belirttiğiniz proje klasörüyle açılır
2. Seçtiğiniz AI extension'ın chat paneli otomatik açılır
3. Mesajınız (Türkçe dahil) yazılır ve gönderilir
4. Ekran görüntüsü ile sonucu takip edersiniz

**Desteklenen AI Extension'lar:**

| Extension | Kısayol | Kullanım |
|-----------|---------|----------|
| **KimiCode** | Command Palette | `extension="kimicode"` |
| **GitHub Copilot** | `Ctrl+Shift+I` | `extension="copilot"` |
| **Claude Code** | Command Palette | `extension="claudecode"` |
| **Codex** | Command Palette | `extension="codex"` |

**Kullanım Örnekleri (Telegram'dan):**
```
"OpenWorld klasörünü VS Code ile aç, KimiCode'a 'auth modülünü refactor et' yaz"
"Projeyi VS Code'da aç, Claude Code'a 'bug var, login çalışmıyor' sor"
"Masaüstündeki projeyi VS Code ile aç, Codex'e 'testleri çalıştır ve düzelt' de"
```

**Tam Uzaktan Kontrol Akışı:**
```
1. Telegram: "VS Code'da projeyi aç, KimiCode'a 'API endpoint ekle' yaz"
2. Ajan: VS Code'u açar → KimiCode panelini açar → mesajı yazar
3. Telegram: "Ekran görüntüsü al" → Sonucu görürsünüz
4. Telegram: "Devam et, şimdi test yaz" → Yeni talimat gönderir
```

> **Not:** AI extension'lar ilk açılışta 30-40 saniye başlatma süresi olabilir. Sonraki kullanımlarda ~8 saniyede hazır olur.

**Araçlar:**
- `git_status`, `git_diff`, `git_log`, `git_commit`, `git_branch`
- `find_symbols` - Sembol bul
- `code_search` - Kodda ara
- `refactor_rename` - Refactor
- `run_tests` - Test çalıştır
- `vscode_command` - VS Code komutu (dosya aç, terminal, diff, **AI extension chat**)
- `claude_code_ask` - Claude Code CLI entegrasyonu
- `analyze_code` - Kod analizi
- `find_code_patterns` - Pattern ara
- `analyze_project_code` - Proje analizi

---

### 10. SİSTEM YÖNETİMİ

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

**Shell Erişimi:**
```
"ipconfig komutunu çalıştır"
"Get-Process | Select-Object -First 10"
```

**Araçlar:**
- `get_system_info` - Sistem bilgisi
- `list_processes` - Process listele
- `kill_process` - Process sonlandır
- `shutdown_system` - Kapat/yeniden başlat
- `execute_command` - PowerShell/Bash komut
- `network_info` - Ağ bilgisi
- `ping_host` - Ping at

---

### 11. USB YÖNETİMİ

**USB Kontrolü:**
```
"Bağlı USB cihazlarını listele"
"E: sürücüsünü güvenli çıkar"
```

**Araçlar:**
- `list_usb_devices` - Listele
- `eject_usb_drive` - Güvenli çıkar

---

### 12. OCR (METİN TANIMA)

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

### 13. DİYALOG PENCERELERİ

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

### 14. GÖREV ve TAKVİM

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

### 15. E-POSTA

**Gmail/Outlook:**
```
"Gmail'deki son 5 okunmamış maili özelle"
"Outlook gelen kutusunu kontrol et"
```

**Araçlar:**
- `check_gmail_messages` - Gmail oku
- `check_outlook_messages` - Outlook oku
- `create_email_draft` - Taslak oluştur

---

### 16. WEB ve ARAŞTIRMA

**Web:**
```
"Bugünün haberlerini getir"
"Şu web sayfasının içeriğini çek"
"Yapay zeka trendleri hakkında araştırma yap ve rapor yaz"
```

**Detaylı Araştırma:**
```
"İran-ABD ilişkilerini detaylı araştır ve rapor hazırla"
"Konu A ve Konu B'yi karşılaştır"
```

**Araçlar:**
- `search_news` - Haber ara
- `fetch_web_page` - Sayfa çek
- `research_and_report` - Detaylı araştırma raporu (senkron, sonucu chat'te gösterir)
- `research_async` - **Otonom arka plan araştırması** — anında "başladı" yanıtı döner, ~3-8 dk sonra Telegram'a özet mesaj + PDF rapor gönderir
- `compare_topics` - İki konuyu karşılaştır
- `research_note` - Araştırma notu al

---

### 17. NOT DEFTERİ SİSTEMİ (Checkpoint'ler)

Karmaşık görevleri **otomatik parçalama** ve **kaldığınız yerden devam etme**:

```
"İran-ABD savaşının küresel finans piyasalarına etkisini detaylı araştır"
```

**Otomatik Akış:**
1. `notebook_create` - Görev planı oluşturulur
2. Her adım `notebook_complete_step` ile işaretlenir
3. Timeout olursa → "**Devam et**" yazarak devam edersiniz
4. `notebook_status` - Durumu kontrol et
5. `notebook_list` - Tüm not defterlerini gör

**Araçlar:**
- `notebook_create` - Not defteri oluştur
- `notebook_add_note` - Not ekle
- `notebook_complete_step` - Adımı tamamla
- `notebook_status` - Durum kontrolü
- `notebook_list` - Listele
- `notebook_add_step` - Yeni adım ekle

---

### 18. HAFIZA SİSTEMİ

Uzun süreli hafıza ve kullanıcı tercihleri:

```
"Benim adım Ahmet, bunu hatırla"
"Tercihim koyu tema"
"Önceki görüşmemizde ne konuşmuştuk?"
```

**Araçlar:**
- `memory_store` - Bilgi kaydet
- `memory_recall` - Bilgi hatırla
- `memory_stats` - Hafıza istatistikleri

---

### ✈️ 19. TELEGRAM ENTEGRASYONU

Telegram bot üzerinden ajanla sohbet edin. Medya dosyaları (ekran görüntüleri, ses, video) otomatik olarak Telegram'a gönderilir.

**Nasıl Çalışır:**

- Telegram bot'a mesaj yazarsınız, ajan cevap verir
- Ajan bir ekran görüntüsü veya ses kaydı ürettiğinde, otomatik olarak Telegram'a iletilir
- **Görseller OCR ile okunur** - Ekran görüntüsü gönderip "bunu analiz et" diyebilirsiniz
- Ayrı bir tool yoktur — medya pipeline'ı otomatiktir

**Kullanım Örnekleri (Telegram'dan yazın):**
```
"Masaüstümün ekran görüntüsünü al"
"GitHub'ın screenshot'ını al"
"5 saniyelik ses kaydı yap"
"[Ekran görüntüsü gönder] Bunu incele"
```

**Kurulum:** `.env` dosyasında `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_ALLOWED_USER_ID` ayarlanmalı

---

### 20. ARKA PLAN SERVİSLERİ (Smart Life Assistant)

Uygulama çalıştığı sürece arka planda aktif olan akıllı asistan servisleri. Hiçbir mesaj göndermenize gerek yok — otomatik çalışır ve önemli durumları Telegram'dan bildirir.

#### E-posta Monitör

Her 15 dakikada bir Gmail'deki **okunmamış** mailleri tarar, Ollama LLM ile önem derecesi belirler:

| Derece | Açıklama | Bildirim |
|--------|----------|----------|
| **KRİTİK** | İş ilanı (Frontend/İzmir/remote), AI model deprecation, güvenlik | ✅ Telegram |
| **ÖNEMLİ** | Kişisel yazışmalar, proje güncellemeleri | ✅ Telegram |
| ⚪ **NORMAL** | Bültenler, düzenli güncellemeler | Sessiz |
| **SPAM** | Reklam, pazarlama, tekrar eden ilanlar | Sessiz |

**Duplicate Filtreleme:** Aynı mail ID + %85+ konu benzerliği olan mailler otomatik elenir. 7 gün boyunca hatırlar.

#### Hava Durumu

Her sabah (07:00-09:00) şehrinizin hava durumunu ve giyim önerisini Telegram'dan gönderir.

#### GitHub Trending

6 saatte bir JavaScript, TypeScript ve Python'daki trending repoları izler, yenilerini bildirir.

#### Teknoloji Haberleri

4 saatte bir AI model değişiklikleri, framework güncellemeleri, breaking change'leri takip eder.

#### Özel Uyarılar

30 dakikada bir `.env`'deki `BG_CUSTOM_ALERTS` terimleriyle haber arar (ör: `izmir frontend,gemini api`).

**Konfigürasyon (`.env`):**
```
BG_EMAIL_MONITOR=true # Email monitör aktif/pasif
BG_EMAIL_INTERVAL_MIN=15 # Tarama aralığı (dakika)
BG_SMART_ASSISTANT=true # Hava durumu, GitHub, teknoloji haberleri
BG_WEATHER_CITY=Izmir # Hava durumu şehri
BG_CUSTOM_ALERTS= # Özel aramalar (virgülle ayrılmış)
```

**Arka Plan Motoru:** Arka plan servisleri artık `APScheduler` ile kurumsal standartlarda, thread-blocking yaratmadan Cron-benzeri çalışır. Durumlar `SQLite` tabanlarına (örn. `email_seen_log`, `smart_assistant_state`) kaydedilir.

**Durum Kontrolü:**
```
GET http://127.0.0.1:8000/services/status
```

---

## Kullanım Örnekleri

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

**Örnek 5: Medya (Otomatik Teslim)**
```
"Masaüstümün ekran görüntüsünü al"
"Webcam'den fotoğraf çek"
"10 saniyelik ses kaydı yap"
```

**Örnek 6: Checkpoint'li Uzun İş**
```
"İran-ABD savaşının küresel finans piyasalarına etkisini detaylı araştır"
[Timeout olursa]
"Devam et"
```

---

## Sorun Giderme

### "Python bulunamadı"
Python kurulumunda "Add to PATH" işaretlememişsiniz. Yeniden kurun.

### "Tesseract not found"
1. Tesseract'ı `C:\Program Files\Tesseract-OCR` klasörüne kurun.
2. `C:\Program Files\Tesseract-OCR\tesseract.exe` dosyasının oluştuğunu doğrulayın.
3. Launcher > `OCR / Tesseract` bölümünde `Tesseract Yolu` alanına bu tam yolu yapıştırıp `Kaydet` düğmesine basın.
4. PATH için eklenecek dizin yalnızca `C:\Program Files\Tesseract-OCR` olmalıdır.
5. Yeni terminal açıp `tesseract --version` komutunu çalıştırın.
6. Gerekirse launcher'ı yeniden başlatın.
7. İndirme: https://github.com/UB-Mannheim/tesseract/wiki

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

## Mimari

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
│                ┌──────────────────┐    ┌─────────────────┐ │
│                │   Agent Core     │◄──►│ APScheduler     │ │
│                │ (Semantic Router)│    │ (BG Services)   │ │
│                └────────┬─────────┘    └─────────────────┘ │
│                         │                                   │
│     ┌───────────────────┼───────────────────┐              │
│     ▼                   ▼                   ▼              │
│  ┌───────┐        ┌───────────┐      ┌──────────┐        │
│  │  LLM  │        │  Memory   │      │  Tools   │        │
│  │Ollama │        │(SQLite +  │      │ (Domains:│        │
│  │       │        │ ChromaDB) │      │ web, sys)│        │
│  └───────┘        └───────────┘      └──────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Bilinen Kısıtlamalar

| Kısıtlama | Açıklama |
|-----------|----------|
| **Çok adımlı GUI otomasyonu** | "VS Code'u aç → KimiCode'a mesaj yaz" gibi zincirleme masaüstü otomasyonları modele bağlıdır. Yerel küçük modeller (Qwen 9B vb.) bu tür çok adımlı planlamada sınırlıdır; tek adımlık araç çağrıları (screenshot al, dosya oku) çok daha güvenilirdir. |
| **LLM model kalitesi** | Araç seçimi ve parametre doğruluğu LLM modeline bağlıdır. Daha büyük modeller (70B+) karmaşık görevlerde daha başarılıdır; küçük modeller basit görevler için optimize edilmiştir. |
| **Timeout'lar** | Telegram üzerinden çok adımlı görevler 2-3 dakikayı aşabilir. Zaman aşımı durumunda `research_async` aracını kullanın — arka planda çalışır, bitince Telegram'a PDF rapor gönderir. |
| **Gmail token yenileme** | Gmail OAuth token'ları periyodik olarak yenilenmeli. Token süresi dolarsa, yenileme otomatik yapılır ama ilk kurulumda manuel OAuth akışı gerekir. |
| **VS Code AI Extension'lar** | KimiCode ve GitHub Copilot tam otomatik desteklenir. Claude Code için hem `claude_code_ask` (CLI, doğrudan) hem de `vscode_command` (VS Code içinden) kullanılabilir. Tüm VS Code etkileşimleri OCR tabanlı onay izleme ile desteklenir. |

---

## Güvenlik

### 4 Katmanlı Güvenlik Modeli

| Katman | Davranış | Örnekler |
| ------ | -------- | -------- |
| **ENGELLENEN** | Her zaman reddedilir | Finansal işlemler (ödeme, transfer, kripto), prompt injection |
| **TEHLİKELİ** | Kullanıcıdan onay ister | Dosya/dizin silme, process sonlandırma, bilgisayarı kapatma, format/diskpart |
| **NORMAL** | Loglanır, çalıştırılır | Dosya yazma, shell komutları, otomasyon, yazılım kurma |
| **GÜVENLİ** | Hemen çalıştırılır | Dosya okuma, sistem bilgisi, screenshot, OCR, web içeriği, ofis belgeleri |

### Bağlam-Duyarlı Policy

**Finansal analiz** ile **finansal işlem** ayrımı:
- ✅ "Finansal piyasalar analizi raporu" → İzin verilir
- ❌ "Para transferi yap" → Engellenir

### Prompt Injection Koruması

- Harici içerikten (web sayfaları, e-postalar, belgeler) gelen talimatlar reddedilir
- Web içeriği okunduktan sonra yüksek etkili araçlar otomatik engellenir (kullanıcı açıkça istemedikçe)
- System prompt değiştirilemez header ile korunur

---

## Bağımlılıklar

```txt
# HTTP/Network/API
fastapi, uvicorn, httpx, aiohttp

# Arka Plan Servisleri & DB
apscheduler, sqlite3

# Memory & NLP Intent Router
chromadb, sentence-transformers

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

## Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun
3. Değişikliklerinizi commit edin
4. Push edin
5. Pull Request açın

---

## Lisans

MIT License
