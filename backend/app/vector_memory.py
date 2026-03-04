import logging
from typing import List, Dict, Any, Optional
import os
from pathlib import Path
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
except ImportError:
    chromadb = None
    SentenceTransformer = None

from app.config import settings
from app.database import memory_store as sqlite_memory_store

logger = logging.getLogger(__name__)

class VectorMemory:
    def __init__(self):
        self._enabled = chromadb is not None
        if not self._enabled:
            logger.warning("ChromaDB/SentenceTransformers not installed. Falling back to SQLite memory only.")
            return
            
        self.db_path = str(settings.data_path / "chroma_db")
        os.makedirs(self.db_path, exist_ok=True)
        
        try:
            # We use a persistent ChromaDB client
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # Using a lightweight local embedding model
            # For a production agent, you might want to switch to Ollama embeddings or an OpenAI model
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Create or get the collection
            self.collection = self.client.get_or_create_collection(
                name="openworld_memory",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("Vector memory initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self._enabled = False

    def store(self, fact: str, source: str = "conversation", category: str = "general", confidence: float = 0.7) -> Dict[str, Any]:
        """Stores a fact in both vector db and SQLite."""
        # 1. Fallback / Synchronize with SQLite
        sql_result = sqlite_memory_store(fact, source, category, confidence)
        
        if not self._enabled:
            return sql_result
            
        # 2. Add to Vector DB
        try:
            # Generate ID from SQLite if available, else standard hash
            doc_id = str(sql_result.get("id", hash(fact)))
            
            # Get embeddings
            embedding = self.embedding_model.encode(fact).tolist()
            
            self.collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[fact],
                metadatas=[{
                    "source": source,
                    "category": category,
                    "confidence": confidence,
                    "sql_id": sql_result.get("id", 0)
                }]
            )
            return {"action": "stored_vector", "fact": fact, "category": category}
        except Exception as e:
            logger.error(f"Vector DB store failed: {e}")
            return sql_result # Still return the SQLite success

    def recall(self, query: str = "", category: str = "", limit: int = 10, threshold: float = 1.5) -> Dict[str, Any]:
        """Recalls facts semantically using vector search."""
        if not self._enabled or not query.strip():
            # Fallback to SQLite text search if no vector db or empty query
            from app.database import memory_recall as sqlite_recall
            return sqlite_recall(query, category, limit)

        try:
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Metadata filter if category is provided
            where_clause = {"category": category} if category.strip() else None
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_clause
            )
            
            facts = []
            if results and "documents" in results and results["documents"]:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if "metadatas" in results and results["metadatas"] else []
                dists = results["distances"][0] if "distances" in results and results["distances"] else []
                
                for i in range(len(docs)):
                    # dists is L2 or Cosine distance. Lower is better. Filter out bad generic matches.
                    if dists and dists[i] > threshold:
                        continue
                        
                    meta = metas[i] if i < len(metas) else {}
                    facts.append({
                        "fact": docs[i],
                        "source": meta.get("source", "unknown"),
                        "category": meta.get("category", "general"),
                        "confidence": meta.get("confidence", 0.7),
                        "distance": dists[i] if dists else 0.0
                    })
                    
            return {
                "facts": facts,
                "count": len(facts),
                "query": query,
                "mode": "semantic"
            }
            
        except Exception as e:
            logger.error(f"Vector DB recall failed: {e}")
            from app.database import memory_recall as sqlite_recall
            return sqlite_recall(query, category, limit)

    def get_context(self, limit: int = 10) -> List[str]:
        # Context usually just pulls most confident/recent facts. 
        # We can just delegate this to the SQLite store since vector DB doesn't easily sort by "most accessed" natively without a query.
        from app.database import memory_get_context as sqlite_get_context
        return sqlite_get_context(limit)

# Singleton instance
vector_db = VectorMemory()

def memory_store(fact: str, source: str = "conversation", category: str = "general", confidence: float = 0.7) -> Dict[str, Any]:
    return vector_db.store(fact, source, category, confidence)

def memory_recall(query: str = "", category: str = "", limit: int = 10) -> Dict[str, Any]:
    return vector_db.recall(query, category, limit)

def memory_get_context(limit: int = 10) -> List[str]:
    return vector_db.get_context(limit)
