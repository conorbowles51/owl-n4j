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
    temperature: Optional[float] = None,
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
    entity_types = config.get("entity_types", [])
    entity_definitions = config.get("entity_definitions", {})
    
    # Get temperature from config or use provided/default
    config_temperature = config.get("temperature")
    if temperature is None:
        temperature = config_temperature if config_temperature is not None else 1.0
    
    # Support both new format (relationship_examples) and old format (relationship_types)
    relationship_examples = config.get("relationship_examples")
    relationship_types = config.get("relationship_types")
    
    # Build entity type descriptions
    entity_descriptions = []
    for entity_type in entity_types:
        entity_def = entity_definitions.get(entity_type, {})
        description = entity_def.get("description", "")
        if description:
            entity_descriptions.append(f"- {entity_type}: {description}")
        else:
            entity_descriptions.append(f"- {entity_type}")

    existing_keys_hint = ""
    if existing_entity_keys:
        keys_sample = existing_entity_keys[:50]  # Limit to avoid prompt bloat
        existing_keys_hint = f"""
The following entities already exist in the investigation graph (use these exact keys if referring to them):
{', '.join(keys_sample)}
{"... and more" if len(existing_entity_keys) > 50 else ""}
"""

    entity_types_str = ", ".join(entity_types)
    
    # Build relationship guidance
    if relationship_examples:
        # New format: use examples to guide the LLM
        relationship_guidance = f"""
For relationships, identify ALL connections between entities based on the context. Use descriptive relationship types that capture the nature of the connection. Examples of relationship types you might identify:
{chr(10).join(f"- {example}" for example in relationship_examples)}

You are not limited to these examples - use your judgment to create appropriate relationship types that accurately describe the connections you find in the document. The system will automatically create these relationship types in Neo4j, so be creative and specific. Examples: "OWNS", "TRANSFERRED_TO", "MET_WITH", "EMAILED", "CALLED", "WORKS_FOR", "DIRECTOR_OF", "SIGNED", "AUTHORIZED", "RECEIVED_FROM", "SENT_TO", etc.
"""
    elif relationship_types:
        # Old format: use predefined types, but allow new ones
        relationship_guidance = f"""
For each relationship, provide:
- from_key: The key of the source entity
- to_key: The key of the target entity
- type: A descriptive relationship type. You may use one of these: [{", ".join(relationship_types)}], but you are also encouraged to create new relationship types if they better describe the connection. The system will automatically create any relationship type you specify.
- notes: Brief description of the relationship as evidenced in this document

IMPORTANT: Create relationship types that accurately capture the connection. You are not limited to the predefined types - create new ones as needed.
"""
    else:
        relationship_guidance = """
For relationships, identify ALL connections between entities and use descriptive relationship types. The system will automatically create these relationship types in Neo4j, so be specific and creative. Examples: "OWNS", "TRANSFERRED_TO", "MET_WITH", "EMAILED", "CALLED", "WORKS_FOR", "DIRECTOR_OF", "SIGNED", "AUTHORIZED", etc.
"""

    entity_guidance = f"""
For each entity, provide:
- key: A stable, lowercase, hyphenated identifier (e.g., "john-smith", "emerald-imports-ltd", "acc-001")
- type: The entity type. Prefer using one of the suggested types: [{entity_types_str}]. However, if you encounter an entity that doesn't fit any of these types, you may create a new descriptive type name (e.g., "Vehicle", "Account", "Transaction", "Meeting", "Email", "PhoneCall"). Use clear, descriptive type names.
- name: Human-readable name (e.g., "John Smith", "Emerald Imports Ltd")
- notes: What role does this entity play in THIS document? What is relevant about them here?
- date: (REQUIRED for event types: Transaction, Transfer, Payment, Communication, Email, PhoneCall, Meeting) The date of the event in YYYY-MM-DD format if mentioned in the text, otherwise null
- location: Any geographic location associated with this entity (address, city, country). Extract the most specific location mentioned. For companies: headquarters or office location. For persons: residence or workplace. For meetings/transactions: where it occurred. Set to null if no location mentioned.

Entity Type Guidelines:
{chr(10).join(entity_descriptions)}

IMPORTANT: If you find entities that don't match the suggested types above, create appropriate new entity types. The system will automatically create and display these new entity types.
"""

    prompt = f"""{system_context}

Extract all entities and relationships from the following document excerpt.

Document: {doc_name}

Text:
\"\"\"{text}\"\"\"
{existing_keys_hint}
{entity_guidance}
{relationship_guidance}

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
      "amount": "string or null (e.g., '$50,000')",
      "location": "string or null (e.g., 'London, UK' or '123 Main St, New York')"
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
    
    response = call_llm(prompt, json_mode=True, temperature=temperature)
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


def get_processing_estimate(
    doc_name: str,
    text_preview: str,
    total_chunks: int,
    existing_entity_count: int,
) -> Dict:
    """
    Get an estimate of processing duration from the LLM.

    Args:
        doc_name: Name of the document being processed
        text_preview: First 2000 characters of the document text
        total_chunks: Total number of chunks the document will be split into
        existing_entity_count: Number of existing entities in the graph

    Returns:
        Dict with 'estimated_duration_seconds' and 'estimated_duration_text'
    """
    prompt = f"""You are analyzing a document that will be processed for entity and relationship extraction.

