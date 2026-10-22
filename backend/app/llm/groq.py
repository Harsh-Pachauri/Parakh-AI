"""Official Groq SDK integration used by all language-model workflows."""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Any

from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq, RateLimitError

from app.config import get_settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GroqRequestError(RuntimeError):
    """Sanitized provider failure suitable for API responses."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@lru_cache(maxsize=2)
def _get_client(api_key: str, timeout: float) -> AsyncGroq:
    """Reuse one SDK client per configured key and timeout for the process lifetime."""
    return AsyncGroq(api_key=api_key, timeout=timeout, max_retries=1)


class GroqProvider(LLMProvider):
    """Provider that sends chat completions only to Groq."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        if not self.api_key:
            raise GroqRequestError("GROQ_API_KEY is not configured.")
        self.timeout = settings.GROQ_TIMEOUT_SECONDS
        self.client = _get_client(self.api_key, self.timeout)

    async def generate(
        self, prompt: str, schema: dict | None = None, *, stream: bool = False
    ) -> Any:
        """Generate and parse a completion, buffering streams before structured parsing."""
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        if schema is not None:
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"Return a JSON object matching this schema: {json.dumps(schema)}",
                },
            )

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=1,
                max_completion_tokens=2048,
                top_p=1,
                reasoning_effort="medium",
                response_format={"type": "json_object"} if schema is not None else None,
                stream=stream,
                stop=None,
            )
            if stream:
                chunks: list[str] = []
                async for chunk in completion:
                    if chunk.choices:
                        content = chunk.choices[0].delta.content
                        if content:
                            chunks.append(content)
                content = "".join(chunks)
            else:
                content = completion.choices[0].message.content
        except RateLimitError as exc:
            logger.warning("Groq request %s was rate limited", request_id)
            raise GroqRequestError("Groq rate limit reached. Please retry shortly.", 429) from exc
        except APITimeoutError as exc:
            logger.warning("Groq request %s timed out", request_id)
            raise GroqRequestError("Groq request timed out. Please retry.", 504) from exc
        except APIConnectionError as exc:
            logger.warning("Groq request %s could not connect", request_id)
            raise GroqRequestError("Groq is unreachable. Check network access and retry.") from exc
        except APIStatusError as exc:
            status_code = exc.status_code
            body = exc.body
            error_body = body.get("error") if isinstance(body, dict) else None
            provider_message = (
                error_body.get("message")
                if isinstance(error_body, dict)
                else error_body
                if isinstance(error_body, str)
                else None
            )
            if isinstance(provider_message, str) and provider_message.strip():
                safe_message = provider_message.replace(self.api_key, "[redacted]")[:500]
                message = f"Groq API returned HTTP {status_code}: {safe_message}"
            elif status_code == 401:
                message = "Groq authentication failed. Verify GROQ_API_KEY."
            elif status_code in (400, 404, 422):
                message = f"Groq rejected the configured model or request (HTTP {status_code})."
            else:
                message = f"Groq request failed with HTTP status {status_code}."
            logger.warning(
                "Groq request %s failed with status %s (provider request id=%s)",
                request_id,
                status_code,
                getattr(exc, "request_id", None),
            )
            safe_status = 429 if status_code == 429 else 502
            raise GroqRequestError(message, safe_status) from exc
        except Exception as exc:
            logger.exception("Groq request %s failed unexpectedly", request_id)
            raise GroqRequestError("Groq request failed unexpectedly. Please retry.") from exc

        logger.info(
            "Groq request %s succeeded in %.2fs",
            request_id,
            time.perf_counter() - started,
        )
        if not isinstance(content, str) or not content.strip():
            raise GroqRequestError("Groq returned an empty completion.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            if schema is not None:
                raise GroqRequestError(
                    "Groq returned invalid JSON for a structured request."
                ) from exc
            return {"text": content}
