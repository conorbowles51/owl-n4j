"""
LLM Service - handles AI API interactions for the investigation console.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import requests
from openai import OpenAI

from config import (
    ANTHROPIC_API_KEY,
    DEEPSEEK_API_KEY,
    GEMINI_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    QUESTION_CLASSIFICATION_ENABLED,
)
from models.llm_models import LLMProvider, get_default_model, get_model_by_id
from profile_loader import get_chat_config
from utils.prompt_trace import log_section


client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

config = get_chat_config(allow_postgres=False)
system_context = config.get("system_context", "You are an AI assistant.")
analysis_guidance = config.get("analysis_guidance", "Provide clear and helpful answers.")

RESPONSES_API_MODEL_PREFIXES = ("gpt-5",)


class LLMExecutionContext:
    def __init__(
        self,
        provider: str,
        model_id: str,
        api_key: str | None = None,
        use_responses_api_for_gpt5: bool = False,
    ):
        self.provider = provider
        self.model_id = model_id
        self.api_key = api_key
        self._client = OpenAI(api_key=api_key) if provider == "openai" and api_key else None
        self.use_responses_api_for_gpt5 = use_responses_api_for_gpt5
        runtime_config = get_chat_config()
        self.system_context = runtime_config.get("system_context", system_context)
        self.analysis_guidance = runtime_config.get("analysis_guidance", analysis_guidance)
        self.last_prompt: str | None = None
        self.last_raw_response: str | None = None
        self.last_usage: dict[str, Any] | None = None
        self.last_request_arguments: dict[str, Any] | None = None
        self.last_response_metadata: dict[str, str] = {}

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
        self.last_request_arguments = None
        self.last_response_metadata = {}

        if self.provider == "openai":
            result = self._call_openai(prompt, temperature, json_mode, timeout)
        elif self.provider == "anthropic":
            result = self._call_anthropic(prompt, temperature, json_mode, timeout)
        elif self.provider == "gemini":
            result = self._call_gemini(prompt, temperature, json_mode, timeout)
        elif self.provider == "deepseek":
            result = self._call_deepseek(prompt, temperature, json_mode, timeout)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        self.last_raw_response = result
        return result

    def _call_openai(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        openai_client = self._client or client
        if not openai_client:
            raise ValueError("OpenAI client not initialized. OPENAI_API_KEY not set.")

        if (
            self.use_responses_api_for_gpt5
            and self.model_id.startswith(RESPONSES_API_MODEL_PREFIXES)
        ):
            return self._call_openai_responses(prompt, temperature, json_mode, timeout)

        models_without_temperature_support = ["o1", "o3", "gpt-5"]
        supports_custom_temperature = not any(
            self.model_id.startswith(prefix) for prefix in models_without_temperature_support
        )

        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": self.system_context},
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

        self._remember_request(kwargs)
        response = openai_client.chat.completions.create(**kwargs)
        self._remember_response(response)
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

    def call_vision_json(
        self,
        prompt: str,
        images_png: list[bytes],
        *,
        schema: dict[str, Any],
        schema_name: str,
        timeout: int = 120,
        detail: str = "high",
        max_output_tokens: int = 8000,
        image_labels: list[str] | None = None,
    ) -> str:
        """One page-image request with schema-enforced JSON output (OpenAI only).

        Raises on any failure (no key, unsupported provider, API error, refusal,
        truncated output) so callers fail closed. The images are never logged or
        remembered; only their count and size are.
        """
        import base64

        self.last_prompt = prompt
        self.last_raw_response = None
        self.last_usage = None
        self.last_request_arguments = None
        self.last_response_metadata = {}
        from services.ai_model_capabilities import require_images

        if self.provider not in ("openai", "deepseek"):
            raise ValueError(f"Page-image reading is not available for provider {self.provider}")
        # Never sent to a model that does not take images (a text-only model can answer without reading them).
        require_images(self.provider, self.model_id, api_key=self.api_key or (DEEPSEEK_API_KEY if self.provider == "deepseek" else None),
                       context="page-image request")
        if self.provider == "deepseek":
            return self._call_deepseek_vision(prompt, images_png, schema=schema, timeout=timeout,
                                              max_output_tokens=max_output_tokens, image_labels=image_labels)
        openai_client = self._client or client
        if not openai_client:
            raise ValueError("OpenAI client not initialized. OPENAI_API_KEY not set.")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for index, image in enumerate(images_png):
            if image_labels:
                content.append({"type": "text", "text": image_labels[index]})
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image).decode("ascii"), "detail": detail}})
        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True, "schema": schema}},
            "timeout": timeout,
        }
        if self.model_id.startswith(("o1", "o3", "gpt-5")):
            kwargs["max_completion_tokens"] = max_output_tokens
        else:
            kwargs["temperature"] = 0
            kwargs["max_tokens"] = max_output_tokens
        self.last_request_arguments = {"model": self.model_id, "images": len(images_png),
                                       "image_bytes": sum(len(i) for i in images_png), "schema": schema_name}
        response = openai_client.chat.completions.create(**kwargs)
        self._remember_response(response)
        choice = response.choices[0]
        usage = response.usage
        if usage:
            self.last_usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        if getattr(choice.message, "refusal", None):
            raise ValueError("The model declined to read the page image")
        if choice.finish_reason != "stop":
            raise ValueError(f"The page-image reading was incomplete ({choice.finish_reason})")
        text = choice.message.content
        if not text:
            raise ValueError("LLM returned empty response")
        self.last_raw_response = text
        return text

    # DeepSeek page-image requests: thinking at its highest effort (Neil, 2026-10-28: example reading compared
    # at max thinking). DeepSeek enforces no schema, so the schema is stated in the prompt and the answer is
    # checked by the caller exactly as an OpenAI answer is.
    DEEPSEEK_VISION_EFFORT = "max"
    # Thinking counts against the answer's tokens; vision_reader reserves this many (DEEPSEEK_RESERVE_OUTPUT_TOKENS).
    DEEPSEEK_VISION_MAX_TOKENS = 64000
    # The longest silence allowed on the connection (DeepSeek sends keep-alive lines while it thinks); the answer as
    # a whole is bounded by the request's timeout, checked as each piece arrives.
    DEEPSEEK_READ_GAP_SECONDS = 300

    def _call_deepseek_vision(self, prompt, images_png, *, schema, timeout, max_output_tokens, image_labels=None):
        import base64

        api_key = self.api_key or DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt + "\n\nReturn only one JSON object that "
                                          "follows this JSON schema exactly (no markdown fence):\n"
                                          + json.dumps(schema, separators=(",", ":"))}]
        for index, image in enumerate(images_png):
            if image_labels:
                content.append({"type": "text", "text": image_labels[index]})
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image).decode("ascii")}})
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "reasoning_effort": self.DEEPSEEK_VISION_EFFORT,
            "max_tokens": self.DEEPSEEK_VISION_MAX_TOKENS,
        }
        self.last_request_arguments = {"model": self.model_id, "images": len(images_png),
                                       "image_bytes": sum(len(i) for i in images_png), "schema": "in prompt",
                                       "reasoning_effort": self.DEEPSEEK_VISION_EFFORT}
        # ``timeout`` bounds the whole answer by the clock: DeepSeek keeps a slow request open with blank keep-alive
        # lines, which would restart a plain read timeout, so the body is read in pieces against a deadline.
        deadline = time.monotonic() + timeout
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json=payload,
            timeout=(10, min(timeout, self.DEEPSEEK_READ_GAP_SECONDS)),
            stream=True,
        )
        # A watchdog closes the connection at the deadline whatever the body's framing (chunked, sized or
        # close-delimited, compressed or not): a read blocked on it then fails and is reported as a timeout.
        import threading
        expired = threading.Event()

        def expire():
            expired.set()
            # Shut the socket down first: that wakes a read already blocked on it (a bare close may not).
            sock = getattr(getattr(response.raw, "_connection", None), "sock", None)
            try:
                if sock is not None:
                    import socket
                    sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # noqa: BLE001 - already closed
                pass
            response.close()
        watchdog = threading.Timer(max(deadline - time.monotonic(), 0), expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            response.raise_for_status()
            body = bytearray()
            try:
                for chunk in response.iter_content(chunk_size=65536):
                    if expired.is_set() or time.monotonic() > deadline:
                        raise requests.exceptions.ReadTimeout(f"DeepSeek did not finish answering within {timeout}s")
                    body.extend(chunk or b"")
            except requests.exceptions.ReadTimeout:
                raise
            except Exception as error:
                if expired.is_set():
                    raise requests.exceptions.ReadTimeout(
                        f"DeepSeek did not finish answering within {timeout}s") from error
                raise
            if expired.is_set():
                raise requests.exceptions.ReadTimeout(f"DeepSeek did not finish answering within {timeout}s")
        finally:
            watchdog.cancel()
            response.close()
        data = json.loads(bytes(body).decode("utf-8").strip() or "{}")
        # Usage first: an answer cut short is still billed, and the caller records what it cost.
        usage = data.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
        }
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("DeepSeek returned no answer")
        if choices[0].get("finish_reason") != "stop":
            raise ValueError(f"The page-image reading was incomplete ({choices[0].get('finish_reason')})")
        text = str((choices[0].get("message") or {}).get("content") or "").strip()
        if not text:
            raise ValueError("DeepSeek returned an empty response")
        self.last_raw_response = text
        return text

    def _call_anthropic(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        api_key = self.api_key or ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        user_prompt = prompt
        if json_mode:
            user_prompt += "\n\nReturn only one valid JSON object with no markdown fence."
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": 8192,
            "system": self.system_context,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if not self.model_id.startswith(("claude-sonnet-5", "claude-opus-4-8", "claude-fable-5")):
            payload["temperature"] = temperature
        self._remember_request(payload)
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=(10, timeout),
        )
        response.raise_for_status()
        data = response.json()
        self._remember_response(data)
        content = "\n".join(
            str(block.get("text") or "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if not content:
            raise ValueError("Anthropic returned an empty response")
        usage = data.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": usage.get("output_tokens"),
            "total_tokens": (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0),
        }
        return content

    def _call_gemini(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        api_key = self.api_key or GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        generation_config: dict[str, Any] = {}
        if not self.model_id.startswith("gemini-3"):
            generation_config["temperature"] = temperature
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload = {
            "systemInstruction": {"parts": [{"text": self.system_context}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        self._remember_request(payload)
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent",
            headers={"x-goog-api-key": api_key, "content-type": "application/json"},
            json=payload,
            timeout=(10, timeout),
        )
        response.raise_for_status()
        data = response.json()
        self._remember_response(data)
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        content = "\n".join(str(part.get("text") or "") for part in parts).strip()
        if not content:
            raise ValueError("Gemini returned an empty response")
        usage = data.get("usageMetadata") or {}
        self.last_usage = {
            "prompt_tokens": usage.get("promptTokenCount"),
            "completion_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        }
        return content

    def _call_deepseek(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        api_key = self.api_key or DEEPSEEK_API_KEY
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set")
        user_prompt = prompt
        if json_mode:
            user_prompt += "\n\nReturn only one valid JSON object with no markdown fence."
        payload: Dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": self.system_context},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            # Non-thinking mode is deliberately used for predictable JSON and
            # OpenAI-compatible multi-turn behavior across Loupe workloads.
            "thinking": {"type": "disabled"},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        self._remember_request(payload)
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=payload,
            timeout=(10, timeout),
        )
        response.raise_for_status()
        data = response.json()
        self._remember_response(data)
        choices = data.get("choices") or []
        content = str(((choices[0].get("message") or {}).get("content") or "")).strip() if choices else ""
        if not content:
            raise ValueError("DeepSeek returned an empty response")
        usage = data.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return content

    def _call_openai_responses(
        self,
        prompt: str,
        temperature: float,
        json_mode: bool,
        timeout: int,
    ) -> str:
        models_without_temperature_support = ["o1", "o3", "gpt-5"]
        supports_custom_temperature = not any(
            self.model_id.startswith(prefix) for prefix in models_without_temperature_support
        )

        kwargs: Dict[str, Any] = {
            "model": self.model_id,
            "instructions": self.system_context,
            "input": prompt,
            "store": False,
            "timeout": timeout,
        }
        if supports_custom_temperature:
            kwargs["temperature"] = temperature
        if json_mode:
            kwargs["text"] = {"format": {"type": "json_object"}}

        log_section(
            source_file=__file__,
            source_func="_call_openai_responses",
            title="HTTP request: OpenAI responses payload",
            content={
                "model_id": self.model_id,
                "provider": self.provider,
                "json_mode": json_mode,
                "temperature": temperature,
                "payload": kwargs,
            },
            as_json=True,
        )

        openai_client = self._client or client
        if not openai_client:
            raise ValueError("OpenAI client not initialized. OPENAI_API_KEY not set.")
        self._remember_request(kwargs)
        response = openai_client.responses.create(**kwargs)
        self._remember_response(response)
        content = self._extract_response_text(response)
        if not content:
            status = getattr(response, "status", None)
            error = getattr(response, "error", None)
            details = getattr(response, "incomplete_details", None)
            raise ValueError(
                "LLM returned empty response"
                f" (status={status}, error={error}, details={details})"
            )

        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = self._usage_value(usage, "input_tokens")
            completion_tokens = self._usage_value(usage, "output_tokens")
            total_tokens = self._usage_value(usage, "total_tokens")
            self.last_usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        return content

    def _remember_request(self, arguments: dict[str, Any]) -> None:
        # SDK arguments or HTTP JSON body only: never headers or credentials.
        from copy import deepcopy
        self.last_request_arguments = deepcopy(arguments)

    def _remember_response(self, response: Any) -> None:
        fields = (("reported_model", ("model", "modelVersion")), ("response_id", ("id", "responseId")))
        captured = {}
        for label, names in fields:
            for name in names:
                value = response.get(name) if isinstance(response, dict) else getattr(response, name, None)
                if isinstance(value, str) and value.strip() and len(value) <= 256:
                    captured[label] = value
                    break
        self.last_response_metadata = captured

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        text_parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content_item in getattr(item, "content", []) or []:
                text = getattr(content_item, "text", None)
                if isinstance(text, str) and text:
                    text_parts.append(text)
        return "\n".join(text_parts).strip()

    @staticmethod
    def _usage_value(usage: Any, key: str) -> Optional[int]:
        if isinstance(usage, dict):
            value = usage.get(key)
        else:
            value = getattr(usage, key, None)
        return int(value) if value is not None else None

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
        prompt = f"""{self.system_context}. You are also a Neo4j Cypher expert.
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
8. Bind EVERY node and relationship to the case: write each node as (n:Label {{case_id: $case_id}}) and each
   relationship as [r:TYPE {{case_id: $case_id}}], or add WHERE n.case_id = $case_id. Never put a case id
   value in the query; $case_id is supplied for you.
