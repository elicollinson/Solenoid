"""Database helpers for persisting ADK memories locally."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

import sqlite_vec

from .embeddings import NomicLocalEmbedder

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
EMB = NomicLocalEmbedder()


def connect_db(
    path: str | Path,
    *,
    initialize: bool = True,
    pragmas: Sequence[tuple[str, str]] | None = None,
) -> sqlite3.Connection:
    """Open a SQLite connection, load sqlite-vec, and optionally apply the schema."""

    conn = sqlite3.connect(str(path), check_same_thread=False)
    if pragmas is None:
        pragmas = (("journal_mode", "WAL"), ("synchronous", "NORMAL"))
    for key, value in pragmas:
        conn.execute(f"PRAGMA {key}={value}")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)  # type: ignore[attr-defined]
    conn.enable_load_extension(False)
    if initialize:
        apply_schema(conn)
    return conn


def apply_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    script_path = schema_path or SCHEMA_PATH
    script = script_path.read_text(encoding="utf-8")
    conn.executescript(script)


def _ensure_embedder(embedder: NomicLocalEmbedder | None) -> NomicLocalEmbedder:
    return embedder or EMB


def upsert_memory(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    app_name: str,
    memory_type: str,
    text: str,
    source: str | None = None,
    importance: int = 1,
    tags: Iterable[str] | None = None,
    expires_at: int | None = None,
    embedder: NomicLocalEmbedder | None = None,
) -> int:
    """Insert a single memory row and its embedding."""

    ts = int(time.time() * 1000)
    tag_list = list(tags or [])
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO memories(user_id, app_name, memory_type, text, source, importance, tags_json, created_at, expires_at)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            app_name,
            memory_type,
            text,
            source,
            importance,
            json.dumps(tag_list, ensure_ascii=False),
            ts,
            expires_at,
        ),
    )
    mem_id = int(cur.lastrowid)

    emb = _ensure_embedder(embedder)
    vec = emb.embed_doc(text)
    cur.execute(
        """
        INSERT INTO memories_vec(rowid, embedding, mem_id)
        VALUES(?, ?, ?)
        """,
        (mem_id, emb.to_blob(vec), mem_id),
    )
    conn.commit()
    return mem_id


def upsert_kb_chunk(
    conn: sqlite3.Connection,
    *,
    title: str,
    text: str,
    meta: dict | None = None,
    doc_id: str | None = None,
    embedder: NomicLocalEmbedder | None = None,
) -> int:
    """Insert a knowledge-base chunk and its vector."""

    ts = int(time.time() * 1000)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO kb_chunks(doc_id, title, text, meta_json, created_at)
        VALUES(?,?,?,?,?)
        """,
        (doc_id, title, text, json.dumps(meta or {}, ensure_ascii=False), ts),
    )
    chunk_id = int(cur.lastrowid)

    emb = _ensure_embedder(embedder)
    vec = emb.embed_doc(text)
    cur.execute(
        "INSERT INTO kb_vec(rowid, embedding, chunk_id) VALUES(?,?,?)",
        (chunk_id, emb.to_blob(vec), chunk_id),
    )
    conn.commit()
    return chunk_id


__all__ = [
    "EMB",
    "apply_schema",
    "connect_db",
    "upsert_kb_chunk",
    "upsert_memory",
]
