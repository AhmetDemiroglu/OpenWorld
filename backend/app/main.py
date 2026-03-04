from __future__ import annotations

import shutil
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .agent import AgentService
from .config import settings
from .database import init_database, migrate_json_sessions, get_tool_stats
from .memory import SessionStore
from .models import ChatRequest, ChatResponse, MediaAttachment
from .tools.audit import run_tools_audit

logger = logging.getLogger(__name__)

# Veritabanını başlat
init_database()

store = SessionStore(settings.sessions_path)
agent = AgentService(store)

# Mevcut JSON session'ları SQLite'a migrate et (ilk çalıştırmada)
migrate_json_sessions(settings.sessions_path)

app = FastAPI(title="OpenWorld Local Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Media dizini
_DATA_DIR = settings.data_path
_MEDIA_DIR = _DATA_DIR / "media"
_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

_MEDIA_TYPE_MAP = {
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image", ".webp": "image",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".m4a": "audio", ".flac": "audio",
    ".mp4": "video", ".avi": "video", ".mkv": "video",
    ".mov": "video", ".webm": "video",
    ".pdf": "document", ".docx": "document", ".xlsx": "document",
    ".pptx": "document", ".zip": "document", ".tar": "document",
    ".gz": "document",
}


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "llm_backend": settings.llm_backend,
        "model": settings.ollama_model,
        "llama_model_path": str(settings.llama_model_path_abs),
        "workspace": str(settings.workspace_path),
        "shell_tool": settings.enable_shell_tool,
    }


@app.get("/sessions")
async def sessions() -> dict:
    return {"sessions": store.list_sessions()}


@app.get("/tools/audit")
async def tools_audit(run_probes: bool = True) -> dict:
    try:
        return run_tools_audit(run_probes=run_probes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        reply, steps, used_tools, media_files = await agent.run(req.session_id, req.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat endpoint failed: session_id=%s source=%s", req.session_id, getattr(req, "source", ""))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Media dosyalarını data/media/ altına kopyala ve URL oluştur
    media = _process_media_files(media_files)

    # Medya linklerini reply'a ekle
    if media:
        reply += "\n\n---\n**Medya Dosyaları:**\n"
        for m in media:
            url = m.url
            filename = m.filename
            if m.type == "image":
                reply += f"\n![{filename}]({url})\n"
            elif m.type == "audio":
                reply += f"\n🎵 [{filename}]({url})\n"
            elif m.type == "video":
                reply += f"\n🎥 [{filename}]({url})\n"
            elif m.type == "document":
                reply += f"\n📄 [{filename}]({url})\n"

    return ChatResponse(
        session_id=req.session_id,
        reply=reply,
        steps=steps,
        used_tools=used_tools,
        media=media,
    )


def _process_media_files(media_files: List[str]) -> List[MediaAttachment]:
    """Media dosyalarını data/media/ altına kopyala ve MediaAttachment listesi döndür."""
    attachments: List[MediaAttachment] = []
    for file_path_str in media_files:
        src = Path(file_path_str)
        if not src.exists() or not src.is_file():
            continue

        media_type = _MEDIA_TYPE_MAP.get(src.suffix.lower())
        if not media_type:
            continue

        # data/media/ altına kopyala (aynı isimle, varsa üzerine yaz)
        dst = _MEDIA_DIR / src.name
        # İsim çakışması varsa unique isim oluştur
        if dst.exists() and not dst.samefile(src):
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while dst.exists():
                dst = _MEDIA_DIR / f"{stem}_{counter}{suffix}"
                counter += 1

        try:
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
        except Exception:
            continue

        file_size = dst.stat().st_size
        attachments.append(MediaAttachment(
            type=media_type,
            url=f"/data/media/{dst.name}",
            filename=dst.name,
            caption=f"{media_type}: {dst.name} ({file_size:,} bytes)",
        ))

    return attachments


# Frontend
frontend_dist = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
index_html = frontend_dist / "index.html"

if frontend_dist.exists() and index_html.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/")
    async def ui_root() -> FileResponse:
        return FileResponse(str(index_html))

# Static files - data dizini (media dahil)
_DATA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_DATA_DIR)), name="data")
