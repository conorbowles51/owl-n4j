"""
System Log Service - centralized logging for all major system actions.

Logs:
- AI Assistant queries and responses
- Graph operations (node creation, relationship creation, etc.)
- Case management (save, load, delete)
- Document ingestion
- User actions
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
from threading import Lock

# Log types
class LogType(str, Enum):
    AI_ASSISTANT = "ai_assistant"
    GRAPH_OPERATION = "graph_operation"
    CASE_MANAGEMENT = "case_management"
    CASE_OPERATION = "case_operation"  # For workspace operations
    DOCUMENT_INGESTION = "document_ingestion"
    USER_ACTION = "user_action"
    SYSTEM = "system"
    ERROR = "error"

# Log origins
class LogOrigin(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    INGESTION = "ingestion"
    SYSTEM = "system"

class SystemLogService:
    """Service for managing system logs."""
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize the log service.
        
        Args:
            log_file: Path to log file (defaults to data/system_logs.jsonl)
        """
        if log_file is None:
            # Default to data directory in project root
            base_dir = Path(__file__).parent.parent.parent
            log_dir = base_dir / "data"
            log_dir.mkdir(exist_ok=True)
            log_file = str(log_dir / "system_logs.jsonl")
        
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._max_logs = 10000  # Keep last 10k logs
        self._current_log_count = 0
        
        # Initialize log count
        self._update_log_count()
    
    def _update_log_count(self):
        """Update the current log count by reading the file."""
        try:
            if self.log_file.exists():
                # Count lines (approximate)
                with open(self.log_file, 'r') as f:
                    self._current_log_count = sum(1 for _ in f)
            else:
                self._current_log_count = 0
        except Exception:
            self._current_log_count = 0
    
    def _rotate_logs_if_needed(self):
        """Rotate logs if we exceed max_logs."""
        if self._current_log_count < self._max_logs:
            return
        
        try:
            # Read all logs
            logs = []
            if self.log_file.exists():
                with open(self.log_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            logs.append(json.loads(line))
            
            # Keep only the most recent logs
            if len(logs) > self._max_logs:
                logs = logs[-self._max_logs:]
                self._current_log_count = len(logs)
                
                # Write back
                with open(self.log_file, 'w') as f:
                    for log in logs:
                        f.write(json.dumps(log) + '\n')
        except Exception as e:
            print(f"[SystemLog] Error rotating logs: {e}")
    
    def log(
        self,
        log_type: LogType,
        origin: LogOrigin,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        user: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Log a system event.
        
        Args:
            log_type: Type of log (AI_ASSISTANT, GRAPH_OPERATION, etc.)
            origin: Where the action originated (FRONTEND, BACKEND, etc.)
            action: Description of the action
            details: Additional details about the action
            user: Username (if applicable)
            success: Whether the action succeeded
            error: Error message (if action failed)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": log_type.value,
            "origin": origin.value,
            "action": action,
            "user": user,
            "success": success,
            "error": error,
            "details": details or {},
        }
        
        with self._lock:
            try:
                # Append to log file (JSONL format)
                with open(self.log_file, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')
                
                self._current_log_count += 1
                self._rotate_logs_if_needed()
            except Exception as e:
                print(f"[SystemLog] Error writing log: {e}")
    
    def get_logs(
        self,
        log_type: Optional[LogType] = None,
        log_types: Optional[List[LogType]] = None,  # Support multiple log types
        origin: Optional[LogOrigin] = None,
        origins: Optional[List[LogOrigin]] = None,  # Support multiple origins
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        user: Optional[str] = None,
        success_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve logs with filtering.
        
        Args:
            log_type: Filter by log type
            origin: Filter by origin
            start_time: Filter logs after this time
            end_time: Filter logs before this time
            limit: Maximum number of logs to return
            offset: Offset for pagination
            user: Filter by user
            success_only: Filter by success status (True/False/None for all)
        
        Returns:
            Dict with 'logs' list and 'total' count
        """
        if not self.log_file.exists():
            return {"logs": [], "total": 0}
        
        logs = []
        total = 0
        
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        log = json.loads(line)
                        
                        # Apply filters
                        # Support both single and multiple log types
                        if log_types:
                            if log.get("type") not in [lt.value for lt in log_types]:
                                continue
                        elif log_type and log.get("type") != log_type.value:
                            continue
                        
                        # Support both single and multiple origins
                        if origins:
                            if log.get("origin") not in [o.value for o in origins]:
                                continue
                        elif origin and log.get("origin") != origin.value:
                            continue
                        if user and log.get("user") != user:
                            continue
                        if success_only is not None and log.get("success") != success_only:
                            continue
                        
                        # Time filters
                        if start_time or end_time:
                            log_time = datetime.fromisoformat(log.get("timestamp", ""))
                            if start_time and log_time < start_time:
                                continue
                            if end_time and log_time > end_time:
                                continue
                        
                        logs.append(log)
                        total += 1
                    except json.JSONDecodeError:
                        continue
            
            # Sort by timestamp (newest first)
            logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Apply pagination
            paginated_logs = logs[offset:offset + limit]
            
            return {
                "logs": paginated_logs,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            print(f"[SystemLog] Error reading logs: {e}")
            return {"logs": [], "total": 0}
    
    def get_log_statistics(self) -> Dict[str, Any]:
        """Get statistics about logs."""
        if not self.log_file.exists():
            return {
                "total_logs": 0,
                "by_type": {},
                "by_origin": {},
                "success_rate": 0.0,
            }
        
        stats = {
            "total_logs": 0,
            "by_type": {},
            "by_origin": {},
            "successful": 0,
            "failed": 0,
        }
        
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        log = json.loads(line)
                        stats["total_logs"] += 1
                        
                        # Count by type
                        log_type = log.get("type", "unknown")
                        stats["by_type"][log_type] = stats["by_type"].get(log_type, 0) + 1
                        
                        # Count by origin
                        origin = log.get("origin", "unknown")
                        stats["by_origin"][origin] = stats["by_origin"].get(origin, 0) + 1
                        
                        # Count success/failure
                        if log.get("success"):
                            stats["successful"] += 1
                        else:
                            stats["failed"] += 1
                    except json.JSONDecodeError:
                        continue
            
            # Calculate success rate
            if stats["total_logs"] > 0:
                stats["success_rate"] = stats["successful"] / stats["total_logs"]
            else:
                stats["success_rate"] = 0.0
            
            return stats
        except Exception as e:
            print(f"[SystemLog] Error calculating statistics: {e}")
            return {
                "total_logs": 0,
                "by_type": {},
                "by_origin": {},
                "success_rate": 0.0,
            }
    
    def clear_logs(self) -> None:
        """Clear all logs."""
        with self._lock:
            try:
                if self.log_file.exists():
                    self.log_file.unlink()
                self._current_log_count = 0
            except Exception as e:
                print(f"[SystemLog] Error clearing logs: {e}")


# Global instance
system_log_service = SystemLogService()

