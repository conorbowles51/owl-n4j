"""
Workspace Service

Handles workspace-specific business logic for case workspaces including:
- Case context (client profile, charges, exposure)
- Witness management
- Task management
- Deadline tracking
- Pinned evidence
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"

# Storage files
WORKSPACE_SESSIONS_FILE = STORAGE_DIR / "workspace_sessions.json"
CASE_CONTEXTS_FILE = STORAGE_DIR / "case_contexts.json"
WITNESSES_FILE = STORAGE_DIR / "witnesses.json"
THEORIES_FILE = STORAGE_DIR / "theories.json"
TASKS_FILE = STORAGE_DIR / "tasks.json"
CASE_DEADLINES_FILE = STORAGE_DIR / "case_deadlines.json"
PINNED_ITEMS_FILE = STORAGE_DIR / "pinned_items.json"
NOTES_FILE = STORAGE_DIR / "investigative_notes.json"


def ensure_storage_dir():
    """Ensure the storage directory exists."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(file_path: Path, default: Any = None) -> Any:
    """Load JSON file, returning default if file doesn't exist."""
    ensure_storage_dir()
    if not file_path.exists():
        return default if default is not None else {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {file_path}: {e}")
        return default if default is not None else {}


def save_json_file(file_path: Path, data: Any):
    """Save data to JSON file atomically."""
    ensure_storage_dir()
    temp_file = file_path.with_suffix('.tmp')
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        temp_file.replace(file_path)
    except IOError as e:
        print(f"Error saving {file_path}: {e}")
        raise


class WorkspaceService:
    """Service for managing workspace data."""
    
    def __init__(self):
        self._case_contexts = load_json_file(CASE_CONTEXTS_FILE, {})
        self._witnesses = load_json_file(WITNESSES_FILE, {})
        self._theories = load_json_file(THEORIES_FILE, {})
        self._tasks = load_json_file(TASKS_FILE, {})
        self._deadlines = load_json_file(CASE_DEADLINES_FILE, {})
        self._pinned_items = load_json_file(PINNED_ITEMS_FILE, {})
        self._notes = load_json_file(NOTES_FILE, {})
    
    def reload(self):
        """Reload all data from disk."""
        self._case_contexts = load_json_file(CASE_CONTEXTS_FILE, {})
        self._witnesses = load_json_file(WITNESSES_FILE, {})
        self._theories = load_json_file(THEORIES_FILE, {})
        self._tasks = load_json_file(TASKS_FILE, {})
        self._deadlines = load_json_file(CASE_DEADLINES_FILE, {})
        self._pinned_items = load_json_file(PINNED_ITEMS_FILE, {})
        self._notes = load_json_file(NOTES_FILE, {})
    
    # Case Context Methods
    def get_case_context(self, case_id: str) -> Optional[Dict]:
        """Get case context for a case."""
        return self._case_contexts.get(case_id)
    
    def save_case_context(self, case_id: str, context: Dict):
        """Save case context."""
        self._case_contexts[case_id] = {
            **context,
            "updated_at": datetime.now().isoformat()
        }
        save_json_file(CASE_CONTEXTS_FILE, self._case_contexts)
    
    # Witness Methods
    def get_witnesses(self, case_id: str) -> List[Dict]:
        """Get all witnesses for a case."""
        case_witnesses = self._witnesses.get(case_id, {})
        return list(case_witnesses.values())
    
    def get_witness(self, case_id: str, witness_id: str) -> Optional[Dict]:
        """Get a specific witness."""
        case_witnesses = self._witnesses.get(case_id, {})
        return case_witnesses.get(witness_id)
    
    def save_witness(self, case_id: str, witness: Dict) -> str:
        """Save a witness, returning witness_id."""
        if case_id not in self._witnesses:
            self._witnesses[case_id] = {}
        
        witness_id = witness.get("witness_id") or f"witness_{uuid.uuid4().hex[:12]}"
        witness["witness_id"] = witness_id
        witness["case_id"] = case_id
        witness["updated_at"] = datetime.now().isoformat()
        
        if "created_at" not in witness:
            witness["created_at"] = datetime.now().isoformat()
        
        self._witnesses[case_id][witness_id] = witness
        save_json_file(WITNESSES_FILE, self._witnesses)
        return witness_id
    
    def delete_witness(self, case_id: str, witness_id: str) -> bool:
        """Delete a witness."""
        if case_id in self._witnesses and witness_id in self._witnesses[case_id]:
            del self._witnesses[case_id][witness_id]
            save_json_file(WITNESSES_FILE, self._witnesses)
            return True
        return False
    
    # Theory Methods
    def get_theories(self, case_id: str, user_role: Optional[str] = None) -> List[Dict]:
        """Get all theories for a case, filtered by privilege if user_role provided."""
        case_theories = self._theories.get(case_id, {})
        theories = list(case_theories.values())
        
        # Filter by privilege level if user is not attorney
        if user_role != "attorney":
            theories = [
                t for t in theories
                if t.get("privilege_level") != "ATTORNEY_ONLY"
            ]
        
        return sorted(theories, key=lambda t: t.get("created_at", ""), reverse=True)
    
    def get_theory(self, case_id: str, theory_id: str) -> Optional[Dict]:
        """Get a specific theory."""
        case_theories = self._theories.get(case_id, {})
        return case_theories.get(theory_id)
    
    def save_theory(self, case_id: str, theory: Dict) -> str:
        """Save a theory, returning theory_id."""
        if case_id not in self._theories:
            self._theories[case_id] = {}
        
        theory_id = theory.get("theory_id") or f"theory_{uuid.uuid4().hex[:12]}"
        theory["theory_id"] = theory_id
        theory["case_id"] = case_id
        theory["updated_at"] = datetime.now().isoformat()
        
        if "created_at" not in theory:
            theory["created_at"] = datetime.now().isoformat()
        
        self._theories[case_id][theory_id] = theory
        save_json_file(THEORIES_FILE, self._theories)
        return theory_id
    
    def delete_theory(self, case_id: str, theory_id: str) -> bool:
        """Delete a theory."""
        if case_id in self._theories and theory_id in self._theories[case_id]:
            del self._theories[case_id][theory_id]
            save_json_file(THEORIES_FILE, self._theories)
            return True
        return False
    
    # Task Methods
    def get_tasks(self, case_id: str) -> List[Dict]:
        """Get all tasks for a case."""
        case_tasks = self._tasks.get(case_id, {})
        return sorted(
            list(case_tasks.values()),
            key=lambda t: (
                {"URGENT": 0, "HIGH": 1, "STANDARD": 2}.get(t.get("priority", "STANDARD"), 2),
                t.get("due_date", "")
            )
        )
    
    def get_task(self, case_id: str, task_id: str) -> Optional[Dict]:
        """Get a specific task."""
        case_tasks = self._tasks.get(case_id, {})
        return case_tasks.get(task_id)
    
    def save_task(self, case_id: str, task: Dict) -> str:
        """Save a task, returning task_id."""
        if case_id not in self._tasks:
            self._tasks[case_id] = {}
        
        task_id = task.get("task_id") or f"task_{uuid.uuid4().hex[:12]}"
        task["task_id"] = task_id
        task["case_id"] = case_id
        task["updated_at"] = datetime.now().isoformat()
        
        if "created_at" not in task:
            task["created_at"] = datetime.now().isoformat()
        
        self._tasks[case_id][task_id] = task
        save_json_file(TASKS_FILE, self._tasks)
        return task_id
    
    def delete_task(self, case_id: str, task_id: str) -> bool:
        """Delete a task."""
        if case_id in self._tasks and task_id in self._tasks[case_id]:
            del self._tasks[case_id][task_id]
            save_json_file(TASKS_FILE, self._tasks)
            return True
        return False
    
    # Deadline Methods
    def get_deadlines(self, case_id: str) -> List[Dict]:
        """Get all deadlines for a case (legacy method - returns deadline items from config)."""
        config = self.get_deadline_config(case_id)
        if not config:
            return []
        return config.get("deadlines", [])
    
    def get_deadline_config(self, case_id: str) -> Optional[Dict]:
        """Get deadline configuration for a case."""
        return self._deadlines.get(case_id)
    
    def save_deadline_config(self, case_id: str, config: Dict):
        """Save deadline configuration for a case."""
        # Ensure deadlines list has IDs
        if "deadlines" in config:
            for deadline in config.get("deadlines", []):
                if "deadline_id" not in deadline:
                    deadline["deadline_id"] = f"deadline_{uuid.uuid4().hex[:12]}"
        
        self._deadlines[case_id] = {
            **config,
            "case_id": case_id,
            "updated_at": datetime.now().isoformat()
        }
        save_json_file(CASE_DEADLINES_FILE, self._deadlines)
    
    def save_deadline(self, case_id: str, deadline: Dict) -> str:
        """Save a deadline (legacy method - updates deadline config)."""
        config = self.get_deadline_config(case_id) or {}
        deadlines = config.get("deadlines", [])
        
        deadline_id = deadline.get("deadline_id") or f"deadline_{uuid.uuid4().hex[:12]}"
        deadline["deadline_id"] = deadline_id
        
        # Update or add deadline
        existing_idx = next((i for i, d in enumerate(deadlines) if d.get("deadline_id") == deadline_id), None)
        if existing_idx is not None:
            deadlines[existing_idx] = deadline
        else:
            deadlines.append(deadline)
        
        config["deadlines"] = deadlines
        self.save_deadline_config(case_id, config)
        return deadline_id
    
    # Pinned Items Methods
    def get_pinned_items(self, case_id: str, user_id: Optional[str] = None) -> List[Dict]:
        """Get pinned items for a case, optionally filtered by user."""
        case_pinned = self._pinned_items.get(case_id, {})
        items = list(case_pinned.values())
        
        if user_id:
            items = [item for item in items if item.get("user_id") == user_id]
        
        return sorted(items, key=lambda i: i.get("pinned_at", ""), reverse=True)
    
    def pin_item(self, case_id: str, item_type: str, item_id: str, user_id: str, annotations_count: int = 0) -> str:
        """Pin an item, returning pin_id."""
        if case_id not in self._pinned_items:
            self._pinned_items[case_id] = {}
        
        pin_id = f"pin_{uuid.uuid4().hex[:12]}"
        self._pinned_items[case_id][pin_id] = {
            "pin_id": pin_id,
            "case_id": case_id,
            "item_type": item_type,
            "item_id": item_id,
            "user_id": user_id,
            "annotations_count": annotations_count,
            "pinned_at": datetime.now().isoformat()
        }
        save_json_file(PINNED_ITEMS_FILE, self._pinned_items)
        return pin_id
    
    def unpin_item(self, case_id: str, pin_id: str) -> bool:
        """Unpin an item."""
        if case_id in self._pinned_items and pin_id in self._pinned_items[case_id]:
            del self._pinned_items[case_id][pin_id]
            save_json_file(PINNED_ITEMS_FILE, self._pinned_items)
            return True
        return False
    
    # Investigative Notes Methods
    def get_notes(self, case_id: str) -> List[Dict]:
        """Get all investigative notes for a case."""
        case_notes = self._notes.get(case_id, {})
        return sorted(list(case_notes.values()), key=lambda n: n.get("created_at", ""), reverse=True)
    
    def get_note(self, case_id: str, note_id: str) -> Optional[Dict]:
        """Get a specific note."""
        case_notes = self._notes.get(case_id, {})
        return case_notes.get(note_id)
    
    def save_note(self, case_id: str, note: Dict) -> str:
        """Save a note, returning note_id."""
        if case_id not in self._notes:
            self._notes[case_id] = {}
        
        note_id = note.get("note_id") or f"note_{uuid.uuid4().hex[:12]}"
        note["note_id"] = note_id
        note["case_id"] = case_id
        note["updated_at"] = datetime.now().isoformat()
        
        if "created_at" not in note:
            note["created_at"] = datetime.now().isoformat()
        
        self._notes[case_id][note_id] = note
        save_json_file(NOTES_FILE, self._notes)
        return note_id
    
    def delete_note(self, case_id: str, note_id: str) -> bool:
        """Delete a note."""
        if case_id in self._notes and note_id in self._notes[case_id]:
            del self._notes[case_id][note_id]
            save_json_file(NOTES_FILE, self._notes)
            return True
        return False
    
    def get_investigation_timeline(self, case_id: str) -> List[Dict]:
        """
        Aggregate all timeline events for a case investigation.
        
        Returns a list of timeline events from various sources:
        - Witness creation
        - Task creation, due dates, status changes
        - Theory creation
        - Snapshot creation
        - Evidence processing
        - Evidence pinning
        - Case deadlines
        - Document uploads
        - System logs for case operations
        """
        from services.system_log_service import system_log_service, LogType
        from services.evidence_storage import evidence_storage
        from services.snapshot_storage import snapshot_storage
        from datetime import datetime
        
        events = []
        
        # 1. Witness creation dates and interviews
        witnesses = self.get_witnesses(case_id)
        for witness in witnesses:
            created_at = witness.get("created_at") or witness.get("added_at")
            if created_at:
                events.append({
                    "id": f"witness_{witness.get('witness_id')}",
                    "type": "witness_created",
                    "thread": "Witnesses",
                    "date": created_at,
                    "title": f"Witness Added: {witness.get('name', 'Unknown')}",
                    "description": f"Witness {witness.get('name', 'Unknown')} added to case",
                    "metadata": {"witness_id": witness.get("witness_id")},
                })
            
            # Witness interview dates (from interviews array)
            interviews = witness.get("interviews", [])
            if isinstance(interviews, list):
                for idx, interview in enumerate(interviews):
                    interview_date = interview.get("interview_date") or interview.get("date") or interview.get("scheduled_date")
                    if interview_date:
                        interview_id = interview.get("interview_id") or f"interview_{idx}"
                        # Use hash to ensure uniqueness
                        interview_hash = hash(f"{witness.get('witness_id')}_{interview_id}_{interview_date}") % 10000
                        events.append({
                            "id": f"witness_interview_{witness.get('witness_id')}_{interview_id}_{interview_hash}",
                            "type": "witness_interview",
                            "thread": "Witnesses",
                            "date": interview_date,
                            "title": f"Interview: {witness.get('name', 'Unknown')}",
                            "description": interview.get("notes") or interview.get("summary") or f"Interview with {witness.get('name', 'Unknown')}",
                            "metadata": {
                                "witness_id": witness.get("witness_id"),
                                "witness_name": witness.get("name"),
                                "interview_id": interview_id,
                                "interviewer": interview.get("interviewer"),
                            },
                        })
            
            # Also check for direct interview_date field on witness (legacy)
            interview_date = witness.get("interview_date") or witness.get("interviewed_at")
            if interview_date and not any(e.get("type") == "witness_interview" and e.get("metadata", {}).get("witness_id") == witness.get("witness_id") for e in events):
                events.append({
                    "id": f"witness_interview_{witness.get('witness_id')}_legacy",
                    "type": "witness_interview",
                    "thread": "Witnesses",
                    "date": interview_date,
                    "title": f"Interview: {witness.get('name', 'Unknown')}",
                    "description": f"Interview conducted with {witness.get('name', 'Unknown')}",
                    "metadata": {"witness_id": witness.get("witness_id"), "name": witness.get("name")},
                })
        
        # 2. Task events (creation, due dates, status changes)
        tasks = self.get_tasks(case_id)
        for task in tasks:
            # Task creation
            created_at = task.get("created_at")
            if created_at:
                events.append({
                    "id": f"task_created_{task.get('task_id')}",
                    "type": "task_created",
                    "thread": "Tasks",
                    "date": created_at,
                    "title": f"Task Created: {task.get('title', 'Untitled')}",
                    "description": task.get("description", ""),
                    "metadata": {"task_id": task.get("task_id"), "priority": task.get("priority")},
                })
            
            # Task due date
            due_date = task.get("due_date")
            if due_date:
                events.append({
                    "id": f"task_due_{task.get('task_id')}",
                    "type": "task_due",
                    "thread": "Tasks",
                    "date": due_date,
                    "title": f"Task Due: {task.get('title', 'Untitled')}",
                    "description": f"Due date for task: {task.get('title', 'Untitled')}",
                    "metadata": {"task_id": task.get("task_id"), "priority": task.get("priority")},
                })
            
            # Task status changes (if we track history)
            status = task.get("status")
            status_text = task.get("status_text")
            if status or status_text:
                updated_at = task.get("updated_at")
                if updated_at and updated_at != created_at:
                    # Use a hash of the status to ensure uniqueness if multiple status changes happen at same time
                    status_hash = hash(f"{status}_{status_text}_{updated_at}") % 10000
                    events.append({
                        "id": f"task_status_{task.get('task_id')}_{updated_at}_{status_hash}",
                        "type": "task_status_change",
                        "thread": "Tasks",
                        "date": updated_at,
                        "title": f"Task Status: {status_text or status}",
                        "description": f"Task '{task.get('title', 'Untitled')}' status changed",
                        "metadata": {"task_id": task.get("task_id"), "status": status, "status_text": status_text},
                    })
        
        # 3. Theory creation dates
        theories = self.get_theories(case_id)
        for theory in theories:
            created_at = theory.get("created_at")
            if created_at:
                events.append({
                    "id": f"theory_{theory.get('theory_id')}",
                    "type": "theory_created",
                    "thread": "Theories",
                    "date": created_at,
                    "title": f"Theory Created: {theory.get('title', 'Untitled')}",
                    "description": theory.get("hypothesis", ""),
                    "metadata": {"theory_id": theory.get("theory_id"), "confidence": theory.get("confidence_score")},
                })
        
        # 4. Snapshot creation dates
        all_snapshots = snapshot_storage.get_all()
        for snapshot_id, snapshot in all_snapshots.items():
            # Filter by case_id if provided
            if case_id and snapshot.get("case_id") != case_id:
                continue
            
            created_at = snapshot.get("created_at") or snapshot.get("timestamp")
            if created_at:
                events.append({
                    "id": f"snapshot_{snapshot_id}",
                    "type": "snapshot_created",
                    "thread": "Snapshots",
                    "date": created_at,
                    "title": f"Snapshot Created: {snapshot.get('name', 'Untitled')}",
                    "description": snapshot.get("notes", "") or snapshot.get("description", ""),
                    "metadata": {"snapshot_id": snapshot_id},
                })
        
        # 5. Evidence processing dates
        evidence_files = evidence_storage.list_files(case_id=case_id)
        for evidence in evidence_files:
            # Evidence upload
            uploaded_at = evidence.get("uploaded_at") or evidence.get("created_at")
            if uploaded_at:
                events.append({
                    "id": f"evidence_upload_{evidence.get('id')}",
                    "type": "evidence_uploaded",
                    "thread": "Evidence",
                    "date": uploaded_at,
                    "title": f"Evidence Uploaded: {evidence.get('original_filename', 'Unknown')}",
                    "description": f"File uploaded: {evidence.get('original_filename', 'Unknown')}",
                    "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                })
            
            # Evidence processing
            if evidence.get("status") == "processed":
                processed_at = evidence.get("processed_at")
                if processed_at:
                    events.append({
                        "id": f"evidence_processed_{evidence.get('id')}",
                        "type": "evidence_processed",
                        "thread": "Evidence",
                        "date": processed_at,
                        "title": f"Evidence Processed: {evidence.get('original_filename', 'Unknown')}",
                        "description": f"Processing completed for {evidence.get('original_filename', 'Unknown')}",
                        "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                    })
        
        # 6. Evidence pinning dates
        pinned_items = self.get_pinned_items(case_id)
        for pinned in pinned_items:
            pinned_at = pinned.get("pinned_at") or pinned.get("created_at")
            if pinned_at:
                item_type = pinned.get("item_type", "unknown")
                item_id = pinned.get("item_id", "")
                events.append({
                    "id": f"pinned_{pinned.get('pin_id')}",
                    "type": "evidence_pinned",
                    "thread": "Pinned Items",
                    "date": pinned_at,
                    "title": f"Item Pinned: {item_type}",
                    "description": f"{item_type} pinned to case",
                    "metadata": {"pin_id": pinned.get("pin_id"), "item_type": item_type, "item_id": item_id},
                })
        
        # 7. Investigative Notes creation/update dates
        notes = self.get_notes(case_id)
        for note in notes:
            created_at = note.get("created_at")
            if created_at:
                events.append({
                    "id": f"note_created_{note.get('note_id')}",
                    "type": "note_created",
                    "thread": "Notes",
                    "date": created_at,
                    "title": f"Note Created: {note.get('title', 'Untitled')}",
                    "description": note.get("content", "")[:100] + "..." if len(note.get("content", "")) > 100 else note.get("content", ""),
                    "metadata": {"note_id": note.get("note_id")},
                })
            
            # Note updates
            updated_at = note.get("updated_at")
            if updated_at and updated_at != created_at:
                # Use hash to ensure uniqueness if multiple updates at same time
                update_hash = hash(f"{note.get('note_id')}_{updated_at}") % 10000
                events.append({
                    "id": f"note_updated_{note.get('note_id')}_{updated_at}_{update_hash}",
                    "type": "note_updated",
                    "thread": "Notes",
                    "date": updated_at,
                    "title": f"Note Updated: {note.get('title', 'Untitled')}",
                    "description": f"Note '{note.get('title', 'Untitled')}' was updated",
                    "metadata": {"note_id": note.get("note_id")},
                })
        
        # 8. Documents (case documents uploaded via Quick Actions)
        # Documents are stored in evidence_storage but marked as case documents
        # We already handle evidence upload above, but we can add a specific thread for case documents
        for evidence in evidence_files:
            # Check if it's a case document (uploaded via Quick Actions)
            if evidence.get("is_case_document") or evidence.get("upload_method") == "quick_action":
                uploaded_at = evidence.get("uploaded_at") or evidence.get("created_at")
                if uploaded_at:
                    events.append({
                        "id": f"document_upload_{evidence.get('id')}",
                        "type": "document_uploaded",
                        "thread": "Documents",
                        "date": uploaded_at,
                        "title": f"Document Uploaded: {evidence.get('original_filename', 'Unknown')}",
                        "description": f"Case document uploaded: {evidence.get('original_filename', 'Unknown')}",
                        "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                    })
        
        # 9. Case deadlines
        deadline_config = self.get_deadline_config(case_id)
        if deadline_config:
            # Trial date
            trial_date = deadline_config.get("trial_date")
            if trial_date:
                events.append({
                    "id": f"deadline_trial_{case_id}",
                    "type": "trial_date",
                    "thread": "Deadlines",
                    "date": trial_date,
                    "title": f"Trial Date: {deadline_config.get('court', 'Unknown Court')}",
                    "description": f"Trial scheduled at {deadline_config.get('court', 'Unknown Court')}",
                    "metadata": {"court": deadline_config.get("court"), "judge": deadline_config.get("judge")},
                })
            
            # Individual deadlines
            deadline_items = deadline_config.get("deadlines", [])
            for idx, deadline in enumerate(deadline_items):
                due_date = deadline.get("due_date")
                if due_date:
                    deadline_id = deadline.get("deadline_id") or f"deadline_{idx}_{due_date}"
                    events.append({
                        "id": f"deadline_{deadline_id}",
                        "type": "deadline",
                        "thread": "Deadlines",
                        "date": due_date,
                        "title": f"Deadline: {deadline.get('title', 'Untitled')}",
                        "description": deadline.get("title", ""),
                        "metadata": {"deadline_id": deadline.get("deadline_id"), "urgency": deadline.get("urgency")},
                    })
        
        # 10. System logs for case operations (excluding audit log)
        try:
            from datetime import datetime as dt
            system_logs = system_log_service.get_logs(
                log_types=[LogType.CASE_OPERATION, LogType.CASE_MANAGEMENT],
                limit=500
            )
            log_index = 0
            for log in system_logs.get("logs", []):
                details = log.get("details", {})
                if details.get("case_id") == case_id:
                    timestamp = log.get("timestamp")
                    if timestamp:
                        log_index += 1
                        events.append({
                            "id": f"log_{log_index}_{timestamp}_{hash(str(details)) % 10000}",
                            "type": "system_action",
                            "thread": "System Actions",
                            "date": timestamp,
                            "title": log.get("action", "System Action"),
                            "description": log.get("action", ""),
                            "metadata": {
                                "log_type": log.get("type"),
                                "user": log.get("user"),
                                "success": log.get("success"),
                                "details": details,
                            },
                        })
        except Exception as e:
            print(f"[Investigation Timeline] Error loading system logs: {e}")
        
        # Sort all events by date
        events.sort(key=lambda x: x.get("date", ""))
        
        return events

    def get_theory_timeline(self, case_id: str, theory_id: str) -> List[Dict]:
        """
        Get timeline events for a specific theory, including only:
        - The theory itself (creation/update)
        - Attached evidence (processing dates)
        - Attached witnesses (creation/interview dates)
        - Attached notes (creation/update dates)
        - Attached snapshots (creation dates)
        - Attached documents (upload/processing dates)
        - Attached tasks (creation/due dates/status changes)
        """
        from services.evidence_storage import evidence_storage
        from services.snapshot_storage import snapshot_storage
        from datetime import datetime
        
        events = []
        
        # Get the theory
        theories = self.get_theories(case_id)
        theory = next((t for t in theories if t.get("theory_id") == theory_id), None)
        if not theory:
            return events
        
        # Get attached item IDs
        attached_evidence_ids = set(theory.get("attached_evidence_ids", []) or [])
        attached_witness_ids = set(theory.get("attached_witness_ids", []) or [])
        attached_note_ids = set(theory.get("attached_note_ids", []) or [])
        attached_snapshot_ids = set(theory.get("attached_snapshot_ids", []) or [])
        attached_document_ids = set(theory.get("attached_document_ids", []) or [])
        attached_task_ids = set(theory.get("attached_task_ids", []) or [])
        
        # 1. Theory creation/update
        created_at = theory.get("created_at")
        if created_at:
            events.append({
                "id": f"theory_{theory_id}_created",
                "type": "theory_created",
                "thread": "Theory",
                "date": created_at,
                "title": f"Theory Created: {theory.get('title', 'Untitled')}",
                "description": theory.get("hypothesis", ""),
                "metadata": {"theory_id": theory_id, "confidence": theory.get("confidence_score")},
            })
        
        updated_at = theory.get("updated_at")
        if updated_at and updated_at != created_at:
            events.append({
                "id": f"theory_{theory_id}_updated",
                "type": "theory_updated",
                "thread": "Theory",
                "date": updated_at,
                "title": f"Theory Updated: {theory.get('title', 'Untitled')}",
                "description": f"Theory '{theory.get('title', 'Untitled')}' was updated",
                "metadata": {"theory_id": theory_id},
            })
        
        # 2. Attached evidence processing dates
        if attached_evidence_ids:
            evidence_files = evidence_storage.list_files(case_id=case_id)
            for evidence in evidence_files:
                if evidence.get("id") in attached_evidence_ids:
                    # Evidence processing
                    if evidence.get("status") == "processed":
                        processed_at = evidence.get("processed_at")
                        if processed_at:
                            events.append({
                                "id": f"evidence_processed_{evidence.get('id')}",
                                "type": "evidence_processed",
                                "thread": "Evidence",
                                "date": processed_at,
                                "title": f"Evidence Processed: {evidence.get('original_filename', 'Unknown')}",
                                "description": f"Processing completed for {evidence.get('original_filename', 'Unknown')}",
                                "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                            })
                    
                    # Evidence upload
                    uploaded_at = evidence.get("uploaded_at") or evidence.get("created_at")
                    if uploaded_at:
                        events.append({
                            "id": f"evidence_upload_{evidence.get('id')}",
                            "type": "evidence_uploaded",
                            "thread": "Evidence",
                            "date": uploaded_at,
                            "title": f"Evidence Uploaded: {evidence.get('original_filename', 'Unknown')}",
                            "description": f"File uploaded: {evidence.get('original_filename', 'Unknown')}",
                            "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                        })
        
        # 3. Attached witnesses (creation and interviews)
        if attached_witness_ids:
            witnesses = self.get_witnesses(case_id)
            for witness in witnesses:
                if witness.get("witness_id") in attached_witness_ids:
                    created_at = witness.get("created_at") or witness.get("added_at")
                    if created_at:
                        events.append({
                            "id": f"witness_{witness.get('witness_id')}",
                            "type": "witness_created",
                            "thread": "Witnesses",
                            "date": created_at,
                            "title": f"Witness Added: {witness.get('name', 'Unknown')}",
                            "description": f"Witness {witness.get('name', 'Unknown')} added to theory",
                            "metadata": {"witness_id": witness.get("witness_id")},
                        })
                    
                    # Witness interview dates
                    interviews = witness.get("interviews", [])
                    if isinstance(interviews, list):
                        for idx, interview in enumerate(interviews):
                            interview_date = interview.get("interview_date") or interview.get("date") or interview.get("scheduled_date")
                            if interview_date:
                                interview_id = interview.get("interview_id") or f"interview_{idx}"
                                interview_hash = hash(f"{witness.get('witness_id')}_{interview_id}_{interview_date}") % 10000
                                events.append({
                                    "id": f"witness_interview_{witness.get('witness_id')}_{interview_id}_{interview_hash}",
                                    "type": "witness_interview",
                                    "thread": "Witnesses",
                                    "date": interview_date,
                                    "title": f"Interview: {witness.get('name', 'Unknown')}",
                                    "description": interview.get("notes") or interview.get("summary") or f"Interview with {witness.get('name', 'Unknown')}",
                                    "metadata": {
                                        "witness_id": witness.get("witness_id"),
                                        "witness_name": witness.get("name"),
                                        "interview_id": interview_id,
                                    },
                                })
        
        # 4. Attached notes (creation/update)
        if attached_note_ids:
            notes = self.get_notes(case_id)
            for note in notes:
                note_id = note.get("note_id") or note.get("id")
                if note_id in attached_note_ids:
                    created_at = note.get("created_at")
                    if created_at:
                        events.append({
                            "id": f"note_created_{note_id}",
                            "type": "note_created",
                            "thread": "Notes",
                            "date": created_at,
                            "title": f"Note Created",
                            "description": note.get("content", "")[:100] + "..." if len(note.get("content", "")) > 100 else note.get("content", ""),
                            "metadata": {"note_id": note_id},
                        })
                    
                    updated_at = note.get("updated_at")
                    if updated_at and updated_at != created_at:
                        update_hash = hash(f"{note_id}_{updated_at}") % 10000
                        events.append({
                            "id": f"note_updated_{note_id}_{updated_at}_{update_hash}",
                            "type": "note_updated",
                            "thread": "Notes",
                            "date": updated_at,
                            "title": f"Note Updated",
                            "description": f"Note was updated",
                            "metadata": {"note_id": note_id},
                        })
        
        # 5. Attached snapshots (creation dates)
        if attached_snapshot_ids:
            all_snapshots = snapshot_storage.get_all()
            for snapshot_id, snapshot in all_snapshots.items():
                if snapshot_id in attached_snapshot_ids:
                    created_at = snapshot.get("created_at") or snapshot.get("timestamp")
                    if created_at:
                        events.append({
                            "id": f"snapshot_{snapshot_id}",
                            "type": "snapshot_created",
                            "thread": "Snapshots",
                            "date": created_at,
                            "title": f"Snapshot Created: {snapshot.get('name', 'Untitled')}",
                            "description": snapshot.get("notes", "") or snapshot.get("description", ""),
                            "metadata": {"snapshot_id": snapshot_id},
                        })
        
        # 6. Attached documents (upload/processing dates)
        if attached_document_ids:
            evidence_files = evidence_storage.list_files(case_id=case_id)
            for evidence in evidence_files:
                if evidence.get("id") in attached_document_ids:
                    uploaded_at = evidence.get("uploaded_at") or evidence.get("created_at")
                    if uploaded_at:
                        events.append({
                            "id": f"document_upload_{evidence.get('id')}",
                            "type": "document_uploaded",
                            "thread": "Documents",
                            "date": uploaded_at,
                            "title": f"Document Uploaded: {evidence.get('original_filename', 'Unknown')}",
                            "description": f"Case document uploaded: {evidence.get('original_filename', 'Unknown')}",
                            "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                        })
                    
                    if evidence.get("status") == "processed":
                        processed_at = evidence.get("processed_at")
                        if processed_at:
                            events.append({
                                "id": f"document_processed_{evidence.get('id')}",
                                "type": "document_processed",
                                "thread": "Documents",
                                "date": processed_at,
                                "title": f"Document Processed: {evidence.get('original_filename', 'Unknown')}",
                                "description": f"Processing completed for {evidence.get('original_filename', 'Unknown')}",
                                "metadata": {"evidence_id": evidence.get("id"), "filename": evidence.get("original_filename")},
                            })
        
        # 7. Attached tasks (creation, due dates, status changes)
        if attached_task_ids:
            tasks = self.get_tasks(case_id)
            for task in tasks:
                if task.get("task_id") in attached_task_ids:
                    # Task creation
                    created_at = task.get("created_at")
                    if created_at:
                        events.append({
                            "id": f"task_created_{task.get('task_id')}",
                            "type": "task_created",
                            "thread": "Tasks",
                            "date": created_at,
                            "title": f"Task Created: {task.get('title', 'Untitled')}",
                            "description": task.get("description", ""),
                            "metadata": {"task_id": task.get("task_id"), "priority": task.get("priority")},
                        })
                    
                    # Task due date
                    due_date = task.get("due_date")
                    if due_date:
                        events.append({
                            "id": f"task_due_{task.get('task_id')}",
                            "type": "task_due",
                            "thread": "Tasks",
                            "date": due_date,
                            "title": f"Task Due: {task.get('title', 'Untitled')}",
                            "description": f"Due date for task: {task.get('title', 'Untitled')}",
                            "metadata": {"task_id": task.get("task_id"), "priority": task.get("priority")},
                        })
                    
                    # Task status changes
                    status = task.get("status")
                    status_text = task.get("status_text")
                    if status or status_text:
                        updated_at = task.get("updated_at")
                        if updated_at and updated_at != created_at:
                            status_hash = hash(f"{status}_{status_text}_{updated_at}") % 10000
                            events.append({
                                "id": f"task_status_{task.get('task_id')}_{updated_at}_{status_hash}",
                                "type": "task_status_change",
                                "thread": "Tasks",
                                "date": updated_at,
                                "title": f"Task Status: {status_text or status}",
                                "description": f"Task '{task.get('title', 'Untitled')}' status changed",
                                "metadata": {"task_id": task.get("task_id"), "status": status, "status_text": status_text},
                            })
        
        # Sort all events by date
        events.sort(key=lambda x: x.get("date", ""))
        
        return events


# Singleton instance
workspace_service = WorkspaceService()
