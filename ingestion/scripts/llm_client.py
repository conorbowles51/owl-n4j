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
import requests

from config import OPENAI_MODEL, OLLAMA_BASE_URL, OLLAMA_MODEL
from profile_loader import get_ingestion_config

client = OpenAI()

def call_llm(
    prompt: str,
    temperature: float = 1,
    json_mode: bool = False,
    timeout: int = 600,  # Increased to 10 minutes for large models
    system_context: Optional[str] = ""
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

    url = f"{OLLAMA_BASE_URL}/api/chat"

    default_system_context = "You are an investigation assistant."
    payload: Dict = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_context if system_context else default_system_context},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    if json_mode:
        payload["format"] = "json"

    # Use tuple format for timeout: (connect_timeout, read_timeout)
    # Connect timeout: 10 seconds, Read timeout: as specified
    try:
        resp = requests.post(url, json=payload, timeout=(10, timeout))
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # Model not found or endpoint issue
            error_msg = f"Ollama API error (404): Model '{OLLAMA_MODEL}' may not be available. "
            error_msg += f"Check that Ollama is running at {OLLAMA_BASE_URL} and the model is installed."
            print(f"[LLM] {error_msg}")
            raise Exception(error_msg) from e
        raise
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to connect to Ollama at {OLLAMA_BASE_URL}: {str(e)}"
        print(f"[LLM] {error_msg}")
        raise Exception(error_msg) from e

    data = resp.json()
    # Ollama chat response shape: { message: { role: "...", content: "..." }, ... }
    return (data.get("message") or {}).get("content", "") or ""

    #------- OpenAI API --------#
    # kwargs = {
    #     "model": OPENAI_MODEL,
    #     "messages": [
    #         {"role": "user", "content": prompt}
    #     ],
    #     "temperature": temperature,
    #     "timeout": timeout,
    # }

    # # Force JSON response if requested
    # if json_mode:
    #     kwargs["response_format"] = {"type": "json_object"}

    # response = client.chat.completions.create(**kwargs)

    # # Extract content
    # return response.choices[0].message.content


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
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
) -> Dict:
    """
    Extract entities and relationships from a text chunk.

    Args:
        text: The text chunk to process
        doc_name: Name of the source document (for notes)
        existing_entity_keys: List of existing entity keys in the graph
                              (helps LLM reference existing entities)
        temperature: LLM temperature parameter
        page_start: First page number this chunk covers (for citation)
        page_end: Last page number this chunk covers (for citation)

    Returns:
        Dict with 'entities' and 'relationships' lists.
        Each entity includes 'verified_facts' and 'ai_insights' arrays.
    """

    profile = get_ingestion_config()
    
    system_context = profile.get("system_context")
    special_entity_types = profile.get("special_entity_types", [])
    
    # Get temperature from config or use provided/default
    profile_temperature = profile.get("temperature")
    if temperature is None:
        temperature = profile_temperature if profile_temperature is not None else 1.0
    
    # Build sepcial entity type descriptions
    special_entity_descriptions = ""
    for entity in special_entity_types:
        special_entity_descriptions += f"1. {entity.get("name")}: {entity.get("description")}.\n"
    

    existing_keys_hint = ""
    if existing_entity_keys:
        keys_sample = existing_entity_keys[:50]  # Limit to avoid prompt bloat
        existing_keys_hint = f"""
The following entities already exist in the investigation graph (use these exact keys if referring to them):
{', '.join(keys_sample)}
{"... and more" if len(existing_entity_keys) > 50 else ""}
"""
    
    # Page context for citations
    page_context = ""
    if page_start is not None:
        if page_end is not None and page_end != page_start:
            page_context = f"\nThis text is from pages {page_start}-{page_end} of the document."
        else:
            page_context = f"\nThis text is from page {page_start} of the document."
    
    # Build relationship guidance

    relationship_guidance = """
For relationships, identify ALL connections between entities and use descriptive relationship types. Examples: "OWNS", "TRANSFERRED_TO", "MET_WITH", "EMAILED", "CALLED", "WORKS_FOR", "DIRECTOR_OF", "SIGNED", "AUTHORIZED", etc.
IMPORTANT: Create relationship types that accurately capture the connection. You are not limited to the example types.
"""

    entity_guidance = f"""
For each entity, you MUST provide:

BASIC INFORMATION:
- key: A stable, lowercase, hyphenated identifier (e.g., "john-smith", "emerald-imports-ltd", "acc-001")
- type: The entity type that best describes this entity. You may use any type that fits - common types include Person, Company, Organisation, Location, Document, Event, etc. However, be aware of these domain-specific types that may be more appropriate:
{special_entity_descriptions}
  Choose the most specific and accurate type for each entity. If none of the special types above fit well, use a general type or create an appropriate one.
- name: Human-readable name (e.g., "John Smith", "Emerald Imports Ltd")
- date: (REQUIRED for event/temporal types like Transaction, Meeting, Communication, etc.) The date in YYYY-MM-DD format if mentioned, otherwise null
- location: Geographic location if mentioned, otherwise null

VERIFIED FACTS (REQUIRED) - Facts that are DIRECTLY stated in the document:
For each entity, provide an array of "verified_facts". Each fact MUST:
- Be directly stated or clearly evidenced in the text (not inferred)
- Include the exact quote from the document that supports it
- Include the page number where it was found
- Include an importance score (1-5) indicating relevance to the investigation

IMPORTANCE SCORING GUIDE:
- 5 = Critical: Key evidence, major actors, significant transactions, smoking gun details
- 4 = High: Important connections, notable activities, relevant financial data
- 3 = Medium: Supporting details, contextual information, secondary actors
- 2 = Low: Minor details, background information
- 1 = Minimal: Tangential information, standard identifiers

VERIFIED FACT FORMAT:
{{
  "text": "The factual statement about this entity",
  "quote": "The exact words from the document that prove this fact",
  "page": <page number as integer>,
  "importance": <1-5 importance score>
}}

AI INSIGHTS (OPTIONAL) - Logical inferences or analysis NOT directly stated:
For each entity, you may provide an array of "ai_insights". These are:
- Logical conclusions drawn from combining multiple facts
- Pattern observations
- Potential connections or implications
- Things that "seem likely" but aren't explicitly stated

AI INSIGHT FORMAT:
{{
  "text": "Your insight or inference",
  "confidence": "high" | "medium" | "low",
  "reasoning": "Why you believe this based on the evidence"
}}

CRITICAL RULES:
1. NEVER put inferences in verified_facts - only things explicitly stated in the document
2. If you cannot find a direct quote for a fact, it belongs in ai_insights instead
3. Always include page numbers for verified_facts
4. Be conservative - when in doubt, put it in ai_insights
"""

    # Determine the page number to use in the output
    current_page = page_start if page_start is not None else 1

    prompt = f"""{system_context}

Extract all entities and relationships from the following document excerpt.
{page_context}

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
      "date": "string or null (YYYY-MM-DD format)",
      "time": "string or null (HH:MM format)",
      "amount": "string or null (e.g., '$50,000')",
      "location": "string or null",
      "verified_facts": [
        {{
          "text": "Factual statement directly from the document",
          "quote": "Exact quote from the text proving this fact",
          "page": {current_page},
          "importance": 4
        }}
      ],
      "ai_insights": [
        {{
          "text": "Inference or analysis not directly stated",
          "confidence": "high|medium|low",
          "reasoning": "Why this inference makes sense"
        }}
      ]
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

IMPORTANT REMINDERS:
1. verified_facts must have direct quotes from the document. If you can't quote it, it's an ai_insight.
2. For event-type entities, dates are REQUIRED if present in the text.
3. Use page number {current_page} for facts from this chunk (or the specific page if you can identify it from page markers in the text).
"""
    
    response = call_llm(prompt, json_mode=True, temperature=temperature, system_context=system_context)
    return parse_json_response(response)


