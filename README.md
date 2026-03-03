<div align="center">

# 🌍 OpenWorld Local Agent

**Kişisel, Gizlilik Odaklı, Yerel Çalışan Yapay Zeka Asistanı**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Modern%20Web%20Framework-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB.svg)](https://react.dev)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange.svg)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ⚠️ ÖNEMLİ: Önce Sistem Gereksinimlerini Kurun!

Bu repository **kaynak kodları** içerir. Klonladıktan sonra kurulum yapmanız gerekir. Önce Python, Node.js ve Ollama kurulumu zorunludur.

> **Sıralama:** Önce Python/Node.js kur → Sonra repoyu klonla → Sonra launcher'ı çalıştır → [Kurulum] butonuna bas

---

## 📋 İçindekiler

- [Sistem Gereksinimleri](#-sistem-gereksinimleri)
- [Ön Kurulum (Zorunlu)](#-ön-kurulum-zorunlu)
- [Uygulama Kurulumu](#-uygulama-kurulumu)
- [Mimari Yapı](#-mimari-yapı)
- [Sorun Giderme](#-sorun-giderme)
- [Özellikler](#-özellikler)

---

## 💻 Sistem Gereksinimleri

### Donanım

| Bileşen | Minimum | Önerilen |
|---------|---------|----------|
| RAM | 8 GB | 16 GB+ |
| Disk (boş alan) | 10 GB | 20 GB+ |
| GPU | Gerekmez | 8 GB VRAM (opsiyonel) |
| İnternet | İlk kurulum için gerekli | Model indirme için |

### İşletim Sistemi

- Windows 10 veya Windows 11 (64-bit)
- Windows PowerShell veya CMD

---

## ✅ Ön Kurulum (Zorunlu)

Uygulamayı çalıştırmadan önce aşağıdaki 3 programı kurmanız zorunludur.

### Adım 1: Python 3.11+ Kurulumu

**1.1. İndirme**

https://python.org/downloads adresine gidin.

**1.2. Kurulum**

İndirilen `.exe` dosyasını çalıştırın ve aşağıdaki adımları takip edin:

```
☑️ Add python.exe to PATH (ALTI ÇİZİLİ - MUTLAKA İŞARETLEYİN)
☑️ Use admin privileges when installing py.exe
☑️ Add Python to environment variables

[Customize installation] → 
  ☑️ Documentation
  ☑️ pip
  ☑️ tcl/tk and IDLE
  ☑️ Python test suite
  ☑️ py launcher
  ☑️ for all users
```

**1.3. Kurulum Doğrulama**

Yeni bir PowerShell veya CMD penceresi açın (eski pencereler kapanmadan yeni değişiklikleri göremez):

```powershell
python --version
```

Beklenen çıktı:
```
Python 3.11.x
```

veya daha yüksek bir sürüm.

**Hata alırsanız:**
- Python'u kaldırın
- Bilgisayarı yeniden başlatın
- Python'u yeniden kurun (PATH seçeneğini işaretleyerek)

---

### Adım 2: Node.js 20+ Kurulumu

**2.1. İndirme**

https://nodejs.org adresine gidin. **LTS** (Long Term Support) sürümünü indirin.

**2.2. Kurulum**

İndirilen `.msi` dosyasını çalıştırın:

```
[Next] → [I accept the terms...] → [Next] → [Next] → [Next] → [Install] → [Finish]
```

Varsayılan ayarlar yeterlidir, değiştirmenize gerek yok.

**2.3. Kurulum Doğrulama**

Yeni bir terminal penceresi açın:

```powershell
node --version
```

Beklenen çıktı:
```
v20.x.x
```

veya daha yüksek bir sürüm.

---

### Adım 3: Ollama Kurulumu

**3.1. İndirme**

https://ollama.com/download adresinden Windows sürümünü indirin.

**3.2. Kurulum**

İndirilen `OllamaSetup.exe` dosyasını çalıştırın. Kurulum otomatik tamamlanır.

**3.3. Kurulum Doğrulama**

Bilgisayarı yeniden başlatın (veya en azından terminali kapatıp yeniden açın):

```powershell
ollama --version
```

Beklenen çıktı:
```
ollama version x.x.x
```

---

### Adım 4: Tüm Kurulumları Tekrar Doğrulama

Her üç programın da doğru kurulduğundan emin olun:

```powershell
python --version    # Python 3.11.x
node --version      # v20.x.x
ollama --version    # ollama version x.x.x
```

**Bu komutların hepsi çalışmadan sonraki adımlara geçmeyin!**

---

## 🚀 Uygulama Kurulumu

Ön kurulum tamamlandıktan sonra uygulamayı kurabilirsiniz.

### Adım 5: Repository'yi İndirme

**Seçenek A: Git ile (Önerilen)**

Git kurulu değilse önce https://git-scm.com/download/win adresinden indirin.

```powershell
# İndirilecek klasöre gidin (örneğin Masaüstü)
cd C:\Users\KullaniciAdi\Desktop

# Repository'yi klonlayın
git clone https://github.com/AhmetDemiroglu/OpenWorld.git

# Klasöre girin
cd OpenWorld
```

**Seçenek B: ZIP olarak indirme**

1. GitHub sayfasına gidin
2. Code → Download ZIP
3. ZIP dosyasını çıkarın
4. CMD/PowerShell ile çıkarılan klasöre gidin

---

### Adım 6: Launcher'ı İlk Kez Çalıştırma

Repository klasöründeyken:

```powershell
python launcher.py
```

**Beklenen davranış:**
- OpenWorld Launcher penceresi açılır
- Koyu tema, yan yana input alanları görürsünüz
- Altta durum çubuğu "Hazır" yazar

**Karşılaşabileceğiniz hatalar:**
- `'python' is not recognized` → Adım 1'i tekrarlayın
- `ModuleNotFoundError: No module named 'tkinter'` → Python'u kaldırıp tcl/tk seçeneğiyle yeniden kurun

---

### Adım 7: Uygulama Bağımlılıklarının Kurulumu

Launcher açıkken:

**7.1. [⚙ Kurulum] Butonuna Tıklayın**

```
┌─────────────────────────────────────────────────────────────┐
│  [▶ Başlat] [■ Durdur] [Arayüz] [⚙ Kurulum] [Kaydet]       │
└─────────────────────────────────────────────────────────────┘
                              ↑
                           Buna tıklayın
```

**7.2. Ne Olacak?**

Bu işlem 5-10 dakika sürecektir. Durum çubuğunda şunları göreceksiniz:

```
14:32:15 - Kurulum başlıyor...
14:32:20 - Python sanal ortamı oluşturuluyor...
14:34:30 - Python paketleri yükleniyor...
14:36:45 - Node.js paketleri yükleniyor...
14:38:10 - Frontend build ediliyor...
14:39:25 - Kurulum tamamlandı.
```

**Bu işlem şunları yapar:**
1. `backend/.venv/` klasörünü oluşturur (Python sanal ortamı)
2. `pip install` ile Python bağımlılıklarını yükler
3. `npm install` ile React bağımlılıklarını yükler (`frontend/node_modules/`)
4. `npm run build` ile web arayüzünü derler (`frontend/dist/`)
5. `backend/.env` dosyasını oluşturur

**Hata alırsanız:**
- PowerShell yönetici olarak çalıştırılmamış olmalı (normal kullanıcı yetkisi yeterli)
- İnternet bağlantınızı kontrol edin
- Antivirüs yazılımı engelliyor olabilir, geçici olarak devre dışı bırakın

---

### Adım 8: AI Modelinin İndirilmesi

**Seçenek A: Terminal'den (Önerilen - En Hızlı)**

Yeni bir terminal penceresi açın (Launcher'ı kapatmayın):

```powershell
ollama pull qwen3.5:9b-q4_K_M
```

İndirme süresi: İnternet hızınıza bağlı olarak 10-30 dakika (yaklaşık 5 GB)

İndirme tamamlandığında:
```
success 
```
mesajı görürsünüz.

**Seçenek B: Launcher'dan**

Launcher'da:
1. "Yapay Zekâ Modeli" bölümünü genişletin
2. Model Adı alanına yazın: `qwen3.5:9b-q4_K_M`
3. [Model Çek] butonuna tıklayın

**Seçenek C: [Qwen3.5] Butonu ile (GGUF)**

Bu buton HuggingFace'den GGUF formatında model indirir (Ollama kullanmadan).

1. [Qwen3.5] butonuna tıklayın
2. İndirme başlayacaktır (5 GB)
3. İndirilen dosya `models/Qwen3.5-9B-Q4_K_M.gguf` olacaktır

**Not:** GGUF kullanmak için Launcher'da Motor olarak `llama_cpp` seçmeniz gerekir.

---

### Adım 9: Ayarların Kaydedilmesi

Launcher'da:

1. **[Kaydet]** butonuna tıklayın
2. Durum çubuğunda "Ayarlar kaydedildi" mesajını görmelisiniz

Bu işlem `backend/.env` dosyasına ayarlarınızı yazar.

---

### Adım 10: Servislerin Başlatılması

**10.1. [▶ Başlat] Butonuna Tıklayın**

Bu işlem şunları başlatır:
- Backend API sunucusu (http://127.0.0.1:8000)
- Telegram botu (eğer token ayarlandıysa)

**10.2. Başarılı Başlatma Kontrolü**

Durum çubuğunda şunu görmelisiniz:
```
Servisler başlatıldı. UI: http://127.0.0.1:8000
```

Pencere başlığında:
```
OpenWorld Launcher │ Ollama: ✅ Aktif │ Backend: ✅ Aktif
```

**Hata alırsanız:**
- `data/logs/backend.err.log` dosyasını kontrol edin
- Ollama çalışıyor mu kontrol edin: `ollama list`

---

### Adım 11: Web Arayüzünün Açılması

**11.1. [Arayüz] Butonuna Tıklayın**

Varsayılan tarayıcınızda http://127.0.0.1:8000 adresi açılır.

**11.2. Veya Manuel Açın**

Tarayıcınıza şunu yazın:
```
http://127.0.0.1:8000
```

**11.3. Karşılama Ekranı**

Web arayüzünde sohbet penceresi görürsünüz. Mesaj yazıp gönderebilirsiniz.

---

## 🔄 Özet Akış

```
┌─────────────────────────────────────────────────────────────┐
│  1. Python 3.11+ Kur  (python.org)                          │
│     └─> "Add to PATH" işaretle!                            │
├─────────────────────────────────────────────────────────────┤
│  2. Node.js 20+ Kur  (nodejs.org)                           │
├─────────────────────────────────────────────────────────────┤
│  3. Ollama Kur  (ollama.com/download)                       │
│     └─> Terminali yeniden başlat!                          │
├─────────────────────────────────────────────────────────────┤
│  4. Hepsini kontrol et:                                     │
│     python --version                                        │
│     node --version                                          │
│     ollama --version                                        │
├─────────────────────────────────────────────────────────────┤
│  5. Repoyu indir:                                           │
│     git clone https://github.com/.../OpenWorld.git          │
├─────────────────────────────────────────────────────────────┤
│  6. Launcher'ı çalıştır:                                    │
│     python launcher.py                                      │
├─────────────────────────────────────────────────────────────┤
│  7. Launcher'da [Kurulum] butonuna tıkla (5-10 dk)         │
├─────────────────────────────────────────────────────────────┤
│  8. Model indir:                                            │
│     ollama pull qwen3.5:9b-q4_K_M  (5-10 dk)               │
├─────────────────────────────────────────────────────────────┤
│  9. Launcher'da: [Kaydet] → [Başlat] → [Arayüz]            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Mimari Yapı

```
┌─────────────────────────────────────────────────────────────────┐
│                        OpenWorld Agent                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Web UI     │    │  Telegram    │    │   REST API   │      │
│  │   (React)    │◄──►│    Bot       │◄──►│  (FastAPI)   │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                 │               │
│                              ┌──────────────────┘               │
│                              ▼                                  │
│                    ┌──────────────────┐                        │
│                    │   Agent Service  │                        │
│                    └────────┬─────────┘                        │
│                             │                                   │
│           ┌─────────────────┼─────────────────┐                │
│           ▼                 ▼                 ▼                │
│    ┌────────────┐   ┌────────────┐   ┌────────────┐           │
│    │    LLM     │   │  Memory    │   │   Tools    │           │
│    │  (Ollama)  │   │ (Session)  │   │ (Registry) │           │
│    └────────────┘   └────────────┘   └────────────┘           │
│                                                 │               │
│                              ┌──────────────────┘               │
│                              ▼                                  │
│                    ┌──────────────────┐                        │
│                    │  External APIs   │                        │
│                    │ Gmail/Outlook/Web│                        │
│                    └──────────────────┘                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Teknoloji Stack

| Katman | Teknoloji |
|--------|-----------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **Frontend** | React 18+, Vite |
| **AI/ML** | Ollama, llama-cpp-python |
| **Mesajlaşma** | python-telegram-bot |
| **E-posta** | Google Gmail API, Microsoft Graph API |
| **Veri** | JSON-based local storage |
| **Güvenlik** | Windows DPAPI şifreleme |

### Proje Yapısı

```
OpenWorld/
├── backend/              # FastAPI Backend
│   ├── app/             # API ve Agent kodları
│   │   ├── agent.py     # Agent servisi
│   │   ├── main.py      # FastAPI uygulaması
│   │   ├── telegram_bridge.py  # Telegram bot
│   │   └── tools/       # Araç kayıtları
│   ├── .venv/           # Python sanal ortam (kurulumda oluşur)
│   ├── .env             # Ayarlar (kurulumda oluşur)
│   └── requirements.txt # Python bağımlılıkları
├── frontend/            # React Frontend
│   ├── src/             # React kaynak kodları
│   │   ├── App.jsx      # Ana uygulama
│   │   └── components/  # React bileşenler
│   ├── dist/            # Build edilmiş UI (kurulumda oluşur)
│   ├── node_modules/    # NPM paketler (kurulumda oluşur)
│   └── package.json     # Node.js bağımlılıkları
├── data/                # Kullanıcı verileri
│   ├── sessions/        # Sohbet geçmişi
│   ├── logs/            # Uygulama logları
│   ├── planner/         # Görev ve takvim
│   └── mail/            # E-posta taslakları
├── models/              # İndirilen AI modelleri
├── scripts/             # Kurulum scriptleri
│   ├── setup.ps1        # Ana kurulum scripti
│   └── install-qwen35-9b.ps1  # Model kurulumu
├── launcher.py          # Tkinter GUI
└── README.md            # Bu dosya
```

---

## 🐛 Sorun Giderme

### Hata: 'python' is not recognized

**Nedeni:** Python PATH'e eklenmemiş.

**Çözüm 1 (Önerilen):**
Python'u kaldırıp yeniden kurun, kurulumda "Add to PATH" seçeneğini işaretleyin.

**Çözüm 2 (Geçici):**
Python'un tam yolunu kullanın:
```powershell
C:\Users\Kullanici\AppData\Local\Programs\Python\Python311\python.exe launcher.py
```

---

### Hata: ModuleNotFoundError: No module named 'tkinter'

**Nedeni:** Python kurulumunda tkinter paketi eksik.

**Çözüm:**
1. Python'u kaldırın (Add/Remove Programs)
2. Bilgisayarı yeniden başlatın
3. Python'u yeniden kurun
4. Kurulumda "tcl/tk and IDLE" seçeneğini işaretleyin

---

### Hata: 'node' is not recognized

**Nedeni:** Node.js PATH'e eklenmemiş.

**Çözüm:**
Node.js'i yeniden kurun. Kurulum otomatik olarak PATH'e ekler.

---

### Hata: 'ollama' is not recognized

**Nedeni:** Ollama PATH'e eklenmemiş veya kurulum tamamlanmamış.

**Çözüm 1:**
Bilgisayarı yeniden başlatın.

**Çözüm 2:**
Ollama'yı yeniden kurun.

---

### Hata: Kurulum scripti çalışmıyor

**Nedeni:** PowerShell Execution Policy kısıtlaması.

**Çözüm:**
```powershell
# PowerShell'de (Yönetici olarak değil, normal olarak):
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Veya Manuel Kurulum:**
```powershell
# 1. Python sanal ortam
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..

# 2. Frontend
cd frontend
npm install
npm run build
cd ..
```

---

### Hata: Port 8000 kullanımda

**Nedeni:** Başka bir program 8000 portunu kullanıyor.

**Çözüm 1:**
Portu kullanan programı bulup kapatın:
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID_NUMARASI> /F
```

**Çözüm 2:**
Farklı port kullanın (kod değişikliği gerekir).

---

### Hata: Backend başlamıyor

**Nedeni 1:** `.venv` klasörü eksik

**Kontrol:**
```powershell
dir backend\.venv
```

**Çözüm:**
[⚙ Kurulum] butonuna tekrar tıklayın.

---

**Nedeni 2:** Ollama çalışmıyor

**Kontrol:**
```powershell
ollama list
```

**Çözüm:**
```powershell
ollama serve
```

veya Ollama'yı Windows servisi olarak başlatın.

---

**Nedeni 3:** Loglara bakın

```powershell
type data\logs\backend.err.log
```

---

### Hata: Model indirme çok yavaş

**Nedeni:** İnternet bağlantısı yavaş veya sunucu yoğunluğu.

**Çözüm 1:**
Terminal'den deneyin (daha hızlı olabilir):
```powershell
ollama pull qwen3.5:9b-q4_K_M
```

**Çözüm 2:**
Daha küçük model kullanın:
```powershell
ollama pull qwen3.5:7b-q4_K_M
```

**Çözüm 3:**
VPN kullanın (bazı bölgelerde daha hızlı olabilir).

---

### Hata: Web arayüzü açılmıyor

**Nedeni:** Frontend build edilmemiş.

**Kontrol:**
```powershell
dir frontend\dist
```

İçinde `index.html` olmalı.

**Çözüm:**
```powershell
cd frontend
npm install
npm run build
cd ..
```

---

### Hata: Telegram bot çalışmıyor

**Kontrol listesi:**
1. Token doğru mu? (@BotFather'dan alınan)
2. User ID doğru mu? (@userinfobot'dan alınan)
3. [Kaydet] butonuna bastınız mı?
4. Backend loglarında hata var mı?

```powershell
type data\logs\telegram.err.log
```

---

## ✨ Özellikler

### 🤖 Yapay Zeka Sohbeti
- **Ollama Entegrasyonu**: `qwen`, `llama`, `mistral`, `deepseek` ve daha fazlası
- **GGUF Desteği**: Kendi modelinizi kullanın
- **Oturum Belleği**: Konuşmaları hatırlar

### 📱 Telegram Botu
- Sadece izin verilen kullanıcıdan komut alma
- Markdown destekli zengin mesajlar

### 📧 E-posta Entegrasyonu
- **Gmail**: OAuth2 ile güvenli bağlantı
- **Outlook**: Microsoft Graph API entegrasyonu

### 🛠️ Araçlar ve Yetenekler

| Araç | Açıklama |
|------|----------|
| `list_dir` | Dizin içeriğini listeleme |
| `read_text_file` | Metin dosyası okuma |
| `write_text_file` | Dosya oluşturma/düzenleme |
| `add_task` | Görev ekleme |
| `list_tasks` | Görevleri listeleme |
| `complete_task` | Görev tamamlama |
| `add_calendar_event` | Takvim etkinliği ekleme |
| `list_calendar_events` | Etkinlikleri görüntüleme |
| `create_email_draft` | E-posta taslağı oluşturma |
| `search_news` | Google News RSS ile haber arama |
| `fetch_web_page` | Web sayfası içeriği çekme |
| `check_gmail_messages` | Gmail mesajlarını okuma |
| `check_outlook_messages` | Outlook mesajlarını okuma |

---

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/yeni-ozellik`)
3. Commit edin (`git commit -m 'Yeni özellik eklendi'`)
4. Push edin (`git push origin feature/yeni-ozellik`)
5. Pull Request açın

---

## 📜 Lisans

MIT License
