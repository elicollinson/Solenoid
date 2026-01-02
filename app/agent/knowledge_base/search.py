# app/agent/knowledge_base/search.py
"""
Scoped search for agent knowledge bases.

Uses the same hybrid search pattern as the memory system:
1. Dense search (vector KNN via sqlite-vec)
2. Sparse search (BM25 via FTS5)
3. Reciprocal Rank Fusion (RRF)
4. Reranking with BGE reranker

Each search is scoped to a specific agent's KB tables.
"""

import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional, Sequence

from app.agent.knowledge_base.schema import get_table_names, validate_agent_name
from app.agent.memory.ollama_embeddings import OllamaEmbedder
from app.agent.memory.rerank import DEFAULT_RERANKER, rerank_texts
from app.agent.config import get_embedding_config

LOGGER = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "memories.db"

# Lazy-initialized embedder
_EMBEDDER: Optional[OllamaEmbedder] = None


def _get_embedder() -> OllamaEmbedder:
    """Get or create the embedder instance using Ollama config."""
    global _EMBEDDER
    if _EMBEDDER is None:
        embed_config = get_embedding_config()
        _EMBEDDER = OllamaEmbedder(
            host=embed_config["host"],
            model=embed_config["model"],
        )
    return _EMBEDDER


@dataclass(slots=True)
class KBChunk:
    """A chunk from an agent's knowledge base."""

    id: int
    doc_id: str
    title: Optional[str]
    url: Optional[str]
    text: str
    chunk_index: int


