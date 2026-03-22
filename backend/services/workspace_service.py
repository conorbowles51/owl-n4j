"""
Workspace Service

Handles workspace-specific business logic for case workspaces including:
- Case context (client profile, charges, exposure)
- Witness management
- Task management
- Deadline tracking
- Pinned evidence
- Investigative notes

Storage: PostgreSQL via JSONB columns (replaced JSON-on-disk in March 2026).
"""

import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlalchemy import select, delete

from postgres.session import get_background_session
from postgres.models.workspace import (
    WorkspaceContext,
    WorkspaceWitness,
    WorkspaceTheory,
    WorkspaceTask,
    WorkspaceNote,
    WorkspacePinnedItem,
    WorkspaceDeadlineConfig,
)


class WorkspaceService:
    """Service for managing workspace data backed by PostgreSQL."""

    def reload(self):
        """No-op — data is always fresh from the database."""
        pass

    # ------------------------------------------------------------------ #
    # Case Context
    # ------------------------------------------------------------------ #

    def get_case_context(self, case_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceContext).where(WorkspaceContext.case_id == case_id)
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_case_context(self, case_id: str, context: Dict):
        context["updated_at"] = datetime.now().isoformat()
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceContext).where(WorkspaceContext.case_id == case_id)
            ).scalar_one_or_none()
            if row:
                row.data = context
            else:
                db.add(WorkspaceContext(case_id=case_id, data=context))

    # ------------------------------------------------------------------ #
    # Witnesses
    # ------------------------------------------------------------------ #

    def get_witnesses(self, case_id: str) -> List[Dict]:
        with get_background_session() as db:
            rows = db.execute(
                select(WorkspaceWitness).where(WorkspaceWitness.case_id == case_id)
            ).scalars().all()
            return [dict(r.data) for r in rows]

    def get_witness(self, case_id: str, witness_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceWitness).where(
                    WorkspaceWitness.case_id == case_id,
                    WorkspaceWitness.witness_id == witness_id,
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_witness(self, case_id: str, witness: Dict) -> str:
        witness_id = witness.get("witness_id") or f"witness_{uuid.uuid4().hex[:12]}"
        witness["witness_id"] = witness_id
        witness["case_id"] = case_id
        witness["updated_at"] = datetime.now().isoformat()
        if "created_at" not in witness:
            witness["created_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceWitness).where(
                    WorkspaceWitness.case_id == case_id,
                    WorkspaceWitness.witness_id == witness_id,
                )
            ).scalar_one_or_none()
            if row:
                row.data = witness
            else:
                db.add(WorkspaceWitness(case_id=case_id, witness_id=witness_id, data=witness))
        return witness_id

    def delete_witness(self, case_id: str, witness_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspaceWitness).where(
                    WorkspaceWitness.case_id == case_id,
                    WorkspaceWitness.witness_id == witness_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Theories
    # ------------------------------------------------------------------ #

    def get_theories(self, case_id: str, user_role: Optional[str] = None) -> List[Dict]:
        with get_background_session() as db:
            rows = db.execute(
                select(WorkspaceTheory).where(WorkspaceTheory.case_id == case_id)
            ).scalars().all()
            theories = [dict(r.data) for r in rows]

        if user_role != "attorney":
            theories = [
                t for t in theories
                if t.get("privilege_level") != "ATTORNEY_ONLY"
            ]

        return sorted(theories, key=lambda t: t.get("created_at", ""), reverse=True)

    def get_theory(self, case_id: str, theory_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceTheory).where(
                    WorkspaceTheory.case_id == case_id,
                    WorkspaceTheory.theory_id == theory_id,
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_theory(self, case_id: str, theory: Dict) -> str:
        theory_id = theory.get("theory_id") or f"theory_{uuid.uuid4().hex[:12]}"
        theory["theory_id"] = theory_id
        theory["case_id"] = case_id
        theory["updated_at"] = datetime.now().isoformat()
        if "created_at" not in theory:
            theory["created_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceTheory).where(
                    WorkspaceTheory.case_id == case_id,
                    WorkspaceTheory.theory_id == theory_id,
                )
            ).scalar_one_or_none()
            if row:
                row.data = theory
            else:
                db.add(WorkspaceTheory(case_id=case_id, theory_id=theory_id, data=theory))
        return theory_id

    def delete_theory(self, case_id: str, theory_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspaceTheory).where(
                    WorkspaceTheory.case_id == case_id,
                    WorkspaceTheory.theory_id == theory_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #

    def get_tasks(self, case_id: str) -> List[Dict]:
        with get_background_session() as db:
            rows = db.execute(
                select(WorkspaceTask).where(WorkspaceTask.case_id == case_id)
            ).scalars().all()
            tasks = [dict(r.data) for r in rows]

        return sorted(
            tasks,
            key=lambda t: (
                {"URGENT": 0, "HIGH": 1, "STANDARD": 2}.get(t.get("priority", "STANDARD"), 2),
                t.get("due_date", ""),
            ),
        )

    def get_task(self, case_id: str, task_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceTask).where(
                    WorkspaceTask.case_id == case_id,
                    WorkspaceTask.task_id == task_id,
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_task(self, case_id: str, task: Dict) -> str:
        task_id = task.get("task_id") or f"task_{uuid.uuid4().hex[:12]}"
        task["task_id"] = task_id
        task["case_id"] = case_id
        task["updated_at"] = datetime.now().isoformat()
        if "created_at" not in task:
            task["created_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceTask).where(
                    WorkspaceTask.case_id == case_id,
                    WorkspaceTask.task_id == task_id,
                )
            ).scalar_one_or_none()
            if row:
                row.data = task
            else:
                db.add(WorkspaceTask(case_id=case_id, task_id=task_id, data=task))
        return task_id

    def delete_task(self, case_id: str, task_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspaceTask).where(
                    WorkspaceTask.case_id == case_id,
                    WorkspaceTask.task_id == task_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Deadlines
    # ------------------------------------------------------------------ #

    def get_deadlines(self, case_id: str) -> List[Dict]:
        config = self.get_deadline_config(case_id)
        if not config:
            return []
        return config.get("deadlines", [])

    def get_deadline_config(self, case_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceDeadlineConfig).where(
                    WorkspaceDeadlineConfig.case_id == case_id
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_deadline_config(self, case_id: str, config: Dict):
        if "deadlines" in config:
            for deadline in config.get("deadlines", []):
                if "deadline_id" not in deadline:
                    deadline["deadline_id"] = f"deadline_{uuid.uuid4().hex[:12]}"

        config["case_id"] = case_id
        config["updated_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceDeadlineConfig).where(
                    WorkspaceDeadlineConfig.case_id == case_id
                )
            ).scalar_one_or_none()
            if row:
                row.data = config
            else:
                db.add(WorkspaceDeadlineConfig(case_id=case_id, data=config))

    def save_deadline(self, case_id: str, deadline: Dict) -> str:
        config = self.get_deadline_config(case_id) or {}
        deadlines = config.get("deadlines", [])

        deadline_id = deadline.get("deadline_id") or f"deadline_{uuid.uuid4().hex[:12]}"
        deadline["deadline_id"] = deadline_id

        existing_idx = next(
            (i for i, d in enumerate(deadlines) if d.get("deadline_id") == deadline_id),
            None,
        )
        if existing_idx is not None:
            deadlines[existing_idx] = deadline
        else:
            deadlines.append(deadline)

        config["deadlines"] = deadlines
        self.save_deadline_config(case_id, config)
        return deadline_id

    # ------------------------------------------------------------------ #
    # Pinned Items
    # ------------------------------------------------------------------ #

    def get_pinned_items(self, case_id: str, user_id: Optional[str] = None) -> List[Dict]:
        with get_background_session() as db:
            stmt = select(WorkspacePinnedItem).where(WorkspacePinnedItem.case_id == case_id)
            if user_id:
                stmt = stmt.where(WorkspacePinnedItem.user_id == user_id)
            rows = db.execute(stmt).scalars().all()
            items = [dict(r.data) for r in rows]

        return sorted(items, key=lambda i: i.get("pinned_at", ""), reverse=True)

    def pin_item(
        self,
        case_id: str,
        item_type: str,
        item_id: str,
        user_id: str,
        annotations_count: int = 0,
    ) -> str:
        pin_id = f"pin_{uuid.uuid4().hex[:12]}"
        data = {
            "pin_id": pin_id,
            "case_id": case_id,
            "item_type": item_type,
            "item_id": item_id,
            "user_id": user_id,
            "annotations_count": annotations_count,
            "pinned_at": datetime.now().isoformat(),
        }
        with get_background_session() as db:
            db.add(
                WorkspacePinnedItem(
                    case_id=case_id,
                    pin_id=pin_id,
                    item_type=item_type,
                    item_id=item_id,
                    user_id=user_id,
                    data=data,
                )
            )
        return pin_id

    def unpin_item(self, case_id: str, pin_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspacePinnedItem).where(
                    WorkspacePinnedItem.case_id == case_id,
                    WorkspacePinnedItem.pin_id == pin_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Investigative Notes
    # ------------------------------------------------------------------ #

    def get_notes(self, case_id: str) -> List[Dict]:
        with get_background_session() as db:
            rows = db.execute(
                select(WorkspaceNote).where(WorkspaceNote.case_id == case_id)
            ).scalars().all()
            notes = [dict(r.data) for r in rows]

        return sorted(notes, key=lambda n: n.get("created_at", ""), reverse=True)

    def get_note(self, case_id: str, note_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceNote).where(
                    WorkspaceNote.case_id == case_id,
                    WorkspaceNote.note_id == note_id,
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_note(self, case_id: str, note: Dict) -> str:
        note_id = note.get("note_id") or f"note_{uuid.uuid4().hex[:12]}"
        note["note_id"] = note_id
        note["case_id"] = case_id
        note["updated_at"] = datetime.now().isoformat()
        if "created_at" not in note:
            note["created_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceNote).where(
                    WorkspaceNote.case_id == case_id,
                    WorkspaceNote.note_id == note_id,
                )
            ).scalar_one_or_none()
            if row:
                row.data = note
            else:
                db.add(WorkspaceNote(case_id=case_id, note_id=note_id, data=note))
        return note_id

    def delete_note(self, case_id: str, note_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspaceNote).where(
                    WorkspaceNote.case_id == case_id,
                    WorkspaceNote.note_id == note_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Investigation Timeline (read-only aggregation)
    # ------------------------------------------------------------------ #

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
        from services.snapshot_storage import snapshot_storage

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
                                "interviewer": interview.get("interviewer"),
                            },
                        })

            interview_date = witness.get("interview_date") or witness.get("interviewed_at")
            if interview_date and not any(
                e.get("type") == "witness_interview"
                and e.get("metadata", {}).get("witness_id") == witness.get("witness_id")
                for e in events
            ):
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
        from services.evidence_db_storage import EvidenceDBStorage
        with get_background_session() as ev_db:
            evidence_files = EvidenceDBStorage.list_files(ev_db, case_id=uuid.UUID(case_id))
            for evidence in evidence_files:
                uploaded_at = evidence.created_at.isoformat() if evidence.created_at else None
                if uploaded_at:
                    events.append({
                        "id": f"evidence_upload_{evidence.id}",
                        "type": "evidence_uploaded",
                        "thread": "Evidence",
                        "date": uploaded_at,
                        "title": f"Evidence Uploaded: {evidence.original_filename or 'Unknown'}",
                        "description": f"File uploaded: {evidence.original_filename or 'Unknown'}",
                        "metadata": {"evidence_id": str(evidence.id), "filename": evidence.original_filename},
                    })

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

            updated_at = note.get("updated_at")
            if updated_at and updated_at != created_at:
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
        for evidence in evidence_files:
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

        # 10. System logs for case operations
        try:
            system_logs = system_log_service.get_logs(
                log_types=[LogType.CASE_OPERATION, LogType.CASE_MANAGEMENT],
                limit=500,
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

        events.sort(key=lambda x: x.get("date", ""))
        return events

    # ------------------------------------------------------------------ #
    # Theory Timeline
    # ------------------------------------------------------------------ #

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
        from services.snapshot_storage import snapshot_storage

        events = []

        theories = self.get_theories(case_id)
        theory = next((t for t in theories if t.get("theory_id") == theory_id), None)
        if not theory:
            return events

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

        # 2. Attached evidence
        if attached_evidence_ids:
            from services.evidence_db_storage import EvidenceDBStorage
            with get_background_session() as ev_db:
                evidence_files = EvidenceDBStorage.list_files(ev_db, case_id=uuid.UUID(case_id))
                for evidence in evidence_files:
                    if str(evidence.id) in attached_evidence_ids:
                        if evidence.status == "processed" and evidence.processed_at:
                            events.append({
                                "id": f"evidence_processed_{evidence.id}",
                                "type": "evidence_processed",
                                "thread": "Evidence",
                                "date": evidence.processed_at.isoformat(),
                                "title": f"Evidence Processed: {evidence.original_filename or 'Unknown'}",
                                "description": f"Processing completed for {evidence.original_filename or 'Unknown'}",
                                "metadata": {"evidence_id": str(evidence.id), "filename": evidence.original_filename},
                            })

                        uploaded_at = evidence.created_at.isoformat() if evidence.created_at else None
                        if uploaded_at:
                            events.append({
                                "id": f"evidence_upload_{evidence.id}",
                                "type": "evidence_uploaded",
                                "thread": "Evidence",
                                "date": uploaded_at,
                                "title": f"Evidence Uploaded: {evidence.original_filename or 'Unknown'}",
                                "description": f"File uploaded: {evidence.original_filename or 'Unknown'}",
                                "metadata": {"evidence_id": str(evidence.id), "filename": evidence.original_filename},
                            })

        # 3. Attached witnesses
        if attached_witness_ids:
            witnesses = self.get_witnesses(case_id)
            for witness in witnesses:
                if witness.get("witness_id") in attached_witness_ids:
                    w_created = witness.get("created_at") or witness.get("added_at")
                    if w_created:
                        events.append({
                            "id": f"witness_{witness.get('witness_id')}",
                            "type": "witness_created",
                            "thread": "Witnesses",
                            "date": w_created,
                            "title": f"Witness Added: {witness.get('name', 'Unknown')}",
                            "description": f"Witness {witness.get('name', 'Unknown')} added to theory",
                            "metadata": {"witness_id": witness.get("witness_id")},
                        })

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

        # 4. Attached notes
        if attached_note_ids:
            notes = self.get_notes(case_id)
            for note in notes:
                note_id = note.get("note_id") or note.get("id")
                if note_id in attached_note_ids:
                    n_created = note.get("created_at")
                    if n_created:
                        events.append({
                            "id": f"note_created_{note_id}",
                            "type": "note_created",
                            "thread": "Notes",
                            "date": n_created,
                            "title": "Note Created",
                            "description": note.get("content", "")[:100] + "..." if len(note.get("content", "")) > 100 else note.get("content", ""),
                            "metadata": {"note_id": note_id},
                        })

                    n_updated = note.get("updated_at")
                    if n_updated and n_updated != n_created:
                        update_hash = hash(f"{note_id}_{n_updated}") % 10000
                        events.append({
                            "id": f"note_updated_{note_id}_{n_updated}_{update_hash}",
                            "type": "note_updated",
                            "thread": "Notes",
                            "date": n_updated,
                            "title": "Note Updated",
                            "description": "Note was updated",
                            "metadata": {"note_id": note_id},
                        })

        # 5. Attached snapshots
        if attached_snapshot_ids:
            all_snapshots = snapshot_storage.get_all()
            for snapshot_id, snapshot in all_snapshots.items():
                if snapshot_id in attached_snapshot_ids:
                    s_created = snapshot.get("created_at") or snapshot.get("timestamp")
                    if s_created:
                        events.append({
                            "id": f"snapshot_{snapshot_id}",
                            "type": "snapshot_created",
                            "thread": "Snapshots",
                            "date": s_created,
                            "title": f"Snapshot Created: {snapshot.get('name', 'Untitled')}",
                            "description": snapshot.get("notes", "") or snapshot.get("description", ""),
                            "metadata": {"snapshot_id": snapshot_id},
                        })

        # 6. Attached documents
        if attached_document_ids:
            from services.evidence_db_storage import EvidenceDBStorage
            with get_background_session() as ev_db:
                evidence_files = EvidenceDBStorage.list_files(ev_db, case_id=uuid.UUID(case_id))
                for evidence in evidence_files:
                    if str(evidence.id) in attached_document_ids:
                        uploaded_at = evidence.created_at.isoformat() if evidence.created_at else None
                        if uploaded_at:
                            events.append({
                                "id": f"document_upload_{evidence.id}",
                                "type": "document_uploaded",
                                "thread": "Documents",
                                "date": uploaded_at,
                                "title": f"Document Uploaded: {evidence.original_filename or 'Unknown'}",
                                "description": f"Case document uploaded: {evidence.original_filename or 'Unknown'}",
                                "metadata": {"evidence_id": str(evidence.id), "filename": evidence.original_filename},
                            })

                        if evidence.status == "processed" and evidence.processed_at:
                            events.append({
                                "id": f"document_processed_{evidence.id}",
                                "type": "document_processed",
                                "thread": "Documents",
                                "date": evidence.processed_at.isoformat(),
                                "title": f"Document Processed: {evidence.original_filename or 'Unknown'}",
                                "description": f"Processing completed for {evidence.original_filename or 'Unknown'}",
                                "metadata": {"evidence_id": str(evidence.id), "filename": evidence.original_filename},
                            })

        # 7. Attached tasks
        if attached_task_ids:
            tasks = self.get_tasks(case_id)
            for task in tasks:
                if task.get("task_id") in attached_task_ids:
                    t_created = task.get("created_at")
                    if t_created:
                        events.append({
                            "id": f"task_created_{task.get('task_id')}",
                            "type": "task_created",
                            "thread": "Tasks",
                            "date": t_created,
                            "title": f"Task Created: {task.get('title', 'Untitled')}",
                            "description": task.get("description", ""),
                            "metadata": {"task_id": task.get("task_id"), "priority": task.get("priority")},
                        })

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

                    status = task.get("status")
                    status_text = task.get("status_text")
                    if status or status_text:
                        t_updated = task.get("updated_at")
                        if t_updated and t_updated != t_created:
                            status_hash = hash(f"{status}_{status_text}_{t_updated}") % 10000
                            events.append({
                                "id": f"task_status_{task.get('task_id')}_{t_updated}_{status_hash}",
                                "type": "task_status_change",
                                "thread": "Tasks",
                                "date": t_updated,
                                "title": f"Task Status: {status_text or status}",
                                "description": f"Task '{task.get('title', 'Untitled')}' status changed",
                                "metadata": {"task_id": task.get("task_id"), "status": status, "status_text": status_text},
                            })

        events.sort(key=lambda x: x.get("date", ""))
        return events


# Singleton instance
workspace_service = WorkspaceService()
