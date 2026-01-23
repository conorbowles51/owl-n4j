"""
Presence Service

Tracks active workspace sessions and user presence for real-time collaboration.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from threading import Lock
import uuid

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
WORKSPACE_SESSIONS_FILE = STORAGE_DIR / "workspace_sessions.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_sessions() -> Dict:
    """Load workspace sessions from JSON file."""
    ensure_storage_dir()
    if not WORKSPACE_SESSIONS_FILE.exists():
        return {}
    try:
        with open(WORKSPACE_SESSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading workspace sessions: {e}")
        return {}


def save_sessions(sessions: Dict):
    """Save workspace sessions to JSON file."""
    ensure_storage_dir()
    temp_file = WORKSPACE_SESSIONS_FILE.with_suffix('.tmp')
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False, default=str)
        temp_file.replace(WORKSPACE_SESSIONS_FILE)
    except IOError as e:
        print(f"Error saving workspace sessions: {e}")
        raise


class PresenceService:
    """Service for tracking user presence in workspace sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, Dict] = load_sessions()
        self._active_sessions: Dict[str, Dict] = {}  # In-memory active sessions (session_id -> session_data)
        self._lock = Lock()
        self._cleanup_interval = timedelta(minutes=5)  # Clean up stale sessions every 5 minutes
    
    def create_session(
        self,
        case_id: str,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        device_info: Optional[str] = None
    ) -> str:
        """Create a new workspace session."""
        session_id = f"ws_{uuid.uuid4().hex[:16]}"
        now = datetime.now().isoformat()
        
        session_data = {
            "session_id": session_id,
            "case_id": case_id,
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "device_info": device_info,
            "started_at": now,
            "last_active": now
        }
        
        with self._lock:
            self._active_sessions[session_id] = session_data
            # Also persist to disk
            if case_id not in self._sessions:
                self._sessions[case_id] = {}
            self._sessions[case_id][session_id] = session_data
            save_sessions(self._sessions)
        
        return session_id
    
    def update_session_activity(self, session_id: str):
        """Update last active timestamp for a session."""
        with self._lock:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["last_active"] = datetime.now().isoformat()
                # Update in persisted sessions
                session = self._active_sessions[session_id]
                case_id = session.get("case_id")
                if case_id and case_id in self._sessions:
                    if session_id in self._sessions[case_id]:
                        self._sessions[case_id][session_id]["last_active"] = self._active_sessions[session_id]["last_active"]
                        save_sessions(self._sessions)
    
    def remove_session(self, session_id: str):
        """Remove a session (user left workspace)."""
        with self._lock:
            if session_id in self._active_sessions:
                session = self._active_sessions[session_id]
                case_id = session.get("case_id")
                del self._active_sessions[session_id]
                
                # Remove from persisted sessions
                if case_id and case_id in self._sessions:
                    if session_id in self._sessions[case_id]:
                        del self._sessions[case_id][session_id]
                        save_sessions(self._sessions)
    
    def get_online_users(self, case_id: str) -> List[Dict]:
        """Get list of users currently online in a workspace."""
        with self._lock:
            online_users = []
            seen_users = set()
            
            # Check active sessions
            for session in self._active_sessions.values():
                if session.get("case_id") == case_id:
                    user_id = session.get("user_id")
                    username = session.get("username")
                    if user_id and user_id not in seen_users:
                        online_users.append({
                            "user_id": user_id,
                            "username": username
                        })
                        seen_users.add(user_id)
            
            return online_users
    
    def cleanup_stale_sessions(self, timeout_minutes: int = 30):
        """Remove sessions that haven't been active for timeout_minutes."""
        cutoff = datetime.now() - timedelta(minutes=timeout_minutes)
        cutoff_iso = cutoff.isoformat()
        
        with self._lock:
            stale_sessions = []
            for session_id, session in self._active_sessions.items():
                last_active = session.get("last_active", "")
                if last_active < cutoff_iso:
                    stale_sessions.append(session_id)
            
            for session_id in stale_sessions:
                self.remove_session(session_id)
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data by session_id."""
        with self._lock:
            return self._active_sessions.get(session_id)


# Singleton instance
presence_service = PresenceService()
