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
    return ChatResponse(session_id=req.session_id, reply=reply, steps=steps, used_tools=used_tools)


frontend_dist = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
index_html = frontend_dist / "index.html"

if frontend_dist.exists() and index_html.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/")
    async def ui_root() -> FileResponse:
        return FileResponse(str(index_html))
