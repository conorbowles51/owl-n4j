import logging
from typing import Any

from app.config import settings
from app.pipeline.extract_text import ExtractedDocument
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 30000
MIN_CONTENT_CHARS = 50


def _format_special_entity_types(
    special_entity_types: list[dict[str, Any]] | None,
) -> str:
    lines: list[str] = []
    for entity_type in special_entity_types or []:
        if not isinstance(entity_type, dict):
            continue

        name = str(entity_type.get("name") or "").strip()
        if not name:
            continue

        description = str(entity_type.get("description") or "").strip()
        lines.append(f"- {name}: {description}" if description else f"- {name}")

    return "\n".join(lines)


def _build_profile_guidance(
    case_context: str | None,
    mandatory_instructions: list[str] | None,
    special_entity_types: list[dict[str, Any]] | None,
) -> str:
    parts: list[str] = []

    if case_context and case_context.strip():
        parts.append(f"**Investigation Context:**\n{case_context.strip()}")

    normalized_instructions = [
        instruction.strip()
        for instruction in mandatory_instructions or []
        if isinstance(instruction, str) and instruction.strip()
    ]
    if normalized_instructions:
        parts.append(
            "**Mandatory Processing Instructions:**\n"
            + "\n".join(f"- {instruction}" for instruction in normalized_instructions)
        )

    special_entities = _format_special_entity_types(special_entity_types)
    if special_entities:
        parts.append(f"**Special Entity Types:**\n{special_entities}")

    if not parts:
        return ""

    return (
        "Use this processing profile to interpret ambiguous identities, roles, shorthand, "
        "and relationships in the document. Treat it as investigator-provided context "
        "for this processing run; do not invent facts beyond the document and profile.\n\n"
        + "\n\n".join(parts)
        + "\n\n"
    )


async def generate_document_summary(
    doc: ExtractedDocument,
    file_name: str,
    *,
    case_context: str | None = None,
    mandatory_instructions: list[str] | None = None,
    special_entity_types: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Generate a structured markdown summary of a document.
    Returns None if the document has insufficient content or if the LLM call fails.
    """
    parts = []
    if doc.text:
        parts.append(doc.text)
    if doc.tables:
        parts.append("\n\n".join(doc.tables))
    content = "\n\n".join(parts)

    if len(content) < MIN_CONTENT_CHARS:
        logger.info("Skipping summary for %s: insufficient content (%d chars)", file_name, len(content))
        return None

    truncated = content[:MAX_CONTENT_CHARS]

    try:
        profile_guidance = _build_profile_guidance(
            case_context,
            mandatory_instructions,
            special_entity_types,
        )
        prompt = (
            "You are an expert investigative analyst. Produce a structured markdown summary of the following document.\n\n"
            f"**Document:** {file_name}\n\n"
            f"{profile_guidance}"
            f"**Content:**\n{truncated}\n\n"
            "Write the summary using the following markdown sections. Omit any section that has no relevant content.\n\n"
            "## Overview\nWhat this document is and why it matters to an investigation. 2-4 sentences.\n\n"
            "## Key Entities\nPeople, organizations, accounts, or assets mentioned. Use a bullet list with brief context for each.\n\n"
            "## Key Facts & Dates\nTimeline-relevant details: dates, amounts, events. Use a bullet list.\n\n"
            "## Notable Connections\nRelationships or patterns observed between entities. Use a bullet list.\n\n"
            "Write factually and concisely. Do not speculate. Be as detailed as the content warrants."
        )
        summary = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=settings.openai_document_summary_model,
        )
        return summary.strip() if summary else None
    except Exception:
        logger.exception("Failed to generate document summary for %s", file_name)
        return None
