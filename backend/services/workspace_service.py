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
    WorkspaceFinding,
    WorkspacePinnedItem,
    WorkspaceDeadlineConfig,
)


class WorkspaceService:
    """Service for managing workspace data backed by PostgreSQL."""

    def reload(self):
        """No-op — data is always fresh from the database."""
        pass

    @staticmethod
    def _iso_to_ts(value: Optional[str]) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _safe_date_sort(event: Dict[str, Any]) -> tuple[str, str]:
        return (event.get("date") or "", event.get("id") or "")

    @staticmethod
    def _is_case_document_filename(filename: Optional[str]) -> bool:
        lower = (filename or "").lower()
        if lower.startswith("note_") and lower.endswith(".txt"):
            return True
        if lower.startswith("link_") or lower.endswith("_link.txt"):
            return True
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"]
        if any(lower.endswith(ext) for ext in image_extensions):
            return True
        doc_extensions = [".pdf", ".doc", ".docx", ".txt", ".rtf"]
        if any(lower.endswith(ext) for ext in doc_extensions):
            is_simple_name = len(lower.split(".")) == 2
            has_quick_action_pattern = lower.startswith("note_") or lower.startswith("link_")
            return is_simple_name or has_quick_action_pattern
        return False

    def _list_evidence_records(self, case_id: str):
        from services.evidence_db_storage import EvidenceDBStorage

        try:
            case_uuid = uuid.UUID(case_id)
        except ValueError:
            return []

        with get_background_session() as db:
            return EvidenceDBStorage.list_files(db, case_id=case_uuid)

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
    # Findings
    # ------------------------------------------------------------------ #

    def get_findings(self, case_id: str) -> List[Dict]:
        with get_background_session() as db:
            rows = db.execute(
                select(WorkspaceFinding).where(WorkspaceFinding.case_id == case_id)
            ).scalars().all()
            findings = [dict(r.data) for r in rows]

        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted(
            findings,
            key=lambda finding: (
                priority_order.get((finding.get("priority") or "MEDIUM").upper(), 1),
                -self._iso_to_ts(finding.get("updated_at")),
            ),
        )

    def get_finding(self, case_id: str, finding_id: str) -> Optional[Dict]:
        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceFinding).where(
                    WorkspaceFinding.case_id == case_id,
                    WorkspaceFinding.finding_id == finding_id,
                )
            ).scalar_one_or_none()
            return dict(row.data) if row else None

    def save_finding(self, case_id: str, finding: Dict) -> str:
        finding_id = finding.get("finding_id") or f"finding_{uuid.uuid4().hex[:12]}"
        finding["finding_id"] = finding_id
        finding["case_id"] = case_id
        finding["updated_at"] = datetime.now().isoformat()
        if "created_at" not in finding:
            finding["created_at"] = datetime.now().isoformat()

        with get_background_session() as db:
            row = db.execute(
                select(WorkspaceFinding).where(
                    WorkspaceFinding.case_id == case_id,
                    WorkspaceFinding.finding_id == finding_id,
                )
            ).scalar_one_or_none()
            if row:
                row.data = finding
            else:
                db.add(
                    WorkspaceFinding(
                        case_id=case_id,
                        finding_id=finding_id,
                        data=finding,
                    )
                )
        return finding_id

    def delete_finding(self, case_id: str, finding_id: str) -> bool:
        with get_background_session() as db:
            result = db.execute(
                delete(WorkspaceFinding).where(
                    WorkspaceFinding.case_id == case_id,
                    WorkspaceFinding.finding_id == finding_id,
                )
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------ #
    # Investigation Timeline (read-only aggregation)
    # ------------------------------------------------------------------ #

    def get_investigation_timeline(self, case_id: str) -> List[Dict]:
        """Aggregate timeline events from workspace tables, evidence, and system logs."""
        from services.system_log_service import LogType, system_log_service

        events: List[Dict[str, Any]] = []

        for witness in self.get_witnesses(case_id):
            witness_id = witness.get("witness_id")
            witness_name = witness.get("name", "Unknown")
            created_at = witness.get("created_at") or witness.get("added_at")
            if created_at:
                events.append({
                    "id": f"witness_created_{witness_id}",
                    "type": "witness_created",
                    "thread": "Witnesses",
                    "date": created_at,
                    "title": f"Witness Added: {witness_name}",
                    "description": f"Witness {witness_name} added to case",
                    "metadata": {"witness_id": witness_id},
                })
            for idx, interview in enumerate(witness.get("interviews") or []):
                interview_date = interview.get("interview_date") or interview.get("date") or interview.get("scheduled_date")
                if not interview_date:
                    continue
                interview_id = interview.get("interview_id") or f"interview_{idx}"
                events.append({
                    "id": f"witness_interview_{witness_id}_{interview_id}",
                    "type": "witness_interview",
                    "thread": "Witnesses",
                    "date": interview_date,
                    "title": f"Interview: {witness_name}",
                    "description": interview.get("statement") or interview.get("summary") or f"Interview with {witness_name}",
                    "metadata": {"witness_id": witness_id, "interview_id": interview_id},
                })

        for task in self.get_tasks(case_id):
            task_id = task.get("task_id")
            created_at = task.get("created_at")
            if created_at:
                events.append({
                    "id": f"task_created_{task_id}",
                    "type": "task_created",
                    "thread": "Tasks",
                    "date": created_at,
                    "title": f"Task Created: {task.get('title', 'Untitled')}",
                    "description": task.get("description", ""),
                    "metadata": {"task_id": task_id, "priority": task.get("priority")},
                })
            due_date = task.get("due_date")
            if due_date:
                events.append({
                    "id": f"task_due_{task_id}",
                    "type": "task_due",
                    "thread": "Tasks",
                    "date": due_date,
                    "title": f"Task Due: {task.get('title', 'Untitled')}",
                    "description": f"Due date for task: {task.get('title', 'Untitled')}",
                    "metadata": {"task_id": task_id},
                })
            updated_at = task.get("updated_at")
            if updated_at and updated_at != created_at and (task.get("status") or task.get("status_text")):
                events.append({
                    "id": f"task_status_{task_id}_{updated_at}",
                    "type": "task_status_change",
                    "thread": "Tasks",
                    "date": updated_at,
                    "title": f"Task Status: {task.get('status_text') or task.get('status')}",
                    "description": f"Task '{task.get('title', 'Untitled')}' status changed",
                    "metadata": {"task_id": task_id, "status": task.get("status")},
                })

        for theory in self.get_theories(case_id, user_role="attorney"):
            theory_id = theory.get("theory_id")
            created_at = theory.get("created_at")
            if created_at:
                events.append({
                    "id": f"theory_created_{theory_id}",
                    "type": "theory_created",
                    "thread": "Theories",
                    "date": created_at,
                    "title": f"Theory Created: {theory.get('title', 'Untitled')}",
                    "description": theory.get("hypothesis", ""),
                    "metadata": {"theory_id": theory_id},
                })
            updated_at = theory.get("updated_at")
            if updated_at and updated_at != created_at:
                events.append({
                    "id": f"theory_updated_{theory_id}_{updated_at}",
                    "type": "theory_updated",
                    "thread": "Theories",
                    "date": updated_at,
                    "title": f"Theory Updated: {theory.get('title', 'Untitled')}",
                    "description": f"Theory '{theory.get('title', 'Untitled')}' was updated",
                    "metadata": {"theory_id": theory_id},
                })

        for finding in self.get_findings(case_id):
            finding_id = finding.get("finding_id")
            created_at = finding.get("created_at")
            if created_at:
                events.append({
                    "id": f"finding_created_{finding_id}",
                    "type": "finding_created",
                    "thread": "Findings",
                    "date": created_at,
                    "title": f"Finding Added: {finding.get('title', 'Untitled')}",
                    "description": finding.get("content", ""),
                    "metadata": {"finding_id": finding_id, "priority": finding.get("priority")},
                })
            updated_at = finding.get("updated_at")
            if updated_at and updated_at != created_at:
                events.append({
                    "id": f"finding_updated_{finding_id}_{updated_at}",
                    "type": "finding_updated",
                    "thread": "Findings",
                    "date": updated_at,
                    "title": f"Finding Updated: {finding.get('title', 'Untitled')}",
                    "description": f"Finding '{finding.get('title', 'Untitled')}' was updated",
                    "metadata": {"finding_id": finding_id},
                })

        for note in self.get_notes(case_id):
            note_id = note.get("note_id")
            created_at = note.get("created_at")
            if created_at:
                events.append({
                    "id": f"note_created_{note_id}",
                    "type": "note_created",
                    "thread": "Notes",
                    "date": created_at,
                    "title": f"Note Created: {note.get('title', 'Untitled')}",
                    "description": note.get("content", ""),
                    "metadata": {"note_id": note_id},
                })
            updated_at = note.get("updated_at")
            if updated_at and updated_at != created_at:
                events.append({
                    "id": f"note_updated_{note_id}_{updated_at}",
                    "type": "note_updated",
                    "thread": "Notes",
                    "date": updated_at,
                    "title": f"Note Updated: {note.get('title', 'Untitled')}",
                    "description": f"Note '{note.get('title', 'Untitled')}' was updated",
                    "metadata": {"note_id": note_id},
                })

        for pinned in self.get_pinned_items(case_id):
            pinned_at = pinned.get("pinned_at") or pinned.get("created_at")
            if pinned_at:
                item_type = pinned.get("item_type") or "item"
                events.append({
                    "id": f"pinned_{pinned.get('pin_id')}",
                    "type": "item_pinned",
                    "thread": "Pinned Evidence",
                    "date": pinned_at,
                    "title": f"{item_type.title()} Pinned",
                    "description": f"{item_type.title()} pinned to workspace",
                    "metadata": {"pin_id": pinned.get("pin_id"), "item_type": item_type, "item_id": pinned.get("item_id")},
                })

        evidence_files = self._list_evidence_records(case_id)
        for evidence in evidence_files:
            evidence_id = str(evidence.id)
            filename = evidence.original_filename or "Unknown"
            thread = "Documents" if self._is_case_document_filename(filename) or getattr(evidence, "upload_method", None) == "quick_action" else "Case Files"
            uploaded_at = evidence.created_at.isoformat() if evidence.created_at else None
            if uploaded_at:
                events.append({
                    "id": f"{thread.lower().replace(' ', '_')}_uploaded_{evidence_id}",
                    "type": "document_uploaded" if thread == "Documents" else "evidence_uploaded",
                    "thread": thread,
                    "date": uploaded_at,
                    "title": f"{'Document' if thread == 'Documents' else 'Evidence'} Uploaded: {filename}",
                    "description": f"File uploaded: {filename}",
                    "metadata": {"evidence_id": evidence_id, "filename": filename},
                })
            if evidence.status == "processed" and evidence.processed_at:
                events.append({
                    "id": f"{thread.lower().replace(' ', '_')}_processed_{evidence_id}",
                    "type": "document_processed" if thread == "Documents" else "evidence_processed",
                    "thread": thread,
                    "date": evidence.processed_at.isoformat(),
                    "title": f"{'Document' if thread == 'Documents' else 'Evidence'} Processed: {filename}",
                    "description": f"Processing completed for {filename}",
                    "metadata": {"evidence_id": evidence_id, "filename": filename},
                })

        deadline_config = self.get_deadline_config(case_id)
        if deadline_config:
            trial_date = deadline_config.get("trial_date")
            if trial_date:
                events.append({
                    "id": f"deadline_trial_{case_id}",
                    "type": "trial_date",
                    "thread": "Deadlines",
                    "date": trial_date,
                    "title": "Trial Date",
                    "description": deadline_config.get("trial_court") or deadline_config.get("court") or "Trial scheduled",
                    "metadata": {"court": deadline_config.get("trial_court") or deadline_config.get("court"), "judge": deadline_config.get("judge")},
                })
            for idx, deadline in enumerate(deadline_config.get("deadlines") or []):
                due_date = deadline.get("due_date") or deadline.get("date")
                if not due_date:
                    continue
                deadline_id = deadline.get("deadline_id") or f"deadline_{idx}"
                events.append({
                    "id": f"deadline_{deadline_id}",
                    "type": "deadline",
                    "thread": "Deadlines",
                    "date": due_date,
                    "title": f"Deadline: {deadline.get('title', 'Untitled')}",
                    "description": deadline.get("notes") or deadline.get("title", ""),
                    "metadata": {"deadline_id": deadline_id},
                })

        try:
            system_logs = system_log_service.get_logs(
                log_types=[LogType.CASE_OPERATION, LogType.CASE_MANAGEMENT],
                limit=500,
            )
            for idx, log in enumerate(system_logs.get("logs", [])):
                details = log.get("details", {})
                if details.get("case_id") != case_id:
                    continue
                timestamp = log.get("timestamp")
                if not timestamp:
                    continue
                events.append({
                    "id": f"log_{idx}_{timestamp}",
                    "type": "system_action",
                    "thread": "System Actions",
                    "date": timestamp,
                    "title": log.get("action", "System Action"),
                    "description": log.get("action", ""),
                    "metadata": {"user": log.get("user"), "success": log.get("success"), "details": details},
                })
        except Exception as e:
            print(f"[Investigation Timeline] Error loading system logs: {e}")

        events.sort(key=self._safe_date_sort)
        return events

    # ------------------------------------------------------------------ #
    # Theory Timeline
    # ------------------------------------------------------------------ #

    def get_theory_timeline(self, case_id: str, theory_id: str) -> List[Dict]:
        """Get timeline events for a theory and its attached items."""
        events: List[Dict[str, Any]] = []
        theory = self.get_theory(case_id, theory_id)
        if not theory:
            return events

        attached_evidence_ids = set(theory.get("attached_evidence_ids") or [])
        attached_witness_ids = set(theory.get("attached_witness_ids") or [])
        attached_note_ids = set(theory.get("attached_note_ids") or [])
        attached_document_ids = set(theory.get("attached_document_ids") or [])
        attached_task_ids = set(theory.get("attached_task_ids") or [])

        created_at = theory.get("created_at")
        if created_at:
            events.append({
                "id": f"theory_created_{theory_id}",
                "type": "theory_created",
                "thread": "Theory",
                "date": created_at,
                "title": f"Theory Created: {theory.get('title', 'Untitled')}",
                "description": theory.get("hypothesis", ""),
                "metadata": {"theory_id": theory_id},
            })
        updated_at = theory.get("updated_at")
        if updated_at and updated_at != created_at:
            events.append({
                "id": f"theory_updated_{theory_id}_{updated_at}",
                "type": "theory_updated",
                "thread": "Theory",
                "date": updated_at,
                "title": f"Theory Updated: {theory.get('title', 'Untitled')}",
                "description": f"Theory '{theory.get('title', 'Untitled')}' was updated",
                "metadata": {"theory_id": theory_id},
            })

        for witness in self.get_witnesses(case_id):
            witness_id = witness.get("witness_id")
            if witness_id not in attached_witness_ids:
                continue
            witness_name = witness.get("name", "Unknown")
            witness_created = witness.get("created_at") or witness.get("added_at")
            if witness_created:
                events.append({
                    "id": f"witness_created_{witness_id}",
                    "type": "witness_created",
                    "thread": "Witnesses",
                    "date": witness_created,
                    "title": f"Witness Added: {witness_name}",
                    "description": f"Witness {witness_name} added to theory",
                    "metadata": {"witness_id": witness_id},
                })
            for idx, interview in enumerate(witness.get("interviews") or []):
                interview_date = interview.get("interview_date") or interview.get("date") or interview.get("scheduled_date")
                if not interview_date:
                    continue
                interview_id = interview.get("interview_id") or f"interview_{idx}"
                events.append({
                    "id": f"witness_interview_{witness_id}_{interview_id}",
                    "type": "witness_interview",
                    "thread": "Witnesses",
                    "date": interview_date,
                    "title": f"Interview: {witness_name}",
                    "description": interview.get("statement") or interview.get("summary") or f"Interview with {witness_name}",
                    "metadata": {"witness_id": witness_id, "interview_id": interview_id},
                })

        for note in self.get_notes(case_id):
            note_id = note.get("note_id")
            if note_id not in attached_note_ids:
                continue
            note_created = note.get("created_at")
            if note_created:
                events.append({
                    "id": f"note_created_{note_id}",
                    "type": "note_created",
                    "thread": "Notes",
                    "date": note_created,
                    "title": f"Note Created: {note.get('title', 'Untitled')}",
                    "description": note.get("content", ""),
                    "metadata": {"note_id": note_id},
                })
            note_updated = note.get("updated_at")
            if note_updated and note_updated != note_created:
                events.append({
                    "id": f"note_updated_{note_id}_{note_updated}",
                    "type": "note_updated",
                    "thread": "Notes",
                    "date": note_updated,
                    "title": f"Note Updated: {note.get('title', 'Untitled')}",
                    "description": "Note was updated",
                    "metadata": {"note_id": note_id},
                })

        for task in self.get_tasks(case_id):
            task_id = task.get("task_id")
            if task_id not in attached_task_ids:
                continue
            task_created = task.get("created_at")
            if task_created:
                events.append({
                    "id": f"task_created_{task_id}",
                    "type": "task_created",
                    "thread": "Tasks",
                    "date": task_created,
                    "title": f"Task Created: {task.get('title', 'Untitled')}",
                    "description": task.get("description", ""),
                    "metadata": {"task_id": task_id},
                })
            due_date = task.get("due_date")
            if due_date:
                events.append({
                    "id": f"task_due_{task_id}",
                    "type": "task_due",
                    "thread": "Tasks",
                    "date": due_date,
                    "title": f"Task Due: {task.get('title', 'Untitled')}",
                    "description": f"Due date for task: {task.get('title', 'Untitled')}",
                    "metadata": {"task_id": task_id},
                })

        for evidence in self._list_evidence_records(case_id):
            evidence_id = str(evidence.id)
            filename = evidence.original_filename or "Unknown"
            is_document = evidence_id in attached_document_ids
            is_evidence = evidence_id in attached_evidence_ids
            if not (is_document or is_evidence):
                continue
            thread = "Documents" if is_document else "Evidence"
            uploaded_at = evidence.created_at.isoformat() if evidence.created_at else None
            if uploaded_at:
                events.append({
                    "id": f"{thread.lower()}_uploaded_{evidence_id}",
                    "type": "document_uploaded" if is_document else "evidence_uploaded",
                    "thread": thread,
                    "date": uploaded_at,
                    "title": f"{'Document' if is_document else 'Evidence'} Uploaded: {filename}",
                    "description": f"File uploaded: {filename}",
                    "metadata": {"evidence_id": evidence_id, "filename": filename},
                })
            if evidence.status == "processed" and evidence.processed_at:
                events.append({
                    "id": f"{thread.lower()}_processed_{evidence_id}",
                    "type": "document_processed" if is_document else "evidence_processed",
                    "thread": thread,
                    "date": evidence.processed_at.isoformat(),
                    "title": f"{'Document' if is_document else 'Evidence'} Processed: {filename}",
                    "description": f"Processing completed for {filename}",
                    "metadata": {"evidence_id": evidence_id, "filename": filename},
                })

        events.sort(key=self._safe_date_sort)
        return events


# Singleton instance
workspace_service = WorkspaceService()
