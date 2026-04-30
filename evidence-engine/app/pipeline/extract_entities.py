import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.ontology import ENTITY_CATEGORIES

logger = logging.getLogger(__name__)
from app.ontology.prompt_builder import (
    build_entity_extraction_prompt,
    build_relationship_extraction_prompt,
)
from app.ontology.schema_builder import get_entity_schema, get_relationship_schema
from app.pipeline.mandatory_rules import normalize_mandatory_instructions
from app.pipeline.chunk_embed import TextChunk
from app.services.openai_client import chat_completion


_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    """Parse confidence values that may arrive as numbers or malformed LLM strings.

    Some LLM responses occasionally emit `confidence` as a string like ``": 0.85"`` or
    ``"confidence: 0.85"`` instead of a number, which crashes ``float()``. Fall back
    to the first numeric token in the string, otherwise the default.
    """
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        try:
            return max(0.0, min(1.0, float(value.strip())))
        except ValueError:
            match = _NUMBER_RE.search(value)
            if match:
                try:
                    return max(0.0, min(1.0, float(match.group(0))))
                except ValueError:
                    pass
            logger.warning("could not parse confidence %r, using default %s", value, default)
    return default


def _clean_entity_name(name: str) -> str:
    """Light cleanup of entity names at extraction time."""
    name = name.strip()
    name = name.rstrip('.')
    return " ".join(name.split())


@dataclass
class RawEntity:
    temp_id: str
    category: str
    specific_type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_quote: str = ""
    confidence: float = 0.5
    source_chunk_index: int = 0
    source_file: str = ""
    verified_facts: list[dict[str, Any]] = field(default_factory=list)
    ai_insights: list[dict[str, Any]] = field(default_factory=list)
    mandatory_instructions: list[str] = field(default_factory=list)


@dataclass
class RawRelationship:
    source_entity_id: str
    target_entity_id: str
    type: str
    detail: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    source_quote: str = ""
    confidence: float = 0.5
    source_chunk_index: int = 0
    source_file: str = ""
    mandatory_instructions: list[str] = field(default_factory=list)


FINANCIAL_RECORD_KINDS = {
    "transaction",
    "invoice",
    "payment_instruction",
    "balance",
    "asset_value",
    "fraud_total",
    "allegation",
    "summary_metric",
    "other",
}
FINANCIAL_VIEW_MODES = {"transaction", "intelligence"}
EVIDENCE_STRENGTHS = {"documentary", "derived", "narrative", "unknown"}
EVIDENCE_SOURCE_TYPES = {
    "bank_statement",
    "invoice",
    "receipt",
    "wire",
    "card_statement",
    "ledger",
    "official_report",
    "email",
    "interview",
    "other",
}
DOCUMENTARY_SOURCE_TYPES = {
    "bank_statement",
    "invoice",
    "receipt",
    "wire",
    "card_statement",
    "ledger",
    "official_report",
}
NARRATIVE_SOURCE_TYPES = {"email", "interview"}
FINANCIAL_CANDIDATE_KEYS = {
    "amount",
    "currency",
    "balance",
    "value",
    "price",
    "cost",
    "total",
}


def _normalized_text(*parts: Any) -> str:
    return " ".join(str(part or "").strip().lower() for part in parts if part).strip()


