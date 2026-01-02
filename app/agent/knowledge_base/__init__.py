# app/agent/knowledge_base/__init__.py
"""
Per-agent knowledge base system.

This module provides isolated knowledge bases for custom agents,
enabling domain-specific RAG (Retrieval Augmented Generation).

Each agent gets its own set of tables:
- kb_{agent_name}_chunks: Document chunks
- kb_{agent_name}_fts: Full-text search index
- kb_{agent_name}_vec: Vector embeddings

The KB system supports:
- Hybrid search (dense + sparse + rerank)
- Document ingestion with chunking
- Lifecycle management (create/delete with agent)
"""

from app.agent.knowledge_base.manager import (
    KnowledgeBaseManager,
    KBStats,
    ChunkData,
    get_kb_manager,
)
from app.agent.knowledge_base.search import (
    KBChunk,
    search_agent_kb,
    format_kb_context,
)
from app.agent.knowledge_base.ingestion import (
    IngestionResult,
    ingest_text,
    ingest_url,
    chunk_text,
)
from app.agent.knowledge_base.callbacks import (
    create_kb_injection_callback,
    get_kb_callback_for_agent,
)

__all__ = [
    # Manager
    "KnowledgeBaseManager",
    "KBStats",
    "ChunkData",
    "get_kb_manager",
    # Search
    "KBChunk",
    "search_agent_kb",
    "format_kb_context",
    # Ingestion
    "IngestionResult",
    "ingest_text",
    "ingest_url",
    "chunk_text",
    # Callbacks
    "create_kb_injection_callback",
    "get_kb_callback_for_agent",
]
