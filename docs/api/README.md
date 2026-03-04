# API Dökümantasyonu

## Base URL

```
http://127.0.0.1:8000
```

## Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "ok": true,
  "llm_backend": "ollama",
  "model": "qwen3.5:9b-q4_K_M",
  "llama_model_path": "...",
  "workspace": "...",
  "shell_tool": true
}
```

### Chat

```http
POST /chat
Content-Type: application/json
```

**Request:**
```json
{
  "session_id": "web_main",
  "message": "Merhaba!",
  "source": "web"
}
```

**Response:**
```json
{
  "session_id": "web_main",
  "reply": "Merhaba! Size nasıl yardımcı olabilirim?",
  "steps": 1,
  "used_tools": [],
  "media": []
}
```

### Sessions

```http
GET /sessions
```

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "web_main",
      "message_count": 10,
      "first_message": "2024-01-01T10:00:00",
      "last_message": "2024-01-01T11:00:00"
    }
  ]
}
```

### Tools Audit

```http
GET /tools/audit?run_probes=true
```

**Response:**
```json
{
  "total": 95,
  "available": 90,
  "failed": 5,
  "tools": [...]
}
```

### Metrics (Prometheus)

```http
GET /metrics
```

**Response:**
```
# HELP openworld_tool_execution_total Total number of tool executions
# TYPE openworld_tool_execution_total counter
openworld_tool_execution_total{tool_name="screenshot_desktop",status="success"} 42
...
```

## WebSocket (Gelecek)

```
ws://127.0.0.1:8000/ws/chat
```

## Hata Kodları

| Kod | Açıklama |
|-----|----------|
| 400 | Bad Request - Geçersiz istek |
| 403 | Forbidden - Politika ihlali |
| 404 | Not Found - Session bulunamadı |
| 500 | Internal Server Error |
| 503 | Service Unavailable - LLM hatası |

## Kimlik Doğrulama

Şu anda yerel çalışan bir uygulama olduğu için kimlik doğrulama gerektirmez.
