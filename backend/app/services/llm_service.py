"""Centralized Groq-backed LLM service and evaluation response cache."""

from __future__ import annotations

import hashlib
from typing import Any

from app.llm.base import LLMProvider
from app.llm.groq import GroqProvider

_CACHE: dict[str, Any] = {}


def _make_cache_key(question_id: str | Any, transcript: str) -> str:
    """Create a stable cache key for an answer-scoring request."""
    payload = f"{str(question_id)}::{(transcript or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_provider() -> LLMProvider:
    """Return the sole supported LLM provider."""
    return GroqProvider()


def get_cached_response(question_id: str | Any, transcript: str) -> Any | None:
    """Return a cached evaluation payload, if present."""
    return _CACHE.get(_make_cache_key(question_id, transcript))


def set_cached_response(question_id: str | Any, transcript: str, response: Any) -> Any:
    """Persist a response in the in-memory cache."""
    key = _make_cache_key(question_id, transcript)
    _CACHE[key] = response
    return response


def clear_cache() -> None:
    """Clear the in-memory evaluation cache."""
    _CACHE.clear()


async def cached_generate(
    question_id: str | Any,
    transcript: str,
    prompt: str,
    schema: dict[str, Any] | None = None,
    provider: LLMProvider | None = None,
) -> Any:
    """Generate a provider response with a simple in-memory cache."""
    key = _make_cache_key(question_id, transcript)
    if key in _CACHE:
        return _CACHE[key]

    llm_provider = provider or get_provider()
    response = await llm_provider.generate(prompt, schema=schema)
    _CACHE[key] = response
    return response


__all__ = [
    "LLMProvider",
    "cached_generate",
    "clear_cache",
    "get_cached_response",
    "get_provider",
    "set_cached_response",
]
