"""
Artifact Storage Service

Handles persistent storage of artifacts in a JSON file.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Storage file location
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "artifacts.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_artifacts() -> Dict:
    """Load artifacts from the JSON file."""
    ensure_storage_dir()
    
    if not STORAGE_FILE.exists():
        return {}
    
    try:
        with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading artifacts: {e}")
        return {}


def save_artifacts(artifacts: Dict):
    """Save artifacts to the JSON file."""
    ensure_storage_dir()
    
    try:
        # Create a temporary file first, then rename for atomic writes
        temp_file = STORAGE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(artifacts, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(STORAGE_FILE)
    except IOError as e:
        print(f"Error saving artifacts: {e}")
        raise


class ArtifactStorage:
    """Service for managing artifact storage."""
    
    def __init__(self):
        self._artifacts = load_artifacts()
    
    def get_all(self) -> Dict:
        """Get all artifacts."""
        return self._artifacts.copy()
    
    def get(self, artifact_id: str) -> Optional[Dict]:
        """Get a specific artifact by ID."""
        return self._artifacts.get(artifact_id)
    
    def save(self, artifact_id: str, artifact_data: Dict):
        """Save an artifact."""
        self._artifacts[artifact_id] = artifact_data
        save_artifacts(self._artifacts)
    
    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact. Returns True if deleted, False if not found."""
        if artifact_id in self._artifacts:
            del self._artifacts[artifact_id]
            save_artifacts(self._artifacts)
            return True
        return False
    
    def reload(self):
        """Reload artifacts from disk."""
        self._artifacts = load_artifacts()


# Singleton instance
artifact_storage = ArtifactStorage()

