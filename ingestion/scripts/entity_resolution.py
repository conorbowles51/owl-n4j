"""
Entity Resolution module - handles entity matching and disambiguation.

Provides functions for:
- Key normalisation
- Exact key matching
- Fuzzy matching with LLM disambiguation
"""

import re
from typing import Optional, Dict, Tuple, Callable

from neo4j_client import Neo4jClient
from llm_client import disambiguate_entity
from logging_utils import log_progress, log_error


def normalise_key(raw: Optional[str]) -> str:
    """
    Normalise a string into a stable key for deduplication.

    Transformation:
    - Lowercase
    - Strip whitespace
    - Replace spaces with hyphens
    - Remove special characters except hyphens
    - Collapse multiple hyphens

    Examples:
        "John Smith" -> "john-smith"
        "Emerald Imports Ltd." -> "emerald-imports-ltd"
        "ACC-001" -> "acc-001"
    """
    if raw is None:
        return ""

    key = raw.strip().lower()

    # Replace spaces and underscores with hyphens
    key = re.sub(r"[\s_]+", "-", key)

    # Remove special characters except hyphens and alphanumerics
    key = re.sub(r"[^a-z0-9\-]", "", key)

    # Collapse multiple hyphens
    key = re.sub(r"-+", "-", key)

    # Strip leading/trailing hyphens
    key = key.strip("-")

    return key


def resolve_entity(
    candidate_key: str,
    candidate_name: str,
    candidate_type: str,
    candidate_facts: str,
    db: Neo4jClient,
    case_id: str,
    profile_name: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, bool]:
    """
    Resolve a candidate entity to an existing entity or confirm it's new.

    Resolution strategy:
    1. Try exact key match
    2. If no exact match, try fuzzy search
    3. If fuzzy matches found, use LLM to disambiguate

    Args:
        candidate_key: Normalised key for the candidate
        candidate_name: Name of the candidate entity
        candidate_type: Type of the candidate entity
        candidate_facts: Facts about the candidate from current document
        db: Neo4j client instance
        case_id: The case ID to scope the search to
        log_callback: Optional callback for logging progress

    Returns:
        Tuple of (resolved_key, is_existing)
        - resolved_key: The key to use (might be existing entity's key)
        - is_existing: True if matched to existing entity
    """
    # Step 1: Exact key match
    existing = db.find_entity_by_key(candidate_key, case_id)
    if existing:
        log_progress(f"Exact match found for '{candidate_key}'", log_callback, prefix="    → ")
        return candidate_key, True

    # Step 2: Fuzzy search
    fuzzy_matches = db.fuzzy_search_entities(
        name=candidate_name,
        case_id=case_id,
        entity_type=candidate_type,
        limit=5,
    )

    if not fuzzy_matches:
        # No matches at all - this is a new entity
        log_progress(f"No matches found for '{candidate_name}', creating new entity", log_callback, prefix="    → ")
        return candidate_key, False

    # Step 3: LLM disambiguation for each fuzzy match
    log_progress(f"Found {len(fuzzy_matches)} fuzzy match(es), disambiguating...", log_callback, prefix="    → ")

    for match in fuzzy_matches:
        # Skip if it's the same key (shouldn't happen but safety check)
        if match.get("key") == candidate_key:
            return candidate_key, True

        try:
            is_same = disambiguate_entity(
                candidate_key=candidate_key,
                candidate_name=candidate_name,
                candidate_type=candidate_type,
                candidate_facts=candidate_facts,
                existing_entity=match,
                profile_name=profile_name,
                log_callback=log_callback,
            )

            if is_same:
                matched_key = match.get("key", candidate_key)
                log_progress(f"LLM confirmed match: '{candidate_name}' = '{match.get('name')}'", log_callback, prefix="    → ")
                return matched_key, True

        except Exception as e:
            log_error(f"Disambiguation error for {match.get('name')}: {e}", log_callback, prefix="    → ")
            continue

    # No matches confirmed - this is a new entity
    log_progress(f"No confirmed matches, creating new entity for '{candidate_name}'", log_callback, prefix="    → ")
    return candidate_key, False


def merge_entity_data(
    existing_entity: Dict,
    new_verified_facts: list,
    new_ai_insights: list,
    doc_name: str,
) -> Dict:
    """
    Merge new verified facts and AI insights into existing entity data.

    Args:
        existing_entity: Current entity data from database
        new_verified_facts: List of new verified fact dicts from extraction
        new_ai_insights: List of new AI insight dicts from extraction
        doc_name: Name of the current document (for source attribution)

    Returns:
        Dict with 'verified_facts' and 'ai_insights' lists (ready for database update)
    """
    import json
    
    # Parse existing verified_facts from JSON string
    existing_facts_json = existing_entity.get("verified_facts")
    try:
        existing_facts = json.loads(existing_facts_json) if existing_facts_json else []
    except (json.JSONDecodeError, TypeError):
        existing_facts = []
    
    # Parse existing ai_insights from JSON string
    existing_insights_json = existing_entity.get("ai_insights")
    try:
        existing_insights = json.loads(existing_insights_json) if existing_insights_json else []
    except (json.JSONDecodeError, TypeError):
        existing_insights = []
    
    # Enrich new facts with source document
    enriched_new_facts = []
    for fact in (new_verified_facts or []):
        enriched_fact = dict(fact)
        enriched_fact["source_doc"] = doc_name
        enriched_new_facts.append(enriched_fact)
    
    # Enrich new insights with source document
    enriched_new_insights = []
    for insight in (new_ai_insights or []):
        enriched_insight = dict(insight)
        enriched_insight["source_doc"] = doc_name
        enriched_new_insights.append(enriched_insight)
    
    # Merge facts - dedupe by text
    existing_fact_texts = {f.get("text", "").lower().strip() for f in existing_facts}
    merged_facts = list(existing_facts)
    for fact in enriched_new_facts:
        fact_text = fact.get("text", "").lower().strip()
        if fact_text and fact_text not in existing_fact_texts:
            merged_facts.append(fact)
            existing_fact_texts.add(fact_text)
    
    # Merge insights - dedupe by text
    existing_insight_texts = {i.get("text", "").lower().strip() for i in existing_insights}
    merged_insights = list(existing_insights)
    for insight in enriched_new_insights:
        insight_text = insight.get("text", "").lower().strip()
        if insight_text and insight_text not in existing_insight_texts:
            merged_insights.append(insight)
            existing_insight_texts.add(insight_text)
    
    return {
        "verified_facts": merged_facts,
        "ai_insights": merged_insights,
    }
