"""
Snapshot Storage Service

Handles persistent storage of snapshots in a JSON file.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Storage file location
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "snapshots.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_snapshots() -> Dict:
    """Load snapshots from the JSON file."""
    ensure_storage_dir()
    
    if not STORAGE_FILE.exists():
        return {}
    
    try:
        with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading snapshots: {e}")
        return {}


def save_snapshots(snapshots: Dict):
    """Save snapshots to the JSON file."""
    ensure_storage_dir()
    
    try:
        # Create a temporary file first, then rename for atomic writes
        temp_file = STORAGE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(STORAGE_FILE)
    except IOError as e:
        print(f"Error saving snapshots: {e}")
        raise


class SnapshotStorage:
    """Service for managing snapshot storage."""
    
    def __init__(self):
        self._snapshots = load_snapshots()
    
    def get_all(self) -> Dict:
        """Get all snapshots."""
        return self._snapshots.copy()
    
    def get(self, snapshot_id: str) -> Optional[Dict]:
        """Get a specific snapshot by ID."""
        return self._snapshots.get(snapshot_id)
    
    def save(self, snapshot_id: str, snapshot_data: Dict):
        """Save a snapshot."""
        self._snapshots[snapshot_id] = snapshot_data
        save_snapshots(self._snapshots)
    
    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Returns True if deleted, False if not found."""
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            save_snapshots(self._snapshots)
            return True
        return False
    
    def reload(self):
        """Reload snapshots from disk."""
        self._snapshots = load_snapshots()


# Singleton instance
snapshot_storage = SnapshotStorage()


