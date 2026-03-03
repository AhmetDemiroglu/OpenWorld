from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: Role
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=10000)
    source: Literal["web", "telegram"] = "web"


class MediaAttachment(BaseModel):
    type: Literal["image", "audio", "video", "document"]
    url: str
    filename: str
    caption: str = ""


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    steps: int
    used_tools: List[str]
    media: List[MediaAttachment] = []


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]

