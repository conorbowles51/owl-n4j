"""
Geo Rescan Service — LLM-powered location extraction and geocoding.

Rescans all document chunks for a case, uses GPT-5.2 to extract
geographic locations mentioned in the text, geocodes them via Nominatim,
and writes the coordinates back to the matching entities in Neo4j
(or creates LOCATED_AT relationships from events/entities to locations).
"""

import json
import time
import hashlib
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
from pathlib import Path

from services.llm_service import LLMService
from services.neo4j_service import neo4j_service

# ---------------------------------------------------------------------------
# Nominatim geocoding (mirrors ingestion/scripts/geocoding.py but standalone)
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "InvestigationConsole/1.0"
_last_request_time = 0.0

# Persistent cache shared with the ingestion geocoder
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "ingestion" / "data"
_CACHE_FILE = _CACHE_DIR / "geocoding_cache.json"


def _load_geocode_cache() -> Dict:
    if _CACHE_FILE.exists():
        try:
            return json.load(open(_CACHE_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_geocode_cache(cache: Dict):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        json.dump(cache, open(_CACHE_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        print(f"[GeoRescan] Cache save error: {e}")


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_request_time = time.time()


def geocode_with_cache(location: str) -> Optional[Dict]:
    """Geocode a location string, using the shared Nominatim cache."""
    if not location or not location.strip():
        return None
    normalized = location.lower().strip()
    cache_key = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    cache = _load_geocode_cache()
    if cache_key in cache:
        return cache[cache_key]  # may be None (previously failed)

    _rate_limit()
    encoded = quote(location.strip())
    url = f"{NOMINATIM_URL}?q={encoded}&format=json&limit=1&addressdetails=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            cache[cache_key] = None
            _save_geocode_cache(cache)
            return None
        r = data[0]
        importance = float(r.get("importance", 0))
        confidence = "high" if importance > 0.7 else ("medium" if importance > 0.4 else "low")
        result = {
            "latitude": float(r["lat"]),
            "longitude": float(r["lon"]),
            "formatted_address": r.get("display_name", location),
            "confidence": confidence,
        }
        cache[cache_key] = result
        _save_geocode_cache(cache)
        return result
    except Exception as e:
        print(f"[GeoRescan] Geocode error for '{location}': {e}")
        cache[cache_key] = None
        _save_geocode_cache(cache)
        return None


# ---------------------------------------------------------------------------
# LLM location extraction
# ---------------------------------------------------------------------------

LOCATION_EXTRACTION_PROMPT = """You are a geographic-location extraction specialist for legal investigations.

Given the following text passages from case documents, extract ALL geographic locations mentioned.
For each location, provide:
- **place**: The most complete, geocodable address or place name (e.g. "23 Fleet Street, London, UK" not just "Fleet Street").
- **context**: One sentence explaining what happened there or why it's relevant.
- **associated_entities**: A list of entity names (people, companies, events) mentioned in connection with this location.

Rules:
1. Include cities, addresses, countries, landmarks, offices, courts, banks, warehouses — anything with a physical location.
2. Be specific: prefer "Zurich, Switzerland" over just "Switzerland" when the text supports it.
3. Ignore vague references like "overseas" or "abroad" unless a specific place is inferable.
4. De-duplicate: if the same place is mentioned multiple times, merge the contexts and entities.
5. Include dates if mentioned near the location.

Return ONLY a JSON object:
{
  "locations": [
    {
      "place": "string",
      "context": "string",
      "associated_entities": ["string"],
      "date": "string or null"
    }
  ]
}

TEXT PASSAGES:
"""

# Maximum chunk chars to send per LLM call (to stay within context window)
MAX_CHUNK_CHARS_PER_CALL = 60000


def _build_batches(chunks: List[str], max_chars: int = MAX_CHUNK_CHARS_PER_CALL) -> List[str]:
    """Combine chunks into batches that fit within the LLM context budget."""
    batches: List[str] = []
    current = ""
    for chunk in chunks:
        if len(current) + len(chunk) + 4 > max_chars and current:
            batches.append(current)
            current = ""
        current += chunk + "\n\n"
    if current.strip():
        batches.append(current)
    return batches


def extract_locations_from_text(text_batch: str, llm: LLMService) -> List[Dict]:
    """Call GPT-5.2 to extract locations from a batch of text."""
    prompt = LOCATION_EXTRACTION_PROMPT + text_batch

    saved_provider, saved_model = llm.get_current_config()
    try:
        llm.set_config("openai", "gpt-5.2")
        raw = llm.call(prompt, temperature=0.2, json_mode=True, timeout=120)
    finally:
        llm.set_config(saved_provider, saved_model)

    try:
        parsed = json.loads(raw)
        return parsed.get("locations", [])
    except json.JSONDecodeError:
        print(f"[GeoRescan] Failed to parse LLM response as JSON")
        return []


# ---------------------------------------------------------------------------
# Entity matching helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return name.lower().strip()


def _match_entity(entity_name: str, graph_entities: Dict[str, Dict]) -> Optional[Dict]:
    """Fuzzy-match an extracted entity name against graph entities."""
    norm = _normalize(entity_name)
    if norm in graph_entities:
        return graph_entities[norm]
    for key, ent in graph_entities.items():
        if norm in key or key in norm:
            return ent
    return None


# ---------------------------------------------------------------------------
# Main rescan pipeline
# ---------------------------------------------------------------------------

def rescan_case_locations(
    case_id: str,
    force_regeocode: bool = False,
) -> Dict:
    """
    Full geo-rescan pipeline for a case.

    1. Retrieve all document chunks from ChromaDB for the case.
    2. Send chunks to GPT-5.2 for location extraction.
    3. Geocode each extracted location via Nominatim.
    4. Match locations to existing graph entities and update their lat/lng.
    5. Create LOCATED_AT relationships from associated entities → location entity.

    Returns summary statistics.
    """
    from services.vector_db_service import get_vector_db_service

    print(f"[GeoRescan] Starting rescan for case {case_id}")

    # ---- Step 1: Get all chunks for this case ----
    vdb = get_vector_db_service()
    if vdb is None:
        return {"error": "Vector DB service not available", "success": False}

    try:
        raw = vdb.chunk_collection.get(where={"case_id": case_id})
    except Exception as e:
        print(f"[GeoRescan] ChromaDB error: {e}")
        return {"error": f"ChromaDB error: {e}", "success": False}

    chunk_texts = raw.get("documents", []) if raw else []
    if not chunk_texts:
        return {"success": True, "message": "No document chunks found for this case", "locations_found": 0}

    print(f"[GeoRescan] Found {len(chunk_texts)} chunks for case {case_id}")

    # ---- Step 2: LLM extraction ----
    llm = LLMService()
    llm.set_cost_tracking_context(case_id=case_id, job_type="geo_rescan", description="Location extraction rescan")

    batches = _build_batches(chunk_texts)
    print(f"[GeoRescan] Processing {len(batches)} batch(es)")

    all_locations: List[Dict] = []
    for i, batch in enumerate(batches):
        print(f"[GeoRescan] Batch {i + 1}/{len(batches)} ({len(batch)} chars)")
        locs = extract_locations_from_text(batch, llm)
        all_locations.extend(locs)
        print(f"[GeoRescan]   → {len(locs)} locations extracted")

    llm.clear_cost_tracking_context()

    if not all_locations:
        return {"success": True, "message": "No locations found in documents", "locations_found": 0}

    # Deduplicate by normalized place name
    seen: Dict[str, Dict] = {}
    for loc in all_locations:
        place = loc.get("place", "").strip()
        if not place:
            continue
        key = _normalize(place)
        if key in seen:
            existing = seen[key]
            existing["associated_entities"] = list(set(
                existing.get("associated_entities", []) + loc.get("associated_entities", [])
            ))
            if loc.get("context") and loc["context"] not in existing.get("context", ""):
                existing["context"] = existing["context"] + "; " + loc["context"]
        else:
            seen[key] = loc
    unique_locations = list(seen.values())
    print(f"[GeoRescan] {len(unique_locations)} unique locations after dedup")

    # ---- Step 3: Geocode ----
    geocoded = []
    failed_geocode = []
    for loc in unique_locations:
        place = loc["place"]
        result = geocode_with_cache(place)
        if result:
            loc["latitude"] = result["latitude"]
            loc["longitude"] = result["longitude"]
            loc["formatted_address"] = result["formatted_address"]
            loc["geocoding_confidence"] = result["confidence"]
            geocoded.append(loc)
        else:
            failed_geocode.append(place)

    print(f"[GeoRescan] Geocoded: {len(geocoded)}, Failed: {len(failed_geocode)}")

    # ---- Step 4: Build entity index from the graph ----
    all_nodes = neo4j_service.get_all_nodes(case_id)
    entity_index: Dict[str, Dict] = {}
    for node in all_nodes:
        name = node.get("name", "")
        if name:
            entity_index[_normalize(name)] = node

    # ---- Step 5: Apply to graph ----
    entities_updated = 0
    relationships_created = 0
    location_nodes_created = 0

    for loc in geocoded:
        place = loc["place"]
        lat = loc["latitude"]
        lng = loc["longitude"]
        formatted = loc.get("formatted_address", place)
        confidence = loc.get("geocoding_confidence", "medium")
        context = loc.get("context", "")
        associated = loc.get("associated_entities", [])

        # Check if a graph entity matches this place name directly
        place_entity = _match_entity(place, entity_index)

        if place_entity:
            node_key = place_entity["key"]
            existing_lat = place_entity.get("latitude")
            if existing_lat is None or force_regeocode:
                neo4j_service.update_entity_location_full(
                    node_key=node_key,
                    case_id=case_id,
                    location_raw=place,
                    latitude=lat,
                    longitude=lng,
                    location_formatted=formatted,
                    geocoding_confidence=confidence,
                )
                entities_updated += 1
        else:
            # Create a Location node in the graph
            node_key = neo4j_service.create_location_node(
                case_id=case_id,
                name=place,
                latitude=lat,
                longitude=lng,
                location_formatted=formatted,
                geocoding_confidence=confidence,
                context=context,
            )
            if node_key:
                location_nodes_created += 1
                entity_index[_normalize(place)] = {"key": node_key, "name": place}
                place_entity = {"key": node_key, "name": place}

        # Create LOCATED_AT relationships from associated entities → this location
        if place_entity:
            for ent_name in associated:
                matched = _match_entity(ent_name, entity_index)
                if matched and matched["key"] != place_entity["key"]:
                    created = neo4j_service.ensure_located_at_relationship(
                        source_key=matched["key"],
                        target_key=place_entity["key"],
                        case_id=case_id,
                        context=context,
                    )
                    if created:
                        relationships_created += 1

    summary = {
        "success": True,
        "chunks_scanned": len(chunk_texts),
        "batches_processed": len(batches),
        "locations_found": len(unique_locations),
        "locations_geocoded": len(geocoded),
        "locations_failed_geocode": len(failed_geocode),
        "failed_places": failed_geocode[:20],
        "entities_updated": entities_updated,
        "location_nodes_created": location_nodes_created,
        "relationships_created": relationships_created,
    }
    print(f"[GeoRescan] Complete: {json.dumps(summary, indent=2)}")
    return summary