def _parse_int_or_none(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_financial_candidate(
    category: str,
    specific_type: str,
    name: str,
    source_quote: str,
    properties: dict[str, Any],
) -> bool:
    if any(properties.get(key) not in ("", None) for key in FINANCIAL_CANDIDATE_KEYS):
        return True
    probe = _normalized_text(category, specific_type, name, source_quote)
    return any(
        keyword in probe
        for keyword in (
            "transaction",
            "payment",
            "invoice",
            "transfer",
            "wire",
            "balance",
            "proceeds",
            "fraud",
            "asset value",
            "valuation",
            "bank statement",
            "ledger",
            "receipt",
            "amount",
            "eur",
            "usd",
            "gbp",
            "€",
            "$",
            "£",
        )
    )


def _infer_evidence_source_type(
    financial_provenance: dict[str, Any] | None,
    *,
    file_name: str,
    file_type: str | None,
    specific_type: str,
    name: str,
    source_quote: str,
    is_table: bool,
) -> str:
    candidate = str((financial_provenance or {}).get("evidence_source_type", "")).strip().lower()
    if candidate in EVIDENCE_SOURCE_TYPES:
        return candidate

    probe = _normalized_text(file_name, file_type, specific_type, name, source_quote)
    keyword_map = (
        ("bank_statement", ("bank statement", "account statement", "bank account statement")),
        ("card_statement", ("card statement", "credit card", "debit card")),
        ("wire", ("wire", "swift", "iban", "bic", "transfer confirmation")),
        ("invoice", ("invoice", "inv-", "bill to", "purchase order")),
        ("receipt", ("receipt", "paid receipt", "proof of payment")),
        ("ledger", ("ledger", "general ledger", "journal entry", "trial balance")),
        ("official_report", ("report", "warrant", "official report", "filing")),
        ("email", ("email", "e-mail", "@")),
        ("interview", ("interview", "statement", "witness", "transcript")),
    )
    for source_type, keywords in keyword_map:
        if any(keyword in probe for keyword in keywords):
            return source_type

    if file_type in {"xlsx", "xls", "csv"}:
        return "ledger" if is_table else "other"
    if file_type == "pdf" and is_table:
        return "official_report"
    return "other"


def _infer_evidence_strength(
    financial_provenance: dict[str, Any] | None,
    *,
    evidence_source_type: str,
    file_type: str | None,
    is_table: bool,
) -> str:
    candidate = str((financial_provenance or {}).get("evidence_strength", "")).strip().lower()
    if candidate in EVIDENCE_STRENGTHS:
        return candidate

    if evidence_source_type in DOCUMENTARY_SOURCE_TYPES:
        return "documentary"
    if evidence_source_type in NARRATIVE_SOURCE_TYPES:
        return "narrative"
    if is_table or file_type in {"xlsx", "xls", "csv"}:
        return "derived"
    return "unknown"


def _infer_financial_record_kind(
    financial_provenance: dict[str, Any] | None,
    *,
    category: str,
    specific_type: str,
    name: str,
    source_quote: str,
    properties: dict[str, Any],
) -> str:
    candidate = str((financial_provenance or {}).get("financial_record_kind", "")).strip().lower()
    if candidate in FINANCIAL_RECORD_KINDS:
        return candidate

    probe = _normalized_text(category, specific_type, name, source_quote)
    if "balance" in probe:
        return "balance"
    if any(keyword in probe for keyword in ("asset value", "valuation", "property value", "worth")):
        return "asset_value"
    if any(keyword in probe for keyword in ("fraud total", "alleged proceeds", "proceeds", "aggregate", "total alleged")):
        return "fraud_total"
    if any(keyword in probe for keyword in ("alleged", "suspected", "claimed", "claim")):
        return "allegation"
    if any(keyword in probe for keyword in ("summary", "total", "aggregate")) and properties.get("amount") not in ("", None):
        return "summary_metric"
    if "invoice" in probe:
        return "invoice"
    if any(keyword in probe for keyword in ("payment instruction", "remittance", "payment order")):
        return "payment_instruction"
    if any(keyword in probe for keyword in ("transaction", "transfer", "payment", "wire", "swift", "deposit", "withdrawal", "purchase")):
        return "transaction"
    if properties.get("amount") not in ("", None):
        return "transaction" if category in {"Transaction", "Event"} else "other"
    return "other"


def _looks_like_transaction_event(
    category: str,
    specific_type: str,
    name: str,
    source_quote: str,
    properties: dict[str, Any],
) -> bool:
    if properties.get("amount") in ("", None):
        return False
    if any(
        properties.get(key) not in ("", None)
        for key in (
            "date",
            "time",
            "from_entity_key",
            "from_entity_name",
            "to_entity_key",
            "to_entity_name",
            "sender",
            "receiver",
            "counterparty",
            "account_number",
            "reference",
            "payment_reference",
        )
    ):
        return True
    probe = _normalized_text(category, specific_type, name, source_quote)
    return any(
        keyword in probe
        for keyword in (
            "transaction",
            "payment",
            "transfer",
            "wire",
            "swift",
            "debit",
            "credit",
            "purchase",
            "deposit",
            "withdrawal",
            "sent to",
            "received from",
        )
    )


def _build_financial_provenance(
    financial_provenance: dict[str, Any] | None,
    *,
    category: str,
    specific_type: str,
    name: str,
    source_quote: str,
    properties: dict[str, Any],
    file_name: str,
    file_type: str | None,
    source_document_id: str | None,
    source_page: int | None,
    confidence: float,
    is_table: bool,
) -> dict[str, Any] | None:
    if not _is_financial_candidate(category, specific_type, name, source_quote, properties):
        return None

    evidence_source_type = _infer_evidence_source_type(
        financial_provenance,
        file_name=file_name,
        file_type=file_type,
        specific_type=specific_type,
        name=name,
        source_quote=source_quote,
        is_table=is_table,
    )
    evidence_strength = _infer_evidence_strength(
        financial_provenance,
        evidence_source_type=evidence_source_type,
        file_type=file_type,
        is_table=is_table,
    )
    record_kind = _infer_financial_record_kind(
        financial_provenance,
        category=category,
        specific_type=specific_type,
        name=name,
        source_quote=source_quote,
        properties=properties,
    )
    transaction_like = _looks_like_transaction_event(
        category,
        specific_type,
        name,
        source_quote,
        properties,
    )
    is_evidence_backed_transaction = (
        record_kind in {"transaction", "payment_instruction"}
        and transaction_like
        and evidence_strength == "documentary"
    )
    financial_view_mode = "transaction" if is_evidence_backed_transaction else "intelligence"
    source_excerpt = str((financial_provenance or {}).get("source_excerpt", "")).strip() or source_quote.strip()
    source_page_value = _parse_int_or_none((financial_provenance or {}).get("source_page"))
    if source_page_value is None:
        source_page_value = source_page

    if transaction_like and not is_evidence_backed_transaction:
        logger.info(
            "Financial candidate downgraded to intelligence: name=%r file=%r source_type=%s strength=%s record_kind=%s",
            name,
            file_name,
            evidence_source_type,
            evidence_strength,
            record_kind,
        )

    return {
        "financial_record_kind": record_kind,
        "financial_view_mode": financial_view_mode,
        "is_financial_event": True,
        "is_evidence_backed_transaction": is_evidence_backed_transaction,
        "evidence_strength": evidence_strength,
        "evidence_source_type": evidence_source_type,
        "source_document_id": source_document_id or file_name,
        "source_filename": file_name,
        "source_page": source_page_value,
        "source_excerpt": source_excerpt,
        "extraction_confidence": round(confidence, 4),
        "financial_model_version": 2,
    }


async def _extract_entities_from_chunk(
    chunk_text: str,
    chunk_index: int,
    file_name: str,
    case_context: str,
    mandatory_instructions: list[str] | None = None,
    special_entity_types: list[dict[str, Any]] | None = None,
    is_table: bool = False,
    sheet_name: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
    file_type: str | None = None,
    source_document_id: str | None = None,
) -> list[RawEntity]:
    normalized_instructions = normalize_mandatory_instructions(mandatory_instructions)
    prompt = build_entity_extraction_prompt(
        chunk_text=chunk_text,
        file_name=file_name,
        case_context=case_context,
        mandatory_instructions=normalized_instructions,
        special_entity_types=special_entity_types,
        is_table=is_table,
        sheet_name=sheet_name,
        page_start=page_start,
        page_end=page_end,
        file_type=file_type,
    )

    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract structured entities from investigative documents. "
                    "The mandatory profile rules in the user prompt are binding and override generic extraction defaults. "
                    "Apply them exactly whenever the document provides enough evidence to do so. "
                    "Treat any response that ignores those rules as invalid. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=settings.openai_extraction_model,
        response_format=get_entity_schema(),
    )

    data = json.loads(response)
    entities: list[RawEntity] = []
    _categories_set = set(ENTITY_CATEGORIES)

    for i, e in enumerate(data.get("entities", [])):
        category = e.get("category", "Other")
        if category not in _categories_set:
            category = "Other"

        name = _clean_entity_name(e.get("name", ""))
        if not name:
            continue

        verified_facts = _normalize_verified_facts(
            e.get("verified_facts", []),
            file_name=file_name,
            fallback_page=page_start,
        )
        ai_insights = _normalize_ai_insights(
            e.get("ai_insights", []),
            file_name=file_name,
        )

        properties = dict(e.get("properties", {}) or {})
        source_quote = str(e.get("source_quote", ""))
        confidence = _coerce_confidence(e.get("confidence"))
        financial_provenance = _build_financial_provenance(
            e.get("financial_provenance"),
            category=category,
            specific_type=e.get("specific_type", category),
            name=name,
            source_quote=source_quote,
            properties=properties,
            file_name=file_name,
            file_type=file_type,
            source_document_id=source_document_id,
            source_page=page_start,
            confidence=confidence,
            is_table=is_table,
        )
        if financial_provenance:
            properties.update(financial_provenance)

        entities.append(
            RawEntity(
                temp_id=f"chunk{chunk_index}_E{i}",
                category=category,
                specific_type=e.get("specific_type", category),
                name=name,
                properties=properties,
                source_quote=source_quote,
                confidence=confidence,
                source_chunk_index=chunk_index,
                source_file=file_name,
                verified_facts=verified_facts,
                ai_insights=ai_insights,
                mandatory_instructions=normalized_instructions,
            )
        )

    return entities


