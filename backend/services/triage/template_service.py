"""
Template Service

Save and load triage workflow templates.
A template captures the custom stages (processor name, config, file_filter)
from an existing case so they can be re-applied to new cases.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional

from config import BASE_DIR

logger = __import__("logging").getLogger(__name__)

DATA_DIR = BASE_DIR / "data"
TEMPLATES_FILE = DATA_DIR / "triage_templates.json"


def _load() -> List[Dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TEMPLATES_FILE.exists():
        return []
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(templates: List[Dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TEMPLATES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)
    tmp.replace(TEMPLATES_FILE)


class TemplateService:
    """Manages triage workflow templates."""

    def __init__(self):
        self._templates: List[Dict] = _load()
        self._lock = RLock()

    def save_template(
        self,
        case_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
    ) -> Dict:
        """
        Save a template from an existing triage case's custom stages.

        Args:
            case_id: Source triage case ID
            name: Template name
            description: Template description
            created_by: User who created the template

        Returns:
            The created template dict
        """
        from services.triage.triage_storage import triage_storage

        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        # Extract custom stages
        custom_stages = []
        for stage in case.get("stages", []):
            if stage.get("type") == "custom":
                custom_stages.append({
                    "name": stage.get("name"),
                    "processor_name": stage.get("config", {}).get("processor_name"),
                    "config": stage.get("config", {}).get("config", {}),
                    "file_filter": stage.get("config", {}).get("file_filter", {}),
                })

        if not custom_stages:
            raise ValueError("No custom stages to save as template")

        template = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "created_by": created_by,
            "created_at": datetime.now().isoformat(),
            "stages": custom_stages,
        }

        with self._lock:
            self._templates.append(template)
            _save(self._templates)

        return template

    def list_templates(self) -> List[Dict]:
        """List all templates with summary info."""
        with self._lock:
            return [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "created_by": t.get("created_by", ""),
                    "created_at": t.get("created_at", ""),
                    "stage_count": len(t.get("stages", [])),
                    "stages": [
                        {"name": s["name"], "processor_name": s["processor_name"]}
                        for s in t.get("stages", [])
                    ],
                }
                for t in sorted(
                    self._templates,
                    key=lambda t: t.get("created_at", ""),
                    reverse=True,
                )
            ]

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get a template by ID."""
        with self._lock:
            for t in self._templates:
                if t.get("id") == template_id:
                    return t
            return None

    def apply_template(self, template_id: str, case_id: str) -> List[Dict]:
        """
        Apply a template's stages to a triage case.

        Args:
            template_id: Template to apply
            case_id: Target triage case

        Returns:
            List of created stage dicts
        """
        from services.triage.triage_storage import triage_storage

        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        created_stages = []
        for stage_def in template.get("stages", []):
            stage = triage_storage.add_stage(
                case_id,
                name=stage_def["name"],
                stage_type="custom",
                config={
                    "processor_name": stage_def["processor_name"],
                    "config": stage_def.get("config", {}),
                    "file_filter": stage_def.get("file_filter", {}),
                },
            )
            if stage:
                created_stages.append(stage)

        return created_stages

    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        with self._lock:
            before = len(self._templates)
            self._templates = [
                t for t in self._templates if t.get("id") != template_id
            ]
            if len(self._templates) < before:
                _save(self._templates)
                return True
            return False


# Singleton
template_service = TemplateService()
