"""Local SQLite + sqlite-vec memory stack for Google ADK."""

from .ollama_embeddings import CROP_DIM, OllamaEmbedder
from .ingestion import connect_db, upsert_kb_chunk, upsert_memory
from .search import search_memories

# Backwards compatibility alias
Embedder = OllamaEmbedder

__all__ = [
    "CROP_DIM",
    "OllamaEmbedder",
    "Embedder",
    "connect_db",
    "search_memories",
    "upsert_kb_chunk",
    "upsert_memory",
]
