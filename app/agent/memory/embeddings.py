"""Local embeddings for the ADK memory store."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
from sentence_transformers import SentenceTransformer
from sqlite_vec import serialize_float32

_LOCAL_MODELS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "resources" / "models"
_MODEL_CACHE: dict[tuple[str, str | None], SentenceTransformer] = {}
_MODEL_NAME: Final[str] = "nomic-ai/nomic-embed-text-v1.5"
_DOC_PREFIX: Final[str] = "search_document: "
_QUERY_PREFIX: Final[str] = "search_query: "
CROP_DIM: Final[int] = 256


def _load_or_download_model(model_name: str, device: str | None) -> SentenceTransformer:
    """
    Load a SentenceTransformer from a local cache if it exists; otherwise
    download it from the Hub and cache it under `resources/models/<model_name>`.
    """
    # -----------------------------------------------------------------------
    # 1. Determine the folder that would hold the cached files.
    # -----------------------------------------------------------------------
    # For a name like "nomic-ai/nomic-embed-text-v1.5" the cache directory
    # will be: resources/models/nomic-ai/nomic-embed-text-v1.5
    cache_dir = _LOCAL_MODELS_ROOT / model_name

    # -----------------------------------------------------------------------
    # 2. If the cache directory already contains a "config.json" we assume
    #    the whole model is present and can be loaded directly.
    # -----------------------------------------------------------------------
    if (cache_dir / "config.json").exists():
        return SentenceTransformer(str(cache_dir), device=device)

    # -----------------------------------------------------------------------
    # 3. If not cached yet, download *only* the files that are required for
    #    SentenceTransformer to load (config, vocab, weights, etc.).
    #    The `SentenceTransformer` constructor will automatically
    #    create the folder and populate it.
    # -----------------------------------------------------------------------
    
    # We force `cache_dir` so the `SentenceTransformer` constructor
    # writes the files there.  The `trust_remote_code=True` flag is still
    # needed for models that ship custom code.
    model = SentenceTransformer(
        model_name,
        trust_remote_code=True,
        device=device,
        cache_folder=str(cache_dir),
    )
    return model

def _ensure_model(model_name: str, device: str | None) -> SentenceTransformer:
    key = (model_name, device)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    
    # Helper to download the model locally if not available.
    model = _load_or_download_model(model_name, device)

    _MODEL_CACHE[key] = model
    return model


class NomicLocalEmbedder:
    """Encoder that keeps the full model in-process on macOS."""

    def __init__(
        self,
        *,
        device: str | None = None,
        model_name: str = _MODEL_NAME,
    ) -> None:
        self.device = device
        self.model_name = model_name
        self.model = _ensure_model(model_name, device)

    @staticmethod
    def _l2(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    def _encode(self, text: str) -> np.ndarray:
        encoded = self.model.encode(
            [text],
            normalize_embeddings=False,
            convert_to_numpy=True,
        )[0]
        arr = np.asarray(encoded, dtype=np.float32)
        arr = self._l2(arr)
        arr = arr[:CROP_DIM]
        if arr.shape[0] < CROP_DIM:
            pad = np.zeros(CROP_DIM - arr.shape[0], dtype=np.float32)
            arr = np.concatenate([arr, pad])
        return self._l2(arr)

    def embed_doc(self, text: str) -> np.ndarray:
        return self._encode(f"{_DOC_PREFIX}{text}")

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode(f"{_QUERY_PREFIX}{text}")

    @staticmethod
    def to_blob(vec: np.ndarray) -> bytes:
        return serialize_float32(vec.astype(np.float32, copy=False))

    def save_embedding(self, path: Path, text: str, *, is_query: bool = False) -> None:
        vec = self.embed_query(text) if is_query else self.embed_doc(text)
        path.write_bytes(self.to_blob(vec))


__all__ = ["CROP_DIM", "NomicLocalEmbedder"]