9. Use only MATCH, OPTIONAL MATCH, WHERE, RETURN, ORDER BY and LIMIT, with single-hop relationships
   (no WITH, UNWIND, UNION, subqueries or variable-length paths)

Return ONLY valid JSON with this structure:
{{
    "can_query": true or false,
    "cypher": "MATCH (n:Person {{case_id: $case_id}}) WHERE n.key = 'john-smith' RETURN n.name, n.summary" or null,
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

        prompt = f"""{self.system_context}

You have access to the following investigation context:

{context}
{history_block}
Based on this investigation context, please answer the question:
"{question}"

Guidelines:
- {self.analysis_guidance}
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

    def create_context(
        self,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        api_key: str | None = None,
        use_responses_api_for_gpt5: bool = False,
    ) -> LLMExecutionContext:
        resolved_provider = (provider or self.default_provider).lower()
        resolved_model = model_id or self.default_model_id
        model = get_model_by_id(resolved_model)
        if model:
            resolved_provider = model.provider.value
        if api_key is None:
            try:
                from postgres.session import get_background_session
                from services.ai_provider_credentials import get_provider_api_key

                with get_background_session() as db:
                    api_key = get_provider_api_key(db, resolved_provider)
            except Exception:
                api_key = None
        return LLMExecutionContext(
            resolved_provider,
            resolved_model,
            api_key=api_key,
            use_responses_api_for_gpt5=use_responses_api_for_gpt5,
        )

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
