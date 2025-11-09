"""Utility tools and helper agent for storing/retrieving memories via ADK."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.load_memory_tool import load_memory

from .adk_sqlite_memory import SqliteMemoryService
from .ingestion import connect_db, upsert_memory
from .search import search_memories

DEFAULT_DB_PATH = Path("memories.db")
_DB_CONN: sqlite3.Connection | None = None
_MEMORY_SERVICE: SqliteMemoryService | None = None


def _get_conn() -> sqlite3.Connection:
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = connect_db(DEFAULT_DB_PATH)
    return _DB_CONN


def _get_memory_service() -> SqliteMemoryService:
    global _MEMORY_SERVICE
    if _MEMORY_SERVICE is None:
        _MEMORY_SERVICE = SqliteMemoryService(DEFAULT_DB_PATH)
    return _MEMORY_SERVICE


def store_memory(
    user_id: str,
    app_name: str,
    text: str,
    memory_type: str = "semantic",
    importance: int = 1,
    tags: Optional[list[str]] = None,
    ttl_ms: Optional[int] = None,
) -> str:
    conn = _get_conn()
    mem_id = upsert_memory(
        conn,
        user_id=user_id,
        app_name=app_name,
        memory_type=memory_type,
        text=text,
        source="tool:store_memory",
        importance=importance,
        tags=tags,
        expires_at=ttl_ms,
    )
    return f"stored:{mem_id}"


def retrieve_memory(
    user_id: str,
    app_name: str,
    query: str,
    top_n: int = 12,
) -> str:
    conn = _get_conn()
    service = _get_memory_service()
    rows = search_memories(
        conn,
        query,
        user_id,
        app_name,
        top_n=top_n,
        dense_limit=service.dense_candidates,
        sparse_limit=service.sparse_candidates,
        fuse_top_k=service.fuse_top_k,
        reranker_model=service.reranker_model,
        embedder=service.embedder,
    )
    payload = [
        {
            "text": text,
            "score": float(score),
            "type": row.memory_type,
            "source": row.source,
            "importance": row.importance,
            "id": row.id,
        }
        for text, score, row in rows
    ]
    return json.dumps(payload, ensure_ascii=False)


StoreMemoryTool = FunctionTool(func=store_memory)
RetrieveMemoryTool = FunctionTool(func=retrieve_memory)

memory_agent = Agent(
    model="gemma2-2b-it",
    name="MemoryAgent",
    instruction=(
        "You manage the user's long-term memory. Use store_memory to persist facts and "
        "retrieve_memory to answer questions about prior preferences or episodes."
    ),
    tools=[StoreMemoryTool, RetrieveMemoryTool, load_memory],
)

__all__ = [
    "RetrieveMemoryTool",
    "StoreMemoryTool",
    "memory_agent",
    "retrieve_memory",
    "store_memory",
]