async def _extract_relationships_from_chunk(
    chunk_text: str,
    chunk_index: int,
    entities: list[RawEntity],
    file_name: str,
    case_context: str,
    mandatory_instructions: list[str] | None = None,
) -> list[RawRelationship]:
    if not entities:
        return []
    normalized_instructions = normalize_mandatory_instructions(mandatory_instructions)

    entities_json = json.dumps(
        [
            {
                "id": e.temp_id,
                "category": e.category,
                "name": e.name,
                "specific_type": e.specific_type,
            }
            for e in entities
        ],
        indent=2,
    )

    prompt = build_relationship_extraction_prompt(
        chunk_text=chunk_text,
        file_name=file_name,
        case_context=case_context,
        entities_json=entities_json,
        mandatory_instructions=normalized_instructions,
    )

    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract relationships between entities. "
                    "The mandatory profile rules in the user prompt are binding and override generic extraction defaults. "
                    "Apply them exactly whenever the document provides enough evidence to do so. "
                    "Treat any response that ignores those rules as invalid. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=settings.openai_extraction_model,
        response_format=get_relationship_schema(),
    )

    data = json.loads(response)
    entity_ids = {e.temp_id for e in entities}
    relationships: list[RawRelationship] = []

    for r in data.get("relationships", []):
        src = r.get("source_entity_id", "")
        tgt = r.get("target_entity_id", "")
        if src not in entity_ids or tgt not in entity_ids:
            continue

        relationships.append(
            RawRelationship(
                source_entity_id=src,
                target_entity_id=tgt,
                type=r.get("type", "ASSOCIATED_WITH"),
                detail=r.get("detail", ""),
                properties=r.get("properties", {}),
                source_quote=r.get("source_quote", ""),
                confidence=_coerce_confidence(r.get("confidence")),
                source_chunk_index=chunk_index,
                source_file=file_name,
                mandatory_instructions=normalized_instructions,
            )
        )

    return relationships


