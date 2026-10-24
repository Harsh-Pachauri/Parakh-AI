"""Tests for health check and root endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Verify that /api/health returns 200 with status ok and db connected."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert "Hello, Viva!" in data.get("message", "")


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Verify that root endpoint / returns 200 with app metadata."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert data["health"] == "/api/health"


from types import SimpleNamespace  # noqa: E402

from app.llm.groq import GroqProvider  # noqa: E402


@pytest.mark.asyncio
async def test_ai_health_check_missing_key(client: AsyncClient, monkeypatch) -> None:
    """Verify /api/health/ai returns 503 when GROQ_API_KEY is missing."""
    monkeypatch.setattr(
        "app.main.settings",
        SimpleNamespace(
            GROQ_API_KEY=None,
            GROQ_MODEL="openai/gpt-oss-120b",
            APP_NAME="Parakh AI",
        ),
    )
    monkeypatch.setattr(
        "app.llm.groq.get_settings",
        lambda: SimpleNamespace(
            GROQ_API_KEY=None,
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_TIMEOUT_SECONDS=3.0,
        ),
    )
    response = await client.get("/api/health/ai")
    assert response.status_code == 503
    assert "GROQ_API_KEY is not configured" in response.text


@pytest.mark.asyncio
async def test_ai_health_check_success(client: AsyncClient, monkeypatch) -> None:
    """Verify /api/health/ai returns 200 when Groq succeeds."""
    monkeypatch.setattr(
        "app.main.settings",
        SimpleNamespace(
            GROQ_API_KEY="test-key",
            GROQ_MODEL="openai/gpt-oss-120b",
            APP_NAME="Parakh AI",
        ),
    )

    monkeypatch.setattr(
        "app.llm.groq.get_settings",
        lambda: SimpleNamespace(
            GROQ_API_KEY="test-key",
            GROQ_MODEL="openai/gpt-oss-120b",
            GROQ_TIMEOUT_SECONDS=5,
        ),
    )

    async def mock_generate(self, prompt, schema=None, stream=False):
        return {"text": "READY"}

    monkeypatch.setattr(GroqProvider, "generate", mock_generate)
    response = await client.get("/api/health/ai")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider"] == "groq"
