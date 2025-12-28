"""
Chat History Storage Service

Handles persistent storage of chat histories.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Storage file location
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "chat_histories.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_chat_histories() -> Dict:
    """Load chat histories from the JSON file."""
    ensure_storage_dir()
    
    if not STORAGE_FILE.exists():
        return {}
    
    try:
        with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading chat histories: {e}")
        return {}


def save_chat_histories(chat_histories: Dict):
    """Save chat histories to the JSON file."""
    ensure_storage_dir()
    
    try:
        # Create a temporary file first, then rename for atomic writes
        temp_file = STORAGE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(chat_histories, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(STORAGE_FILE)
    except IOError as e:
        print(f"Error saving chat histories: {e}")
        raise


class ChatHistoryStorage:
    """Service for managing chat history storage."""
    
    def __init__(self):
        self._chat_histories = load_chat_histories()
    
    def get_all(self) -> Dict:
        """Get all chat histories."""
        return self._chat_histories.copy()
    
    def get(self, chat_id: str) -> Optional[Dict]:
        """Get a specific chat history by ID."""
        return self._chat_histories.get(chat_id)
    
    def save(self, chat_id: str, chat_data: Dict):
        """Save a chat history."""
        self._chat_histories[chat_id] = chat_data
        save_chat_histories(self._chat_histories)
    
    def delete(self, chat_id: str) -> bool:
        """Delete a chat history. Returns True if deleted, False if not found."""
        if chat_id in self._chat_histories:
            del self._chat_histories[chat_id]
            save_chat_histories(self._chat_histories)
            return True
        return False
    
    def list_by_user(self, username: str) -> List[Dict]:
        """List all chat histories for a specific user."""
        return [
            chat for chat in self._chat_histories.values()
            if chat.get("owner") == username
        ]
    
    def list_by_snapshot(self, snapshot_id: str) -> List[Dict]:
        """List all chat histories associated with a snapshot."""
        return [
            chat for chat in self._chat_histories.values()
            if chat.get("snapshot_id") == snapshot_id
        ]
    
    def reload(self):
        """Reload chat histories from disk."""
        self._chat_histories = load_chat_histories()


# Singleton instance
chat_history_storage = ChatHistoryStorage()


