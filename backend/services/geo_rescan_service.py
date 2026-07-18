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

from services.llm_service import LLMService
from services.location_validation import (
    GEOCODING_STATUS_MAPPED,
    GEOCODING_STATUS_REJECTED,
    GEOCODING_STATUS_UNMAPPED_RETRIABLE,
    GeocodeProvenance,
    validate_location,
)
from services.neo4j_service import neo4j_service
from postgres.models.geocoding_cache import GeocodingCacheEntry
from postgres.session import get_background_session

# ---------------------------------------------------------------------------
# Nominatim geocoding for persisted location entities.
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "InvestigationConsole/1.0"
_last_request_time = 0.0

def _get_cached_geocode(cache_key: str) -> tuple[bool, Optional[Dict]]:
    with get_background_session() as db:
        entry = db.get(GeocodingCacheEntry, ("nominatim", cache_key))
        if not entry:
            return False, None
        if entry.status == GEOCODING_STATUS_UNMAPPED_RETRIABLE:
            return False, None
        result = {
            "status": entry.status,
            "latitude": entry.latitude,
            "longitude": entry.longitude,
            "geocoder": entry.geocoder or entry.provider,
            "query": entry.query or entry.original_query,
            "formatted_address": entry.formatted_address,
            "precision": entry.precision,
            "confidence": entry.confidence,
            "candidates": entry.candidates or [],
            "rejection_reason": entry.rejection_reason,
            "provider_error": entry.provider_error,
        }
        if entry.status in {GEOCODING_STATUS_MAPPED, "success"}:
            validated = validate_location(
                latitude=entry.latitude,
                longitude=entry.longitude,
                entity_type="Location",
                provenance=GeocodeProvenance(
                    geocoder=result["geocoder"],
                    query=result["query"],
                    formatted_address=entry.formatted_address,
                    precision=entry.precision,
                    confidence=entry.confidence,
                    candidates=result["candidates"],
                    provider_status=entry.status,
                ),
            )
            if not validated.is_valid:
                result.update(
                    {
                        "status": validated.status,
                        "latitude": None,
                        "longitude": None,
                        "rejection_reason": validated.rejection_reason.value if validated.rejection_reason else None,
                    }
                )
            elif entry.status == "success":
                result["status"] = GEOCODING_STATUS_MAPPED
                result["latitude"] = validated.latitude
                result["longitude"] = validated.longitude
        return True, result


def _save_geocode_cache(cache_key: str, original_query: str, result: Dict) -> None:
    with get_background_session() as db:
        entry = GeocodingCacheEntry(
            provider="nominatim",
            normalized_query=cache_key,
            original_query=original_query,
            status=result.get("status", GEOCODING_STATUS_REJECTED),
            latitude=result.get("latitude"),
            longitude=result.get("longitude"),
            geocoder=result.get("geocoder") or "nominatim",
            query=result.get("query") or original_query,
            formatted_address=result.get("formatted_address"),
            precision=result.get("precision"),
            confidence=result.get("confidence"),
            candidates=result.get("candidates"),
            rejection_reason=result.get("rejection_reason"),
            provider_error=result.get("provider_error"),
            raw_response=result.get("raw_response") or result,
        )
        db.merge(entry)


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
    cached, cached_result = _get_cached_geocode(cache_key)
    if cached:
        return cached_result

    _rate_limit()
    encoded = quote(location.strip())
    url = f"{NOMINATIM_URL}?q={encoded}&format=json&limit=5&addressdetails=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            result = {
                "status": GEOCODING_STATUS_REJECTED,
                "geocoder": "nominatim",
                "query": location,
                "rejection_reason": "no_results",
                "raw_response": {"results": []},
            }
            _save_geocode_cache(cache_key, location, result)
            return result
        r = data[0]
        importance = float(r.get("importance", 0))
        confidence = "high" if importance > 0.7 else ("medium" if importance > 0.4 else "low")
        precision = _precision_from_nominatim(r)
        candidates = [_candidate_from_nominatim(item) for item in data[:5]]
        result = {
            "status": GEOCODING_STATUS_MAPPED,
            "latitude": _safe_float(r.get("lat")),
            "longitude": _safe_float(r.get("lon")),
            "geocoder": "nominatim",
            "query": location,
            "formatted_address": r.get("display_name", location),
            "precision": precision,
            "confidence": confidence,
            "candidates": candidates,
            "raw_response": data,
        }
        validated = validate_location(
            latitude=result["latitude"],
            longitude=result["longitude"],
            entity_type="Location",
            provenance=GeocodeProvenance(
                geocoder="nominatim",
                query=location,
                formatted_address=result["formatted_address"],
                precision=precision,
                confidence=confidence,
                candidates=candidates,
                provider_status=GEOCODING_STATUS_MAPPED,
            ),
        )
        if not validated.is_valid:
            result["status"] = validated.status
            result["latitude"] = None
            result["longitude"] = None
            result["rejection_reason"] = validated.rejection_reason.value if validated.rejection_reason else None
        _save_geocode_cache(cache_key, location, result)
        return result
    except Exception as e:
        print(f"[GeoRescan] Geocode error for '{location}': {e}")
        result = {
            "status": GEOCODING_STATUS_UNMAPPED_RETRIABLE,
            "geocoder": "nominatim",
            "query": location,
            "provider_error": str(e),
        }
        _save_geocode_cache(cache_key, location, result)
        return result


def _precision_from_nominatim(item: Dict) -> Optional[str]:
    return item.get("addresstype") or item.get("type") or item.get("class")


def _candidate_from_nominatim(item: Dict) -> Dict:
    importance = float(item.get("importance", 0) or 0)
    confidence = "high" if importance > 0.7 else ("medium" if importance > 0.4 else "low")
    return {
        "latitude": _safe_float(item.get("lat")),
        "longitude": _safe_float(item.get("lon")),
        "formatted_address": item.get("display_name"),
        "precision": _precision_from_nominatim(item),
        "confidence": confidence,
    }


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
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
        if result and result.get("status") == GEOCODING_STATUS_MAPPED:
            loc["latitude"] = result["latitude"]
            loc["longitude"] = result["longitude"]
            loc["formatted_address"] = result["formatted_address"]
            loc["geocoding_provider"] = result.get("geocoder")
            loc["geocoding_query"] = result.get("query")
            loc["geocoding_precision"] = result.get("precision")
            loc["geocoding_confidence"] = result["confidence"]
            loc["geocoding_candidates"] = json.dumps(result.get("candidates") or [], separators=(",", ":"))
            geocoded.append(loc)
        else:
            failed_geocode.append(
                {
                    "place": place,
                    "status": result.get("status") if result else GEOCODING_STATUS_REJECTED,
                    "reason": (result.get("rejection_reason") or result.get("provider_error")) if result else None,
                }
            )

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
        provider = loc.get("geocoding_provider")
        query = loc.get("geocoding_query") or place
        precision = loc.get("geocoding_precision")
        confidence = loc.get("geocoding_confidence", "medium")
        candidates = loc.get("geocoding_candidates")
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
                    geocoding_provider=provider,
                    geocoding_query=query,
                    geocoding_precision=precision,
                    geocoding_candidates=candidates,
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
                geocoding_provider=provider,
                geocoding_query=query,
                geocoding_precision=precision,
                geocoding_candidates=candidates,
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
