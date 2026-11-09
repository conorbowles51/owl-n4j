"""Which model writes an agent answer (AG-08): the Settings default, or one a person picks for a single message.

The choices are the agent-capable models of every provider connected in Settings → AI settings, except OpenAI
(standing decision, 2026-10: DeepSeek everywhere, no OpenAI calls). DeepSeek models are also offered with their
higher reasoning effort (AG-07). The default is the agent workload's model from Settings at the default reasoning
level (graph.DEFAULT_REASONING, or AGENT_REASONING in the environment).

Every run records which model and reasoning level wrote it and whether a person chose it (run metadata
``model_choice``); the answer shows it (rule 1: who or what wrote a reading is shown on it).

Decision: a pick applies to the one message it is sent with; the box keeps the pick for the next message until the
person changes it, and a new conversation starts on the default. Reverse if testers want a pick to stick to a thread.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from models.llm_models import AVAILABLE_MODELS, LLMModel, get_model_by_id

NOT_OFFERED_PROVIDERS = frozenset({"openai"})
# The agent's LangChain client per provider (services.agent.graph.AgentGraphRunner); a provider without one installed
# cannot run the agent, so it is not offered.
_CLIENT_MODULE = {"deepseek": "langchain_openai", "anthropic": "langchain_anthropic",
                  "gemini": "langchain_google_genai"}
# Models that are image readers, not agents.
_NOT_AGENT_MODELS = frozenset({"deepseek-flash", "gemini-3.5-flash-lite"})
REASONING_LABELS = {"off": "", "high": "thinks longer", "max": "thinks longest"}
# The faster level, named only where it is a choice in the list (not on old answers, which all used it).
CHOICE_LABELS = {**REASONING_LABELS, "off": "answers faster"}


def default_reasoning() -> str:
    from services.agent.graph import DEFAULT_REASONING, REASONING_LEVELS
    value = (os.environ.get("AGENT_REASONING") or DEFAULT_REASONING).strip().lower()
    return value if value in REASONING_LEVELS else DEFAULT_REASONING


@dataclass(frozen=True)
class Choice:
    provider: str
    model_id: str
    model_name: str
    reasoning: str

    @property
    def key(self) -> str:
        return f"{self.model_id}:{self.reasoning}"

    @property
    def label(self) -> str:
        extra = (CHOICE_LABELS if self.provider == "deepseek" else REASONING_LABELS).get(self.reasoning) or ""
        return f"{self.model_name} · {extra}" if extra else self.model_name


def written_by(model_name: str | None, reasoning: str | None) -> str:
    """The line on an answer: "Written by DeepSeek V4 Pro · thinks longer"."""
    if not model_name:
        return ""
    extra = REASONING_LABELS.get(reasoning or "off") or ""
    return f"Written by {model_name}" + (f" · {extra}" if extra else "")


def _installed(provider: str) -> bool:
    module = _CLIENT_MODULE.get(provider)
    return bool(module) and importlib.util.find_spec(module) is not None


def _levels(model: LLMModel) -> tuple[str, ...]:
    from services.agent.graph import REASONING_LEVELS
    return REASONING_LEVELS if model.provider.value == "deepseek" else ("off",)


def default_choice(db: Session, workload_model=None) -> Choice:
    """The Settings default for the agent workload. ``workload_model``: services.ai_model_policy.get_workload_model."""
    if workload_model is None:
        from services.ai_model_policy import get_workload_model as workload_model
    default_provider, default_model_id = workload_model(db, "agent")
    default_model = get_model_by_id(default_model_id)
    if default_model is None:
        raise ValueError(f"Invalid model: {default_model_id}")
    reasoning = default_reasoning() if default_model.provider.value == "deepseek" else "off"
    return Choice(default_provider, default_model.id, default_model.name, reasoning)


def choices(db: Session, workload_model=None) -> tuple[list[Choice], Choice]:
    """Every model the agent may use now, and the default (always first)."""
    from services.ai_model_policy import provider_is_configured
    default = default_choice(db, workload_model)
    out = [default]
    for model in AVAILABLE_MODELS:
        provider = model.provider.value
        if provider in NOT_OFFERED_PROVIDERS or model.id in _NOT_AGENT_MODELS or not _installed(provider):
            continue
        if not provider_is_configured(provider, db):
            continue
        for level in _levels(model):
            choice = Choice(provider, model.id, model.name, level)
            if choice.key != default.key:
                out.append(choice)
    return out, default


def resolve(db: Session, *, model: str | None, provider: str | None, reasoning: str | None,
            workload_model=None) -> tuple[Choice, bool]:
    """The choice a message runs on and whether a person picked it. Anything not offered is refused in plain words."""
    if not model and not reasoning and not provider:
        return default_choice(db, workload_model), False
    offered, default = choices(db, workload_model)
    model_id = model or default.model_id
    known = get_model_by_id(model_id)
    if (provider or "").lower() in NOT_OFFERED_PROVIDERS or (known and known.provider.value in NOT_OFFERED_PROVIDERS):
        raise ValueError("OpenAI models are not offered for the agent. Pick another model.")
    if reasoning:
        level = reasoning
    elif model_id == default.model_id:
        level = default.reasoning
    else:
        level = default_reasoning() if known and known.provider.value == "deepseek" else "off"
    for choice in offered:
        if choice.model_id == model_id and choice.reasoning == level and (not provider or provider == choice.provider):
            return choice, choice.key != default.key
    raise ValueError("That model is not set up for the agent. Pick one from the list, or connect its provider in "
                     "Settings → AI settings.")


def as_payload(db: Session) -> dict[str, Any]:
    offered, default = choices(db)
    return {"default": default.key, "choices": [
        {"key": c.key, "provider": c.provider, "model_id": c.model_id, "model_name": c.model_name,
         "reasoning": c.reasoning, "label": c.label, "default": c.key == default.key} for c in offered]}
