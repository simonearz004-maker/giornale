"""Chiamate ai modelli linguistici.

Ordine di utilizzo: i modelli Gemini gratuiti indicati in GEMINI_MODELS, uno dopo l'altro
quando un modello esaurisce la quota; poi, SOLO se è impostata ANTHROPIC_API_KEY,
Claude Haiku come riserva a pagamento. Senza quella chiave la riserva non esiste.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class ModelExhausted(LLMError):
    """Quota del modello esaurita (es. limite giornaliero gratuito)."""


class ModelUnavailable(LLMError):
    """Modello inesistente o non abilitato per questa chiave."""


class AllModelsExhausted(LLMError):
    pass


class BudgetExhausted(LLMError):
    pass


def _retry_delay(body: str) -> float | None:
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    return float(m.group(1)) if m else None


class GeminiProvider:
    kind = "gemini"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=120)

    @property
    def name(self) -> str:
        return self.model

    def generate(self, system: str, user: str, sleep: Callable[[float], None] = time.sleep) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }
        for attempt in range(4):
            try:
                r = self.client.post(url, json=payload, headers={"x-goog-api-key": self.api_key})
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise LLMError(f"Rete: {exc}") from exc
                sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                data = r.json()
                cands = data.get("candidates") or []
                if not cands:
                    reason = (data.get("promptFeedback") or {}).get("blockReason", "nessuna risposta")
                    raise LLMError(f"Risposta vuota da {self.model}: {reason}")
                parts = (cands[0].get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if not text.strip():
                    raise LLMError(f"Testo vuoto da {self.model} (finishReason={cands[0].get('finishReason')})")
                return text
            body = r.text
            if r.status_code == 429:
                if "PerDay" in body or "per day" in body.lower() or "daily" in body.lower():
                    raise ModelExhausted(f"{self.model}: quota giornaliera esaurita")
                delay = _retry_delay(body) or 20 * (attempt + 1)
                if attempt == 3 or delay > 90:
                    raise ModelExhausted(f"{self.model}: troppe richieste (429)")
                sleep(delay + 1)
                continue
            if r.status_code in (400, 403, 404) and ("not found" in body.lower() or "not supported" in body.lower()
                                                     or "permission" in body.lower()):
                raise ModelUnavailable(f"{self.model}: {r.status_code} {body[:200]}")
            if r.status_code >= 500 and attempt < 3:
                sleep(10 * (attempt + 1))
                continue
            raise LLMError(f"{self.model}: HTTP {r.status_code} {body[:300]}")
        raise LLMError(f"{self.model}: tentativi esauriti")


class AnthropicProvider:
    """Riserva a pagamento (Claude Haiku). Attiva solo se è presente la chiave."""
    kind = "anthropic"

    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None):
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=180)

    @property
    def name(self) -> str:
        return self.model

    def generate(self, system: str, user: str, sleep: Callable[[float], None] = time.sleep) -> str:
        for attempt in range(3):
            r = self.client.post("https://api.anthropic.com/v1/messages", headers={
                "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 4096, "temperature": 0.2, "system": system,
                      "messages": [{"role": "user", "content": user + "\n\nRispondi solo con il JSON richiesto."}]})
            if r.status_code == 200:
                return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
            if r.status_code in (429, 529) and attempt < 2:
                sleep(20 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise ModelUnavailable(f"{self.model}: chiave non valida")
            if r.status_code == 400 and "credit" in r.text.lower():
                raise ModelExhausted(f"{self.model}: credito esaurito")
            raise LLMError(f"{self.model}: HTTP {r.status_code} {r.text[:300]}")
        raise ModelExhausted(f"{self.model}: troppe richieste")


def parse_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class LLM:
    def __init__(self, providers: list, max_requests: int, min_interval: float = 6.5,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if not providers:
            raise LLMError("Nessun modello configurato")
        self.providers = providers
        self.max_requests = max_requests
        self.used = 0
        self.min_interval = min_interval
        self.sleep = sleep
        self.clock = clock
        self._last = -1e9
        self.dead: set[str] = set()
        self.models_used: list[str] = []
        self.notes: list[str] = []

    @property
    def remaining(self) -> int:
        return self.max_requests - self.used

    def _throttle(self):
        wait = self.min_interval - (self.clock() - self._last)
        if wait > 0:
            self.sleep(wait)
        self._last = self.clock()

    def _raw(self, system: str, user: str) -> tuple[str, str]:
        for p in self.providers:
            if p.name in self.dead:
                continue
            if self.used >= self.max_requests:
                raise BudgetExhausted("Budget di richieste esaurito per questa esecuzione")
            self._throttle()
            self.used += 1
            try:
                text = p.generate(system, user, sleep=self.sleep)
            except (ModelExhausted, ModelUnavailable) as exc:
                self.dead.add(p.name)
                self.notes.append(str(exc))
                log.warning("Passo al modello successivo: %s", exc)
                continue
            if p.name not in self.models_used:
                self.models_used.append(p.name)
            return text, p.name
        raise AllModelsExhausted("Tutti i modelli disponibili hanno esaurito la quota: " + "; ".join(self.notes))

    def json(self, system: str, user: str, model: type[T]) -> tuple[T, str]:
        """Chiede un JSON e lo valida; se non è valido riprova una volta spiegando l'errore.
        Se anche il secondo tentativo non è valido solleva LLMError (la notizia viene esclusa,
        l'edizione prosegue)."""
        text, name = self._raw(system, user)
        try:
            return _validate(model, text), name
        except (ValueError, ValidationError) as exc:
            fix = (f"{user}\n\nATTENZIONE: la risposta precedente non rispettava lo schema "
                   f"({str(exc)[:400]}). Restituisci un solo oggetto JSON, completo di tutti i campi richiesti.")
            text, name = self._raw(system, fix)
            try:
                return _validate(model, text), name
            except (ValueError, ValidationError) as exc2:
                raise LLMError(f"Risposta non valida da {name} anche dopo la correzione: {str(exc2)[:200]}") from exc2


def _validate(model, text: str):
    data = parse_json(text)
    # alcuni modelli restituiscono [ {...} ] invece di {...}
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    return model.model_validate(data)


def build_llm(cfg, max_requests: int, sleep=time.sleep) -> LLM:
    providers: list = []
    if cfg.gemini_key:
        client = httpx.Client(timeout=120)
        providers += [GeminiProvider(cfg.gemini_key, m, client) for m in cfg.gemini_models]
    if cfg.anthropic_key:
        providers.append(AnthropicProvider(cfg.anthropic_key, cfg.anthropic_model))
    return LLM(providers, max_requests=max_requests, min_interval=cfg.min_interval_s, sleep=sleep)
