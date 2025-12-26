"""
Snapshot Storage Service

Handles persistent storage of snapshots in a JSON file.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from services.snapshot_chunk_storage import (
    chunk_data, save_chunk, load_chunk, delete_chunks, reassemble_chunks
)

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
        """Get a specific snapshot by ID. Reassembles chunks if needed."""
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            return None
        
        # Check if this is a chunked snapshot
        if snapshot.get("_chunked") and snapshot.get("_num_chunks"):
            # Reassemble from chunks
            try:
                return reassemble_chunks(snapshot_id, snapshot["_num_chunks"])
            except Exception as e:
                print(f"Error reassembling chunks for snapshot {snapshot_id}: {e}")
                raise
        
        # Not chunked, return as-is
        return snapshot
    
    def save(self, snapshot_id: str, snapshot_data: Dict):
        """Save a snapshot. Automatically chunks if too large."""
        # Try to save normally first
        try:
            # Test if we can stringify it
            test_json = json.dumps(snapshot_data, ensure_ascii=False)
            # If successful and not too large, save normally
            if len(test_json.encode('utf-8')) < 50 * 1024 * 1024:  # 50MB threshold
                self._snapshots[snapshot_id] = snapshot_data
                save_snapshots(self._snapshots)
                return
        except (ValueError, TypeError, OverflowError) as e:
            error_msg = str(e).lower()
            if 'invalid string length' not in error_msg and 'string length' not in error_msg and 'overflow' not in error_msg:
                # Different error, re-raise
                raise
        
        # Too large or failed to stringify - use chunking
        chunks, is_chunked = chunk_data(snapshot_data)
        
        if is_chunked:
            # Save chunks to disk
            for i, chunk_json in enumerate(chunks):
                save_chunk(snapshot_id, i, chunk_json)
            
            # Save metadata in main storage pointing to chunks
            chunk_metadata = {
                "id": snapshot_id,
                "name": snapshot_data.get("name"),
                "notes": snapshot_data.get("notes"),
                "timestamp": snapshot_data.get("timestamp"),
                "created_at": snapshot_data.get("created_at"),
                "owner": snapshot_data.get("owner"),
                "case_id": snapshot_data.get("case_id"),
                "case_version": snapshot_data.get("case_version"),
                "case_name": snapshot_data.get("case_name"),
                "_chunked": True,
                "_num_chunks": len(chunks),
            }
            self._snapshots[snapshot_id] = chunk_metadata
        else:
            # Single chunk, save normally
            self._snapshots[snapshot_id] = snapshot_data
        
        save_snapshots(self._snapshots)
    
    def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Returns True if deleted, False if not found."""
        if snapshot_id in self._snapshots:
            snapshot = self._snapshots[snapshot_id]
            # If chunked, delete chunks too
            if snapshot.get("_chunked") and snapshot.get("_num_chunks"):
                delete_chunks(snapshot_id, snapshot["_num_chunks"])
            
            del self._snapshots[snapshot_id]
            save_snapshots(self._snapshots)
            return True
        return False
    
    def reload(self):
        """Reload snapshots from disk."""
        self._snapshots = load_snapshots()


# Singleton instance
snapshot_storage = SnapshotStorage()



