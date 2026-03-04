import logging
from typing import List, Dict, Any, Tuple
import math

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
except ImportError:
    SentenceTransformer = None
    np = None

from app.tools.registry import TOOLS, DEFAULT_TOOL_NAMES

logger = logging.getLogger(__name__)

class SemanticToolSelector:
    def __init__(self):
        self._enabled = SentenceTransformer is not None and np is not None
        self.model = None
        self.tool_embeddings = {}
        self.tool_names = list(TOOLS.keys())
        self._initialized = False

    def _ensure_initialized(self):
        if not self._enabled or self._initialized:
            return
            
        logger.info("Lazy initializing SemanticToolSelector with all-MiniLM-L6-v2...")
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self._compute_tool_embeddings()
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize SemanticToolSelector: {e}")
            self._enabled = False

    def _compute_tool_embeddings(self):
        """Computes embeddings for all tools based on their name and description."""
        texts = []
        for name in self.tool_names:
            spec = TOOLS.get(name, (None, {}))[1]
            desc = spec.get("function", {}).get("description", "")
            # Combine name and description for better semantic matching
            texts.append(f"{name.replace('_', ' ')}: {desc}")
            
        if texts:
            embeddings = self.model.encode(texts)
            for i, name in enumerate(self.tool_names):
                self.tool_embeddings[name] = embeddings[i]

    def _cosine_similarity(self, vec1, vec2) -> float:
        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    def get_relevant_tools(self, user_message: str, top_k: int = 15) -> List[Dict[str, Any]]:
        """Returns the most relevant tools for a given user message."""
        # Always include core tools
        core_tools = {"execute_command", "read_file", "write_file"}
        
        self._ensure_initialized()
        if not user_message.strip() or not self._enabled:
            # Fallback to defaults
            default_pool = list(core_tools) + [name for name in DEFAULT_TOOL_NAMES if name in TOOLS and name not in core_tools]
            return [TOOLS[name][1] for name in default_pool[:top_k]]

        try:
            query_embedding = self.model.encode(user_message)
            
            scored_tools: List[Tuple[float, str]] = []
            for name, emb in self.tool_embeddings.items():
                if name in core_tools:
                    continue # handled separately
                score = self._cosine_similarity(query_embedding, emb)
                scored_tools.append((score, name))
                
            # Sort by similarity descending
            scored_tools.sort(reverse=True, key=lambda x: x[0])
            
            selected_names = list(core_tools)
            
            # Add top semantic matches
            for score, name in scored_tools:
                if len(selected_names) >= top_k:
                    break
                # Only include tools that have a somewhat reasonable similarity to the query
                if score > 0.15:
                    selected_names.append(name)
                    
            return [TOOLS[name][1] for name in selected_names]
            
        except Exception as e:
            logger.error(f"Semantic tool selection failed: {e}")
            default_pool = list(core_tools) + [name for name in DEFAULT_TOOL_NAMES if name in TOOLS and name not in core_tools]
            return [TOOLS[name][1] for name in default_pool[:top_k]]

# Singleton instance
tool_selector = SemanticToolSelector()

def get_semantic_tools(user_message: str, top_k: int = 15) -> List[Dict[str, Any]]:
    return tool_selector.get_relevant_tools(user_message, top_k)
