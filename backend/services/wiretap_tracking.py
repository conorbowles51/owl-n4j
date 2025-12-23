"""
Wiretap Processing Status Tracking

Tracks which folders have been processed as wiretaps.
"""

import json
from pathlib import Path
from typing import Dict, Set, Optional, List
from datetime import datetime

from config import BASE_DIR


DATA_DIR = BASE_DIR / "data"
TRACKING_FILE = DATA_DIR / "wiretap_tracking.json"


def _load_tracking() -> Dict[str, dict]:
    """Load wiretap tracking data from JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TRACKING_FILE.exists():
        return {}
    try:
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading wiretap tracking: {e}")
        return {}


def _save_tracking(tracking: Dict[str, dict]) -> None:
    """Persist wiretap tracking data to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TRACKING_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tracking, f, indent=2, ensure_ascii=False)
    tmp.replace(TRACKING_FILE)


def mark_wiretap_processed(case_id: str, folder_path: str) -> None:
    """
    Mark a folder as processed as a wiretap.
    
    Args:
        case_id: Case ID
        folder_path: Relative folder path from case data directory
    """
    tracking = _load_tracking()
    key = f"{case_id}:{folder_path}"
    tracking[key] = {
        "case_id": case_id,
        "folder_path": folder_path,
        "processed_at": datetime.now().isoformat()
    }
    _save_tracking(tracking)


def is_wiretap_processed(case_id: str, folder_path: str) -> bool:
    """
    Check if a folder has been processed as a wiretap.
    
    Args:
        case_id: Case ID
        folder_path: Relative folder path from case data directory
    
    Returns:
        True if folder has been processed, False otherwise
    """
    tracking = _load_tracking()
    key = f"{case_id}:{folder_path}"
    return key in tracking


def get_wiretap_status(case_id: str, folder_path: str) -> Optional[dict]:
    """
    Get wiretap processing status for a folder.
    
    Args:
        case_id: Case ID
        folder_path: Relative folder path from case data directory
    
    Returns:
        Dict with processing info or None if not processed
    """
    tracking = _load_tracking()
    key = f"{case_id}:{folder_path}"
    return tracking.get(key)


def list_processed_wiretaps(case_id: Optional[str] = None) -> List[dict]:
    """
    List all processed wiretap folders.
    
    Args:
        case_id: Optional case ID to filter by. If None, returns all processed wiretaps.
    
    Returns:
        List of dicts with processing info, sorted by processed_at (newest first)
    """
    tracking = _load_tracking()
    results = []
    
    for key, data in tracking.items():
        if case_id is None or data.get("case_id") == case_id:
            results.append({
                "case_id": data.get("case_id"),
                "folder_path": data.get("folder_path"),
                "processed_at": data.get("processed_at"),
            })
    
    # Sort by processed_at (newest first)
    results.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
    return results

