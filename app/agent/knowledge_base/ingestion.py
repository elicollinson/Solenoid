# app/agent/knowledge_base/ingestion.py
"""
Content ingestion pipeline for agent knowledge bases.

Handles:
- Fetching content from URLs
- Chunking text into appropriately sized pieces
- Batch embedding and storage
"""

import logging
import uuid
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.agent.knowledge_base.manager import (
    KnowledgeBaseManager,
    ChunkData,
    get_kb_manager,
)

LOGGER = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 500  # tokens (approximate)
DEFAULT_CHUNK_OVERLAP = 50  # tokens overlap between chunks
CHARS_PER_TOKEN = 4  # Rough approximation


@dataclass
class IngestionResult:
    """Result of ingesting content into KB."""

    doc_id: str
    title: Optional[str]
    url: Optional[str]
    chunk_count: int
    total_chars: int
    success: bool
    error: Optional[str] = None


def fetch_url_content(url: str, timeout: int = 30) -> tuple[str, Optional[str]]:
    """
    Fetch and extract text content from a URL.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (text_content, title)
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; KnowledgeBot/1.0)"
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Get title
        title = None
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text content
        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        text = "\n".join(line for line in lines if line)

        return text, title

    except Exception as e:
        LOGGER.error(f"Failed to fetch URL {url}: {e}")
        raise


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split text into overlapping chunks.

    Uses a simple sentence-aware chunking strategy:
    1. Split by paragraphs/sentences
    2. Combine until chunk size reached
    3. Overlap by specified amount

    Args:
        text: The text to chunk
        chunk_size: Target size in tokens (approximate)
        chunk_overlap: Overlap between chunks in tokens

    Returns:
        List of text chunks
    """
    # Convert token counts to character counts
    target_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = chunk_overlap * CHARS_PER_TOKEN

    if len(text) <= target_chars:
        return [text] if text.strip() else []

    # Split into sentences (simple regex)
    sentence_pattern = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_pattern.split(text)

    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_length = len(sentence)

        if current_length + sentence_length > target_chars and current_chunk:
            # Save current chunk
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)

            # Start new chunk with overlap
            # Take sentences from end that fit in overlap
            overlap_sentences = []
            overlap_length = 0
            for s in reversed(current_chunk):
                if overlap_length + len(s) <= overlap_chars:
                    overlap_sentences.insert(0, s)
                    overlap_length += len(s)
                else:
                    break

            current_chunk = overlap_sentences
            current_length = overlap_length

        current_chunk.append(sentence)
        current_length += sentence_length

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def ingest_text(
    agent_name: str,
    text: str,
    title: Optional[str] = None,
    url: Optional[str] = None,
    doc_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    manager: Optional[KnowledgeBaseManager] = None,
) -> IngestionResult:
    """
    Ingest text content into an agent's knowledge base.

    Args:
        agent_name: The agent's name
        text: The text content to ingest
        title: Optional document title
        url: Optional source URL
        doc_id: Optional document ID (generated if not provided)
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks
        manager: Optional KB manager (uses global if not provided)

    Returns:
        IngestionResult with details
    """
    if not text.strip():
        return IngestionResult(
            doc_id="",
            title=title,
            url=url,
            chunk_count=0,
            total_chars=0,
            success=False,
            error="Empty text content",
        )

    doc_id = doc_id or str(uuid.uuid4())
    kb_manager = manager or get_kb_manager()

    try:
        # Ensure KB exists
        kb_manager.ensure_kb_exists(agent_name)

        # Chunk the text
        chunks = chunk_text(text, chunk_size, chunk_overlap)

        if not chunks:
            return IngestionResult(
                doc_id=doc_id,
                title=title,
                url=url,
                chunk_count=0,
                total_chars=len(text),
                success=False,
                error="No chunks generated from text",
            )

        # Create chunk data objects
        chunk_data_list = [
            ChunkData(
                doc_id=doc_id,
                title=title,
                url=url,
                text=chunk_text,
                chunk_index=i,
            )
            for i, chunk_text in enumerate(chunks)
        ]

        # Add chunks with embeddings
        kb_manager.add_chunks(agent_name, chunk_data_list, embed=True)

        LOGGER.info(
            f"Ingested {len(chunks)} chunks for doc '{title or doc_id}' "
            f"into KB for agent {agent_name}"
        )

        return IngestionResult(
            doc_id=doc_id,
            title=title,
            url=url,
            chunk_count=len(chunks),
            total_chars=sum(len(c) for c in chunks),
            success=True,
        )

    except Exception as e:
        LOGGER.error(f"Ingestion failed for agent {agent_name}: {e}")
        return IngestionResult(
            doc_id=doc_id,
            title=title,
            url=url,
            chunk_count=0,
            total_chars=0,
            success=False,
            error=str(e),
        )


def ingest_url(
    agent_name: str,
    url: str,
    doc_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    manager: Optional[KnowledgeBaseManager] = None,
) -> IngestionResult:
    """
    Fetch and ingest content from a URL into an agent's KB.

    Args:
        agent_name: The agent's name
        url: The URL to fetch and ingest
        doc_id: Optional document ID
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks
        manager: Optional KB manager

    Returns:
        IngestionResult with details
    """
    try:
        # Fetch content
        text, title = fetch_url_content(url)

        if not text:
            return IngestionResult(
                doc_id=doc_id or "",
                title=title,
                url=url,
                chunk_count=0,
                total_chars=0,
                success=False,
                error="No content extracted from URL",
            )

        # Use URL domain as fallback title
        if not title:
            parsed = urlparse(url)
            title = parsed.netloc

        return ingest_text(
            agent_name=agent_name,
            text=text,
            title=title,
            url=url,
            doc_id=doc_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            manager=manager,
        )

    except Exception as e:
        return IngestionResult(
            doc_id=doc_id or "",
            title=None,
            url=url,
            chunk_count=0,
            total_chars=0,
            success=False,
            error=str(e),
        )


__all__ = [
    "IngestionResult",
    "fetch_url_content",
    "chunk_text",
    "ingest_text",
    "ingest_url",
]
