"""Central configuration, loaded from environment / `.env`.

A single `settings` singleton is imported across the backend. Everything that
might differ between dev (laptop + local Ollama) and prod (funiserver container +
host Ollama) lives here so nothing else needs to know about the environment.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ollama (OpenAI-compatible endpoint) ---
    ollama_base_url: str = Field(default="http://localhost:11434/v1")
    ollama_api_key: str = Field(default="ollama")  # Ollama ignores it; SDK requires non-empty
    narration_model: str = Field(default="llama3.1")
    adjudication_model: str = Field(default="llama3.1")
    embed_model: str = Field(default="nomic-embed-text")
    # Private out-of-campaign companion chats — keep it fast/local; no need for cloud prose.
    chat_model: str = Field(default="gemma4:e4b")

    narration_temperature: float = Field(default=0.9)
    adjudication_temperature: float = Field(default=0.2)

    # --- paths ---
    db_path: Path = Field(default=Path("./data/emberheart.db"))
    corpus_claudes_emberheart: Path | None = Field(default=None)
    corpus_origins: Path | None = Field(default=None)

    # --- DM output mode ---
    # When true, the DM is asked for a strict JSON object (guaranteed-parseable) instead
    # of the bracket-section contract. More robust on models that drift; loses live token
    # streaming (the turn arrives buffered).
    strict_output: bool = Field(default=False)

    # --- big-context + content routing ---
    # FULL_CONTEXT stuffs the entire campaign (whole chronicle, all hooks/NPCs/state) into
    # every prompt instead of RAG top-k. Only sane with a large-context model (e.g. a cloud
    # model). Off by default for small local windows.
    full_context: bool = Field(default=False)

    # Optional uncensored local model for mature/romance beats a cloud model would refuse.
    # If set and route_intimate is true, those turns are routed here. Blank = no routing.
    intimate_model: str = Field(default="")
    route_intimate: bool = Field(default=False)

    # Latency fallback: if the primary model doesn't begin producing within this many
    # seconds (first token when streaming; total when buffered) — or it errors — the turn
    # drops to fallback_model so play never hangs on a slow/cold cloud model.
    narration_timeout: float = Field(default=75.0)
    fallback_model: str = Field(default="")

    # A model's FIRST call (cold load / cloud spin-up) gets this larger budget before the
    # fallback kicks in; once it's produced once it drops to narration_timeout. Warming a
    # model on session start pays this up front so you rarely see it mid-turn.
    cold_start_timeout: float = Field(default=180.0)

    # --- memory tuning ---
    rag_top_k: int = Field(default=5)
    rag_relevance_threshold: float = Field(default=0.35)
    consolidate_every_turns: int = Field(default=8)

    # --- world simulation ---
    economy_tick_enabled: bool = Field(default=False)
    economy_tick_seconds: int = Field(default=300)

    # --- web ---
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_password: str = Field(default="")

    @property
    def db_path_resolved(self) -> Path:
        """Absolute DB path with parent directory guaranteed to exist."""
        p = self.db_path.expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
