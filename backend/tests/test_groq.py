"""Deterministic tests for the official Groq SDK adapter."""

from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError, APITimeoutError, RateLimitError

from app.config import get_settings
from app.llm.groq import GroqProvider, GroqRequestError, _get_client


def make_provider(monkeypatch, completion_create):
    _get_client.cache_clear()
    monkeypatch.setattr(
        "app.llm.groq.get_settings",
        lambda: SimpleNamespace(
            GROQ_API_KEY="test-key",
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_TIMEOUT_SECONDS=3.0,
        ),
    )
    provider = GroqProvider()
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=completion_create),
        )
    )
    return provider


def test_groq_provider_requires_key(monkeypatch):
    monkeypatch.setattr(
        "app.llm.groq.get_settings",
        lambda: SimpleNamespace(
            GROQ_API_KEY=None,
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_TIMEOUT_SECONDS=3.0,
        ),
    )
    with pytest.raises(GroqRequestError, match="GROQ_API_KEY is not configured"):
        GroqProvider()


@pytest.mark.asyncio
async def test_groq_provider_uses_configured_model_and_parses_json(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"ask_question"}'))]
        )

    provider = make_provider(monkeypatch, create)
    result = await provider.generate("Return a decision", schema={"type": "object"})

    assert result == {"action": "ask_question"}
    assert captured["model"] == "openai/gpt-oss-120b"
    assert captured["max_completion_tokens"] == 2048
    assert captured["reasoning_effort"] == "medium"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["stream"] is False


@pytest.mark.asyncio
async def test_groq_provider_buffers_stream_before_parsing(monkeypatch):
    async def chunks():
        for content in ['{"ok":', "true}"]:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])

    async def create(**kwargs):
        assert kwargs["stream"] is True
        return chunks()

    provider = make_provider(monkeypatch, create)
    assert await provider.generate("Return JSON", schema={"type": "object"}, stream=True) == {
        "ok": True
    }


@pytest.mark.asyncio
async def test_groq_provider_maps_rate_limit_and_timeout(monkeypatch):
    request = httpx.Request("POST", "https://api.groq.com")
    response = httpx.Response(429, request=request)
    rate_limit = RateLimitError("too many requests", response=response, body={})

    async def limited(**kwargs):
        raise rate_limit

    with pytest.raises(GroqRequestError, match="rate limit") as rate_error:
        await make_provider(monkeypatch, limited).generate("test")
    assert rate_error.value.status_code == 429

    async def timed_out(**kwargs):
        raise APITimeoutError(request=request)

    with pytest.raises(GroqRequestError, match="timed out") as timeout_error:
        await make_provider(monkeypatch, timed_out).generate("test")
    assert timeout_error.value.status_code == 504


@pytest.mark.asyncio
async def test_groq_provider_surfaces_auth_and_model_errors_without_provider_switch(monkeypatch):
    request = httpx.Request("POST", "https://api.groq.com")

    async def rejected(status_code, message):
        response = httpx.Response(status_code, request=request)
        raise APIStatusError(
            message,
            response=response,
            body={"error": {"message": message}},
        )

    provider = make_provider(monkeypatch, lambda **kwargs: rejected(401, "Invalid API key"))
    with pytest.raises(GroqRequestError, match="Invalid API key") as auth_error:
        await provider.generate("test")
    assert auth_error.value.status_code == 502

    provider = make_provider(
        monkeypatch, lambda **kwargs: rejected(404, "The model does not exist")
    )
    with pytest.raises(GroqRequestError, match="The model does not exist") as model_error:
        await provider.generate("test")
    assert model_error.value.status_code == 502


@pytest.mark.asyncio
async def test_actual_groq_model_integration_when_credentials_are_available():
    if not get_settings().GROQ_API_KEY:
        pytest.skip("GROQ_API_KEY is not configured in this environment")
    result = await GroqProvider().generate("Reply with the single word READY.")
    assert result.get("text", "").strip().upper() == "READY"
