"""
Profiles Router

Handles listing, retrieving, creating, and updating LLM profile configurations.
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


class EntityDefinition(BaseModel):
    """Definition of an entity type."""
    name: str
    color: str  # Hex color code
    description: Optional[str] = None  # Instructions for LLM on how to identify


class ProfileSummary(BaseModel):
    """Summary of a profile (name and description)."""
    name: str
    description: str


class ProfileDetail(BaseModel):
    """Full profile details."""
    name: str
    description: str
    case_type: Optional[str] = None
    agent_description: Optional[str] = None
    instructions: Optional[str] = None
    characteristics: Optional[str] = None
    ingestion: Dict[str, Any]
    chat: Dict[str, Any]


class ProfileCreate(BaseModel):
    """Request model for creating/updating a profile."""
    name: str
    description: str
    case_type: Optional[str] = None
    agent_description: Optional[str] = None
    instructions: Optional[str] = None
    characteristics: Optional[str] = None
    entities: List[EntityDefinition]
    relationship_examples: List[str]  # Example relationships instead of types
    chat_system_context: Optional[str] = None
    chat_analysis_guidance: Optional[str] = None
    temperature: Optional[float] = 1.0  # LLM temperature (0.0-2.0, default 1.0)


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
                agent_description=data.get("agent_description"),
                instructions=data.get("instructions"),
                characteristics=data.get("characteristics"),
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
    
    # Build the profile structure
    profile_data = {
        "name": profile.name,
        "description": profile.description,
        "case_type": profile.case_type,
        "agent_description": profile.agent_description,
        "instructions": profile.instructions,
        "characteristics": profile.characteristics,
        "ingestion": {
            "system_context": _build_system_context(profile),
            "entity_types": [e.name for e in profile.entities],
            "entity_definitions": {
                e.name: {
                    "color": e.color,
                    "description": e.description or ""
                }
                for e in profile.entities
            },
            "relationship_examples": profile.relationship_examples,
            "temperature": profile.temperature if profile.temperature is not None else 1.0,
        },
        "chat": {
            "system_context": profile.chat_system_context or f"You are an AI assistant helping to analyze {profile.case_type or 'documents'}.",
            "analysis_guidance": profile.chat_analysis_guidance or "Provide clear explanations and highlight important connections."
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
            agent_description=profile_data["agent_description"],
            instructions=profile_data["instructions"],
            characteristics=profile_data["characteristics"],
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


def _build_system_context(profile: ProfileCreate) -> str:
    """Build the system context prompt from profile configuration."""
    parts = []
    
    if profile.case_type:
        parts.append(f"Case Type: {profile.case_type}")
    
    if profile.agent_description:
        parts.append(f"Agent Description: {profile.agent_description}")
    
    if profile.instructions:
        parts.append(f"Instructions: {profile.instructions}")
    
    if profile.characteristics:
        parts.append(f"Characteristics: {profile.characteristics}")
    
    if parts:
        return "You are an assistant helping with " + ". ".join(parts) + "."
    else:
        return "You are an assistant helping to extract structured information from documents."

