import logging

from app.pipeline.extract_text import ExtractedDocument
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 30000
MIN_CONTENT_CHARS = 50


async def generate_document_summary(
    doc: ExtractedDocument, file_name: str
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
        prompt = (
            "You are an expert investigative analyst. Produce a structured markdown summary of the following document.\n\n"
            f"**Document:** {file_name}\n\n"
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
            temperature=0.3,
        )
        return summary.strip() if summary else None
    except Exception:
        logger.exception("Failed to generate document summary for %s", file_name)
        return None
