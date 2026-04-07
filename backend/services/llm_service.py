"""
LLM Service - handles AI API interactions for the investigation console.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests
from openai import OpenAI

from config import (
    LLM_MODEL,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OPENAI_API_KEY,
    QUESTION_CLASSIFICATION_ENABLED,
)
from models.llm_models import LLMProvider, get_default_model, get_model_by_id
from profile_loader import get_chat_config
from utils.prompt_trace import log_section


client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

config = get_chat_config()
system_context = config.get("system_context", "You are an AI assistant.")
analysis_guidance = config.get("analysis_guidance", "Provide clear and helpful answers.")


class LLMExecutionContext:
    def __init__(self, provider: str, model_id: str):
        self.provider = provider
        self.model_id = model_id
        self.last_prompt: str | None = None
        self.last_raw_response: str | None = None
        self.last_usage: dict[str, Any] | None = None

    def call(
        self,
        prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        timeout: int = 600,
    ) -> str:
        self.last_prompt = prompt
        self.last_raw_response = None
        self.last_usage = None

        if self.provider == "ollama":
            result = self._call_ollama(prompt, temperature, json_mode, timeout)
        elif self.provider == "openai":
            result = self._call_openai(prompt, temperature, json_mode, timeout)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.last_raw_response = result
        return result

    def _call_ollama(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        url = f"{OLLAMA_BASE_URL}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        log_section(
            source_file=__file__,
            source_func="_call_ollama",
            title="HTTP request: Ollama /api/chat payload",
            content={
                "url": url,
                "model_id": self.model_id,
                "provider": self.provider,
                "json_mode": json_mode,
                "temperature": temperature,
                "payload": payload,
            },
            as_json=True,
        )

        response = requests.post(url, json=payload, timeout=(10, timeout))
        response.raise_for_status()
        data = response.json()
        content = (data.get("message") or {}).get("content", "") or ""
        if not content.strip():
            raise ValueError("LLM returned empty response")
        return content

    def _call_openai(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        if not client:
            raise ValueError("OpenAI client not initialized. OPENAI_API_KEY not set.")

        models_without_temperature_support = ["o1", "o3", "gpt-5"]
        supports_custom_temperature = not any(
            self.model_id.startswith(prefix) for prefix in models_without_temperature_support
        )

        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt},
            ],
            "timeout": timeout,
        }
        if supports_custom_temperature:
            kwargs["temperature"] = temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        log_section(
            source_file=__file__,
            source_func="_call_openai",
            title="HTTP request: OpenAI chat.completions payload",
            content={
                "model_id": self.model_id,
                "provider": self.provider,
                "json_mode": json_mode,
                "temperature": temperature,
                "payload": kwargs,
            },
            as_json=True,
        )

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty response")

        usage = response.usage
        if usage:
            self.last_usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        return content

    def parse_json_response(self, response_text: str) -> Dict[str, Any]:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in response")
        return json.loads(response_text[start : end + 1])

    def classify_question(self, question: str) -> str:
        if not QUESTION_CLASSIFICATION_ENABLED:
            return "hybrid"

        prompt = f"""Classify this investigation question into exactly one category.

Categories:
- "semantic": Questions about content, meaning, descriptions, what someone said or did, summaries of events or documents
- "structural": Questions about counts, lists of connections, network patterns, who is connected to whom, how many, which entities
- "hybrid": Questions that need both text understanding AND graph/structural information

Question: "{question}"

Return ONLY valid JSON:
{{"classification": "semantic" or "structural" or "hybrid"}}"""

        try:
            response = self.call(prompt, temperature=0.0, json_mode=True)
            result = self.parse_json_response(response)
            classification = result.get("classification", "hybrid").lower().strip()
            if classification in ("semantic", "structural", "hybrid"):
                return classification
            return "hybrid"
        except Exception:
            return "hybrid"

    def generate_cypher(self, question: str, schema_info: str) -> Optional[str]:
        prompt = f"""{system_context}. You are also a Neo4j Cypher expert.
Given the following graph schema and AVAILABLE ENTITIES:
{schema_info}

Generate a Cypher query to answer this question:
"{question}"

CRITICAL RULES:
1. You MUST use the EXACT 'key' values from the AVAILABLE ENTITIES list above
2. DO NOT guess or invent keys - only use keys that appear in the list
3. Keys are lowercase with hyphens (e.g., 'john-smith'), NOT the display name
4. If you cannot find the exact entity key in the list, return can_query: false
5. Use only the entity types and relationship types from the schema
6. Return relevant properties (name, key, type, summary)
7. Keep queries simple and readable

