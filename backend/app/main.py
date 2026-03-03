from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .agent import AgentService
from .config import settings
from .memory import SessionStore
from .models import ChatRequest, ChatResponse

store = SessionStore(settings.sessions_path)
agent = AgentService(store)

app = FastAPI(title="OpenWorld Local Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        reply, steps, used_tools = await agent.run(req.session_id, req.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    
    # Detect media files from tool results and reply
    media = _detect_media_files(reply, used_tools)
    
    # Append media links to reply for frontend display
    if media:
        reply += "\n\n---\n📎 **Medya Dosyaları:**\n"
        for m in media:
            url = m["url"]
            filename = m["filename"]
            media_type = m["type"]
            
            if media_type == "image":
                reply += f"\n![{filename}]({url})\n"
                reply += f"🔗 [Görüntüyü İndir: {filename}]({url})\n"
            elif media_type == "audio":
                reply += f"\n🎵 **Ses Dosyası:** [{filename}]({url})\n"
            elif media_type == "video":
                reply += f"\n🎥 **Video:** [{filename}]({url})\n"
            else:
                reply += f"\n📄 **Dosya:** [{filename}]({url})\n"
    
    return ChatResponse(
        session_id=req.session_id,
        reply=reply,
        steps=steps,
        used_tools=used_tools,
        media=media
    )


def _detect_media_files(reply: str, used_tools: List[str]) -> List[dict]:
    """Extract media file references from reply and tool results."""
    import re
    from pathlib import Path
    
    media = []
    data_dir = Path(settings.data_dir).resolve()
    
    # Find all file paths in reply (common patterns)
    file_patterns = [
        # Image files
        (r'(\S+\.(?:png|jpg|jpeg|gif|bmp|webp))', 'image'),
        # Audio files  
        (r'(\S+\.(?:wav|mp3|ogg|m4a|flac))', 'audio'),
        # Video files
        (r'(\S+\.(?:mp4|avi|mkv|mov|webm))', 'video'),
        # Documents
        (r'(\S+\.(?:pdf|docx|xlsx|zip|tar))', 'document'),
    ]
    
    found_files = set()
    for pattern, media_type in file_patterns:
        matches = re.findall(pattern, reply, re.IGNORECASE)
        for match in matches:
            filename = match.strip()
            if filename in found_files:
                continue
            found_files.add(filename)
            
            # Check various locations
            possible_paths = [
                data_dir / filename,
                Path(filename),
                Path.cwd() / filename,
            ]
            
            for file_path in possible_paths:
                if file_path.exists() and file_path.is_file():
                    file_size = file_path.stat().st_size
                    media.append({
                        "type": media_type,
                        "url": f"/data/{filename}",
                        "filename": filename,
                        "caption": f"{media_type.capitalize()}: {filename} ({file_size} bytes)"
                    })
                    break
    
    return media


frontend_dist = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
index_html = frontend_dist / "index.html"

# Static files for frontend assets
if frontend_dist.exists() and index_html.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/")
    async def ui_root() -> FileResponse:
        return FileResponse(str(index_html))

# Static files for user data (screenshots, audio, etc.)
data_dir = Path(settings.data_dir).resolve()
data_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")
