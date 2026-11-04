"""
Geo Rescan Service — LLM-powered location extraction and geocoding.

Rescans all document chunks for a case, uses GPT-5.2 to extract
geographic locations mentioned in the text, geocodes them via Nominatim,
and writes the coordinates back to the matching entities in Neo4j
(or creates LOCATED_AT relationships from events/entities to locations).
"""

import fcntl
import ipaddress
import json
import os
import tempfile
import threading
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

from services.llm_service import LLMService
from services.neo4j_service import neo4j_service
from postgres.models.geocoding_cache import GeocodingCacheEntry
from postgres.session import get_background_session

# ---------------------------------------------------------------------------
# Nominatim geocoding for persisted location entities.
# ---------------------------------------------------------------------------

# Addresses from evidence are sent to an outside geocoder only when a person asks for that address to be looked up
# (Neil 2026-11-04: "Flagging potential lookups and having them user activated is best"). Automatic paths (the case
# rescan, ingestion) send nothing: an address they cannot place from the cache is flagged for review, where a person
# can click "Look up". A geocoder held on this server or its private network (GEOCODER_SEARCH_URL, for example
# http://localhost:8080/search) may be asked automatically, since nothing then leaves the server.
PUBLIC_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_URL = os.environ.get("GEOCODER_SEARCH_URL", "").strip() or PUBLIC_NOMINATIM_URL
# Nominatim's usage policy: identify the application; no personal contact details are sent.
USER_AGENT = "InvestigationConsole/1.0"
NOT_LOOKED_UP_MESSAGE = (
    "Places not already in the address cache were not looked up: nothing is sent to the outside address service "
    "automatically."
)
LOOKUP_SERVICE_NAME = "OpenStreetMap address service (nominatim.openstreetmap.org)"
# requested_by for lookups made on their own because the case's address lookup is automatic (services.address_lookup).
AUTOMATIC = "automatic"


def held_on_this_server(url: str) -> bool:
    """Whether a service address is on this server or its private network (loopback, a private address, or a
    one-word container name), never a public host."""
    try:
        host = (urlsplit(url).hostname or "").strip().lower()
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost" or "." not in host and ":" not in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def automatic_lookup_allowed() -> bool:
    """Whether an address may be looked up without a person asking: only when the geocoder is on this server."""
    return held_on_this_server(NOMINATIM_URL)


class GeocoderUnavailable(Exception):
    """The geocoder did not answer (network error, refusal, bad reply). Not cached: asking again may work."""


_last_request_time = 0.0
# Nominatim allows one request a second. Geocoding route handlers run in FastAPI's thread pool and the backend runs
# more than one worker process, so the spacing is kept under a thread lock plus a file lock shared by the workers,
# held through the wait, with the time of the last request written in the file.
_rate_lock = threading.Lock()
_RATE_FILE = os.path.join(tempfile.gettempdir(), "loupe-geocoder-rate.lock")

def _get_cached_geocode(cache_key: str) -> tuple[bool, Optional[Dict]]:
    with get_background_session() as db:
        entry = db.get(GeocodingCacheEntry, ("nominatim", cache_key))
        if not entry:
            return False, None
        if entry.status == "failed":
            return True, None
        return True, {
            "provider": entry.provider,
            "query": entry.original_query,
            "latitude": entry.latitude,
            "longitude": entry.longitude,
            "formatted_address": entry.formatted_address,
            "confidence": entry.confidence,
            "location_granularity": (entry.raw_response or {}).get("location_granularity"),
            # set when the result came from a lookup a person asked for: a machine reading not yet confirmed
            "requested_by": (entry.raw_response or {}).get("requested_by"),
        }


def _save_geocode_cache(
    cache_key: str, original_query: str, result: Optional[Dict], *, requested_by: Optional[str] = None
) -> None:
    asked = {"requested_by": requested_by, "requested_at": datetime.now(timezone.utc).isoformat()} if requested_by else {}
    with get_background_session() as db:
        if result:
            entry = GeocodingCacheEntry(
                provider="nominatim",
                normalized_query=cache_key,
                original_query=original_query,
                status="success",
                latitude=result.get("latitude"),
                longitude=result.get("longitude"),
                formatted_address=result.get("formatted_address"),
                confidence=result.get("confidence"),
                raw_response={**result, **asked},
            )
        else:
            entry = GeocodingCacheEntry(
                provider="nominatim",
                normalized_query=cache_key,
                original_query=original_query,
                status="failed",
                raw_response=asked,
            )
        db.merge(entry)