Return ONLY valid JSON with this structure:
{{
    "can_query": true or false,
    "cypher": "MATCH ... RETURN ..." or null,
    "explanation": "brief explanation of what the query does"
}}
"""

        try:
            response = self.call(prompt, json_mode=True)
            result = self.parse_json_response(response)
            if result.get("can_query") and result.get("cypher"):
                return result["cypher"]
            return None
        except Exception:
            return None

    def answer_question(self, question: str, context: str, conversation_history: list[dict[str, str]] | None = None) -> str:
        answer, _ = self.answer_question_with_prompt(question, context, conversation_history=conversation_history)
        return answer

    def answer_question_with_prompt(
        self,
        question: str,
        context: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, str]:
        history_block = ""
        if conversation_history:
            history_lines: list[str] = []
            for message in conversation_history[-12:]:
                role = "User" if message.get("role") == "user" else "Assistant"
                content = (message.get("content") or "").strip()
                if content:
                    history_lines.append(f"{role}: {content}")
            if history_lines:
                history_block = (
                    "\nRecent conversation history:\n\n"
                    + "\n\n".join(history_lines)
                    + "\n"
                )

        prompt = f"""{system_context}

You have access to the following investigation context:

{context}
{history_block}
Based on this investigation context, please answer the question:
"{question}"

Guidelines:
- {analysis_guidance}
- Format your response using markdown (use **bold** for emphasis, bullet points with -)
- Do NOT use tables - use bullet points or numbered lists instead for structured data
- CITE SOURCES: When referencing specific facts, create a clickable markdown link using the format [document name, p.N](doc://document_filename.pdf/N) where N is the page number. For example: [Financial Report, p.3](doc://Financial_Report.pdf/3). Use the exact filename from the passage headers above (e.g., "USA-ET-000021.pdf"). If no page number is available, use page 1.
- When verified facts are provided with quotes, reference the original quote to support your answer
- Be specific and cite document names when relevant
- If you identify patterns or important information, explain them
- Use ALL available information from the context above - extract and synthesize details from text passages, entity information, graph connections, and any query results
- If specific details (like exact dates, amounts, or names) are mentioned, include them in your answer
- Only say "insufficient information" if the context truly contains NO relevant information about the question
- If the context has related information (even if incomplete), provide what you can find and note what additional details would be helpful
- Keep your response focused and professional
- Highlight any connections or patterns you notice across different sources of information

Answer:"""

        answer = self.call(prompt, temperature=0.3)
        if not answer or not answer.strip():
            raise ValueError("LLM returned empty answer")
        return answer, prompt


class LLMService:
    """Service for creating isolated LLM execution contexts."""

    def __init__(self):
        self.default_provider = (LLM_PROVIDER or "openai").lower()
        self.default_model_id = LLM_MODEL
        if not self.default_model_id:
            provider_enum = LLMProvider(self.default_provider)
            self.default_model_id = get_default_model(provider_enum).id

        model = get_model_by_id(self.default_model_id)
        if not model:
            provider_enum = LLMProvider(self.default_provider)
            default_model = get_default_model(provider_enum)
            self.default_provider = default_model.provider.value
            self.default_model_id = default_model.id

    @property
    def model(self) -> str:
        return self.default_model_id

    def get_current_config(self) -> tuple[str, str]:
        return self.default_provider, self.default_model_id

    def set_config(self, provider: str, model_id: str):
        self.default_provider = provider.lower()
        self.default_model_id = model_id

    def create_context(self, provider: Optional[str] = None, model_id: Optional[str] = None) -> LLMExecutionContext:
        resolved_provider = (provider or self.default_provider).lower()
        resolved_model = model_id or self.default_model_id
        model = get_model_by_id(resolved_model)
        if model:
            resolved_provider = model.provider.value
        return LLMExecutionContext(resolved_provider, resolved_model)

    # Compatibility helpers for non-chat callers.
    def call(self, prompt: str, temperature: float = 0.3, json_mode: bool = False, timeout: int = 600) -> str:
        return self.create_context().call(prompt, temperature=temperature, json_mode=json_mode, timeout=timeout)

    def parse_json_response(self, response_text: str) -> Dict[str, Any]:
        return self.create_context().parse_json_response(response_text)

    def classify_question(self, question: str) -> str:
        return self.create_context().classify_question(question)

    def generate_cypher(self, question: str, schema_info: str) -> Optional[str]:
        return self.create_context().generate_cypher(question, schema_info)

    def answer_question(self, question: str, context: str) -> str:
        return self.create_context().answer_question(question, context)

    def answer_question_with_prompt(self, question: str, context: str) -> tuple[str, str]:
        return self.create_context().answer_question_with_prompt(question, context)

    # Backwards-compatible no-ops for older callers that still try to set request-local cost context.
    def set_cost_tracking_context(self, **_: Any):
        return None

    def clear_cost_tracking_context(self):
        return None


llm_service = LLMService()
