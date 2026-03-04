# Yapılandırma Rehberi

## Ortam Değişkenleri

`.env` dosyasında ayarlanabilir:

### Sunucu Ayarları
```env
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=http://localhost:5173
```

### LLM Ayarları
```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:9b-q4_K_M
OLLAMA_MAX_STEPS=25
```

### Güvenlik Ayarları
```env
ENABLE_SHELL_TOOL=true
SHELL_ALLOWED_PREFIXES=*
SHELL_TIMEOUT_SEC=120
ALLOW_FULL_DISK_ACCESS=false
BLOCK_FINANCIAL_OPERATIONS=true
```

### Telegram Entegrasyonu
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USER_ID=your_user_id
```

## Yapılandırma Dosyaları

### config.yaml
Daha gelişmiş yapılandırma için:

```yaml
server:
  host: "127.0.0.1"
  port: 8000
  workers: 1

llm:
  backend: ollama
  model: qwen3.5:9b-q4_K_M
  temperature: 0.7
  max_tokens: 2048

logging:
  level: INFO
  structured: false
  file: true

security:
  enable_shell: true
  block_financial: true
  allowed_paths:
    - "C:\\Users\\%USERNAME%\\Documents"
```

## Loglama Yapılandırması

### Seviyeler
- DEBUG: Geliştirme için detaylı
- INFO: Genel bilgi
- WARNING: Uyarılar
- ERROR: Hatalar

### Structured Logging
```env
STRUCTURED_LOGGING=true
```
JSON formatında loglar `data/logs/` dizinine kaydedilir.