def _rrf(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score."""
    return 1.0 / (k + rank)


def _chunk_from_record(record: Sequence) -> KBChunk:
    """Convert a database record to a KBChunk."""
    return KBChunk(
        id=int(record[0]),
        doc_id=str(record[1]),
        title=record[2] if record[2] else None,
        url=record[3] if record[3] else None,
        text=str(record[4]),
        chunk_index=int(record[5]) if record[5] else 0,
    )


def _hybrid_candidates(
    conn: sqlite3.Connection,
    agent_name: str,
    query_text: str,
    dense_limit: int,
    sparse_limit: int,
    fuse_top_k: int,
    embedder: OllamaEmbedder,
) -> list[KBChunk]:
    """
    Get hybrid search candidates using dense + sparse search with RRF fusion.

    Args:
        conn: Database connection
        agent_name: The agent's name
        query_text: The search query
        dense_limit: Max results from vector search
        sparse_limit: Max results from FTS search
        fuse_top_k: Number of results after fusion
        embedder: Embedder for query vectors

    Returns:
        List of KBChunk candidates
    """
    tables = get_table_names(agent_name)

    # Get query embedding
    qvec = embedder.embed_query(query_text)
    qblob = embedder.to_blob(qvec)

    # Dense search (vector KNN)
    try:
        dense_rows = conn.execute(
            f"""
            SELECT c.id, c.doc_id, c.title, c.url, c.text, c.chunk_index, v.distance
            FROM {tables['vec']} AS v
            JOIN {tables['chunks']} AS c ON c.id = v.chunk_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            LIMIT ?
            """,
            (qblob, dense_limit, dense_limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        LOGGER.warning(f"Dense search failed for {agent_name}: {e}")
        dense_rows = []

    # Sparse search (FTS5 BM25)
    # Sanitize query for FTS5
    safe_query = "".join(c for c in query_text if c.isalnum() or c.isspace())

    try:
        sparse_rows = conn.execute(
            f"""
            SELECT c.id, c.doc_id, c.title, c.url, c.text, c.chunk_index, bm25({tables['fts']}) AS bm25_score
            FROM {tables['fts']}
            JOIN {tables['chunks']} AS c ON {tables['fts']}.rowid = c.id
            WHERE {tables['fts']} MATCH ?
            ORDER BY bm25_score
            LIMIT ?
            """,
            (safe_query, sparse_limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        LOGGER.warning(f"Sparse search failed for {agent_name}: {e}")
        sparse_rows = []

    # RRF fusion
    scores: dict[int, float] = {}
    candidates: dict[int, KBChunk] = {}

    for rank, record in enumerate(dense_rows, start=1):
        chunk = _chunk_from_record(record)
        candidates[chunk.id] = chunk
        scores[chunk.id] = scores.get(chunk.id, 0.0) + _rrf(rank)

    for rank, record in enumerate(sparse_rows, start=1):
        chunk = _chunk_from_record(record)
        candidates[chunk.id] = chunk
        scores[chunk.id] = scores.get(chunk.id, 0.0) + _rrf(rank)

    # Sort by fused score and take top k
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:fuse_top_k]
    return [candidates[chunk_id] for chunk_id, _ in fused]


def search_agent_kb(
    agent_name: str,
    query_text: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    top_n: int = 10,
    dense_limit: int = 50,
    sparse_limit: int = 50,
    fuse_top_k: int = 20,
    reranker_model: str = DEFAULT_RERANKER,
    min_score: float = 0.0,
) -> list[tuple[str, float, KBChunk]]:
    """
    Search an agent's knowledge base with hybrid search and reranking.

    Args:
        agent_name: The agent's name
        query_text: The search query
        db_path: Path to the database
        top_n: Number of final results to return
        dense_limit: Max results from vector search
        sparse_limit: Max results from FTS search
        fuse_top_k: Number of candidates for reranking
        reranker_model: Model to use for reranking
        min_score: Minimum reranker score to include

    Returns:
        List of (text, score, chunk) tuples, sorted by relevance
    """
    if not validate_agent_name(agent_name):
        raise ValueError(f"Invalid agent name: {agent_name}")

    if not query_text.strip():
        return []

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    import sqlite_vec

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    try:
        embedder = _get_embedder()

        # Get hybrid candidates
        candidates = _hybrid_candidates(
            conn,
            agent_name,
            query_text,
            dense_limit=dense_limit,
            sparse_limit=sparse_limit,
            fuse_top_k=fuse_top_k,
            embedder=embedder,
        )

        if not candidates:
            return []

        # Rerank candidates
        texts = [chunk.text for chunk in candidates]
        reranked = rerank_texts(
            query=query_text,
            texts=texts,
            top_n=min(top_n, len(texts)),
            model_name=reranker_model,
        )

        # Build results with score filtering
        results: list[tuple[str, float, KBChunk]] = []
        for idx, score in reranked:
            if score >= min_score:
                chunk = candidates[idx]
                results.append((chunk.text, float(score), chunk))

        LOGGER.debug(
            f"KB search for {agent_name}: {len(candidates)} candidates, "
            f"{len(results)} results after reranking"
        )

        return results

    except Exception as e:
        LOGGER.error(f"KB search failed for {agent_name}: {e}")
        return []

    finally:
        conn.close()


def format_kb_context(
    results: list[tuple[str, float, KBChunk]],
    max_length: int = 4000,
) -> str:
    """
    Format KB search results as context for injection into agent prompts.

    Args:
        results: Search results from search_agent_kb
        max_length: Maximum total length of formatted context

    Returns:
        Formatted context string
    """
    if not results:
        return ""

    lines = ["## Relevant Knowledge Base Content:\n"]
    current_length = len(lines[0])

    for i, (text, score, chunk) in enumerate(results, 1):
        # Format chunk info
        source = ""
        if chunk.title:
            source = f" (from: {chunk.title})"
        elif chunk.url:
            source = f" (from: {chunk.url})"

        chunk_text = f"[{i}]{source}:\n{text}\n\n"

        if current_length + len(chunk_text) > max_length:
            break

        lines.append(chunk_text)
        current_length += len(chunk_text)

    return "".join(lines)


__all__ = ["KBChunk", "search_agent_kb", "format_kb_context"]
