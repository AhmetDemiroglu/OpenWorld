# Mimari Dökümantasyonu

## Genel Bakış

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
│  │Ollama │        │(Session+ │       │ (95+ Adt)│        │
│  │        │        │ Notebook)│       │          │        │
│  └───────┘        └──────────┘       └──────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Katmanlar

### 1. Presentation Layer
- **React Frontend**: Kullanıcı arayüzü
- **Telegram Bot**: Telegram entegrasyonu
- **REST API**: FastAPI endpoint'leri

### 2. Business Layer
- **AgentService**: Ana iş mantığı
- **Policy Engine**: Güvenlik ve yetkilendirme
- **Tool Registry**: Araç yönetimi

### 3. Data Layer
- **SQLite**: Sohbet ve hafıza
- **File System**: Medya ve belgeler
- **Ollama**: LLM entegrasyonu

## Veri Akışı

### Sohbet Akışı
1. Kullanıcı mesajı → API
2. AgentService işleme
3. LLM'den yanıt
4. Tool çağrıları (gerekirse)
5. Yanıt kullanıcıya

### Hafıza Akışı
1. Önemli bilgi tespiti
2. MemoryFacts tablosuna kayıt
3. Konuşma başlangıcında context ekleme
4. Benzerlik bazlı geri çağırma

## Güvenlik Mimarisi

```
Kullanıcı Mesajı
     │
     ▼
┌─────────────┐
│   Parser    │
└─────────────┘
     │
     ▼
┌─────────────┐     ┌─────────────┐
│   Policy    │────►│  Engelle    │
│   Check     │     │  (Yasak)    │
└─────────────┘     └─────────────┘
     │
     ▼
┌─────────────┐     ┌─────────────┐
│   Risk      │────►│   Onay      │
│   Level     │     │   İste      │
└─────────────┘     └─────────────┘
     │
     ▼
┌─────────────┐
│  Çalıştır   │
└─────────────┘
```
