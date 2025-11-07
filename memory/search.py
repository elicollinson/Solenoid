"""Hybrid search routines that combine sqlite-vec KNN, FTS5 BM25, and reranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import sqlite3

from .embeddings import NomicLocalEmbedder
from .rerank import DEFAULT_RERANKER, rerank_texts

EMB = NomicLocalEmbedder()


@dataclass(slots=True)
class MemoryRow:
    id: int
    text: str
    memory_type: str
    source: str | None
    importance: int


def _rrf(rank: int) -> float:
    return 1.0 / (60.0 + rank)


def _row_from_record(record: Sequence) -> MemoryRow:
    return MemoryRow(
        id=int(record[0]),
        text=str(record[1]),
        memory_type=str(record[2]),
        source=(record[3] if record[3] is not None else None),
        importance=int(record[4]),
    )


def _hybrid_candidates(
    conn: sqlite3.Connection,
    *,
    query_text: str,
    user_id: str,
    app_name: str,
    dense_limit: int,
    sparse_limit: int,
    fuse_top_k: int,
    embedder: NomicLocalEmbedder,
) -> List[MemoryRow]:
    qvec = embedder.embed_query(query_text)
    qblob = embedder.to_blob(qvec)

    dense_rows = conn.execute(
        """
        SELECT m.id, m.text, m.memory_type, m.source, m.importance, v.distance
        FROM memories_vec AS v
        JOIN memories AS m ON m.id = v.rowid
        WHERE m.user_id = ? AND m.app_name = ? AND v.embedding MATCH ?
        ORDER BY v.distance
        LIMIT ?
        """,
        (user_id, app_name, qblob, dense_limit),
    ).fetchall()

    sparse_rows = conn.execute(
        """
        SELECT m.id, m.text, m.memory_type, m.source, m.importance, bm25(memories_fts) AS bm25_score
        FROM memories_fts
        JOIN memories AS m ON memories_fts.rowid = m.id
        WHERE m.user_id = ? AND m.app_name = ? AND memories_fts MATCH ?
        ORDER BY bm25_score
        LIMIT ?
        """,
        (user_id, app_name, query_text, sparse_limit),
    ).fetchall()

    scores: dict[int, float] = {}
    candidates: dict[int, MemoryRow] = {}

    for rank, record in enumerate(dense_rows, start=1):
        row = _row_from_record(record)
        candidates[row.id] = row
        scores[row.id] = scores.get(row.id, 0.0) + _rrf(rank)

    for rank, record in enumerate(sparse_rows, start=1):
        row = _row_from_record(record)
        candidates[row.id] = row
        scores[row.id] = scores.get(row.id, 0.0) + _rrf(rank)

    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:fuse_top_k]
    return [candidates[row_id] for row_id, _ in fused]


def search_memories(
    conn: sqlite3.Connection,
    query_text: str,
    user_id: str,
    app_name: str,
    *,
    top_n: int = 12,
    dense_limit: int = 80,
    sparse_limit: int = 80,
    fuse_top_k: int = 30,
    reranker_model: str = DEFAULT_RERANKER,
    embedder: NomicLocalEmbedder | None = None,
) -> list[tuple[str, float, MemoryRow]]:
    """Return reranked memories for the calling agent."""

    emb = embedder or EMB
    if dense_limit <= 0 and sparse_limit <= 0:
        return []

    candidates = _hybrid_candidates(
        conn,
        query_text=query_text,
        user_id=user_id,
        app_name=app_name,
        dense_limit=max(dense_limit, 0),
        sparse_limit=max(sparse_limit, 0),
        fuse_top_k=fuse_top_k,
        embedder=emb,
    )

    if not candidates:
        return []

    texts = [row.text for row in candidates]
    reranked = rerank_texts(
        query=query_text,
        texts=texts,
        top_n=min(top_n, len(texts)),
        model_name=reranker_model,
    )

    hits: list[tuple[str, float, MemoryRow]] = []
    for idx, score in reranked:
        row = candidates[idx]
        hits.append((row.text, float(score), row))
    return hits


__all__ = ["MemoryRow", "search_memories"]
