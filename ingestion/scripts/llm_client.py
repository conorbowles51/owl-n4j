"""
LLM Client module - handles all Ollama API interactions.

Provides functions for:
- Entity/relationship extraction from text
- Entity disambiguation (fuzzy matching decisions)
- Summary generation/updates
"""
from openai import OpenAI

from typing import Dict, Optional
import json

from config import OPENAI_MODEL
from profile_loader import get_ingestion_config

client = OpenAI()

def call_llm(
    prompt: str,
    temperature: float = 1,
    json_mode: bool = False,
    timeout: int = 180,
) -> str:
    """
    Call the local Ollama LLM endpoint.

    Args:
        prompt: The prompt to send
        temperature: Sampling temperature (lower = more deterministic)
        json_mode: If True, request JSON-formatted output
        timeout: Request timeout in seconds

    Returns:
        The model's response text
    """

    kwargs = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "timeout": timeout,
    }

    # Force JSON response if requested
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)

    # Extract content
    return response.choices[0].message.content


def parse_json_response(response_text: str) -> Dict:
    """
    Parse LLM response as JSON.

    Handles cases where the model wraps JSON with extra text.
    Extracts the first valid JSON object from the response.
    """
    start = response_text.find("{")
    end = response_text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        print("Could not locate a JSON object in the LLM response.")
        print("Raw response was:\n", response_text[:500])
        raise ValueError("No JSON object found in LLM response")

    json_str = response_text[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Failed to parse extracted JSON: {e}")
        print("Extracted JSON was:\n", json_str[:500])
        raise


def extract_entities_and_relationships(
    text: str,
    doc_name: str,
    existing_entity_keys: Optional[list] = None,
) -> Dict:
    """
    Extract entities and relationships from a text chunk.

    Args:
        text: The text chunk to process
        doc_name: Name of the source document (for notes)
        existing_entity_keys: List of existing entity keys in the graph
                              (helps LLM reference existing entities)

    Returns:
        Dict with 'entities' and 'relationships' lists
    """

    config = get_ingestion_config()
    
    system_context = config.get("system_context")
    entity_types = config.get("entity_types")
    relationship_types = config.get("relationship_types")

    existing_keys_hint = ""
    if existing_entity_keys:
        keys_sample = existing_entity_keys[:50]  # Limit to avoid prompt bloat
        existing_keys_hint = f"""
The following entities already exist in the investigation graph (use these exact keys if referring to them):
{', '.join(keys_sample)}
{"... and more" if len(existing_entity_keys) > 50 else ""}
"""

    entity_types_str = ", ".join(entity_types)
    relationship_types_str = ", ".join(relationship_types)

    prompt = f"""{system_context}

Extract all entities and relationships from the following document excerpt.

Document: {doc_name}

Text:
\"\"\"{text}\"\"\"
{existing_keys_hint}
For each entity, provide:
- key: A stable, lowercase, hyphenated identifier (e.g., "john-smith", "emerald-imports-ltd", "acc-001")
- type: One of [{entity_types_str}]
- name: Human-readable name (e.g., "John Smith", "Emerald Imports Ltd")
- notes: What role does this entity play in THIS document? What is relevant about them here?
- date: (REQUIRED for event types: Transaction, Transfer, Payment, Communication, Email, PhoneCall, Meeting) The date of the event in YYYY-MM-DD format if mentioned in the text, otherwise null

For each relationship, provide:
- from_key: The key of the source entity
- to_key: The key of the target entity
- type: One of [{relationship_types_str}]
- notes: Brief description of the relationship as evidenced in this document

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{{
  "entities": [
    {{
      "key": "string",
      "type": "string",
      "name": "string",
      "notes": "string",
      "date": "string or null (YYYY-MM-DD format, REQUIRED for event types)",
      "time": "string or null (HH:MM format)",
      "amount": "string or null (e.g., '$50,000')"
    }}
  ],
  "relationships": [
    {{
      "from_key": "string",
      "to_key": "string",
      "type": "string",
      "notes": "string"
    }}
  ]
}}

IMPORTANT: For event-type entities (Transaction, Transfer, Payment, Communication, Email, PhoneCall, Meeting), you MUST look for dates in the text. Convert any date format (e.g., "March 15, 2024", "15/03/2024", "3-15-24") to YYYY-MM-DD format.
"""
    
    response = call_llm(prompt, json_mode=True)
    return parse_json_response(response)


def disambiguate_entity(
    candidate_key: str,
    candidate_name: str,
    candidate_type: str,
    candidate_notes: str,
    existing_entity: Dict,
) -> bool:
    """
    Ask the LLM whether a candidate entity matches an existing entity.

    Args:
        candidate_key: The key of the new candidate
        candidate_name: The name of the new candidate
        candidate_type: The type of the new candidate
        candidate_notes: Notes about the candidate from the current document
        existing_entity: Dict with existing entity's key, name, type, summary, notes

    Returns:
        True if they are the same entity, False if different
    """
    prompt = f"""You are helping with entity disambiguation in a fraud investigation.

I found a potential entity in a document:
- Key: {candidate_key}
- Name: {candidate_name}
- Type: {candidate_type}
- Context: {candidate_notes}

There is an existing entity in the database that might be the same:
- Key: {existing_entity.get('key', 'unknown')}
- Name: {existing_entity.get('name', 'unknown')}
- Type: {existing_entity.get('type', 'unknown')}
- Summary: {existing_entity.get('summary', 'No summary available')}
- Previous notes: {existing_entity.get('notes', 'No notes')[:500]}

Are these the SAME entity (just referenced differently) or DIFFERENT entities?

Consider:
- Name variations (nicknames, abbreviations, typos)
- Context clues
- Entity types

Return ONLY valid JSON:
{{
  "same_entity": true or false,
  "confidence": "high" or "medium" or "low",
  "reasoning": "brief explanation"
}}
"""

    response = call_llm(prompt, json_mode=True)
    result = parse_json_response(response)
    return result.get("same_entity", False)


def generate_entity_summary(
    entity_key: str,
    entity_name: str,
    entity_type: str,
    all_notes: str,
    related_entities: Optional[list] = None,
) -> str:
    """
    Generate or update an entity's summary based on all accumulated notes.

    Args:
        entity_key: The entity's key
        entity_name: The entity's name
        entity_type: The entity's type
        all_notes: All notes accumulated for this entity
        related_entities: List of related entity names/descriptions

    Returns:
        A concise summary paragraph
    """
    related_context = ""
    if related_entities:
        related_context = f"""
Related entities:
{chr(10).join(f'- {r}' for r in related_entities[:10])}
"""

    prompt = f"""You are summarising an entity in a fraud investigation.

Entity: {entity_name}
Key: {entity_key}
Type: {entity_type}

All observations from documents:
{all_notes}
{related_context}
Write a concise summary (2-4 sentences) describing who/what this entity is and their significance to the investigation. Focus on facts, roles, and connections.

Return ONLY the summary text, no JSON, no quotes, no preamble.
"""

    response = call_llm(prompt, temperature=0.2)
    return response.strip()


def update_entity_notes(
    existing_notes: str,
    doc_name: str,
    new_observations: str,
) -> str:
    """
    Update entity notes with new observations from a document.

    This simply appends the new document observations to existing notes
    in a structured format.

    Args:
        existing_notes: Current notes text
        doc_name: Name of the new document
        new_observations: What was observed about this entity in the new document

    Returns:
        Updated notes text
    """
    new_entry = f"\n\n[{doc_name}]\n{new_observations}"

    if existing_notes and existing_notes.strip():
        return existing_notes.strip() + new_entry
    else:
        return f"[{doc_name}]\n{new_observations}"