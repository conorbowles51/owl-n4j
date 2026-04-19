"""
Triage Case Storage

Lightweight JSON-backed storage for triage case metadata and stage orchestration state.
File inventory and artifacts live in Neo4j; this stores only orchestration state.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from threading import RLock

from config import BASE_DIR


DATA_DIR = BASE_DIR / "data"
STORAGE_FILE = DATA_DIR / "triage_cases.json"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_cases() -> List[Dict]:
    _ensure_dir()
    if not STORAGE_FILE.exists():
        return []
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_cases(cases: List[Dict]) -> None:
    _ensure_dir()
    tmp = STORAGE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)
    tmp.replace(STORAGE_FILE)


class TriageStorage:
    """JSON-file backed storage for triage case orchestration state. Thread-safe."""

    def __init__(self) -> None:
        self._cases: List[Dict] = _load_cases()
        self._lock = RLock()

    def reload(self) -> None:
        with self._lock:
            self._cases = _load_cases()

    def _persist(self) -> None:
        _save_cases(self._cases)

    # ── Case CRUD ──────────────────────────────────────────────────────

    def create_case(
        self,
        *,
        name: str,
        description: str = "",
        source_path: str,
        created_by: str,
    ) -> Dict:
        with self._lock:
            case_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            case = {
                "id": case_id,
                "name": name,
                "description": description,
                "source_path": source_path,
                "status": "created",
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
                "stages": [
                    _make_stage(0, "Scan", "scan"),
                    _make_stage(1, "Classify", "classify"),
                    _make_stage(2, "Profile", "profile"),
                ],
                "scan_cursor": None,
                "scan_stats": {
                    "total_files": 0,
                    "total_size": 0,
                    "os_detected": None,
                },
            }

            self._cases.append(case)
            self._persist()
            return case

    def get_case(self, case_id: str) -> Optional[Dict]:
        with self._lock:
            for c in self._cases:
                if c.get("id") == case_id:
                    return c
            return None

    def update_case(self, case_id: str, **updates) -> Optional[Dict]:
        with self._lock:
            case = None
            for c in self._cases:
                if c.get("id") == case_id:
                    case = c
                    break
            if not case:
                return None

            for key, val in updates.items():
                if key == "scan_stats" and isinstance(val, dict):
                    case.setdefault("scan_stats", {}).update(val)
                elif key == "stages":
                    case["stages"] = val
                else:
                    case[key] = val

            case["updated_at"] = datetime.now().isoformat()
            self._persist()
            return case

    def list_cases(self, owner: Optional[str] = None) -> List[Dict]:
        with self._lock:
            cases = self._cases.copy()
            if owner:
                cases = [c for c in cases if c.get("created_by") == owner]
            return sorted(cases, key=lambda c: c.get("created_at", ""), reverse=True)

    def delete_case(self, case_id: str) -> bool:
        with self._lock:
            before = len(self._cases)
            self._cases = [c for c in self._cases if c.get("id") != case_id]
            if len(self._cases) < before:
                self._persist()
                return True
            return False

    # ── Stage helpers ──────────────────────────────────────────────────

    def get_stage(self, case_id: str, stage_id: str) -> Optional[Dict]:
        case = self.get_case(case_id)
        if not case:
            return None
        for s in case.get("stages", []):
            if s.get("id") == stage_id:
                return s
        return None

    def update_stage(self, case_id: str, stage_id: str, **updates) -> Optional[Dict]:
        with self._lock:
            case = None
            for c in self._cases:
                if c.get("id") == case_id:
                    case = c
                    break
            if not case:
                return None

            for stage in case.get("stages", []):
                if stage.get("id") == stage_id:
                    for key, val in updates.items():
                        stage[key] = val
                    case["updated_at"] = datetime.now().isoformat()
                    self._persist()
                    return stage
            return None

    def add_stage(
        self,
        case_id: str,
        *,
        name: str,
        stage_type: str = "custom",
        config: Optional[Dict] = None,
    ) -> Optional[Dict]:
        with self._lock:
            case = None
            for c in self._cases:
                if c.get("id") == case_id:
                    case = c
                    break
            if not case:
                return None

            order = len(case.get("stages", []))
            stage = _make_stage(order, name, stage_type, config)
            case.setdefault("stages", []).append(stage)
            case["updated_at"] = datetime.now().isoformat()
            self._persist()
            return stage

    def remove_stage(self, case_id: str, stage_id: str) -> bool:
        with self._lock:
            case = None
            for c in self._cases:
                if c.get("id") == case_id:
                    case = c
                    break
            if not case:
                return False

            before = len(case.get("stages", []))
            case["stages"] = [
                s for s in case.get("stages", []) if s.get("id") != stage_id
            ]
            if len(case["stages"]) < before:
                # Re-number order
                for i, s in enumerate(case["stages"]):
                    s["order"] = i
                case["updated_at"] = datetime.now().isoformat()
                self._persist()
                return True
            return False


def _make_stage(
    order: int,
    name: str,
    stage_type: str,
    config: Optional[Dict] = None,
) -> Dict:
    return {
        "id": str(uuid.uuid4()),
        "order": order,
        "name": name,
        "type": stage_type,
        "status": "pending",
        "config": config or {},
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "files_total": 0,
        "files_processed": 0,
        "files_failed": 0,
        "error": None,
    }


# Singleton
triage_storage = TriageStorage()
