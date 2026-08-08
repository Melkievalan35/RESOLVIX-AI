"""
model_loader.py
----------------
Centralized loader for LLM clients used across Resolvix-AI's agents
(customer_agent, evidence_agent, policy_agent, fraud_agent, resolution_agent,
workflow_agent, escalation_agent, learning_agent).

Supports multiple providers (Anthropic, OpenAI, local/Ollama) selected via
environment variables so agents don't need to know provider details.
"""

import os
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("resolvix.ai.model_loader")


class ModelProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


@dataclass
class ModelConfig:
    provider: ModelProvider
    model_name: str
    temperature: float = 0.2
    max_tokens: int = 1024
    top_p: float = 1.0
    timeout: int = 60
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# Default per-agent model configs. Cheaper/faster models for high-volume,
# low-complexity tasks (sentiment, ocr parsing); stronger models for
# reasoning-heavy tasks (resolution, fraud, escalation).
AGENT_MODEL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "customer_agent": {"model_name": "claude-sonnet-5", "temperature": 0.4},
    "evidence_agent": {"model_name": "claude-sonnet-5", "temperature": 0.0},
    "policy_agent": {"model_name": "claude-sonnet-5", "temperature": 0.0},
    "fraud_agent": {"model_name": "claude-opus-4-8", "temperature": 0.0},
    "resolution_agent": {"model_name": "claude-opus-4-8", "temperature": 0.2},
    "workflow_agent": {"model_name": "claude-haiku-4-5", "temperature": 0.0},
    "escalation_agent": {"model_name": "claude-sonnet-5", "temperature": 0.1},
    "learning_agent": {"model_name": "claude-sonnet-5", "temperature": 0.3},
    "default": {"model_name": "claude-sonnet-5", "temperature": 0.2},
}


class ModelLoadError(Exception):
    """Raised when a model client cannot be constructed."""


class BaseLLMClient:
    """Common interface every provider-specific client must implement."""

    def __init__(self, config: ModelConfig):
        self.config = config

    def generate(self, system: str, prompt: str, **kwargs) -> str:
        raise NotImplementedError

    def generate_with_retry(
        self, system: str, prompt: str, retries: int = 3, backoff: float = 1.5, **kwargs
    ) -> str:
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                return self.generate(system, prompt, **kwargs)
            except Exception as exc:  # noqa: BLE001 - broad by design, provider errors vary
                last_exc = exc
                wait = backoff ** attempt
                logger.warning(
                    "LLM call failed (attempt %s/%s) for model=%s: %s. Retrying in %.1fs",
                    attempt, retries, self.config.model_name, exc, wait,
                )
                time.sleep(wait)
        raise ModelLoadError(f"LLM generation failed after {retries} attempts") from last_exc


class AnthropicClient(BaseLLMClient):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            import anthropic
        except ImportError as exc:
            raise ModelLoadError(
                "anthropic package not installed. Run `pip install anthropic`."
            ) from exc
        self._client = anthropic.Anthropic(
            api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate(self, system: str, prompt: str, **kwargs) -> str:
        response = self._client.messages.create(
            model=self.config.model_name,
            system=system,
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            temperature=kwargs.get("temperature", self.config.temperature),
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIClient(BaseLLMClient):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            import openai
        except ImportError as exc:
            raise ModelLoadError(
                "openai package not installed. Run `pip install openai`."
            ) from exc
        self._client = openai.OpenAI(
            api_key=config.api_key or os.environ.get("OPENAI_API_KEY")
        )

    def generate(self, system: str, prompt: str, **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self.config.model_name,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content


class OllamaClient(BaseLLMClient):
    """Local inference client for on-prem / offline deployments."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        try:
            import requests
        except ImportError as exc:
            raise ModelLoadError("requests package required for Ollama client.") from exc
        self._requests = requests
        self._base_url = config.base_url or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )

    def generate(self, system: str, prompt: str, **kwargs) -> str:
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": self.config.top_p,
            },
        }
        resp = self._requests.post(
            f"{self._base_url}/api/generate", json=payload, timeout=self.config.timeout
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


_PROVIDER_MAP = {
    ModelProvider.ANTHROPIC: AnthropicClient,
    ModelProvider.OPENAI: OpenAIClient,
    ModelProvider.OLLAMA: OllamaClient,
}

_client_cache: Dict[str, BaseLLMClient] = {}


def _resolve_provider() -> ModelProvider:
    raw = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    try:
        return ModelProvider(raw)
    except ValueError as exc:
        raise ModelLoadError(f"Unknown LLM_PROVIDER '{raw}'") from exc


def get_model_config(agent_name: str) -> ModelConfig:
    """Build a ModelConfig for a given agent, using env overrides where set."""
    defaults = AGENT_MODEL_DEFAULTS.get(agent_name, AGENT_MODEL_DEFAULTS["default"])
    provider = _resolve_provider()

    model_name = os.environ.get(
        f"{agent_name.upper()}_MODEL", defaults["model_name"]
    )
    temperature = float(
        os.environ.get(f"{agent_name.upper()}_TEMPERATURE", defaults.get("temperature", 0.2))
    )
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", 1024))

    return ModelConfig(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def load_model(agent_name: str = "default", config: Optional[ModelConfig] = None) -> BaseLLMClient:
    """
    Return a cached LLM client for the given agent. Each agent gets its own
    cached client instance keyed by (agent_name, provider, model_name) so
    repeated calls within a request/response cycle don't reinitialize SDKs.
    """
    cfg = config or get_model_config(agent_name)
    cache_key = f"{agent_name}:{cfg.provider}:{cfg.model_name}"

    if cache_key in _client_cache:
        return _client_cache[cache_key]

    client_cls = _PROVIDER_MAP.get(cfg.provider)
    if client_cls is None:
        raise ModelLoadError(f"No client implementation for provider '{cfg.provider}'")

    logger.info("Loading model for agent=%s provider=%s model=%s", agent_name, cfg.provider, cfg.model_name)
    client = client_cls(cfg)
    _client_cache[cache_key] = client
    return client


def clear_cache() -> None:
    """Useful in tests or when rotating API keys/configs at runtime."""
    _client_cache.clear()
