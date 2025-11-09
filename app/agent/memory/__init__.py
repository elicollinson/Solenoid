"""Local SQLite + sqlite-vec memory stack for Google ADK."""

from .embeddings import CROP_DIM, NomicLocalEmbedder
from .ingestion import connect_db, upsert_kb_chunk, upsert_memory
from .search import search_memories

__all__ = [
    "CROP_DIM",
    "NomicLocalEmbedder",
    "connect_db",
    "search_memories",
    "upsert_kb_chunk",
    "upsert_memory",
]