Document name: {doc_name}
Document preview (first 2000 characters):
{text_preview}

Processing parameters:
- Document will be split into {total_chunks} chunks
- There are currently {existing_entity_count} existing entities in the knowledge graph

Based on the document length, complexity, number of chunks, and existing graph size, estimate:
1. How long the processing will take in seconds
2. A human-readable description (e.g., "approximately 2-3 minutes")

Consider:
- Longer documents take more time
- More chunks mean more LLM calls
- Existing entity resolution adds processing time
- Each chunk requires entity extraction, entity resolution, and relationship creation

Return ONLY valid JSON:
{{
  "estimated_duration_seconds": <number>,
  "estimated_duration_text": "<human-readable estimate>",
  "reasoning": "<brief explanation of the estimate>"
}}
"""
    
    response = call_llm(prompt, json_mode=True, temperature=0.3)
    result = parse_json_response(response)
    
    return {
        "estimated_duration_seconds": result.get("estimated_duration_seconds", 60),
        "estimated_duration_text": result.get("estimated_duration_text", "approximately 1 minute"),
        "reasoning": result.get("reasoning", ""),
    }


def get_processing_progress_update(
    doc_name: str,
    chunks_processed: int,
    total_chunks: int,
    entities_processed: int,
    relationships_processed: int,
    elapsed_seconds: int,
    initial_estimate_seconds: Optional[int] = None,
) -> Dict:
    """
    Get a progress update from the LLM about work done and remaining.

    Args:
        doc_name: Name of the document being processed
        chunks_processed: Number of chunks processed so far
        total_chunks: Total number of chunks
        entities_processed: Number of entities processed so far
        relationships_processed: Number of relationships processed so far
        elapsed_seconds: Number of seconds elapsed so far
        initial_estimate_seconds: Optional initial time estimate in seconds

    Returns:
        Dict with progress information
    """
    progress_percent = (chunks_processed / total_chunks * 100) if total_chunks > 0 else 0
    
    if initial_estimate_seconds:
        estimated_remaining = max(0, initial_estimate_seconds - elapsed_seconds)
        estimated_remaining_text = f"approximately {estimated_remaining // 60} minutes {estimated_remaining % 60} seconds" if estimated_remaining >= 60 else f"approximately {estimated_remaining} seconds"
        estimate_context = f"\nInitial estimate was {initial_estimate_seconds} seconds. Based on progress so far, remaining time is estimated at {estimated_remaining_text}."
    else:
        # Estimate based on current rate
        if chunks_processed > 0:
            seconds_per_chunk = elapsed_seconds / chunks_processed
            remaining_chunks = total_chunks - chunks_processed
            estimated_remaining = int(remaining_chunks * seconds_per_chunk)
            estimated_remaining_text = f"approximately {estimated_remaining // 60} minutes {estimated_remaining % 60} seconds" if estimated_remaining >= 60 else f"approximately {estimated_remaining} seconds"
        else:
            estimated_remaining_text = "calculating..."
        estimate_context = f"\nBased on current processing rate, remaining time is estimated at {estimated_remaining_text}."
    
    prompt = f"""You are monitoring the progress of document ingestion.

Document: {doc_name}

Current progress:
- Chunks processed: {chunks_processed} / {total_chunks} ({progress_percent:.1f}%)
- Entities processed so far: {entities_processed}
- Relationships processed so far: {relationships_processed}
- Elapsed time: {elapsed_seconds} seconds ({elapsed_seconds // 60} minutes {elapsed_seconds % 60} seconds)
{estimate_context}

Provide a concise progress update that:
1. Describes what work has been completed
2. Estimates remaining work and time
3. Notes any patterns or observations about the processing so far

Return ONLY valid JSON:
{{
  "work_completed": "<description of what has been done>",
  "remaining_work": "<description of what remains>",
  "estimated_remaining_seconds": <number>,
  "estimated_remaining_text": "<human-readable time estimate>",
  "observations": "<any notable observations about progress>"
}}
"""
    
    response = call_llm(prompt, json_mode=True, temperature=0.3)
    result = parse_json_response(response)
    
    return {
        "work_completed": result.get("work_completed", ""),
        "remaining_work": result.get("remaining_work", ""),
        "estimated_remaining_seconds": result.get("estimated_remaining_seconds", 60),
        "estimated_remaining_text": result.get("estimated_remaining_text", "approximately 1 minute"),
        "observations": result.get("observations", ""),
    }