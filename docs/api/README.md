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

## Kimlik Dogrulama

Su anda yerel calisan bir uygulama oldugu icin kimlik dogrulama gerektirmez.

---

## Telegram Komutlari

### Temel Komutlar

| Komut | Aciklama |
|-------|----------|
| `/ekran [x y w h]` | Ekran goruntusu al ve Telegram'a gonder |
| `/tikla X Y` | Koordinata tikla |
| `/yaz [metin]` | Aktif pencereye metin yaz (Unicode destekli) |
| `/tus [tus]` | Tus bas (orn: `/tus ctrl+s`, `/tus enter`) |
| `/durum` | Sistem durumu (CPU/RAM + servisler) |
| `/arastir [konu]` | Arka planda arastirma baslat, PDF rapor gelir |
| `/not [metin]` | Gunluk not ekle |
| `/notlar [dun\|hafta]` | Notlari listele |

### Otonom Kodlama Sureci Komutlari

| Komut | Aciklama |
|-------|----------|
| `/izle [profil]` | Onay izleyiciyi baslat. Profiller: `gemini`, `codex`, `claudecode`, `kimicode`, `copilot`, `generic` |
| `/izleme_durdur` | Onay izleyiciyi durdur |
| `/izleme_durum` | Izleyici durumu + ekran goruntusu |
| `/tikla_metin [metin]` | Ekranda belirtilen metni OCR ile bul ve tikla (fuzzy matching) |
| `/ajanyaz [ajan] [mesaj]` | VS Code'daki AI ajana mesaj yaz (orn: `/ajanyaz codex bu hatayi duzelt`) |
| `/analiz [profil]` | Ekrani LLM ile analiz et: durum, aksiyon, butonlari tanimla |

### Inline Button Callback'leri

| Callback | Aciklama |
|----------|----------|
| `watcher_stop` | Onay izleyiciyi durdur (completion bildirimindeki buton) |
| `watcher_continue` | Izleyiciyi acik birak |
| `watcher_screenshot` | Guncel ekran goruntusu gonder |
| `watcher_choice:[metin]` | Ekranda belirtilen secenege tikla |

### Otonom Kodlama Sureci

Approval watcher, VS Code'da calisan AI ajanlarinin (Gemini, Codex, Claude Code, KimiCode, Copilot) onay adimlarini otomatik olarak yonetir:

1. **Baslat:** `/izle gemini` (veya baska profil)
2. **Izleyici calisir:** OCR ile ekrani okur, onay butonlarini bulur ve tiklar
3. **LLM analizi:** Keyword matching'in yetmedigi durumlarda Ollama'ya sorar
4. **Expand/Run zinciri:** "Expand All" -> tikla -> "Run" -> tikla
5. **Tamamlanma algilama:** Keyword + LLM hybrid - gorev bittiginde Telegram'a screenshot + inline butonlar gonderir
6. **Soru/secenek algilama:** Ajan soru sordugunda veya secenek sundugunda Telegram'a bildirim + secenekler
7. **Ajana mesaj yazma:** `/ajanyaz codex [mesaj]` ile istenen ajana komut gonderme

#### Profil Ozellikleri

| Profil | Ozel Davranislar |
|--------|------------------|
| `gemini` | Alt bar approval, "Expand All" -> "Run", "Allow once/this conversation" |
| `codex` | "Run Alt+J" kisayol destegi, multi-step approval |
| `claudecode` | "Allow this bash command?" -> "Yes" akisi |
| `kimicode` | "Run", "Continue" butonlari |
| `copilot` | "Accept", "Accept All" butonlari |
| `generic` | Tum profillerin ortak terimlerini kullanir |

#### State Machine

```
WATCHING -> APPROVAL_CLICKED -> BUSY -> COMPLETED
                                    -> QUESTION_DETECTED
```

Her state gecisinde izleyici durumu guncellenir ve opsiyonel olarak Telegram'a bildirim gonderilir.

---

## Yeni Tool'lar

### click_text_on_screen

Ekranda belirtilen metni OCR ile bulup tiklar. Fuzzy matching (SequenceMatcher >= 0.75) destekler.

```json
{
  "target_text": "Allow once",
  "window_pattern": "Visual Studio Code",
  "lang": "tur+eng",
  "min_confidence": 25.0
}
```

### type_in_agent_input

VS Code'da calisan AI ajan paneline odaklanip mesaj yazar.

```json
{
  "agent": "codex",
  "text": "Bu hatayi duzelt",
  "press_enter": true
}
```

Desteklenen ajanlar: `codex`, `claudecode`, `kimicode`, `copilot`, `gemini`

### analyze_screen

Ekrani OCR + LLM (Ollama) ile analiz eder. IDE durumunu, aksiyonu, butonu tanimlar.

```json
{
  "window_pattern": "Visual Studio Code",
  "profile": "gemini"
}
```

**Response:**
```json
{
  "state": "approval",
  "action": "click_button",
  "target_text": "Allow once",
  "confidence": 0.92,
  "reasoning": "Gemini dizin erisimi icin onay istiyor...",
  "options": [],
  "completion_summary": ""
}
```
