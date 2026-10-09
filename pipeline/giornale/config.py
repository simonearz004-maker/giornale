"""Configurazione letta dalle variabili d'ambiente (GitHub Secrets in produzione)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_GEMINI_MODELS = "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si", "sì"}


@dataclass
class Config:
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").rstrip("/"))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY", ""))
    gemini_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_models: list[str] = field(default_factory=lambda: [
        m.strip() for m in (os.getenv("GEMINI_MODELS") or DEFAULT_GEMINI_MODELS).split(",") if m.strip()])
    # Riserva a pagamento: resta spenta finché ANTHROPIC_API_KEY non è impostata.
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL") or "claude-haiku-4-5")
    min_interval_s: float = field(default_factory=lambda: float(os.getenv("LLM_MIN_INTERVAL") or "6.5"))
    force: bool = field(default_factory=lambda: _bool("FORCE_RUN"))
    trigger: str = field(default_factory=lambda: os.getenv("RUN_TRIGGER", "schedule"))
    user_agent: str = field(default_factory=lambda: os.getenv(
        "HTTP_USER_AGENT", "IlMioGiornale/1.0 (giornale personale; lettura feed RSS)"))
    max_window_hours: int = 36
    min_relevance: int = 3
    max_new_glossary_terms: int = 6

    def validate(self) -> list[str]:
        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_key:
            missing.append("SUPABASE_SERVICE_KEY")
        if not self.gemini_key and not self.anthropic_key:
            missing.append("GEMINI_API_KEY")
        return missing
