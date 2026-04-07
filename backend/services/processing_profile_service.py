from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.processing_profile import CaseProcessingConfig, ProcessingProfile


def normalize_instruction_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        instruction = str(item or "").strip()
        if not instruction:
            continue
        key = instruction.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(instruction)
    return normalized


def normalize_special_entity_types(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized_item = {"name": name}
        description = str(item.get("description", "")).strip()
        if description:
            normalized_item["description"] = description
        normalized.append(normalized_item)
    return normalized


def merge_special_entity_types(*lists: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for special_entity_types in lists:
        for item in normalize_special_entity_types(special_entity_types):
            merged[item["name"].strip().lower()] = item
    return list(merged.values())


def merge_instruction_lists(*lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for instruction_list in lists:
        for instruction in normalize_instruction_list(instruction_list):
            key = instruction.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(instruction)
    return merged


def list_processing_profiles(db: Session) -> list[ProcessingProfile]:
    return list(
        db.scalars(select(ProcessingProfile).order_by(ProcessingProfile.name)).all()
    )


def get_processing_profile(db: Session, profile_name: str) -> ProcessingProfile | None:
    return db.scalars(
        select(ProcessingProfile).where(ProcessingProfile.name == profile_name)
    ).first()


def save_processing_profile(
    db: Session,
    *,
    name: str,
    description: str | None,
    context_instructions: str | None,
    mandatory_instructions: list[str] | None,
    special_entity_types: list[dict[str, str]] | None,
) -> ProcessingProfile:
    profile = get_processing_profile(db, name)
    if profile is None:
        profile = ProcessingProfile(name=name)
        db.add(profile)

    profile.description = description
    profile.context_instructions = context_instructions
    profile.mandatory_instructions = normalize_instruction_list(mandatory_instructions)
    profile.special_entity_types = normalize_special_entity_types(special_entity_types)
    db.flush()
    return profile


def delete_processing_profile(db: Session, profile_name: str) -> bool:
    profile = get_processing_profile(db, profile_name)
    if profile is None:
        return False
    db.delete(profile)
    db.flush()
    return True


def get_case_processing_config(
    db: Session, case_id: uuid.UUID
) -> CaseProcessingConfig | None:
    return db.get(CaseProcessingConfig, case_id)


def get_or_create_case_processing_config(
    db: Session, case_id: uuid.UUID
) -> CaseProcessingConfig:
    config = db.get(CaseProcessingConfig, case_id)
    if config is None:
        if db.get(Case, case_id) is None:
            raise ValueError(f"Case {case_id} not found")
        config = CaseProcessingConfig(case_id=case_id)
        db.add(config)
        db.flush()
    return config


def upsert_case_processing_config(
    db: Session,
    *,
    case_id: uuid.UUID,
    source_profile_name: str | None,
    context_instructions: str | None,
    mandatory_instructions: list[str] | None,
    special_entity_types: list[dict[str, str]] | None,
) -> CaseProcessingConfig:
    config = get_or_create_case_processing_config(db, case_id)

    source_profile = None
    if source_profile_name:
        source_profile = get_processing_profile(db, source_profile_name)
        if source_profile is None:
            raise ValueError(f"Profile '{source_profile_name}' not found")

    config.source_profile_id = source_profile.id if source_profile else None
    config.source_profile_name_snapshot = source_profile.name if source_profile else None
    config.context_instructions = context_instructions
    config.mandatory_instructions = normalize_instruction_list(mandatory_instructions)
    config.special_entity_types = normalize_special_entity_types(special_entity_types)
    db.flush()
    return config


def copy_profile_to_case_config(
    db: Session,
    *,
    case_id: uuid.UUID,
    source_profile_name: str,
) -> CaseProcessingConfig:
    profile = get_processing_profile(db, source_profile_name)
    if profile is None:
        raise ValueError(f"Profile '{source_profile_name}' not found")

    config = get_or_create_case_processing_config(db, case_id)
    config.source_profile_id = profile.id
    config.source_profile_name_snapshot = profile.name
    config.context_instructions = profile.context_instructions
    config.mandatory_instructions = normalize_instruction_list(profile.mandatory_instructions)
    config.special_entity_types = normalize_special_entity_types(profile.special_entity_types)
    db.flush()
    return config
