from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from postgres.models.case_context import (
    CaseContext,
    CaseContextTemplate,
    CaseContextTemplateField,
    CaseContextValue,
    CaseMandateVersion,
)
from postgres.models.case_profile import CaseProfile
from postgres.models.user import User


FIELD_TYPES = {
    "short_text", "long_text", "date", "number", "boolean",
    "single_choice", "multiple_choice", "dossier_reference",
}
MANDATE_FIELDS = (
    "objective", "key_questions", "in_scope", "out_of_scope",
    "perspective", "success_criteria", "constraints",
)


class CaseContextValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedMandateContext:
    version: CaseMandateVersion | None
    override: dict[str, Any] | None
    block: str


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _serialize_version(version: CaseMandateVersion | None) -> dict[str, Any] | None:
    if not version:
        return None
    return {
        "id": str(version.id),
        "case_id": str(version.case_id),
        "version_number": version.version_number,
        "objective": version.objective,
        "key_questions": version.key_questions or [],
        "in_scope": version.in_scope,
        "out_of_scope": version.out_of_scope,
        "perspective": version.perspective,
        "success_criteria": version.success_criteria,
        "constraints": version.constraints,
        "author_user_id": str(version.author_user_id) if version.author_user_id else None,
        "author_name": version.author.name if version.author else None,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


class MandateContextService:
    def list_templates(self, db: Session) -> list[dict[str, Any]]:
        rows = (
            db.query(CaseContextTemplate)
            .options(joinedload(CaseContextTemplate.fields))
            .order_by(CaseContextTemplate.name)
            .all()
        )
        return [self._serialize_template(row) for row in rows]

    @staticmethod
    def _serialize_template(template: CaseContextTemplate) -> dict[str, Any]:
        return {
            "key": template.key,
            "name": template.name,
            "description": template.description,
            "is_builtin": template.is_builtin,
            "fields": [
                {
                    "key": field.field_key,
                    "label": field.label,
                    "type": field.field_type,
                    "choices": field.choices or [],
                    "required": field.required,
                    "position": field.position,
                }
                for field in sorted(template.fields, key=lambda item: (item.position, item.label))
            ],
        }

    def get_context(self, db: Session, *, case_id: UUID) -> dict[str, Any]:
        context = (
            db.query(CaseContext)
            .options(
                joinedload(CaseContext.values).joinedload(CaseContextValue.field),
                joinedload(CaseContext.active_mandate_version).joinedload(CaseMandateVersion.author),
            )
            .filter(CaseContext.case_id == case_id)
            .first()
        )
        templates = self.list_templates(db)
        if not context:
            return {
                "case_id": str(case_id), "case_summary": None, "background": None,
                "investigation_type": None, "jurisdiction": None,
                "active_template_key": "generic", "custom_values": {},
                "active_mandate": None, "mandate_complete": False,
                "templates": templates, "updated_at": None,
            }
        return {
            "case_id": str(context.case_id),
            "case_summary": context.case_summary,
            "background": context.background,
            "investigation_type": context.investigation_type,
            "jurisdiction": context.jurisdiction,
            "active_template_key": context.active_template_key,
            "custom_values": {value.field.field_key: value.value for value in context.values},
            "active_mandate": _serialize_version(context.active_mandate_version),
            "mandate_complete": context.active_mandate_version_id is not None,
            "templates": templates,
            "updated_at": context.updated_at.isoformat() if context.updated_at else None,
        }

    def update_context(
        self,
        db: Session,
        *,
        case_id: UUID,
        user: User,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        template_key = payload.get("active_template_key") or "generic"
        template = (
            db.query(CaseContextTemplate)
            .options(joinedload(CaseContextTemplate.fields))
            .filter(CaseContextTemplate.key == template_key)
            .first()
        )
        if not template:
            raise CaseContextValidationError("Unknown case-context template")

        context = db.query(CaseContext).filter(CaseContext.case_id == case_id).first()
        if not context:
            context = CaseContext(case_id=case_id, created_by_user_id=user.id)
            db.add(context)
            db.flush()
        context.case_summary = _clean_text(payload.get("case_summary"))
        context.background = _clean_text(payload.get("background"))
        context.investigation_type = _clean_text(payload.get("investigation_type"))
        context.jurisdiction = _clean_text(payload.get("jurisdiction"))
        context.active_template_key = template_key
        context.updated_by_user_id = user.id

        fields = {field.field_key: field for field in template.fields}
        supplied_values = payload.get("custom_values") or {}
        if not isinstance(supplied_values, dict):
            raise CaseContextValidationError("custom_values must be an object")
        unknown = sorted(set(supplied_values) - set(fields))
        if unknown:
            raise CaseContextValidationError(f"Fields do not belong to template {template_key}: {', '.join(unknown)}")

        db.query(CaseContextValue).filter(CaseContextValue.context_id == context.id).delete(
            synchronize_session=False
        )
        for key, field in fields.items():
            raw = supplied_values.get(key)
            if raw in (None, "", []):
                if field.required:
                    raise CaseContextValidationError(f"{field.label} is required")
                continue
            value = self._validate_field_value(db, case_id=case_id, field=field, value=raw)
            db.add(CaseContextValue(
                context_id=context.id, case_id=case_id, template_field_id=field.id, value=value,
            ))
        db.flush()
        return self.get_context(db, case_id=case_id)

    @staticmethod
    def _validate_field_value(
        db: Session, *, case_id: UUID, field: CaseContextTemplateField, value: Any
    ) -> Any:
        if field.field_type not in FIELD_TYPES:
            raise CaseContextValidationError(f"Unsupported field type: {field.field_type}")
        if field.field_type in {"short_text", "long_text"}:
            if not isinstance(value, str):
                raise CaseContextValidationError(f"{field.label} must be text")
            cleaned = value.strip()
            if field.field_type == "short_text" and len(cleaned) > 500:
                raise CaseContextValidationError(f"{field.label} must be 500 characters or fewer")
            return cleaned
        if field.field_type == "date":
            if not isinstance(value, str):
                raise CaseContextValidationError(f"{field.label} must be an ISO date")
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError as exc:
                raise CaseContextValidationError(f"{field.label} must be an ISO date") from exc
        if field.field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CaseContextValidationError(f"{field.label} must be a number")
            return value
        if field.field_type == "boolean":
            if not isinstance(value, bool):
                raise CaseContextValidationError(f"{field.label} must be true or false")
            return value
        choices = field.choices or []
        if field.field_type == "single_choice":
            if not isinstance(value, str) or value not in choices:
                raise CaseContextValidationError(f"{field.label} must be one of its configured choices")
            return value
        if field.field_type == "multiple_choice":
            if not isinstance(value, list) or any(not isinstance(item, str) or item not in choices for item in value):
                raise CaseContextValidationError(f"{field.label} contains an invalid choice")
            return list(dict.fromkeys(value))
        if field.field_type == "dossier_reference":
            try:
                dossier_id = UUID(str(value))
            except (TypeError, ValueError) as exc:
                raise CaseContextValidationError(f"{field.label} must reference a Dossier") from exc
            exists = db.query(CaseProfile.id).filter(
                CaseProfile.id == dossier_id, CaseProfile.case_id == case_id,
                CaseProfile.status != "deleted",
            ).first()
            if not exists:
                raise CaseContextValidationError(f"{field.label} must reference a Dossier in this case")
            return str(dossier_id)
        raise CaseContextValidationError(f"Unsupported field type: {field.field_type}")

    def create_version(
        self,
        db: Session,
        *,
        case_id: UUID,
        user: User,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        cleaned = self.validate_override(payload, allow_empty=False)
        context = db.query(CaseContext).filter(CaseContext.case_id == case_id).first()
        if not context:
            context = CaseContext(case_id=case_id, active_template_key="generic", created_by_user_id=user.id)
            db.add(context)
            db.flush()
        current = db.query(func.max(CaseMandateVersion.version_number)).filter(
            CaseMandateVersion.case_id == case_id
        ).scalar() or 0
        version = CaseMandateVersion(
            case_id=case_id, version_number=current + 1, author_user_id=user.id, **cleaned,
        )
        db.add(version)
        db.flush()
        context.active_mandate_version_id = version.id
        context.updated_by_user_id = user.id
        db.flush()
        db.refresh(version)
        return _serialize_version(version) or {}

    def list_versions(self, db: Session, *, case_id: UUID) -> list[dict[str, Any]]:
        rows = (
            db.query(CaseMandateVersion)
            .options(joinedload(CaseMandateVersion.author))
            .filter(CaseMandateVersion.case_id == case_id)
            .order_by(CaseMandateVersion.version_number.desc())
            .all()
        )
        return [_serialize_version(row) or {} for row in rows]

    def active_version(self, db: Session, *, case_id: UUID) -> CaseMandateVersion | None:
        context = db.query(CaseContext).filter(CaseContext.case_id == case_id).first()
        if not context or not context.active_mandate_version_id:
            return None
        return db.query(CaseMandateVersion).filter(
            CaseMandateVersion.id == context.active_mandate_version_id,
            CaseMandateVersion.case_id == case_id,
        ).first()

    def get_version(self, db: Session, *, case_id: UUID, version_id: UUID | None) -> CaseMandateVersion | None:
        if not version_id:
            return None
        if not isinstance(version_id, UUID):
            try:
                version_id = UUID(str(version_id))
            except (TypeError, ValueError):
                return None
        return db.query(CaseMandateVersion).filter(
            CaseMandateVersion.id == version_id, CaseMandateVersion.case_id == case_id
        ).first()

    def resolve(
        self,
        db: Session,
        *,
        case_id: UUID,
        version_id: UUID | None,
        override: dict[str, Any] | None = None,
    ) -> ResolvedMandateContext:
        version = self.get_version(db, case_id=case_id, version_id=version_id)
        normalized_override = self.validate_override(override, allow_empty=True) if override else None
        return ResolvedMandateContext(
            version=version,
            override=normalized_override,
            block=self.render(version=version, override=normalized_override),
        )

    @staticmethod
    def validate_override(payload: dict[str, Any] | None, *, allow_empty: bool) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CaseContextValidationError("Mandate must be an object")
        unknown = sorted(set(payload) - set(MANDATE_FIELDS))
        if unknown:
            raise CaseContextValidationError(f"Unknown mandate fields: {', '.join(unknown)}")
        cleaned: dict[str, Any] = {}
        for field in MANDATE_FIELDS:
            value = payload.get(field)
            if field == "key_questions":
                if value is None:
                    cleaned[field] = []
                elif not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise CaseContextValidationError("key_questions must be a list of text questions")
                else:
                    cleaned[field] = [item.strip() for item in value if item.strip()]
            else:
                cleaned[field] = _clean_text(value)
        if not allow_empty and not any(cleaned.get(field) for field in MANDATE_FIELDS):
            raise CaseContextValidationError("Add at least one meaningful mandate field")
        return cleaned

    @staticmethod
    def render(*, version: CaseMandateVersion | None, override: dict[str, Any] | None) -> str:
        if not version and not override:
            return ""
        base = {
            field: getattr(version, field, None) if version else ([] if field == "key_questions" else None)
            for field in MANDATE_FIELDS
        }
        if override:
            for key, value in override.items():
                if value not in (None, "", []):
                    base[key] = value
        labels = {
            "objective": "Objective", "key_questions": "Key questions", "in_scope": "In scope",
            "out_of_scope": "Out of scope", "perspective": "Perspective / posture",
            "success_criteria": "Expected output / success criteria",
            "constraints": "Constraints / special instructions",
        }
        lines = ["CASE MANDATE — investigator-authored working instructions, not evidence:"]
        if version:
            lines.append(f"Mandate version: {version.version_number} ({version.id})")
        if override:
            lines.append("Temporary request override is applied for this request only.")
        for key in MANDATE_FIELDS:
            value = base.get(key)
            if not value:
                continue
            if isinstance(value, list):
                rendered = "\n".join(f"  - {item}" for item in value)
                lines.append(f"{labels[key]}:\n{rendered}")
            else:
                lines.append(f"{labels[key]}: {value}")
        lines.append("Use balanced retrieval: actively look for both supporting and contradicting material. Cite evidence for factual claims.")
        return "\n".join(lines)

    def metadata(self, db: Session, *, case_id: UUID, version_id: UUID | None) -> dict[str, Any]:
        active = self.active_version(db, case_id=case_id)
        anchored = self.get_version(db, case_id=case_id, version_id=version_id)
        return {
            "version": _serialize_version(anchored),
            "active_version_id": str(active.id) if active else None,
            "active_version_number": active.version_number if active else None,
            "is_stale": bool(active and anchored and active.id != anchored.id),
            "is_incomplete": anchored is None,
        }


mandate_context_service = MandateContextService()
