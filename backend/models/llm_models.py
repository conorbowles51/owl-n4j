"""Provider-neutral catalog of generative models exposed by Loupe."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class LLMModel:
    def __init__(
        self,
        *,
        id: str,
        name: str,
        provider: LLMProvider,
        description: str,
        pros: list[str] | None = None,
        cons: list[str] | None = None,
        context_window: Optional[int] = None,
        parameters: Optional[str] = None,
        supports_agent: bool = True,
        supports_structured_output: bool = True,
    ) -> None:
        self.id = id
        self.name = name
        self.provider = provider
        self.description = description
        self.pros = pros or []
        self.cons = cons or []
        self.context_window = context_window
        self.parameters = parameters
        self.supports_agent = supports_agent
        self.supports_structured_output = supports_structured_output

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "description": self.description,
            "pros": self.pros,
            "cons": self.cons,
            "context_window": self.context_window,
            "parameters": self.parameters,
            "supports_agent": self.supports_agent,
            "supports_structured_output": self.supports_structured_output,
        }


def _model(
    id: str,
    name: str,
    provider: LLMProvider,
    description: str,
    *,
    context_window: int | None = None,
    supports_agent: bool = True,
    supports_structured_output: bool = True,
) -> LLMModel:
    return LLMModel(
        id=id,
        name=name,
        provider=provider,
        description=description,
        context_window=context_window,
        supports_agent=supports_agent,
        supports_structured_output=supports_structured_output,
    )


# Keep legacy models that may be recorded in old conversations, while placing
# the current recommended models first in each provider group.
AVAILABLE_MODELS = [
    _model(
        "gpt-5.6-sol",
        "GPT-5.6 Sol",
        LLMProvider.OPENAI,
        "OpenAI's quality-first model for difficult synthesis and agent work.",
        context_window=1_050_000,
    ),
    _model(
        "gpt-5.6-terra",
        "GPT-5.6 Terra",
        LLMProvider.OPENAI,
        "Balanced OpenAI model for production analysis, chat, and extraction.",
        context_window=1_050_000,
    ),
    _model(
        "gpt-5.6-luna",
        "GPT-5.6 Luna",
        LLMProvider.OPENAI,
        "Economical OpenAI model for high-volume, well-evaluated workloads.",
        context_window=1_050_000,
    ),
    _model("gpt-5-mini", "GPT-5 Mini", LLMProvider.OPENAI, "Legacy economical OpenAI model."),
    _model("gpt-5", "GPT-5", LLMProvider.OPENAI, "Legacy GPT-5 model."),
    _model("gpt-4o", "GPT-4o", LLMProvider.OPENAI, "Legacy multimodal OpenAI model."),
    _model(
        "claude-sonnet-5",
        "Claude Sonnet 5",
        LLMProvider.ANTHROPIC,
        "Anthropic's strong general-purpose model for agents and analysis.",
    ),
    _model(
        "claude-opus-4-8",
        "Claude Opus 4.8",
        LLMProvider.ANTHROPIC,
        "Anthropic's high-capability model for complex knowledge work.",
    ),
    _model(
        "claude-haiku-4-5",
        "Claude Haiku 4.5",
        LLMProvider.ANTHROPIC,
        "Fast, cost-effective Anthropic model for high-volume tasks.",
    ),
    _model(
        "gemini-3.6-flash",
        "Gemini 3.6 Flash",
        LLMProvider.GEMINI,
        "Google's current agentic Flash model for reasoning and tool workflows.",
    ),
    _model(
        "gemini-3.5-flash",
        "Gemini 3.5 Flash",
        LLMProvider.GEMINI,
        "Stable Google model for balanced generation and structured extraction.",
    ),
    _model(
        "gemini-3.5-flash-lite",
        "Gemini 3.5 Flash-Lite",
        LLMProvider.GEMINI,
        "Google's economical model for document extraction and structured JSON.",
    ),
]


def get_models_by_provider(provider: LLMProvider) -> list[LLMModel]:
    return [model for model in AVAILABLE_MODELS if model.provider == provider]


def get_model_by_id(model_id: str) -> Optional[LLMModel]:
    return next((model for model in AVAILABLE_MODELS if model.id == model_id), None)


def get_default_model(provider: LLMProvider) -> LLMModel:
    defaults = {
        LLMProvider.OPENAI: "gpt-5.6-terra",
        LLMProvider.ANTHROPIC: "claude-sonnet-5",
        LLMProvider.GEMINI: "gemini-3.6-flash",
    }
    return get_model_by_id(defaults[provider]) or get_models_by_provider(provider)[0]
