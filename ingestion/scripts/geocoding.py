"""
Geocoding module - converts location strings to coordinates.

Uses Nominatim (OpenStreetMap) for geocoding with local caching
to avoid redundant API calls and respect rate limits.
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import quote
import urllib.request
import urllib.error

# Cache file location (relative to this script)
CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = CACHE_DIR / "geocoding_cache.json"

# Nominatim configuration
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "InvestigationConsole/1.0"  # Required by Nominatim ToS

# Rate limiting - Nominatim requires max 1 request/second
_last_request_time = 0.0


def _normalize_location(location: str) -> str:
    """
    Normalize location string for cache key.
    
    Args:
        location: Raw location string
        
    Returns:
        Normalized lowercase string
    """
    return location.lower().strip()


def _get_cache_key(location: str) -> str:
    """
    Generate a cache key for a location string.
    
    Args:
        location: Normalized location string
        
    Returns:
        MD5 hash of the location (for safe filenames)
    """
    return hashlib.md5(location.encode('utf-8')).hexdigest()


def _load_cache() -> Dict:
    """
    Load the geocoding cache from disk.
    
    Returns:
        Dict mapping cache keys to geocoding results
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load geocoding cache: {e}")
    return {}


def _save_cache(cache: Dict):
    """
    Save the geocoding cache to disk.
    
    Args:
        cache: Dict mapping cache keys to geocoding results
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save geocoding cache: {e}")


def _rate_limit():
    """
    Enforce rate limiting for Nominatim API.
    Waits if necessary to ensure at least 1 second between requests.
    """
    global _last_request_time
    
    elapsed = time.time() - _last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    
    _last_request_time = time.time()


def geocode_location(location: str) -> Optional[Dict]:
    """
    Geocode a location string using Nominatim.
    
    Args:
        location: Location string (e.g., "London, UK" or "123 Main St, New York")
        
    Returns:
        Dict with geocoding result:
        {
            "latitude": float,
            "longitude": float,
            "formatted_address": str,
            "confidence": str,  # "high", "medium", "low"
            "raw_response": dict  # Original Nominatim response
        }
        
        Returns None if geocoding fails.
    """
    if not location or not location.strip():
        return None
    
    # Rate limit
    _rate_limit()
    
    # Build request URL
    encoded_location = quote(location)
    url = f"{NOMINATIM_URL}?q={encoded_location}&format=json&limit=1&addressdetails=1"
    
    try:
        # Create request with required User-Agent header
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
        )
        
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if not data:
            print(f"  Geocoding: No results for '{location}'")
            return None
        
        # Get the first (best) result
        result = data[0]
        
        # Determine confidence based on importance score and type
        importance = float(result.get("importance", 0))
        if importance > 0.7:
            confidence = "high"
        elif importance > 0.4:
            confidence = "medium"
        else:
            confidence = "low"
        
        geocode_result = {
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
            "formatted_address": result.get("display_name", location),
            "confidence": confidence,
            "place_type": result.get("type", "unknown"),
            "raw_response": result,
        }
        
        print(f"  Geocoded '{location}' -> ({geocode_result['latitude']:.4f}, {geocode_result['longitude']:.4f}) [{confidence}]")
        return geocode_result
        
    except urllib.error.URLError as e:
        print(f"  Geocoding error for '{location}': {e}")
        return None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"  Geocoding parse error for '{location}': {e}")
        return None


def geocode_with_cache(location: str) -> Optional[Dict]:
    """
    Geocode a location string, using cache to avoid redundant API calls.
    
    Args:
        location: Location string
        
    Returns:
        Geocoding result dict or None if geocoding fails
    """
    if not location or not location.strip():
        return None
    
    normalized = _normalize_location(location)
    cache_key = _get_cache_key(normalized)
    
    # Check cache
    cache = _load_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        # Check if this was a failed geocoding (stored as null/None)
        if cached is None:
            print(f"  Cache hit (failed): '{location}'")
            return None
        print(f"  Cache hit: '{location}'")
        return cached
    
    # Not in cache - geocode
    result = geocode_location(location)
    
    # Store in cache (including None for failed lookups to avoid retrying)
    cache[cache_key] = result
    _save_cache(cache)
    
    return result


def batch_geocode(locations: list) -> Dict[str, Optional[Dict]]:
    """
    Geocode multiple locations, using cache where possible.
    
    Args:
        locations: List of location strings
        
    Returns:
        Dict mapping original location strings to geocoding results
    """
    results = {}
    
    for location in locations:
        if location:
            results[location] = geocode_with_cache(location)
    
    return results


def get_location_properties(location: str) -> Dict:
    """
    Get Neo4j-ready properties for a location.
    
    This is the main function to call during ingestion.
    Returns a dict that can be passed as extra_props to create_entity.
    
    Args:
        location: Location string from LLM extraction
        
    Returns:
        Dict with location properties:
        {
            "location_raw": str,  # Original location text
            "latitude": float or None,
            "longitude": float or None,
            "location_formatted": str or None,
            "geocoding_status": str,  # "success", "failed", "not_provided"
            "geocoding_confidence": str or None  # "high", "medium", "low"
        }
    """
    if not location or not location.strip():
        return {
            "geocoding_status": "not_provided",
        }
    
    # Clean the location string
    location = location.strip()
    
    # Try to geocode
    result = geocode_with_cache(location)
    
    if result:
        return {
            "location_raw": location,
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "location_formatted": result["formatted_address"],
            "geocoding_status": "success",
            "geocoding_confidence": result["confidence"],
        }
    else:
        return {
            "location_raw": location,
            "geocoding_status": "failed",
        }


# For testing
if __name__ == "__main__":
    test_locations = [
        "London, UK",
        "Monaco",
        "123 Fleet Street, London",
        "Cayman Islands",
        "Invalid Location XYZ123",
    ]
    
    print("Testing geocoding module:\n")
    for loc in test_locations:
        print(f"\nTesting: '{loc}'")
        props = get_location_properties(loc)
        print(f"  Result: {props}")

