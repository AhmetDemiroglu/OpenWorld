from __future__ import annotations

from typing import Any, Dict

from ...database import get_tool_stats
from ...vector_memory import memory_store, memory_recall


def tool_memory_store(fact: str, source: str = "conversation", category: str = "general") -> Dict[str, Any]:
    """Uzun sureli hafizaya bilgi kaydet."""
    return memory_store(fact=fact, source=source, category=category)


def tool_memory_recall(query: str = "", category: str = "", limit: int = 10) -> Dict[str, Any]:
    """Hafizadan bilgi cagir."""
    return memory_recall(query=query, category=category, limit=limit)


def tool_memory_stats() -> Dict[str, Any]:
    """Hafiza ve arac kullanim istatistiklerini dondur."""
    return get_tool_stats(days=7)