def disambiguate_entity(
    candidate_key: str,
    candidate_name: str,
    candidate_type: str,
    candidate_facts: str,
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

    # Flatten existing entity's verified_facts from JSON to string
    existing_facts_json = existing_entity.get('verified_facts', '[]')
    try:
        existing_facts = json.loads(existing_facts_json) if existing_facts_json else []
    except (json.JSONDecodeError, TypeError):
        existing_facts = []
    
    existing_entity_facts_str = "\n".join(
        fact.get("text", "") for fact in existing_facts if fact.get("text")
    )[:500]  # Limit length for prompt

    prompt = f"""You are helping with entity disambiguation in a fraud investigation.

I found a potential entity in a document:
- Key: {candidate_key}
- Name: {candidate_name}
- Type: {candidate_type}
- Facts about this entity: {candidate_facts}

There is an existing entity in the database that might be the same:
- Key: {existing_entity.get('key', 'unknown')}
- Name: {existing_entity.get('name', 'unknown')}
- Type: {existing_entity.get('type', 'unknown')}
- Summary: {existing_entity.get('summary', 'No summary available')}
- Facts about this entity: {existing_entity_facts_str or 'No facts available'}

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
    verified_facts: Optional[list] = None,
) -> str:
    """
    Generate or update an entity's summary based on VERIFIED FACTS ONLY.

    Args:
        entity_key: The entity's key
        entity_name: The entity's name
        entity_type: The entity's type
        all_notes: All notes accumulated for this entity (legacy, used as fallback)
        related_entities: List of related entity names/descriptions
        verified_facts: List of verified fact objects with text, quote, page, source_doc

    Returns:
        A concise, factual summary paragraph
    """
    related_context = ""
    if related_entities:
        related_context = f"""
Related entities:
{chr(10).join(f'- {r}' for r in related_entities[:10])}
"""

    # Build facts context from verified_facts if available
    if verified_facts and len(verified_facts) > 0:
        facts_text = "\n".join([
            f"- {fact.get('text', '')} (Source: {fact.get('source_doc', 'unknown')}, p.{fact.get('page', '?')})"
            for fact in verified_facts[:20]  # Limit to avoid prompt bloat
        ])
        observations_section = f"""
VERIFIED FACTS from source documents:
{facts_text}
"""
    else:
        # Fallback to legacy notes
        observations_section = f"""
Observations from documents:
{all_notes}
"""

    prompt = f"""You are summarising an entity in an investigation.

Entity: {entity_name}
Key: {entity_key}
Type: {entity_type}
{observations_section}
{related_context}

CRITICAL INSTRUCTIONS:
1. Write a concise summary (2-4 sentences) describing ONLY verified facts about this entity
2. Do NOT include any speculation, inference, or "likely" statements
3. Do NOT add information beyond what is in the verified facts
4. Focus on: who/what this entity is, their role, and documented actions
5. Use factual language only (e.g., "is the CFO of..." not "appears to be..." or "may be...")

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