"""LLM Provider configuration manager.

Stores provider configs in data/providers.json.
Supports Ollama (local) and OpenAI-compatible cloud APIs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings

_PROVIDERS_FILE = settings.data_path / "providers.json"

# Default provider definitions
_DEFAULTS: List[Dict[str, Any]] = [
    {
        "id": "ollama",
        "name": "Ollama (Yerel)",
        "type": "ollama",
        "api_key": "",
        "base_url": settings.ollama_base_url,
        "model": settings.ollama_model,
        "models": ["qwen3.5:9b-q4_K_M", "qwen2.5:7b", "llama3.1:8b", "gemma2:9b", "mistral:7b"],
    },
    {
        "id": "groq",
        "name": "Groq",
        "type": "openai_compatible",
        "api_key": "",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "qwen/qwen-3-32b",
        ],
    },
    {
        "id": "zai",
        "name": "Z.AI (Zhipu)",
        "type": "openai_compatible",
        "api_key": "",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "model": "glm-4.7",
        "models": ["glm-5", "glm-4.7", "glm-4.7-flash", "glm-4.6", "glm-4.5-flash"],
    },
    {
        "id": "codex",
        "name": "Codex CLI (OpenAI)",
        "type": "codex_cli",
        "api_key": "",
        "base_url": "",
        "model": "codex-mini-latest",
        "models": ["codex-mini-latest", "o4-mini", "gpt-4.1"],
    },
]


def _load() -> Dict[str, Any]:
    if _PROVIDERS_FILE.exists():
        try:
            data = json.loads(_PROVIDERS_FILE.read_text("utf-8"))
            # Ensure all default providers exist (merge new ones)
            existing_ids = {p["id"] for p in data.get("providers", [])}
            for default in _DEFAULTS:
                if default["id"] not in existing_ids:
                    data["providers"].append(default)
            return data
        except Exception:
            pass
    return _init_defaults()


def _init_defaults() -> Dict[str, Any]:
    data = {
        "active_provider_id": "ollama",
        "providers": [dict(p) for p in _DEFAULTS],
    }
    _save(data)
    return data


def _save(data: Dict[str, Any]) -> None:
    _PROVIDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROVIDERS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), "utf-8"
    )


def get_all_providers() -> List[Dict[str, Any]]:
    data = _load()
    active_id = data.get("active_provider_id", "ollama")
    providers = data.get("providers", [])
    for p in providers:
        p["is_active"] = p["id"] == active_id
    return providers


def get_active_provider_id() -> str:
    data = _load()
    return data.get("active_provider_id", "ollama")


def get_active_provider() -> Dict[str, Any]:
    data = _load()
    active_id = data.get("active_provider_id", "ollama")
    for p in data.get("providers", []):
        if p["id"] == active_id:
            return p
    for p in data.get("providers", []):
        if p["id"] == "ollama":
            return p
    return _DEFAULTS[0]


def update_provider(provider_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    data = _load()
    for p in data.get("providers", []):
        if p["id"] == provider_id:
            for k, v in updates.items():
                if k not in ("id", "is_active"):
                    p[k] = v
            _save(data)
            return p
    raise ValueError(f"Provider not found: {provider_id}")


def set_active_provider(provider_id: str) -> Dict[str, Any]:
    data = _load()
    target = None
    for p in data.get("providers", []):
        if p["id"] == provider_id:
            target = p
            break
    if not target:
        raise ValueError(f"Provider not found: {provider_id}")
    data["active_provider_id"] = provider_id
    _save(data)
    return target