def _rate_limit():
    global _last_request_time
    with _rate_lock:
        try:
            handle = open(_RATE_FILE, "a+")
        except OSError:
            handle = None
        try:
            last = _last_request_time
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_EX)
                handle.seek(0)
                try:
                    last = max(last, float(handle.read().strip() or 0))
                except ValueError:
                    pass
            elapsed = time.time() - last
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            _last_request_time = time.time()
            if handle is not None:
                handle.seek(0)
                handle.truncate()
                handle.write(repr(_last_request_time))
                handle.flush()
        finally:
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()


def _location_granularity(result: Dict) -> Optional[str]:
    address = result.get("address") or {}
    result_type = str(result.get("type") or result.get("addresstype") or "").lower()
    if address.get("house_number") or result_type in {"house", "building"}:
        return "address"
    if address.get("road") or result_type in {"road", "street"}:
        return "street"
    if result_type in {"neighbourhood", "neighborhood", "suburb", "quarter", "hamlet"}:
        return "neighborhood"
    if result_type in {"city", "town", "village", "municipality", "borough"}:
        return "city"
    if result_type in {"county", "state", "region"}:
        return "region"
    if result_type == "country":
        return "country"
    return None


def geocode_with_cache(location: str, *, requested_by: Optional[str] = None) -> Optional[Dict]:
    """Geocode a location string, using the shared Nominatim cache.

    requested_by names the person who clicked Look up for this address, or is AUTOMATIC for a case whose address
    lookup is automatic (services.address_lookup checks the case's mode before each call). Without it nothing is sent
    to an outside geocoder: the address is placed from the cache or not at all. With it, exactly one request is sent when the cache
    holds no success (an earlier failure is asked again: the person asked for a fresh lookup). A geocoder that does not
    answer raises GeocoderUnavailable when a person asked (so they are told), and is never cached as "no match".
    """
    if not location or not location.strip():
        return None
    normalized = location.lower().strip()
    cache_key = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    cached, cached_result = _get_cached_geocode(cache_key)
    if cached and requested_by == AUTOMATIC:
        # A case in automatic mode: one request per new address; an address the service answered before is not
        # asked again (a person can still click Look up for a fresh answer).
        return cached_result
    if cached and cached_result and cached_result.get("requested_by") and not requested_by:
        # Found by a lookup a person asked for: it is placed only on that person's entity, as a machine placement.
        # An automatic path does not reuse it as a settled result elsewhere.
        return None
    if cached and (cached_result or not requested_by):
        return cached_result
    if not requested_by and not automatic_lookup_allowed():
        # Nothing is sent and nothing is cached: the address stays flagged until a person asks for it.
        return None

    _rate_limit()
    encoded = quote(location.strip())
    url = f"{NOMINATIM_URL}?q={encoded}&format=json&limit=1&addressdetails=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data:
            r = data[0]
            importance = float(r.get("importance") or 0)
            latitude, longitude = float(r["lat"]), float(r["lon"])
    except Exception as e:
        print(f"[GeoRescan] Geocoder did not answer usably for '{location}': {type(e).__name__}")
        if requested_by:
            raise GeocoderUnavailable(f"The address service did not answer usably ({type(e).__name__}).") from e
        return None
    if not data:
        _save_geocode_cache(cache_key, location, None, requested_by=requested_by)
        return None
    confidence = "high" if importance > 0.7 else ("medium" if importance > 0.4 else "low")
    result = {
        "provider": "nominatim",
        "query": location.strip(),
        "latitude": latitude,
        "longitude": longitude,
        "formatted_address": r.get("display_name", location),
        "confidence": confidence,
        "location_granularity": _location_granularity(r),
    }
    _save_geocode_cache(cache_key, location, result, requested_by=requested_by)
    return result


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
            loc["location_granularity"] = result.get("location_granularity")
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
        granularity = loc.get("location_granularity")
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
                    location_granularity=granularity,
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
                location_granularity=granularity,
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
        "geocoding_not_run": None if automatic_lookup_allowed() else NOT_LOOKED_UP_MESSAGE,
        "entities_updated": entities_updated,
        "location_nodes_created": location_nodes_created,
        "relationships_created": relationships_created,
    }
    print(f"[GeoRescan] Complete: {json.dumps(summary, indent=2)}")
    return summary
