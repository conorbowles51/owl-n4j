"""
Case Storage Service

Handles persistent storage of cases with versioning in a JSON file.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import uuid

# Storage file location
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "cases.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_cases() -> Dict:
    """Load cases from the JSON file."""
    ensure_storage_dir()
    
    if not STORAGE_FILE.exists():
        return {}
    
    try:
        # Use a timeout to prevent hanging on very large files
        # For most cases, this should be fast
        with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Validate it's a dict
            if not isinstance(data, dict):
                print(f"Warning: cases.json does not contain a dict, got {type(data)}")
                return {}
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading cases: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error loading cases: {e}")
        return {}


def save_cases(cases: Dict):
    """Save cases to the JSON file."""
    ensure_storage_dir()
    
    try:
        # Create a temporary file first, then rename for atomic writes
        temp_file = STORAGE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cases, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(STORAGE_FILE)
    except IOError as e:
        print(f"Error saving cases: {e}")
        raise


class CaseStorage:
    """Service for managing case storage with versioning."""
    
    def __init__(self):
        self._cases = load_cases()
    
    def get_all(self, owner: Optional[str] = None) -> Dict:
        """
        Get all cases.
        
        If owner is provided, only return cases owned by that username.
        """
        if not owner:
            return self._cases.copy()
        return {
            case_id: data
            for case_id, data in self._cases.items()
            if data.get("owner") == owner
        }
    
    def get_case(self, case_id: str) -> Optional[Dict]:
        """Get a specific case by ID."""
        return self._cases.get(case_id)
    
    def get_case_versions(self, case_id: str) -> List[Dict]:
        """Get all versions of a case, sorted by version number."""
        case = self._cases.get(case_id)
        if not case:
            return []
        
        versions = case.get("versions", [])
        return sorted(versions, key=lambda v: v.get("version", 0), reverse=True)
    
    def get_latest_version(self, case_id: str) -> Optional[Dict]:
        """Get the latest version of a case."""
        versions = self.get_case_versions(case_id)
        return versions[0] if versions else None
    
    def save_case_version(
        self,
        case_id: Optional[str],
        case_name: str,
        cypher_queries: str,
        snapshots: List[Dict],
        save_notes: str = "",
        owner: Optional[str] = None,
    ) -> Dict:
        """
        Save a new version of a case.
        
        Args:
            case_id: Existing case ID (None to create new case)
            case_name: Name of the case
            cypher_queries: Cypher queries to recreate the graph
            snapshots: List of full snapshot data dictionaries
            save_notes: Notes for this save
            
        Returns:
            Dict with case_id, version, and timestamp
        """
        # Generate new case ID if creating new case
        if not case_id:
            case_id = f"case_{uuid.uuid4().hex[:12]}"
        
        # Get existing case or create new
        if case_id not in self._cases:
            self._cases[case_id] = {
                "id": case_id,
                "name": case_name,
                "created_at": datetime.now().isoformat(),
                "versions": [],
                "owner": owner,
            }
        else:
            # Update case name if provided
            if case_name:
                self._cases[case_id]["name"] = case_name
            # Ensure owner consistency if provided
            existing_owner = self._cases[case_id].get("owner")
            if owner and existing_owner and existing_owner != owner:
                raise ValueError(f"Case owner mismatch for {case_id}")
        
        case = self._cases[case_id]
        case_owner = case.get("owner") or owner
        
        # Determine next version number
        existing_versions = case.get("versions", [])
        next_version = len(existing_versions) + 1
        
        # Collect all snapshots from previous versions to preserve them
        # Use a set to track snapshot IDs and avoid duplicates
        all_snapshot_ids = set()
        all_snapshots = []
        
        # First, add snapshots from previous versions
        for version in existing_versions:
            if version.get("snapshots"):
                for snap in version["snapshots"]:
                    snap_id = snap.get("id") if isinstance(snap, dict) else None
                    if snap_id and snap_id not in all_snapshot_ids:
                        all_snapshot_ids.add(snap_id)
                        # Update metadata to point to the new version
                        snap_copy = snap.copy() if isinstance(snap, dict) else {}
                        snap_copy["case_version"] = next_version
                        snap_copy["case_name"] = case_name
                        all_snapshots.append(snap_copy)
        
        # Then, add new snapshots (avoid duplicates)
        for snapshot in snapshots:
            snapshot_id = snapshot.get("id") if isinstance(snapshot, dict) else None
            if snapshot_id and snapshot_id not in all_snapshot_ids:
                all_snapshot_ids.add(snapshot_id)
                snapshot_with_metadata = snapshot.copy()
                snapshot_with_metadata["case_id"] = case_id
                snapshot_with_metadata["case_version"] = next_version
                snapshot_with_metadata["case_name"] = case_name
                if case_owner:
                    snapshot_with_metadata["owner"] = case_owner
                all_snapshots.append(snapshot_with_metadata)
            elif not snapshot_id:
                # If snapshot doesn't have an ID, add it anyway (shouldn't happen, but be safe)
                snapshot_with_metadata = snapshot.copy()
                snapshot_with_metadata["case_id"] = case_id
                snapshot_with_metadata["case_version"] = next_version
                snapshot_with_metadata["case_name"] = case_name
                if case_owner:
                    snapshot_with_metadata["owner"] = case_owner
                all_snapshots.append(snapshot_with_metadata)
        
        snapshots_with_metadata = all_snapshots
        
        # Create new version
        version_data = {
            "version": next_version,
            "cypher_queries": cypher_queries,
            "snapshots": snapshots_with_metadata,  # Store full snapshot data with case/version metadata
            "save_notes": save_notes,
            "timestamp": datetime.now().isoformat(),
        }
        
        case["versions"].append(version_data)
        case["updated_at"] = datetime.now().isoformat()
        
        # Save to disk
        save_cases(self._cases)
        
        return {
            "case_id": case_id,
            "version": next_version,
            "timestamp": version_data["timestamp"],
        }
    
    def delete_case(self, case_id: str) -> bool:
        """Delete a case. Returns True if deleted, False if not found."""
        if case_id in self._cases:
            del self._cases[case_id]
            save_cases(self._cases)
            return True
        return False
    
    def reload(self):
        """Reload cases from disk."""
        self._cases = load_cases()


# Singleton instance
case_storage = CaseStorage()

