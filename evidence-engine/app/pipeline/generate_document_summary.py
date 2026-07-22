import asyncio
import json
import logging
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.pipeline.extract_text import ExtractedDocument
from app.pipeline.prompt_security import secure_system_prompt
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 30000
MIN_CONTENT_CHARS = 50
SUMMARY_MAP_CHARS = 18000
SUMMARY_REDUCE_CHARS = 28000
SUMMARY_MAP_OUTPUT_TOKENS = 16384
SUMMARY_REDUCE_OUTPUT_TOKENS = 16384
SUMMARY_RETRY_OUTPUT_TOKENS = 32768
SUMMARY_MAX_REDUCTION_LEVELS = 8

_DOCUMENT_SUMMARY_REVIEW_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "document_summary_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "corrected_summary": {"type": "string"},
                "correction_count": {"type": "integer"},
            },
            "required": ["corrected_summary", "correction_count"],
            "additionalProperties": False,
        },
    },
}


def _page_aware_text(doc: ExtractedDocument) -> str:
    page_spans = doc.metadata.get("page_spans") or []
    if doc.metadata.get("file_type") != "pdf" or not page_spans:
        return doc.text
    pages: list[str] = []
    for span in page_spans:
        try:
            page = int(span["page"])
            start = int(span["start_char"])
            end = int(span["end_char"])
        except (KeyError, TypeError, ValueError):
            continue
        pages.append(f"[PDF page {page}]\n{doc.text[start:end]}")
    return "\n\n".join(pages) if pages else doc.text


async def _review_document_summary(
    *,
    draft: str,
    evidence_context: str,
    file_name: str,
    citation_target: str,
) -> tuple[str, int]:
    prompt = (
        "Audit and correct the draft document summary against the supplied evidence context. "
        "Return the complete corrected markdown summary. Remove or rewrite every unsupported count, "
        "cardinality, identity, ownership, motive, intent, significance claim, causal claim, pattern, "
        "or other interpretation. Preserve qualifiers such as alleged, reported, claimed, and disputed. "
        "Do not turn role titles, phone-tower activity, proximity, timing, or initials into conclusions. "
        "Retain material facts and the existing section structure. Every overview paragraph and every "
        "bullet containing a factual claim must end with the most specific available source link in the "
        f"form [{file_name}, p.N](doc://{citation_target}/N). Use page 1 only when the context has no page labels.\n\n"
        f"EVIDENCE CONTEXT:\n{evidence_context}\n\nDRAFT SUMMARY:\n{draft}"
    )
    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": secure_system_prompt(
                    "You are a strict source-entailment editor. Correct unsupported summary claims; do not add analysis."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        workload="ingestion_quality",
        response_format=_DOCUMENT_SUMMARY_REVIEW_SCHEMA,
    )
    data = json.loads(response)
    corrected = str(data.get("corrected_summary") or "").strip()
    corrections = int(data.get("correction_count") or 0)
    return corrected or draft, corrections


def _overview_length_guidance(doc: ExtractedDocument, content_length: int) -> str:
    raw_page_count = doc.metadata.get("page_count")
    try:
        page_count = int(raw_page_count) if raw_page_count is not None else 0
    except (TypeError, ValueError):
        page_count = 0

    if page_count >= 100 or content_length >= 250_000:
        return "Write five to eight substantive paragraphs (roughly 600-1,000 words)."
    if page_count >= 25 or content_length >= 75_000:
        return "Write three to five substantive paragraphs (roughly 350-650 words)."
    if page_count >= 5 or content_length >= 15_000:
        return "Write two to four substantive paragraphs (roughly 200-450 words)."
    return "Write one to three substantive paragraphs (roughly 120-300 words)."


