"""
Workspace Router

Handles workspace-specific endpoints for case workspaces including:
- Case context management
- Witness matrix
- Investigation theories
- Task management
- Deadline tracking
- Pinned evidence
- Presence tracking
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.workspace_service import workspace_service
from services.presence_service import presence_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from services.case_service import get_case_if_allowed, CaseNotFound, CaseAccessDenied
from services.vector_db_service import vector_db_service
from services.embedding_service import EmbeddingService
from services.evidence_storage import evidence_storage
from services.neo4j_service import neo4j_service
from pathlib import Path
from utils.text_extraction import extract_text_from_file
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


# Pydantic Models
class CaseContextUpdate(BaseModel):
    client_profile: Optional[Dict] = None
    charges: Optional[List[str]] = None
    allegations: Optional[List[str]] = None
    denials: Optional[List[str]] = None
    legal_exposure: Optional[Dict] = None
    defense_strategy: Optional[List[str]] = None
    trial_date: Optional[str] = None
    court_info: Optional[Dict] = None


class WitnessInterview(BaseModel):
    interview_id: Optional[str] = None
    date: str  # ISO date string
    duration: Optional[str] = None  # e.g., "45 minutes", "1 hour 30 minutes"
    statement: Optional[str] = None
    status: Optional[str] = None  # e.g., "Cooperating Witness (CW)"
    credibility_rating: Optional[int] = None  # 1-5
    risk_assessment: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WitnessCreate(BaseModel):
    name: str
    role: Optional[str] = None
    organization: Optional[str] = None
    category: str  # "FRIENDLY", "NEUTRAL", "ADVERSE"
    status: Optional[str] = None
    credibility_rating: Optional[int] = None  # 1-5
    statement_summary: Optional[str] = None
    risk_assessment: Optional[str] = None
    strategy_notes: Optional[str] = None
    interviews: Optional[List[WitnessInterview]] = None


class TheoryCreate(BaseModel):
    title: str
    type: str  # "PRIMARY", "SECONDARY", "NOTE"
    confidence_score: Optional[int] = None  # 0-100
    hypothesis: Optional[str] = None
    supporting_evidence: Optional[List[str]] = None
    counter_arguments: Optional[List[str]] = None
    next_steps: Optional[List[str]] = None
    privilege_level: str = "PUBLIC"  # "PUBLIC", "ATTORNEY_ONLY", "PRIVATE"
    attached_snapshot_ids: Optional[List[str]] = None  # Snapshot IDs linked to this theory
    attached_evidence_ids: Optional[List[str]] = None  # Evidence file IDs linked to this theory
    attached_witness_ids: Optional[List[str]] = None  # Witness IDs linked to this theory
    attached_note_ids: Optional[List[str]] = None  # Investigative note IDs linked to this theory
    attached_document_ids: Optional[List[str]] = None  # Document IDs linked to this theory
    attached_task_ids: Optional[List[str]] = None  # Task IDs linked to this theory


class NoteCreate(BaseModel):
    content: str
    tags: Optional[List[str]] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str  # "URGENT", "HIGH", "STANDARD"
    due_date: Optional[str] = None
    assigned_to: Optional[str] = None
    status: str = "PENDING"  # "PENDING", "IN_PROGRESS", "COMPLETED"
    completion_percentage: int = 0
    status_text: Optional[str] = None  # Custom status message (e.g., "Waiting on Lab Results", "Interview Scheduled Jan 28")


class DeadlineItem(BaseModel):
    """Individual deadline item"""
    deadline_id: Optional[str] = None
    title: str
    due_date: str
    urgency_level: str = "STANDARD"  # "URGENT", "HIGH", "STANDARD"
    completed: bool = False


class DeadlineCreate(BaseModel):
    """Deadline configuration for a case"""
    trial_date: Optional[str] = None  # ISO date string
    trial_court: Optional[str] = None  # e.g., "U.S. District Court, E.D. Virginia"
    judge: Optional[str] = None  # e.g., "Hon. Patricia M. Richardson"
    court_division: Optional[str] = None  # e.g., "Alexandria Division"
    deadlines: Optional[List[DeadlineItem]] = None  # List of deadline items


# Case Context Endpoints
@router.get("/{case_id}/context")
async def get_case_context(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get case context for a workspace."""
    try:
        # Verify case exists and user has access
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        context = workspace_service.get_case_context(case_id)
        if not context:
            # Return default structure
            return {
                "case_id": case_id,
                "client_profile": {},
                "charges": [],
                "allegations": [],
                "denials": [],
                "legal_exposure": {},
                "defense_strategy": [],
                "trial_date": None,
                "court_info": {}
            }

        return context
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/context")
async def update_case_context(
    case_id: str,
    context: CaseContextUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update case context."""
    try:
        # Verify case exists and user has access
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        # Get existing context or create new
        existing = workspace_service.get_case_context(case_id) or {}
        updated = {
            "case_id": case_id,
            **existing,
            **context.dict(exclude_unset=True),
            "updated_at": datetime.now().isoformat()
        }

        workspace_service.save_case_context(case_id, updated)

        # Log the update
        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Update Case Context",
            details={"case_id": case_id},
            user=current_user.email,
            success=True,
        )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Witness Endpoints
@router.get("/{case_id}/witnesses")
async def get_witnesses(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get all witnesses for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        witnesses = workspace_service.get_witnesses(case_id)
        return {"witnesses": witnesses}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/witnesses")
async def create_witness(
    case_id: str,
    witness: WitnessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new witness."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        witness_data = witness.dict()
        witness_id = workspace_service.save_witness(case_id, witness_data)

        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Create Witness",
            details={"case_id": case_id, "witness_id": witness_id, "name": witness.name},
            user=current_user.email,
            success=True,
        )

        return {"witness_id": witness_id, **witness_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/witnesses/{witness_id}")
async def update_witness(
    case_id: str,
    witness_id: str,
    witness: WitnessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update a witness."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        existing = workspace_service.get_witness(case_id, witness_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Witness not found")

        witness_data = {**existing, **witness.dict(exclude_unset=True)}
        workspace_service.save_witness(case_id, witness_data)

        return witness_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/witnesses/{witness_id}")
async def delete_witness(
    case_id: str,
    witness_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Delete a witness."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        if not workspace_service.delete_witness(case_id, witness_id):
            raise HTTPException(status_code=404, detail="Witness not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Theory Endpoints
@router.get("/{case_id}/theories")
async def get_theories(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get all theories for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        # Get user role for privilege filtering
        user_role = current_user.global_role.value if current_user.global_role else "investigator"
        theories = workspace_service.get_theories(case_id, user_role=user_role)
        return {"theories": theories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/theories")
async def create_theory(
    case_id: str,
    theory: TheoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new theory."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        theory_data = theory.dict()
        theory_data["author_id"] = current_user.email
        theory_id = workspace_service.save_theory(case_id, theory_data)

        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Create Theory",
            details={"case_id": case_id, "theory_id": theory_id, "title": theory.title},
            user=current_user.email,
            success=True,
        )

        return {"theory_id": theory_id, **theory_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/theories/{theory_id}")
async def update_theory(
    case_id: str,
    theory_id: str,
    theory: TheoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update a theory."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        existing = workspace_service.get_theory(case_id, theory_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Theory not found")

        theory_data = {**existing, **theory.dict(exclude_unset=True)}
        workspace_service.save_theory(case_id, theory_data)

        return theory_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/theories/{theory_id}")
async def delete_theory(
    case_id: str,
    theory_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Delete a theory."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        if not workspace_service.delete_theory(case_id, theory_id):
            raise HTTPException(status_code=404, detail="Theory not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BuildTheoryGraphRequest(BaseModel):
    """Request model for building theory graph."""
    include_attached_items: bool = True  # Whether to include attached documents/evidence
    top_k: int = 20  # Number of similar entities to return


@router.post("/{case_id}/theories/{theory_id}/build-graph")
async def build_theory_graph(
    case_id: str,
    theory_id: str,
    request: BuildTheoryGraphRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Build a graph for a theory by:
    1. Combining theory text with attached document text (if requested)
    2. Creating a vector embedding
    3. Searching for similar entities in the vector DB
    4. Returning relevant entity keys to display in graph
    """
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")
        
        # Get the theory
        theory = workspace_service.get_theory(case_id, theory_id)
        if not theory:
            raise HTTPException(status_code=404, detail="Theory not found")
        
        # Build combined text
        text_parts = []
        
        # Add theory text
        if theory.get("hypothesis"):
            text_parts.append(f"Theory: {theory['hypothesis']}")
        if theory.get("title"):
            text_parts.append(f"Title: {theory['title']}")
        if theory.get("supporting_evidence"):
            text_parts.append(f"Supporting Evidence: {' '.join(theory['supporting_evidence'])}")
        if theory.get("counter_arguments"):
            text_parts.append(f"Counter Arguments: {' '.join(theory['counter_arguments'])}")
        
        # Add text from attached items if requested
        if request.include_attached_items:
            # Extract text from attached evidence
            if theory.get("attached_evidence_ids"):
                for evidence_id in theory["attached_evidence_ids"]:
                    try:
                        evidence_record = evidence_storage.get(evidence_id)
                        if evidence_record and evidence_record.get("stored_path"):
                            file_path = Path(evidence_record["stored_path"])
                            text = extract_text_from_file(file_path)
                            if text:
                                text_parts.append(f"Evidence {evidence_record.get('original_filename', evidence_id)}: {text[:5000]}")  # Limit to 5k chars per file
                    except Exception as e:
                        print(f"[Build Theory Graph] Failed to extract text from evidence {evidence_id}: {e}")
                        continue
            
            # Extract text from attached documents (same as evidence)
            if theory.get("attached_document_ids"):
                for doc_id in theory["attached_document_ids"]:
                    try:
                        doc_record = evidence_storage.get(doc_id)
                        if doc_record and doc_record.get("stored_path"):
                            file_path = Path(doc_record["stored_path"])
                            text = extract_text_from_file(file_path)
                            if text:
                                text_parts.append(f"Document {doc_record.get('original_filename', doc_id)}: {text[:5000]}")
                    except Exception as e:
                        print(f"[Build Theory Graph] Failed to extract text from document {doc_id}: {e}")
                        continue
            
            # Add notes text
            if theory.get("attached_note_ids"):
                try:
                    notes_data = workspace_service.get_notes(case_id)
                    all_notes = notes_data.get("notes", [])
                    for note_id in theory["attached_note_ids"]:
                        note = next((n for n in all_notes if (n.get("note_id") or n.get("id")) == note_id), None)
                        if note and note.get("content"):
                            text_parts.append(f"Note: {note['content']}")
                except Exception as e:
                    print(f"[Build Theory Graph] Failed to load notes: {e}")
        
        # Combine all text
        combined_text = "\n\n".join(text_parts)
        
        if not combined_text.strip():
            raise HTTPException(status_code=400, detail="No text available to create embedding")
        
        # Create embedding
        try:
            embedding_service = EmbeddingService()
            query_embedding = embedding_service.generate_embedding(combined_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create embedding: {str(e)}")
        
        # Search for similar entities
        try:
            # Search entities (case_id filter may not be in metadata, so we'll filter after)
            similar_entities = vector_db_service.search_entities(
                query_embedding=query_embedding,
                top_k=request.top_k * 2,  # Get more results, then filter by case_id
                filter_metadata=None  # Don't filter by case_id in vector DB (may not be in metadata)
            )
            
            # Extract entity keys from results and verify they belong to this case
            entity_keys = []
            entities_data = []
            for entity in similar_entities:
                entity_key = entity.get("id")
                if not entity_key:
                    continue
                
                try:
                    # Verify entity belongs to this case by checking Neo4j
                    entity_details = neo4j_service.get_node_details(entity_key, case_id=case_id)
                    if entity_details:
                        # Entity exists and belongs to this case
                        entity_keys.append(entity_key)
                        entities_data.append({
                            "key": entity_key,
                            "name": entity_details.get("name"),
                            "type": entity_details.get("type"),
                            "summary": entity_details.get("summary"),
                            "distance": entity.get("distance"),
                        })
                        
                        # Stop when we have enough results
                        if len(entity_keys) >= request.top_k:
                            break
                except Exception as e:
                    # Entity doesn't exist or doesn't belong to this case, skip it
                    continue
            
            result = {
                "entity_keys": entity_keys,
                "entities": entities_data,
                "similarity_results": similar_entities,
                "text_length": len(combined_text),
            }
            
            # Store the graph data in the theory
            theory["attached_graph_data"] = {
                "entity_keys": entity_keys,
                "entities": entities_data,
                "created_at": datetime.now().isoformat(),
                "include_attached_items": request.include_attached_items,
                "top_k": request.top_k,
            }
            workspace_service.save_theory(case_id, theory)
            
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to search entities: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/investigation-timeline")
async def get_investigation_timeline(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get investigation timeline events for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        events = workspace_service.get_investigation_timeline(case_id)
        return {"events": events, "total": len(events)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{case_id}/theories/{theory_id}/timeline")
async def get_theory_timeline(
    case_id: str,
    theory_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get timeline events for a specific theory and its attached items."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        events = workspace_service.get_theory_timeline(case_id, theory_id)
        return {"events": events, "total": len(events)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Task Endpoints
@router.get("/{case_id}/tasks")
async def get_tasks(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get all tasks for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        tasks = workspace_service.get_tasks(case_id)
        return {"tasks": tasks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/tasks")
async def create_task(
    case_id: str,
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new task."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        task_data = task.dict()
        task_id = workspace_service.save_task(case_id, task_data)

        return {"task_id": task_id, **task_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/tasks/{task_id}")
async def update_task(
    case_id: str,
    task_id: str,
    task: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update a task."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        existing = workspace_service.get_task(case_id, task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")

        task_data = {**existing, **task.dict(exclude_unset=True)}
        workspace_service.save_task(case_id, task_data)

        return task_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/tasks/{task_id}")
async def delete_task(
    case_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Delete a task."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        if not workspace_service.delete_task(case_id, task_id):
            raise HTTPException(status_code=404, detail="Task not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Deadline Endpoints
@router.get("/{case_id}/deadlines")
async def get_deadlines(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get deadline configuration for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        deadline_config = workspace_service.get_deadline_config(case_id)
        if not deadline_config:
            # Return default structure
            return {
                "trial_date": None,
                "trial_court": None,
                "judge": None,
                "court_division": None,
                "deadlines": []
            }

        return deadline_config
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/deadlines")
async def update_deadlines(
    case_id: str,
    deadline_config: DeadlineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update deadline configuration for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        config_data = deadline_config.dict()
        workspace_service.save_deadline_config(case_id, config_data)

        return config_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Pinned Items Endpoints
@router.get("/{case_id}/pinned")
async def get_pinned_items(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get pinned items for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        pinned = workspace_service.get_pinned_items(case_id, user_id=current_user.email)
        return {"pinned_items": pinned}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/pinned")
async def pin_item(
    case_id: str,
    item_type: str = Query(..., description="Type of item: 'evidence' or 'document'"),
    item_id: str = Query(..., description="ID of the item to pin"),
    annotations_count: int = Query(0, description="Number of annotations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Pin an item to the workspace."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        pin_id = workspace_service.pin_item(
            case_id=case_id,
            item_type=item_type,
            item_id=item_id,
            user_id=current_user.email,
            annotations_count=annotations_count
        )

        return {"pin_id": pin_id, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/pinned/{pin_id}")
async def unpin_item(
    case_id: str,
    pin_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Unpin an item from the workspace."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        if not workspace_service.unpin_item(case_id, pin_id):
            raise HTTPException(status_code=404, detail="Pinned item not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Investigative Notes Endpoints
@router.get("/{case_id}/notes")
async def get_notes(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get all investigative notes for a case."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        notes = workspace_service.get_notes(case_id)
        return {"notes": notes}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{case_id}/notes")
async def create_note(
    case_id: str,
    note: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new investigative note."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        note_data = note.dict()
        note_id = workspace_service.save_note(case_id, note_data)

        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Create Investigative Note",
            details={"case_id": case_id, "note_id": note_id},
            user=current_user.email,
            success=True,
        )

        return {"note_id": note_id, **note_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{case_id}/notes/{note_id}")
async def update_note(
    case_id: str,
    note_id: str,
    note: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update an investigative note."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        existing = workspace_service.get_note(case_id, note_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Note not found")

        note_data = {**existing, **note.dict(exclude_unset=True)}
        workspace_service.save_note(case_id, note_data)

        return note_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{case_id}/notes/{note_id}")
async def delete_note(
    case_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Delete an investigative note."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        if not workspace_service.delete_note(case_id, note_id):
            raise HTTPException(status_code=404, detail="Note not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Presence Endpoints
@router.get("/{case_id}/presence")
async def get_presence(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get online users for a workspace."""
    try:
        try:
            get_case_if_allowed(db=db, case_id=UUID(case_id), user=current_user)
        except (CaseNotFound, CaseAccessDenied):
            raise HTTPException(status_code=404, detail="Case not found")

        online_users = presence_service.get_online_users(case_id)
        return {"online_users": online_users, "count": len(online_users)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/{case_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    case_id: str,
):
    """WebSocket endpoint for real-time workspace updates."""
    await websocket.accept()
    session_id = None
    
    try:
        # Get user info from query params or initial message
        # For now, we'll use a simple approach - in production, use proper auth
        user_id = "unknown"
        username = "unknown"
        
        # Create session
        session_id = presence_service.create_session(
            case_id=case_id,
            user_id=user_id,
            username=username,
            ip_address=websocket.client.host if websocket.client else None
        )
        
        # Send initial presence update
        online_users = presence_service.get_online_users(case_id)
        await websocket.send_json({
            "type": "presence_update",
            "online_users": online_users
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")
                
                if message_type == "ping":
                    presence_service.update_session_activity(session_id)
                    await websocket.send_json({"type": "pong"})
                elif message_type == "activity":
                    # Broadcast activity to other users in workspace
                    # This would be handled by a WebSocket manager in production
                    pass
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
                
    except Exception as e:
        print(f"WebSocket connection error: {e}")
    finally:
        if session_id:
            presence_service.remove_session(session_id)
        try:
            await websocket.close()
        except:
            pass
