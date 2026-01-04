"""
Profiles Router

Handles listing, retrieving, creating, and updating LLM profile configurations.

Profile Structure:
{
    "name": "profile_name",
    "description": "Profile description",
    "case_type": "Type of case",
    "ingestion": {
        "system_context": "System prompt for entity extraction",
        "special_entity_types": [{"name": "EntityType", "description": "Description of entity"}],
        "temperature": 1.0
    },
    "chat": {
        "system_context": "System prompt for chat assistant",
        "analysis_guidance": "Guidance for analysis",
        "temperature": 1.0
    }
}
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

# Profiles are at the project root, not in backend/
# __file__ is backend/routers/profiles.py
# So we need to go up 3 levels: backend/routers -> backend -> project_root
PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


class SpecialEntityType(BaseModel):
    """Definition of a special entity type for extraction."""
    name: str
    description: Optional[str] = None


class ProfileSummary(BaseModel):
    """Summary of a profile (name and description)."""
    name: str
    description: str


class ProfileDetail(BaseModel):
    """Full profile details."""
    name: str
    description: str
    case_type: Optional[str] = None
    ingestion: Dict[str, Any]
    chat: Dict[str, Any]


class ProfileCreate(BaseModel):
    """Request model for creating/updating a profile."""
    name: str
    description: str
    case_type: Optional[str] = None
    # Ingestion config
    ingestion_system_context: Optional[str] = None
    special_entity_types: Optional[List[SpecialEntityType]] = []
    ingestion_temperature: Optional[float] = 1.0
    # Chat config
    chat_system_context: Optional[str] = None
    chat_analysis_guidance: Optional[str] = None
    chat_temperature: Optional[float] = 1.0


@router.get("", response_model=List[ProfileSummary])
async def list_profiles():
    """List all available profiles."""
    profiles = []
    
    if not PROFILES_DIR.exists():
        return profiles
    
    for profile_file in PROFILES_DIR.glob("*.json"):
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                profiles.append(ProfileSummary(
                    name=data.get("name", profile_file.stem),
                    description=data.get("description", "")
                ))
        except Exception as e:
            # Skip invalid profile files
            continue
    
    # Sort by name
    profiles.sort(key=lambda p: p.name)
    return profiles


@router.get("/{profile_name}", response_model=ProfileDetail)
async def get_profile(profile_name: str):
    """Get detailed information about a specific profile."""
    profile_path = PROFILES_DIR / f"{profile_name}.json"
    
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return ProfileDetail(
                name=data.get("name", profile_name),
                description=data.get("description", ""),
                case_type=data.get("case_type"),
                ingestion=data.get("ingestion", {}),
                chat=data.get("chat", {})
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load profile: {str(e)}")


@router.post("", response_model=ProfileDetail)
async def create_or_update_profile(profile: ProfileCreate):
    """Create or update a profile."""
    # Validate profile name (must be valid filename)
    if not profile.name or not profile.name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Profile name must contain only alphanumeric characters, hyphens, and underscores"
        )
    
    # Ensure profiles directory exists
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    profile_path = PROFILES_DIR / f"{profile.name}.json"
    
    # Build the profile structure matching the new simplified format
    # Convert special_entity_types to list of dicts for JSON serialization
    special_entities = [
        {"name": e.name, "description": e.description or ""}
        for e in (profile.special_entity_types or [])
    ]
    
    profile_data = {
        "name": profile.name,
        "description": profile.description,
        "case_type": profile.case_type,
        "ingestion": {
            "system_context": profile.ingestion_system_context or _build_default_ingestion_context(profile),
            "special_entity_types": special_entities,
            "temperature": profile.ingestion_temperature if profile.ingestion_temperature is not None else 1.0
        },
        "chat": {
            "system_context": profile.chat_system_context or f"You are an AI assistant helping to analyze {profile.case_type or 'case documents'}.",
            "analysis_guidance": profile.chat_analysis_guidance or "Identify patterns, highlight connections, and provide clear explanations.",
            "temperature": profile.chat_temperature if profile.chat_temperature is not None else 1.0
        }
    }
    
    try:
        # Write the profile file
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)
        
        return ProfileDetail(
            name=profile_data["name"],
            description=profile_data["description"],
            case_type=profile_data["case_type"],
            ingestion=profile_data["ingestion"],
            chat=profile_data["chat"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")


@router.delete("/{profile_name}")
async def delete_profile(profile_name: str):
    """Delete a profile."""
    profile_path = PROFILES_DIR / f"{profile_name}.json"
    
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
    
    # Don't allow deleting the generic profile
    if profile_name == "generic":
        raise HTTPException(status_code=400, detail="Cannot delete the generic profile")
    
    try:
        profile_path.unlink()
        return {"status": "deleted", "name": profile_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {str(e)}")


def _build_default_ingestion_context(profile: ProfileCreate) -> str:
    """Build a default ingestion system context from profile configuration."""
    case_type = profile.case_type or "document analysis"
    return f"You are an expert analyst extracting entities and relationships from {case_type} documents. Focus on identifying key people, organizations, locations, events, and their connections. Capture dates for events and relevant details that establish relationships between entities."

