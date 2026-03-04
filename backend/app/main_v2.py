"""
OpenWorld Local Agent - Enhanced API
With structured logging, metrics, and improved error handling
"""
from __future__ import annotations

import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

from .agent import AgentService
from .config import settings
from .database import init_database, migrate_json_sessions, get_tool_stats
from .memory import SessionStore
from .models import ChatRequest, ChatResponse, MediaAttachment
from .tools.audit import run_tools_audit
from .core.logging import setup_logging, logger, log_tool_execution, log_llm_interaction
from .core.metrics import (
    get_all_metrics, 
    chat_sessions_active, 
    messages_total,
    errors_total,
    tool_execution_total,
    tool_execution_duration,
    llm_requests_total,
    llm_tokens_total,
    llm_request_duration,
    timer
)
from .core.exceptions import OpenWorldException, ToolExecutionError, LLMError
from .services.email_monitor import EmailMonitor
from .services.smart_assistant import SmartAssistant

# Setup structured logging
logger = setup_logging(
    level=settings.log_level if hasattr(settings, "log_level") else "INFO",
    structured=getattr(settings, "structured_logging", False),
    log_to_file=True
)

# Startup time for uptime tracking
STARTUP_TIME = time.time()

# Data directories
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


# Background service instances (module-level for status endpoint access)
_email_monitor = EmailMonitor()
_smart_assistant = SmartAssistant()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("OpenWorld starting up...")
    init_database()
    store = SessionStore(settings.sessions_path)
    migrate_json_sessions(settings.sessions_path)
    
    # Track active sessions
    sessions = store.list_sessions()
    chat_sessions_active.set(len(sessions))
    
    # Start background services
    if settings.bg_email_monitor:
        await _email_monitor.start()
    if settings.bg_smart_assistant:
        await _smart_assistant.start()
    
    logger.info(f"OpenWorld started. Sessions: {len(sessions)}")
    yield
    # Shutdown
    _email_monitor.stop()
    _smart_assistant.stop()
    logger.info("OpenWorld shutting down...")


app = FastAPI(
    title="OpenWorld Local Agent",
    description="Yerel Yapay Zeka Asistanı API",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize store and agent
store = SessionStore(settings.sessions_path)
agent = AgentService(store)


@app.exception_handler(OpenWorldException)
async def openworld_exception_handler(request: Request, exc: OpenWorldException):
    """Handle custom exceptions."""
    errors_total.inc(type=exc.error_code)
    logger.error(
        f"OpenWorld exception: {exc.message}",
        extra={"error_code": exc.error_code, "details": exc.details}
    )
    return HTTPException(status_code=exc.status_code, detail=exc.to_dict())


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    errors_total.inc(type="unexpected")
    logger.exception("Unexpected error occurred")
    return HTTPException(status_code=500, detail={"error": "Internal server error"})


@app.get("/health")
async def health() -> dict:
    """Health check endpoint with detailed status."""
    uptime = time.time() - STARTUP_TIME
    
    return {
        "ok": True,
        "version": "0.1.0",
        "llm_backend": settings.llm_backend,
        "model": settings.ollama_model,
        "llama_model_path": str(settings.llama_model_path_abs),
        "workspace": str(settings.workspace_path),
        "shell_tool": settings.enable_shell_tool,
        "uptime_seconds": round(uptime, 2),
        "sessions_count": len(store.list_sessions()),
    }


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    # Update uptime gauge
    uptime_seconds = time.time() - STARTUP_TIME
    from .core.metrics import uptime_seconds as uptime_gauge
    uptime_gauge.set(uptime_seconds)
    
    metrics_data = get_all_metrics()
    return PlainTextResponse(content=metrics_data, media_type="text/plain")


@app.get("/sessions")
async def sessions() -> dict:
    """List all sessions."""
    sessions_list = store.list_sessions()
    chat_sessions_active.set(len(sessions_list))
    return {"sessions": sessions_list}


@app.get("/services/status")
async def services_status() -> dict:
    """Background services status."""
    return {
        "email_monitor": _email_monitor.status,
        "smart_assistant": _smart_assistant.status,
    }


@app.get("/tools/audit")
async def tools_audit(run_probes: bool = True) -> dict:
    """Run tools audit."""
    try:
        with timer(tool_execution_duration, tool_name="tools_audit"):
            result = run_tools_audit(run_probes=run_probes)
            tool_execution_total.inc(tool_name="tools_audit", status="success")
            return result
    except Exception as exc:
        tool_execution_total.inc(tool_name="tools_audit", status="error")
        logger.exception("Tools audit failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Process chat message with full observability."""
    start_time = time.time()
    session_id = req.session_id
    
    logger.info(
        f"Chat request received",
        extra={"session_id": session_id, "source": req.source, "message_length": len(req.message)}
    )
    
    messages_total.inc(role="user", source=req.source)
    
    try:
        with timer(llm_request_duration, model=settings.ollama_model):
            reply, steps, used_tools, media_files = await agent.run(session_id, req.message)
        
        # Track LLM metrics (estimated)
        prompt_tokens = len(req.message.split()) + 100  # Rough estimate
        completion_tokens = len(reply.split())
        llm_tokens_total.inc(model=settings.ollama_model, type="prompt")
        llm_tokens_total.inc(model=settings.ollama_model, type="completion")
        llm_requests_total.inc(model=settings.ollama_model, status="success")
        
        # Track tool executions
        for tool in used_tools:
            tool_execution_total.inc(tool_name=tool, status="success")
        
        # Process media files
        media = _process_media_files(media_files)
        
        # Build response with media links
        if media:
            reply += "\n\n---\n**Medya Dosyaları:**\n"
            for m in media:
                if m.type == "image":
                    reply += f"\n![{m.filename}]({m.url})\n"
                elif m.type == "audio":
                    reply += f"\n🎵 [{m.filename}]({m.url})\n"
                elif m.type == "video":
                    reply += f"\n🎥 [{m.filename}]({m.url})\n"
                elif m.type == "document":
                    reply += f"\n📄 [{m.filename}]({m.url})\n"
        
        duration_ms = (time.time() - start_time) * 1000
        messages_total.inc(role="assistant", source=req.source)
        
        logger.info(
            f"Chat response completed",
            extra={
                "session_id": session_id,
                "duration_ms": duration_ms,
                "steps": steps,
                "tools_used": used_tools,
            }
        )
        
        return ChatResponse(
            session_id=session_id,
            reply=reply,
            steps=steps,
            used_tools=used_tools,
            media=media,
        )
        
    except Exception as exc:
        llm_requests_total.inc(model=settings.ollama_model, status="error")
        errors_total.inc(type="chat")
        logger.exception(f"Chat processing failed for session {session_id}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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

        # data/media/ altına kopyala
        dst = _MEDIA_DIR / src.name
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
        except Exception as e:
            logger.warning(f"Failed to copy media file: {e}")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
