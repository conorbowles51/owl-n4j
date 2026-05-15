"""
LLM Processor

Generic LLM-based file processor for triage.
Supports multiple prompt templates: summarize, extract_entities, classify_content, custom.
Uses LLMService for both Ollama and OpenAI backends.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from services.triage_processors.base_processor import BaseTriageProcessor, ProcessingResult

logger = logging.getLogger(__name__)

# ── Built-in prompt templates ─────────────────────────────────────────

_TEMPLATES = {
    "summarize": {
        "description": "Summarize the document content",
        "prompt": (
            "Summarize the following document content in 2-5 sentences. "
            "Focus on the key facts, entities, and any investigative relevance.\n\n"
            "Content:\n{content}\n\nSummary:"
        ),
        "json_mode": False,
    },
    "extract_entities": {
        "description": "Extract named entities (people, orgs, locations, dates, amounts)",
        "prompt": (
            "Extract all named entities from the following document. "
            "Return a JSON object with these keys: "
            '"people" (list of names), "organizations" (list), '
            '"locations" (list), "dates" (list), "amounts" (list of monetary values), '
            '"emails" (list), "phone_numbers" (list), "other" (list of other notable entities).\n\n'
            "Content:\n{content}\n\nJSON:"
        ),
        "json_mode": True,
    },
    "classify_content": {
        "description": "Classify the document by topic and relevance",
        "prompt": (
            "Classify the following document content. Return a JSON object with: "
            '"topic" (primary topic), "subtopics" (list), '
            '"relevance" ("high", "medium", "low", "none"), '
            '"relevance_reason" (brief explanation), '
            '"language" (detected language), '
            '"content_type" (e.g. "letter", "report", "chat", "email", "receipt", "legal", "other").\n\n'
            "Content:\n{content}\n\nJSON:"
        ),
        "json_mode": True,
    },
    "custom": {
        "description": "Custom user-supplied prompt",
        "prompt": "{custom_prompt}\n\nContent:\n{content}",
        "json_mode": False,
    },
}


def _read_file_text(file_path: str, max_chars: int = 50000) -> str:
    """Read text content from a file, truncating if needed."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(max_chars)
        return text
    except Exception:
        pass

    # Try binary extraction for common formats
    try:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

        if ext == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for page in reader.pages[:50]:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
            return text[:max_chars]

        if ext in ("docx",):
            from docx import Document
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text[:max_chars]

    except Exception:
        pass

    return ""


class LLMProcessor(BaseTriageProcessor):
    name = "llm_processor"
    display_name = "LLM Analysis"
    description = "Analyze files using an LLM (summarize, extract entities, classify, or custom prompt)"
    input_types = ["documents", "emails", "web"]
    output_types = ["llm_summary", "llm_entities", "llm_classification", "llm_custom"]
    requires_llm = True
    config_schema = {
        "template": {
            "type": "string",
            "default": "summarize",
            "description": "Prompt template: summarize, extract_entities, classify_content, custom",
            "enum": list(_TEMPLATES.keys()),
        },
        "custom_prompt": {
            "type": "string",
            "default": "",
            "description": "Custom prompt (used when template='custom'). Use {content} as placeholder.",
        },
        "max_chars": {
            "type": "integer",
            "default": 30000,
            "description": "Max characters to send to LLM per file",
        },
        "model_provider": {
            "type": "string",
            "default": "",
            "description": "LLM provider override: 'ollama' or 'openai' (empty = use current)",
        },
        "model_id": {
            "type": "string",
            "default": "",
            "description": "Model ID override (empty = use current)",
        },
    }

    def process_file(
        self,
        file_path: str,
        file_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        from services.llm_service import llm_service

        template_name = config.get("template", "summarize")
        template = _TEMPLATES.get(template_name)
        if not template:
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="llm_error",
                error=f"Unknown template: {template_name}",
            )]

        max_chars = config.get("max_chars", 30000)

        # Read file content
        content = _read_file_text(file_path, max_chars)
        if not content.strip():
            return []  # Skip empty files

        # Build prompt
        prompt = template["prompt"].format(
            content=content[:max_chars],
            custom_prompt=config.get("custom_prompt", "Analyze this content."),
        )

        # Optionally override model
        model_provider = config.get("model_provider", "")
        model_id = config.get("model_id", "")
        original_config = None

        if model_provider and model_id:
            original_config = llm_service.get_current_config()
            llm_service.set_config(model_provider, model_id)

        try:
            # Set cost tracking context
            llm_service.set_cost_tracking_context(
                job_type="ingestion",
                description=f"triage_llm_{template_name}",
            )

            response = llm_service.call(
                prompt=prompt,
                temperature=0.2,
                json_mode=template.get("json_mode", False),
                timeout=120,
            )

            # Parse response
            artifact_type = f"llm_{template_name}"
            metadata = {
                "template": template_name,
                "model_provider": model_provider or llm_service.get_current_config()[0],
                "model_id": model_id or llm_service.get_current_config()[1],
                "input_chars": len(content),
            }

            if template.get("json_mode"):
                try:
                    parsed = llm_service.parse_json_response(response)
                    metadata["parsed"] = parsed
                    response = json.dumps(parsed, indent=2)
                except (json.JSONDecodeError, ValueError):
                    pass  # Keep raw response

            return [ProcessingResult(
                source_path=file_path,
                artifact_type=artifact_type,
                content=response,
                metadata=metadata,
            )]

        except Exception as e:
            return [ProcessingResult(
                source_path=file_path,
                artifact_type=f"llm_{template_name}",
                error=str(e),
            )]
        finally:
            llm_service.clear_cost_tracking_context()
            if original_config:
                llm_service.set_config(*original_config)
