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

## 📋 İçindekiler

- [Proje Hakkında](#-proje-hakkında)
- [Özellikler](#-özellikler)
- [Mimari Yapı](#-mimari-yapı)
- [Kurulum](#-kurulum)
- [Hızlı Başlangıç](#-hızlı-başlangıç)
- [Model Kurulumu](#-model-kurulumu)
- [Telegram Entegrasyonu](#-telegram-entegrasyonu)
- [E-posta Entegrasyonu](#-e-posta-entegrasyonu)
- [Kullanım Rehberi](#-kullanım-rehberi)
- [Güvenlik Politikaları](#-güvenlik-politikaları)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 Proje Hakkında

**OpenWorld Local Agent**, verilerinizi cihazınızda tutan, internet bağlantısı olmadan çalışabilen, kişisel yapay zeka asistanıdır. Gizlilik önceliklidir - hiçbir veri buluta gönderilmez, tüm işlemler yerel olarak gerçekleşir.

### Neden OpenWorld?

| Özellik | Açıklama |
|---------|----------|
| 🔒 **Tam Gizlilik** | Verileriniz sadece sizin cihazınızda kalır |
| 🚀 **Çevrimdışı Çalışma** | İnternet olmadan LLM sohbeti yapın |
| 🤖 **Çoklu Platform** | Web arayüzü + Telegram entegrasyonu |
| 📧 **E-posta Yönetimi** | Gmail/Outlook entegrasyonu ile mail özetleme |
| 📁 **Dosya Yönetimi** | Yerel dosyaları okuyun, yazın, düzenleyin |
| 📅 **Planlama** | Görev ve takvim yönetimi |
| 🔧 **Genişletilebilir** | Özel araçlar ekleyin |

---

## ✨ Özellikler

### 🤖 Yapay Zeka Sohbeti
- **Ollama Entegrasyonu**: `qwen`, `llama`, `mistral`, `deepseek` ve daha fazlası
- **llama.cpp Desteği**: GGUF formatında kendi modelinizi kullanın
- **Oturum Belleği**: Konuşmaları hatırlayan bağlam yönetimi
- **Çok Adımlı Akış**: Karmaşık görevleri otomatik parçalama

### 📱 Telegram Botu
- Sadece izin verilen kullanıcıdan komut alma
- Markdown destekli zengin mesajlar
- Güvenli kimlik doğrulama
- Anlık bildirimler

### 📧 E-posta Entegrasyonu
- **Gmail**: OAuth2 ile güvenli bağlantı (sadece okuma)
- **Outlook**: Microsoft Graph API entegrasyonu
- Otomatik token yenileme
- Okunmamış mailleri özetleme

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
| `research_and_report` | Otomatik araştırma raporu oluşturma |
| `check_gmail_messages` | Gmail mesajlarını okuma |
| `check_outlook_messages` | Outlook mesajlarını okuma |
| `run_shell` | Kısıtlı PowerShell komutları çalıştırma |

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

---

## 🚀 Kurulum

### Gereksinimler

- **İşletim Sistemi**: Windows 11 (Windows 10 da çalışır)
- **Python**: 3.11 veya üzeri
- **Node.js**: 20 veya üzeri
- **Git**: Son sürüm
- **Ollama**: [ollama.com](https://ollama.com) adresinden indirin

### Adım 1: Repoyu Klonlayın

```powershell
# PowerShell veya CMD'de çalıştırın
git clone https://github.com/kullaniciadi/OpenWorld.git
cd OpenWorld
```

### Adım 2: Otomatik Kurulum

**En kolay yöntem** - Launcher'ı açın ve tek tıkla kurun:

```powershell
# Windows'ta çift tıklayarak veya:
.\OpenWorld-Launcher.bat
```

**Veya manuel kurulum:**

```powershell
# PowerShell yönetici olarak çalıştırın
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Bu komut şunları yapar:
- ✅ Python sanal ortamı oluşturur (`backend/.venv`)
- ✅ Tüm bağımlılıkları yükler
- ✅ Frontend'i build eder
- ✅ Gerekli klasör yapısını oluşturur
- ✅ Varsayılan `.env` dosyasını hazırlar

---

## 🎮 Hızlı Başlangıç

### 1. Launcher'ı Açın

```powershell
python launcher.py
# veya
.\OpenWorld-Launcher.bat
```

### 2. Kurulum Sırası

```
┌────────────────────────────────────────────────────────────┐
│                    OpenWorld Launcher                       │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  [▶ Başlat] [■ Durdur] [Arayüz] [⚙ Kurulum] [Kaydet]      │
│                                                             │
│  ▼ Kullanıcı Profili                                        │
│    Adınız: [Ahmet..........................]                │
│    İlgi Alanları: [Teknoloji, otomasyon...]                 │
│                                                             │
│  ▼ Yapay Zekâ Modeli                                        │
│    Motor: [ollama ▼]                                        │
│    Model Adı: [qwen3.5:9b-q4_K_M...........]                │
│                                                             │
│  [Model Çek] [GGUF İndir] [Qwen3.5] [Eski Sil]              │
│                                                             │
│  ▶ Telegram Botu                                            │
│  ▶ Gmail Entegrasyonu (İsteğe Bağlı)                        │
│  ▶ Outlook Entegrasyonu (İsteğe Bağlı)                      │
│  ▶ Web Güvenliği                                            │
│                                                             │
│  Durum: 14:32:15 - Hazır                                   │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### 3. Model İndirme

**Ollama ile (Önerilen):**
1. "Yapay Zekâ Modeli" bölümünü açın
2. Model adını girin (örn: `qwen3.5:9b-q4_K_M`)
3. **[Model Çek]** butonuna tıklayın

**GGUF ile (Kendi modeliniz):**
1. Model URL'sini girin
2. **[GGUF İndir]** butonuna tıklayın

**Hazır Kurulum:**
- **[Qwen3.5]** butonu ile otomatik kurulum yapın

### 4. Başlatma

1. **[Kaydet]** - Ayarları kaydedin
2. **[▶ Başlat]** - Servisleri başlatın
3. **[Arayüz]** - Web arayüzünü açın

### 5. Web Arayüzüne Erişim

Tarayıcınızda açılacak veya manuel olarak:
```
http://127.0.0.1:8000
```

---

## 🤖 Model Kurulumu

### Ollama ile Çalışma (Önerilen)

**Ollama Kurulumu:**

1. [ollama.com/download](https://ollama.com/download) adresinden indirin
2. Kurulumu tamamlayın
3. Terminalde test edin:
   ```powershell
   ollama --version
   ```

**Model İndirme:**

```powershell
# Qwen 3.5 9B (Önerilen - dengeli performans)
ollama pull qwen3.5:9b-q4_K_M

# Daha hafif alternatif
ollama pull qwen3.5:7b-q4_K_M

# Daha güçlü
ollama pull qwen3.5:14b-q4_K_M

# Diğer modeller
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull deepseek-coder:6.7b
```

**Launcher'da Model Ayarı:**

```
Motor: ollama
Model Adı: qwen3.5:9b-q4_K_M
```

### GGUF ile Çalışma

Kendi indirdiğiniz GGUF modellerini kullanın:

```powershell
# Hugging Face'den model indirme örneği
# URL: https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf
```

**Launcher Ayarları:**
```
Motor: llama_cpp
GGUF Yolu: ../models/Qwen3.5-9B-Q4_K_M.gguf
GGUF URL: [indirme linki]
```

---

## 💬 Telegram Entegrasyonu

### 1. Telegram Bot Oluşturma

1. **[@BotFather](https://t.me/botfather)** ile konuşma başlatın
2. `/newbot` komutunu gönderin
3. Bot adı ve kullanıcı adı belirleyin
4. **Bot Token** kopyalayın (örn: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Kullanıcı ID Öğrenme

1. **[@userinfobot](https://t.me/userinfobot)** mesaj atın
2. Size verecek olan ID'yi kopyalayın (örn: `123456789`)

### 3. Launcher'da Yapılandırma

```
▼ Telegram Botu
  Bot Token: [****************************]  (Gizli)
  Kullanıcı ID: [123456789]
```

### 4. Kaydet ve Başlat

1. **[Kaydet]** butonuna tıklayın
2. **[▶ Başlat]** ile servisleri başlatın
3. Telegram'da botunuza `/start` yazın

### Güvenlik Notu

- Bot token'ınız **Windows DPAPI** ile şifrelenerek saklanır
- Sadece belirttiğiniz kullanıcı ID'si ile etkileşime geçebilir
- Başka kimse botunuza erişemez

---

## 📧 E-posta Entegrasyonu

### Gmail Entegrasyonu

#### Adım 1: Google Cloud Projesine Git

1. [Google Cloud Console](https://console.cloud.google.com/) açın
2. Yeni proje oluşturun veya mevcut projeyi seçin
3. **APIs & Services** > **Credentials** bölümüne gidin

#### Adım 2: OAuth Client ID Oluştur

```
1. [+ CREATE CREDENTIALS] > [OAuth client ID]
2. Application type: Desktop app
3. Name: OpenWorld Agent
4. [CREATE]
```

#### Adım 3: Client ID Kopyala

```
Client ID: 123456789-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com
Client Secret: [Gizli değer - opsiyonel]
```

**Önemli:** Client ID formatı şöyle olmalı:
```
XXXXXX.apps.googleusercontent.com
```

#### Adım 4: Gmail API'yi Etkinleştir

```
APIs & Services > Library > Gmail API > Enable
```

#### Adım 5: Launcher'da OAuth Bağlan

```
▼ Gmail Entegrasyonu
  Client ID: [XXXXXX.apps.googleusercontent.com]
  Client Secret: [Opsiyonel]
  
  [OAuth Bağlan] [Client ID Nereden?]
```

1. **[OAuth Bağlan]** butonuna tıklayın
2. Tarayıcıda Google hesabınızla giriş yapın
3. İzinleri onaylayın
4. Tokenlar otomatik kaydedilir

### Outlook Entegrasyonu

#### Adım 1: Azure App Registration

1. [Azure Portal](https://portal.azure.com/) açın
2. **Microsoft Entra ID** > **App registrations** > **New registration**

#### Adım 2: Uygulama Kaydı

```
Name: OpenWorld Agent
Supported account types: Accounts in any organizational directory and personal Microsoft accounts
Redirect URI: Public client/native (mobile & desktop) > http://localhost
```

#### Adım 3: API İzinleri Ekle

```
API permissions > Add permission > Microsoft Graph > Delegated permissions:
- offline_access
- Mail.Read
```

#### Adım 4: Client ID Kopyala

```
Overview > Application (client) ID: 12345678-1234-1234-1234-123456789012
```

Bu bir **GUID** formatındadır (e-posta adresi değil!)

#### Adım 5: Launcher'da Yapılandır

```
▼ Outlook Entegrasyonu
  Client ID: [12345678-1234-1234-1234-123456789012]
  Tenant ID: [common]  (veya organizasyon GUID)
  
  [OAuth Bağlan] [Client ID Nereden?]
```

---

## 📖 Kullanım Rehberi

### Web Arayüzü Kullanımı

```
┌─────────────────────────────────────────────────────────────┐
│  🌍 OpenWorld Agent                    [Yeni Sohbet]       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Sistem: OpenWorld Agent aktif. Size nasıl yardımcı  │  │
│  │  olabilirim?                                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  👤 Bugünün haberlerini özetler misin?               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  🤖 Elbette! İşte günün öne çıkan haberleri:         │  │
│  │                                                         │  │
│  │  ## Gündem Özeti - 3 Mart 2025                         │  │
│  │                                                         │  │
│  │  ### Siyaset                                           │  │
│  │  - **Önemli Gelişme**: Açıklama... [Kaynak](link)      │  │
│  │                                                         │  │
│  │  ### Ekonomi                                           │  │
│  │  | Veri      | Değer    | Değişim |                    │  │
│  │  |----------|----------|---------|                    │  │
│  │  | Dolar/TL  | 36.45    | +0.2%   |                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  [Mesajınızı yazın...                    ] [Gönder]  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Örnek Komutlar

| Senaryo | Örnek Mesaj |
|---------|-------------|
| **Haber** | "Bugünün önemli haberlerini özetle" |
| **Dosya Oku** | "workspace/projects klasöründeki dosyaları listele" |
| **Dosya Yaz** | "notes.txt dosyasına alışveriş listesi oluştur" |
| **Görev** | "Yarın saat 14:00'te toplantı görevi ekle" |
| **Takvim** | "15 Mart için doğum günü etkinliği ekle" |
| **E-posta** | "Gmail'deki son 5 maili özetle" |
| **Araştırma** | "Yapay zeka trendleri hakkında rapor hazırla" |
| **Web** | "https://example.com sayfasının içeriğini analiz et" |

### Telegram Kullanımı

Botunuza doğrudan mesaj atın:

```
👤: Merhaba, bugünkü görevlerim neler?

🤖: İşte açık görevleriniz:
   
   1. [abc123] Proje raporunu tamamla - 5 Mart 2025
   2. [def456] Müşteri toplantısı hazırlığı - 7 Mart 2025
```

---

## 🔒 Güvenlik Politikaları

### Finansal Güvenlik

```yaml
❌ YASAK İŞLEMLER:
  - Ödeme işlemleri
  - Kredi kartı bilgisi işleme
  - Para transferi
  - Satın alma işlemleri
  - Finansal kimlik bilgileri
```

### Token Güvenliği

| Özellik | Açıklama |
|---------|----------|
| Şifreleme | Windows DPAPI (Data Protection API) |
| Saklama | `*_ENC` suffix ile şifrelenmiş |
| Erişim | Sadece mevcut Windows kullanıcısı |

### Web Güvenliği

```yaml
WEB_BLOCK_PRIVATE_HOSTS: true
  # localhost, 127.0.0.1, 192.168.x.x, 10.x.x.x engeller

WEB_ALLOWED_DOMAINS:
  # Boş = Tüm domainlere izin ver
  # Dolu = Sadece belirtilen domainler
  # Örnek: "github.com,stackoverflow.com"
```

### Shell Güvenliği

```yaml
ENABLE_SHELL_TOOL: false  # Varsayılan kapalı

# Etkinleştirildiğinde sadece belirli prefix'lere izin:
# - Get-
# - Write-Output
# - Select-Object
# - ...vb

# YASAK komutlar:
# - Remove-Item
# - Format
# - Shutdown
# - Restart-Computer
```

---

## 🔧 Yapılandırma Dosyası

`backend/.env` dosyası yapısı:

```ini
# LLM Backend
LLM_BACKEND=ollama                    # ollama | llama_cpp
OLLAMA_MODEL=qwen3.5:9b-q4_K_M
LLAMA_MODEL_PATH=../models/model.gguf

# Telegram
TELEGRAM_BOT_TOKEN_ENC=dpapi:xxx      # Şifrelenmiş
TELEGRAM_ALLOWED_USER_ID=123456789

# Gmail OAuth
GMAIL_CLIENT_ID=xxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET_ENC=dpapi:xxx
GMAIL_ACCESS_TOKEN_ENC=dpapi:xxx
GMAIL_REFRESH_TOKEN_ENC=dpapi:xxx

# Outlook OAuth
OUTLOOK_CLIENT_ID=xxx-xxx-xxx
OUTLOOK_TENANT_ID=common
OUTLOOK_ACCESS_TOKEN_ENC=dpapi:xxx
OUTLOOK_REFRESH_TOKEN_ENC=dpapi:xxx

# Web Güvenliği
WEB_ALLOWED_DOMAINS=
WEB_BLOCK_PRIVATE_HOSTS=true

# Shell
ENABLE_SHELL_TOOL=false

# Kullanıcı
OWNER_NAME=Ahmet
OWNER_PROFILE=Teknoloji, otomasyon, urun gelistirme
```

---

## 🐛 Troubleshooting

### Backend Başlamıyor

```powershell
# Logları kontrol edin
cat data/logs/backend.err.log

# Yaygın çözümler:
1. Port 8000'in boş olduğundan emin olun
   netstat -ano | findstr :8000

2. Ollama'nın çalıştığından emin olun
   ollama list

3. Sanal ortamı yeniden oluşturun
   Remove-Item -Recurse -Force backend/.venv
   .\scripts\setup.ps1
```

### Model İndirme Hatası

```powershell
# Manuel indirme
ollama pull qwen3.5:9b-q4_K_M

# Veya
ollama run qwen3.5:9b-q4_K_M
```

### Telegram Bot Çalışmıyor

```powershell
# Logları kontrol edin
cat data/logs/telegram.err.log

# Yaygın hatalar:
1. "Conflict": Başka bir bot instance'ı çalışıyor
   - Launcher'dan [■ Durdur] yapın, 10 saniye bekleyin, tekrar [▶ Başlat]

2. "Unauthorized": Token hatalı
   - BotFather'dan yeni token alın

3. "Not found": Bot silinmiş
   - Yeni bot oluşturun
```

### Gmail/Outlook OAuth Hatası

| Hata | Çözüm |
|------|-------|
| `invalid_client` | Client ID formatını kontrol edin (`...apps.googleusercontent.com`) |
| `redirect_uri_mismatch` | Launcher içinden OAuth'u başlatın |
| `invalid_scope` | API Library'den Gmail API'yi etkinleştirin |
| `AADSTS700016` | Outlook Client ID GUID formatında olmalı |

### Web Sayfası Çekilemiyor

```yaml
Nedenler:
  1. WEB_ALLOWED_DOMAINS kısıtlaması
  2. WEB_BLOCK_PRIVATE_HOSTS=true ile local adres
  3. Hedef site bot koruması (Cloudflare vb.)

Çözüm:
  - Domain'i WEB_ALLOWED_DOMAINS'a ekleyin
  - Veya tamamen boş bırakın (tümüne izin)
```

---

## 📁 Proje Yapısı

```
OpenWorld/
├── 📁 backend/                 # FastAPI Backend
│   ├── 📁 app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI uygulaması
│   │   ├── agent.py           # Agent servisi
│   │   ├── llm.py             # LLM client
│   │   ├── memory.py          # Oturum yönetimi
│   │   ├── telegram_bridge.py # Telegram bot
│   │   ├── system_prompt.py   # Sistem talimatları
│   │   ├── config.py          # Yapılandırma
│   │   ├── policy.py          # Güvenlik politikaları
│   │   ├── secrets.py         # Şifreleme
│   │   └── 📁 tools/
│   │       └── registry.py    # Araç kayıtları
│   ├── .env                   # Çevre değişkenleri
│   └── requirements.txt       # Python bağımlılıkları
│
├── 📁 frontend/               # React Frontend
│   ├── 📁 src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── styles.css
│   │   └── 📁 components/
│   │       ├── ChatMessage.jsx
│   │       ├── Header.jsx
│   │       ├── OpenWorldLogo.jsx
│   │       └── TypingIndicator.jsx
│   ├── index.html
│   └── package.json
│
├── 📁 data/                   # Veri dizini
│   ├── 📁 sessions/           # Sohbet geçmişi
│   ├── 📁 planner/            # Görev ve takvim
│   ├── 📁 mail/drafts/        # E-posta taslakları
│   ├── 📁 reports/            # Araştırma raporları
│   └── 📁 logs/               # Uygulama logları
│
├── 📁 models/                 # GGUF modelleri
├── 📁 scripts/                # Kurulum scriptleri
│   ├── setup.ps1
│   └── install-qwen35-9b.ps1
│
├── launcher.py               # Tkinter GUI launcher
├── OpenWorld-Launcher.bat    # Windows başlatıcı
└── README.md                 # Bu dosya
```

---

## 🤝 Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen şu adımları izleyin:

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Değişikliklerinizi commit edin (`git commit -m 'Add amazing feature'`)
4. Push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

---

## 📜 Lisans

Bu proje MIT Lisansı altında lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.

---

## 🙏 Teşekkürler

- [Ollama](https://ollama.com) - Yerel LLM çalıştırma
- [FastAPI](https://fastapi.tiangolo.com) - Modern web framework
- [React](https://react.dev) - Kullanıcı arayüzü
- [python-telegram-bot](https://python-telegram-bot.org) - Telegram entegrasyonu

---

<div align="center">

**⭐ Bu projeyi beğendiyseniz yıldız vermeyi unutmayın! ⭐**

Made with ❤️ in Türkiye

</div>
