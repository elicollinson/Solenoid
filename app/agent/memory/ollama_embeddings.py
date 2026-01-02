"""Ollama-based embeddings for the ADK memory store.

This module provides an embedder that uses Ollama's embedding API,
avoiding the threading/multiprocessing issues with sentence-transformers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import httpx
import numpy as np
from sqlite_vec import serialize_float32

LOGGER = logging.getLogger(__name__)

# Default configuration
_DEFAULT_OLLAMA_HOST: Final[str] = "http://localhost:11434"
_DEFAULT_MODEL: Final[str] = "nomic-embed-text"
_DOC_PREFIX: Final[str] = "search_document: "
_QUERY_PREFIX: Final[str] = "search_query: "
CROP_DIM: Final[int] = 256

# Connection settings
_TIMEOUT: Final[float] = 30.0  # seconds


class OllamaEmbedder:
    """Embedder that uses Ollama's embedding API.

    This avoids the threading/multiprocessing issues with sentence-transformers
    by delegating to Ollama as an external service.
    """

    def __init__(
        self,
        *,
        host: str = _DEFAULT_OLLAMA_HOST,
        model: str = _DEFAULT_MODEL,
        crop_dim: int = CROP_DIM,
    ) -> None:
        """Initialize the Ollama embedder.

        Args:
            host: Ollama server URL (default: http://localhost:11434)
            model: Embedding model name (default: nomic-embed-text)
            crop_dim: Dimension to crop embeddings to (default: 256)
        """
        self.host = host.rstrip("/")
        self.model = model
        self.crop_dim = crop_dim
        self._client = httpx.Client(timeout=_TIMEOUT)

    def __del__(self) -> None:
        """Clean up the HTTP client."""
        if hasattr(self, '_client'):
            self._client.close()

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        """L2 normalize a vector."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    def _embed(self, text: str) -> np.ndarray:
        """Generate embedding for text using Ollama API.

        Args:
            text: The text to embed (with prefix already applied)

        Returns:
            L2-normalized, cropped embedding as numpy array

        Raises:
            RuntimeError: If Ollama API call fails
        """
        url = f"{self.host}/api/embed"
        payload = {
            "model": self.model,
            "input": text,
        }

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Ollama returns {"embeddings": [[...vector...]]}
            embeddings = data.get("embeddings", [])
            if not embeddings or not embeddings[0]:
                raise RuntimeError(f"Empty embedding returned for text: {text[:50]}...")

            vec = np.asarray(embeddings[0], dtype=np.float32)

        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.host}. "
                f"Ensure Ollama is running and the model '{self.model}' is available. "
                f"Run: ollama pull {self.model}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama API error: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Embedding failed: {e}") from e

        # L2 normalize
        vec = self._l2_normalize(vec)

        # Crop to target dimension
        vec = vec[:self.crop_dim]

        # Pad if needed (unlikely with nomic-embed-text's 768 dims)
        if vec.shape[0] < self.crop_dim:
            pad = np.zeros(self.crop_dim - vec.shape[0], dtype=np.float32)
            vec = np.concatenate([vec, pad])

        # Re-normalize after cropping
        return self._l2_normalize(vec)

    def embed_doc(self, text: str) -> np.ndarray:
        """Generate embedding for a document.

        Uses the 'search_document: ' prefix as per nomic-embed-text conventions.

        Args:
            text: Document text to embed

        Returns:
            L2-normalized embedding vector
        """
        return self._embed(f"{_DOC_PREFIX}{text}")

    def embed_query(self, text: str) -> np.ndarray:
        """Generate embedding for a search query.

        Uses the 'search_query: ' prefix as per nomic-embed-text conventions.

        Args:
            text: Query text to embed

        Returns:
            L2-normalized embedding vector
        """
        return self._embed(f"{_QUERY_PREFIX}{text}")

    @staticmethod
    def to_blob(vec: np.ndarray) -> bytes:
        """Serialize a vector for storage in sqlite-vec.

        Args:
            vec: Numpy array to serialize

        Returns:
            Bytes suitable for sqlite-vec storage
        """
        return serialize_float32(vec.astype(np.float32, copy=False))

    def save_embedding(self, path: Path, text: str, *, is_query: bool = False) -> None:
        """Generate and save an embedding to a file.

        Args:
            path: File path to save the embedding
            text: Text to embed
            is_query: If True, use query prefix; otherwise use document prefix
        """
        vec = self.embed_query(text) if is_query else self.embed_doc(text)
        path.write_bytes(self.to_blob(vec))


# Type alias for compatibility with existing code
Embedder = OllamaEmbedder


__all__ = ["CROP_DIM", "OllamaEmbedder", "Embedder"]
