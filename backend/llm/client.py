"""LLM client — talks to a local Ollama via its OpenAI-compatible `/v1` API.

Two temperature regimes per the design spec:

  * **hot** (`narration_temperature`) for `[NARRATIVE]` prose, and
  * **cold** (`adjudication_temperature`) for mechanical adjudication.

Embeddings use a *separate, fixed* local model (`embed_model`). Once the vector
store is populated you must not change it — mixing embedding models breaks cosine
similarity. See `backend/memory/rag.py`.

The client is intentionally thin: callers pass full message lists. Prompt
assembly lives in `backend/dm/` and `backend/memory/`.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Iterable, Literal

import httpx
from openai import AsyncOpenAI

from backend.core.config import settings

logger = logging.getLogger("emberheart.llm")

Message = dict[str, str]  # {"role": "system|user|assistant", "content": "..."}
Mode = Literal["narration", "adjudication"]


class LLMClient:
    """Async wrapper around the Ollama OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key or "ollama",
            timeout=300.0,
            max_retries=1,
        )
        # Plain httpx for /api/* native endpoints (health, model listing) that
        # the OpenAI surface doesn't expose.
        self._native_base = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
        self._http = httpx.AsyncClient(timeout=30.0)

    # ------------------------------------------------------------------ chat
    def _model_and_temp(self, mode: Mode) -> tuple[str, float]:
        if mode == "adjudication":
            return settings.adjudication_model, settings.adjudication_temperature
        return settings.narration_model, settings.narration_temperature

    async def chat(
        self,
        messages: Iterable[Message],
        *,
        mode: Mode = "narration",
        temperature: float | None = None,
        model: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """Single-shot completion. Returns the full assistant text.

        Pass `response_format={"type": "json_object"}` for strict structured output.
        """
        m, t = self._model_and_temp(mode)
        kwargs: dict = {
            "model": model or m,
            "messages": list(messages),
            "temperature": t if temperature is None else temperature,
            "stream": False,
        }
        if response_format:
            kwargs["response_format"] = response_format
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._hint(exc, model or m)) from exc
        return resp.choices[0].message.content or ""

    async def stream_chat(
        self,
        messages: Iterable[Message],
        *,
        mode: Mode = "narration",
        temperature: float | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion token-deltas (used for live narration)."""
        m, t = self._model_and_temp(mode)
        stream = await self._client.chat.completions.create(
            model=model or m,
            messages=list(messages),
            temperature=t if temperature is None else temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    @staticmethod
    def _hint(exc: Exception, model: str) -> str:
        """Turn opaque Ollama errors into actionable messages."""
        msg = str(exc)
        if "not found" in msg and "model" in msg:
            return f"Model '{model}' is not pulled. Run: ollama pull {model}"
        if "Connection" in msg or "connect" in msg.lower():
            return "Ollama is not reachable — is it running on OLLAMA_BASE_URL?"
        return msg

    # ------------------------------------------------------------- embeddings
    async def embed(self, text: str) -> list[float]:
        """Embed a single string with the fixed local embedding model."""
        try:
            resp = await self._client.embeddings.create(
                model=settings.embed_model,
                input=text,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._hint(exc, settings.embed_model)) from exc
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many strings in one request (ingestion path)."""
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=settings.embed_model,
            input=texts,
        )
        # Preserve request order (OpenAI guarantees index alignment).
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    # ------------------------------------------------------------------ admin
    async def health_check(self) -> bool:
        """True if Ollama answers on its native /api/tags endpoint."""
        try:
            r = await self._http.get(f"{self._native_base}/api/tags", timeout=10.0)
            return r.status_code == 200
        except Exception as exc:  # noqa: BLE001 - health is best-effort
            logger.warning("Ollama health check failed: %s", exc)
            return False

    async def list_models(self) -> list[str]:
        try:
            r = await self._http.get(f"{self._native_base}/api/tags", timeout=10.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list Ollama models: %s", exc)
            return []

    async def close(self) -> None:
        await self._client.close()
        await self._http.aclose()


# Module-level singleton; created lazily so importing the module never needs a
# running Ollama (keeps unit tests of pure-Python modules import-safe).
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
