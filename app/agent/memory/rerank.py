"""Wrapper around the FlagEmbedding BGE reranker."""

from __future__ import annotations

from typing import Sequence

from FlagEmbedding import FlagReranker

DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"
_RERANKER_CACHE: dict[tuple[str, bool], FlagReranker] = {}


def get_reranker(model_name: str = DEFAULT_RERANKER, *, use_fp16: bool = True) -> FlagReranker:
    key = (model_name, use_fp16)
    cached = _RERANKER_CACHE.get(key)
    if cached is not None:
        return cached
    reranker = FlagReranker(model_name, use_fp16=use_fp16)
    _RERANKER_CACHE[key] = reranker
    return reranker


def rerank_texts(
    *,
    query: str,
    texts: Sequence[str],
    top_n: int = 12,
    model_name: str = DEFAULT_RERANKER,
    use_fp16: bool = True,
) -> list[tuple[int, float]]:
    if not texts or top_n <= 0:
        return []
    reranker = get_reranker(model_name, use_fp16=use_fp16)
    pairs = [[query, text] for text in texts]
    scores = reranker.compute_score(pairs)
    indexed = list(enumerate(scores))
    indexed.sort(key=lambda kv: kv[1], reverse=True)
    top = indexed[:top_n]
    return [(idx, float(score)) for idx, score in top]


__all__ = ["DEFAULT_RERANKER", "get_reranker", "rerank_texts"]
