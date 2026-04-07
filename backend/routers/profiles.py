"""
Profiles Router

DB-backed processing profile library used by cases as snapshot templates.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.session import get_db
from services.processing_profile_service import (
    delete_processing_profile,
    get_processing_profile,
    list_processing_profiles,
    normalize_instruction_list,
    normalize_special_entity_types,
    save_processing_profile,
)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class SpecialEntityType(BaseModel):
    name: str
    description: str | None = None


class ProcessingProfileSummary(BaseModel):
    name: str
    description: str | None = None
    context_instructions: str | None = None
    mandatory_instructions: list[str] = []
    special_entity_types: list[SpecialEntityType] = []


class ProcessingProfileCreate(BaseModel):
    name: str
    description: str | None = None
    context_instructions: str | None = None
    mandatory_instructions: list[str] = []
    special_entity_types: list[SpecialEntityType] = []


def _to_response(profile) -> ProcessingProfileSummary:
    return ProcessingProfileSummary(
        name=profile.name,
        description=profile.description,
        context_instructions=profile.context_instructions,
        mandatory_instructions=normalize_instruction_list(profile.mandatory_instructions),
        special_entity_types=normalize_special_entity_types(profile.special_entity_types),
    )


@router.get("", response_model=List[ProcessingProfileSummary])
async def list_profiles(db: Session = Depends(get_db)):
    return [_to_response(profile) for profile in list_processing_profiles(db)]


@router.get("/{profile_name}", response_model=ProcessingProfileSummary)
async def get_profile(profile_name: str, db: Session = Depends(get_db)):
    profile = get_processing_profile(db, profile_name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    return _to_response(profile)


@router.post("", response_model=ProcessingProfileSummary)
async def create_or_update_profile(
    profile: ProcessingProfileCreate,
    db: Session = Depends(get_db),
):
    if not profile.name or not profile.name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Profile name must contain only alphanumeric characters, hyphens, and underscores",
        )

    saved = save_processing_profile(
        db,
        name=profile.name,
        description=profile.description,
        context_instructions=profile.context_instructions,
        mandatory_instructions=profile.mandatory_instructions,
        special_entity_types=[item.model_dump() for item in profile.special_entity_types],
    )
    db.commit()
    db.refresh(saved)
    return _to_response(saved)


@router.delete("/{profile_name}")
async def delete_profile(profile_name: str, db: Session = Depends(get_db)):
    if not delete_processing_profile(db, profile_name):
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    db.commit()
    return {"status": "deleted", "name": profile_name}
