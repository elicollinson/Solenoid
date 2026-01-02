"""ADK memory service backed by SQLite, FTS5, and sqlite-vec."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:  # ADK recently moved Session under google.adk.sessions.session
    from google.adk.sessions import Session
except ImportError:  # pragma: no cover - fallback for older package
    from google.adk.sessions.session import Session  # type: ignore

from google.adk.memory import BaseMemoryService
from google.genai.types import Content, Part

from .ollama_embeddings import OllamaEmbedder
from .ingestion import connect_db, upsert_memory
from .search import MemoryRow, search_memories

# Use file-based logging to avoid Textual UI interference
_MEMORY_LOG_FILE = Path("memory_debug.log")
_file_handler = logging.FileHandler(_MEMORY_LOG_FILE, mode='a')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

LOGGER = logging.getLogger("memory.adk_sqlite_memory")
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(_file_handler)
LOGGER.propagate = False

MemoryExtractor = Callable[[Session, str], Iterable[dict]]


class SqliteMemoryService(BaseMemoryService):
    """Implements ADK's memory contract with local persistence."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        ollama_host: str = "http://localhost:11434",
        embedding_model: str = "nomic-embed-text",
        dense_candidates: int = 80,
        sparse_candidates: int = 80,
        fuse_top_k: int = 30,
        rerank_top_n: int = 12,
        reranker_model: str | None = None,
        max_events: int = 20,
        extractor: MemoryExtractor | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.conn = connect_db(self.db_path)
        self.embedder = OllamaEmbedder(host=ollama_host, model=embedding_model)
        self.dense_candidates = dense_candidates
        self.sparse_candidates = sparse_candidates
        self.fuse_top_k = fuse_top_k
        self.rerank_top_n = rerank_top_n
        self.reranker_model = reranker_model or "BAAI/bge-reranker-v2-m3"
        self.max_events = max_events
        self.extractor = extractor

    async def add_session_to_memory(self, session: Session) -> None:  # type: ignore[override]
        LOGGER.info(f"[MemoryService] add_session_to_memory called")
        LOGGER.info(f"[MemoryService] Session ID: {session.id}, User: {session.user_id}, App: {session.app_name}")

        events = getattr(session, "events", None) or []
        LOGGER.info(f"[MemoryService] Session has {len(events)} events")

        # Debug: Log event details
        for i, event in enumerate(events[-5:] if len(events) > 5 else events):  # Log last 5 events
            content = getattr(event, "content", None)
            parts_count = len(content.parts) if content and hasattr(content, 'parts') else 0
            LOGGER.debug(f"[MemoryService]   Event {i}: {type(event).__name__}, parts: {parts_count}")

        tail_text = self._tail_text(events)
        LOGGER.info(f"[MemoryService] Extracted tail_text length: {len(tail_text)} chars")
        if tail_text:
            preview = tail_text[:200] + "..." if len(tail_text) > 200 else tail_text
            LOGGER.debug(f"[MemoryService] tail_text preview: {preview}")

        if not tail_text:
            LOGGER.warning("[MemoryService] tail_text is EMPTY - skipping memory extraction")
            return

        LOGGER.info("[MemoryService] Calling extractor...")
        memories = list(self._extract_memories(session, tail_text))
        LOGGER.info(f"[MemoryService] Extractor returned {len(memories)} memories")

        if not memories:
            LOGGER.warning("[MemoryService] No memories extracted - nothing to persist")
            return

        for i, mem in enumerate(memories):
            LOGGER.info(f"[MemoryService] Persisting memory {i+1}: {mem.get('text', '')[:50]}...")
            try:
                mem_id = upsert_memory(
                    self.conn,
                    user_id=session.user_id,
                    app_name=session.app_name,
                    memory_type=mem.get("type", "semantic"),
                    text=mem.get("text", ""),
                    source=mem.get("source", f"session:{session.id}"),
                    importance=int(mem.get("importance", 1)),
                    tags=mem.get("tags"),
                    expires_at=mem.get("ttl"),
                    embedder=self.embedder,
                )
                LOGGER.info(f"[MemoryService] Successfully persisted memory with ID: {mem_id}")
            except Exception as e:  # pragma: no cover - defensive logging
                LOGGER.exception(f"Failed to persist extracted memory: {e}")

    async def search_memory(  # type: ignore[override]
        self,
        query: str,
        *,
        user_id: str,
        app_name: str,
        top_n: int = 12,
    ) -> Content:
        hits = search_memories(
            self.conn,
            query,
            user_id,
            app_name,
            top_n=min(top_n, self.rerank_top_n),
            dense_limit=self.dense_candidates,
            sparse_limit=self.sparse_candidates,
            fuse_top_k=self.fuse_top_k,
            reranker_model=self.reranker_model,
            embedder=self.embedder,
        )

        parts = [self._row_to_part(text, score, row) for text, score, row in hits]
        return Content(parts=parts)

    def _tail_text(self, events: Sequence) -> str:
        snippets: list[str] = []
        if not events:
            return ""
        for event in events[-self.max_events :]:
            content = getattr(event, "content", None)
            if not content or not getattr(content, "parts", None):
                continue
            text_parts = []
            for part in content.parts:
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(text)
            if text_parts:
                snippets.append("\n".join(text_parts))
        return "\n".join(snippets)

    def _extract_memories(self, session: Session, tail: str) -> Iterable[dict]:
        if self.extractor:
            try:
                return self.extractor(session, tail) or []
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Custom memory extractor crashed")
        return []

    @staticmethod
    def _row_to_part(text: str, score: float, row: MemoryRow) -> Part:
        payload = {
            "text": text,
            "score": float(score),
            "type": row.memory_type,
            "source": row.source,
            "importance": row.importance,
            "id": row.id,
        }
        return Part(text=json.dumps(payload, ensure_ascii=False))


__all__ = ["SqliteMemoryService"]