_STRIP_PREFIXES = {
    "mr", "mrs", "ms", "dr", "prof", "sir", "lord", "lady",
    "rev", "sgt", "cpl", "lt", "capt", "maj", "col", "gen", "hon",
}


def _normalize_name(name: str) -> str:
    """Normalize for overlap dedup: lowercase, strip punctuation/titles, collapse whitespace."""
    name = unicodedata.normalize("NFKD", name)
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    tokens = name.split()
    if tokens and tokens[0] in _STRIP_PREFIXES:
        tokens = tokens[1:]
    return " ".join(tokens)


def _normalize_verified_facts(
    facts: list[dict[str, Any]],
    *,
    file_name: str,
    fallback_page: int | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for fact in facts or []:
        text = str(fact.get("text", "")).strip()
        quote = str(fact.get("quote", "")).strip()
        if not text or not quote:
            continue

        page = fact.get("page")
        if page in ("", None):
            page = fallback_page
        try:
            page = int(page) if page is not None else None
        except (TypeError, ValueError):
            page = fallback_page

        importance = fact.get("importance", 3)
        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 3

        normalized.append(
            {
                "text": text,
                "quote": quote,
                "page": page,
                "importance": max(1, min(5, importance)),
                "source_doc": file_name,
            }
        )

    return normalized


def _normalize_ai_insights(
    insights: list[dict[str, Any]],
    *,
    file_name: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for insight in insights or []:
        text = str(insight.get("text", "")).strip()
        reasoning = str(insight.get("reasoning", "")).strip()
        confidence = str(insight.get("confidence", "medium")).strip().lower()
        if not text or not reasoning:
            continue
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"

        normalized.append(
            {
                "text": text,
                "confidence": confidence,
                "reasoning": reasoning,
                "source_doc": file_name,
                "status": "pending",
            }
        )

    return normalized


def _merge_verified_facts(
    existing: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(existing or [])
    seen = {
        (
            str(item.get("text", "")).strip().lower(),
            str(item.get("source_doc", "")).strip().lower(),
            item.get("page"),
        )
        for item in merged
    }

    for item in new_items or []:
        key = (
            str(item.get("text", "")).strip().lower(),
            str(item.get("source_doc", "")).strip().lower(),
            item.get("page"),
        )
        if not key[0] or key in seen:
            continue
        merged.append(item)
        seen.add(key)

    return merged


def _merge_ai_insights(
    existing: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = list(existing or [])
    seen = {
        (
            str(item.get("text", "")).strip().lower(),
            str(item.get("source_doc", "")).strip().lower(),
        )
        for item in merged
    }

    for item in new_items or []:
        key = (
            str(item.get("text", "")).strip().lower(),
            str(item.get("source_doc", "")).strip().lower(),
        )
        if not key[0] or key in seen:
            continue
        merged.append(item)
        seen.add(key)

    return merged


def _dedup_within_file(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Merge entities with identical normalized names extracted from
    overlapping chunks within the same file.  Remaps relationship IDs."""
    if not entities:
        return entities, relationships

    # Group by (category, normalized_name)
    groups: dict[tuple[str, str], list[int]] = {}
    for i, e in enumerate(entities):
        key = (e.category, _normalize_name(e.name))
        groups.setdefault(key, []).append(i)

    id_remap: dict[str, str] = {}  # old temp_id → surviving temp_id
    kept: list[RawEntity] = []

    for indices in groups.values():
        if len(indices) == 1:
            kept.append(entities[indices[0]])
            continue

        # Pick primary: highest confidence, then most properties
        primary_idx = max(
            indices, key=lambda i: (entities[i].confidence, len(entities[i].properties))
        )
        primary = entities[primary_idx]

        # Merge from others into primary
        all_names: set[str] = set()
        merged_props = dict(primary.properties)
        best_confidence = primary.confidence

        for idx in indices:
            e = entities[idx]
            id_remap[e.temp_id] = primary.temp_id
            all_names.add(e.name)
            best_confidence = max(best_confidence, e.confidence)
            for k, v in e.properties.items():
                if k not in merged_props or not merged_props[k]:
                    merged_props[k] = v
            primary.verified_facts = _merge_verified_facts(
                primary.verified_facts, e.verified_facts
            )
            primary.ai_insights = _merge_ai_insights(
                primary.ai_insights, e.ai_insights
            )

        all_names.discard(primary.name)
        # Store other name forms as aliases
        existing_aliases = list(merged_props.get("aliases") or [])
        for name in all_names:
            if name not in existing_aliases:
                existing_aliases.append(name)
        if existing_aliases:
            merged_props["aliases"] = existing_aliases

        primary.properties = merged_props
        primary.confidence = best_confidence
        kept.append(primary)

    merged_count = len(entities) - len(kept)
    if merged_count:
        logger.info(
            "Overlap dedup: merged %d duplicate entities (%d → %d)",
            merged_count, len(entities), len(kept),
        )

    # Remap relationship IDs
    remapped_rels: list[RawRelationship] = []
    for r in relationships:
        r.source_entity_id = id_remap.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = id_remap.get(r.target_entity_id, r.target_entity_id)
        remapped_rels.append(r)

    return kept, remapped_rels


async def extract_entities_and_relationships(
    chunks: list[TextChunk],
    case_context: str,
    file_name: str,
    mandatory_instructions: list[str] | None = None,
    special_entity_types: list[dict[str, Any]] | None = None,
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Two-pass extraction: entities first, then relationships with known entities."""
    if not chunks:
        return [], []

    # Pass 1: Extract entities from all chunks (parallel, bounded by semaphore)
    entity_tasks = [
        _extract_entities_from_chunk(
            chunk.text,
            chunk.index,
            file_name,
            case_context,
            mandatory_instructions=mandatory_instructions,
            special_entity_types=special_entity_types,
            is_table=chunk.is_table,
            sheet_name=chunk.metadata.get("sheet_name", ""),
            page_start=chunk.metadata.get("page_start"),
            page_end=chunk.metadata.get("page_end"),
            file_type=chunk.metadata.get("file_type"),
            source_document_id=chunk.metadata.get("job_id"),
        )
        for chunk in chunks
    ]
    entity_results = await asyncio.gather(*entity_tasks)

    all_entities: list[RawEntity] = []
    entities_by_chunk: dict[int, list[RawEntity]] = {}
    for chunk, chunk_entities in zip(chunks, entity_results):
        all_entities.extend(chunk_entities)
        entities_by_chunk[chunk.index] = chunk_entities

    # Pass 2: Extract relationships using known entities (parallel)
    rel_tasks = [
        _extract_relationships_from_chunk(
            chunk.text,
            chunk.index,
            entities_by_chunk.get(chunk.index, []),
            file_name,
            case_context,
            mandatory_instructions=mandatory_instructions,
        )
        for chunk in chunks
    ]
    rel_results = await asyncio.gather(*rel_tasks)

    all_relationships: list[RawRelationship] = []
    for chunk_rels in rel_results:
        all_relationships.extend(chunk_rels)

    # Deduplicate entities extracted from overlapping chunks
    all_entities, all_relationships = _dedup_within_file(all_entities, all_relationships)

    return all_entities, all_relationships