def _split_summary_segments(content: str) -> list[tuple[int, int, str]]:
    """Cover the full source in ordered, non-overlapping, natural-break segments."""
    segments: list[tuple[int, int, str]] = []
    start = 0
    while start < len(content):
        end = min(start + SUMMARY_MAP_CHARS, len(content))
        if end < len(content):
            search_start = start + (SUMMARY_MAP_CHARS // 2)
            for separator in ("\n\n", "\n", ". ", " "):
                candidate = content.rfind(separator, search_start, end)
                if candidate >= 0:
                    end = candidate + len(separator)
                    break
        segments.append((start, end, content[start:end]))
        start = end
    return segments


def _digest_groups(digests: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for digest in digests:
        size = len(digest) + 2
        if current and current_chars + size > SUMMARY_REDUCE_CHARS:
            groups.append(current)
            current = []
            current_chars = 0
        current.append(digest)
        current_chars += size
    if current:
        groups.append(current)
    return groups


def _pairwise_digest_groups(digests: list[str]) -> list[list[str]]:
    """Guarantee structural progress when size-based grouping yields singletons."""
    return [digests[index : index + 2] for index in range(0, len(digests), 2)]


def _digest_payload_chars(digests: list[str]) -> int:
    return len("\n\n".join(digests))


async def _summarize_all_segments(
    content: str,
    *,
    file_name: str,
    profile_guidance: str,
) -> str:
    segments = _split_summary_segments(content)
    semaphore = asyncio.Semaphore(max(1, settings.document_summary_max_concurrency))

    async def summarize_segment(index: int, start: int, end: int, text: str) -> str:
        prompt = (
            "Create a dense, facts-only evidence digest for this complete source segment. "
            "Retain material names, roles, dates, amounts, identifiers, events, allegations with attribution, "
            "relationships explicitly stated by the source, findings, and requested actions. Do not infer, "
            "evaluate, or omit material detail merely because it seems repetitive. Prioritize the details most "
            "important to an investigator and keep the digest to no more than 1,200 words. This digest will be "
            "used to build the document-level summary.\n\n"
            f"Document: {file_name}\n"
            f"SOURCE SEGMENT {index + 1} OF {len(segments)} "
            f"(characters {start + 1}-{end} of {len(content)}):\n"
            f"{profile_guidance}{text}"
        )
        messages = [
            {
                "role": "system",
                "content": secure_system_prompt(
                    "Create facts-only evidence digests and preserve source attribution."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        async with semaphore:
            digest = await chat_completion(
                messages=messages,
                workload="ingestion_document_summary",
                max_output_tokens=SUMMARY_MAP_OUTPUT_TOKENS,
            )
            if not digest or not digest.strip():
                logger.warning(
                    "Empty digest for source segment %d; retrying with a larger output budget",
                    index + 1,
                )
                digest = await chat_completion(
                    messages=messages,
                    workload="ingestion_document_summary",
                    max_output_tokens=SUMMARY_RETRY_OUTPUT_TOKENS,
                )
        if not digest or not digest.strip():
            raise RuntimeError(f"Empty digest for source segment {index + 1}")
        return (
            f"[Source segment {index + 1} of {len(segments)}; characters {start + 1}-{end}]\n"
            f"{digest.strip()}"
        )

    digests = await asyncio.gather(
        *(
            summarize_segment(index, start, end, text)
            for index, (start, end, text) in enumerate(segments)
        )
    )

    level = 1
    while _digest_payload_chars(digests) > SUMMARY_REDUCE_CHARS:
        if level > SUMMARY_MAX_REDUCTION_LEVELS:
            raise RuntimeError(
                "Document digest reduction exceeded the maximum number of levels"
            )

        before_chars = _digest_payload_chars(digests)
        groups = _digest_groups(digests)
        if len(groups) >= len(digests) and len(digests) > 1:
            # Verbose model output can make every size-based group a singleton.
            # Pair adjacent digests so the hierarchy still converges.
            groups = _pairwise_digest_groups(digests)

        reduced: list[str] = []
        for group_index, group in enumerate(groups, start=1):
            prompt = (
                "DIGEST CONSOLIDATION: Combine the following ordered evidence digests into one dense, "
                "facts-only digest. Preserve all material names, dates, amounts, identifiers, events, "
                "attributed allegations, explicit relationships, findings, and actions. Do not add analysis. "
                "Prioritize the details most important to an investigator and keep the consolidated digest "
                "to no more than 1,200 words.\n\n"
                + "\n\n".join(group)
            )
            messages = [
                {
                    "role": "system",
                    "content": secure_system_prompt(
                        "Consolidate evidence digests without adding facts or analysis."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            digest = await chat_completion(
                messages=messages,
                workload="ingestion_document_summary",
                max_output_tokens=SUMMARY_REDUCE_OUTPUT_TOKENS,
            )
            if not digest or not digest.strip():
                logger.warning(
                    "Empty digest during reduction level %d, group %d; "
                    "retrying with a larger output budget",
                    level,
                    group_index,
                )
                digest = await chat_completion(
                    messages=messages,
                    workload="ingestion_document_summary",
                    max_output_tokens=SUMMARY_RETRY_OUTPUT_TOKENS,
                )
            if not digest or not digest.strip():
                raise RuntimeError(
                    f"Empty digest during reduction level {level}, group {group_index}"
                )
            reduced.append(
                f"[Consolidated digest level {level}, group {group_index} of {len(groups)}]\n"
                f"{digest.strip()}"
            )

        after_chars = _digest_payload_chars(reduced)
        if len(reduced) >= len(digests) and after_chars >= before_chars:
            raise RuntimeError(
                "Document digest reduction made no progress "
                f"({before_chars} characters before, {after_chars} after)"
            )
        digests = reduced
        level += 1

    return "\n\n".join(digests)


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
        parts.append(_page_aware_text(doc))
    if doc.tables:
        parts.append("\n\n".join(doc.tables))
    content = "\n\n".join(parts)

    if len(content) < MIN_CONTENT_CHARS:
        doc.metadata["document_summary_status"] = "skipped_insufficient_content"
        logger.info("Skipping summary for %s: insufficient content (%d chars)", file_name, len(content))
        return None

    try:
        profile_guidance = _build_profile_guidance(
            case_context,
            mandatory_instructions,
            special_entity_types,
        )
        overview_length_guidance = _overview_length_guidance(doc, len(content))
        citation_target = quote(file_name, safe="")
        is_hierarchical = len(content) > MAX_CONTENT_CHARS
        summary_content = (
            await _summarize_all_segments(
                content,
                file_name=file_name,
                profile_guidance=profile_guidance,
            )
            if is_hierarchical
            else content
        )
        content_heading = (
            "**COMPLETE SET OF SOURCE-SEGMENT DIGESTS:**"
            if is_hierarchical
            else "**Content:**"
        )
        prompt = (
            "You are an expert investigative analyst. Produce a structured markdown summary of the following document.\n\n"
            f"**Document:** {file_name}\n\n"
            f"{profile_guidance}"
            f"{content_heading}\n{summary_content}\n\n"
            "Write the summary using the following markdown sections. Omit any section that has no relevant content.\n\n"
            "## Overview\n"
            "Write a standalone, comprehensive narrative summary of the document, not merely an abstract or introduction. "
            f"{overview_length_guidance} "
            "Do not limit the Overview to an abstract or a few introductory sentences. "
            "Explain the document's purpose and scope, principal subjects, material chronology, significant events or transactions, "
            "key supporting details, and any stated findings, outcomes, or requested actions. Connect these details into a coherent account "
            "so an investigator can understand the document without first reading the lists below. It is acceptable to repeat the most "
            "important facts later in the structured sections.\n\n"
            "## Key Entities\nPeople, organizations, accounts, or assets mentioned. Use a bullet list with brief context for each.\n\n"
            "## Key Facts & Dates\nTimeline-relevant details: dates, amounts, events. Use a bullet list.\n\n"
            "## Notable Connections\nRelationships or patterns observed between entities. Use a bullet list.\n\n"
            "Write factually and precisely. Do not speculate, infer motives, or add opinions. Clearly distinguish documented facts from "
            "attributed allegations, claims, and disputed statements. Do not describe a communication pattern as consistent with a type "
            "of conduct unless the document itself says that. Do not infer identity from initials, proximity, role, or timing. "
            "Every Overview paragraph and every factual bullet must end with a source link using "
            f"[{file_name}, p.N](doc://{citation_target}/N), choosing the supporting PDF page number shown in the content. "
            "Use page 1 when the source has no page labels. Be as detailed as the content warrants."
        )
        summary = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": secure_system_prompt(
                        "Produce a factual, source-bound investigative document summary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            workload="ingestion_document_summary",
        )
        rendered = summary.strip() if summary else ""
        if rendered:
            try:
                rendered, correction_count = await _review_document_summary(
                    draft=rendered,
                    evidence_context=summary_content,
                    file_name=file_name,
                    citation_target=citation_target,
                )
                doc.metadata["document_summary_correction_count"] = correction_count
                doc.metadata["document_summary_quality_status"] = "reviewed"
            except Exception as review_exc:
                logger.exception("Document summary review failed for %s", file_name)
                doc.metadata["document_summary_quality_status"] = "review_failed"
                doc.metadata["document_summary_quality_error"] = str(review_exc)[:1000]
            doc.metadata["document_summary_status"] = "generated"
            doc.metadata.pop("document_summary_error", None)
            return rendered
        doc.metadata["document_summary_status"] = "failed"
        doc.metadata["document_summary_error"] = "The summary model returned an empty response"
        return None
    except Exception as exc:
        doc.metadata["document_summary_status"] = "failed"
        doc.metadata["document_summary_error"] = str(exc)[:1000]
        logger.exception("Failed to generate document summary for %s", file_name)
        return None
