"""
Database Router - endpoints for vector database management.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.vector_db_service import vector_db_service
from services.neo4j_service import neo4j_service
from services.evidence_storage import evidence_storage
from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

router = APIRouter(prefix="/api/database", tags=["database"])


class RetrievalHistoryEntry(BaseModel):
    """Model for a retrieval history entry."""
    query: str
    timestamp: str
    distance: Optional[float] = None


class EntityResponse(BaseModel):
    """Response model for an entity."""
    id: str  # entity_key
    text: str
    metadata: dict


class EntitiesListResponse(BaseModel):
    """Response model for entities list."""
    entities: List[EntityResponse]
    total: int


class EntityStatusResponse(BaseModel):
    """Response model for entity status."""
    key: str
    name: str
    entity_type: str
    has_embedding: bool
    summary: Optional[str] = None


class EntitiesStatusResponse(BaseModel):
    """Response model for entities status list."""
    entities: List[EntityStatusResponse]
    total: int
    embedded: int
    not_embedded: int


# =====================
# Entity Endpoints
# =====================

@router.get("/entities/status", response_model=EntitiesStatusResponse)
async def list_entities_status(
    user: dict = Depends(get_current_user),
):
    """
    List all entities with their embedding status.

    Shows entities from Neo4j and whether they have embeddings in the vector DB.
    """
    try:
        # Get all entities from Neo4j (excluding Document nodes)
        cypher = """
        MATCH (e)
        WHERE NOT e:Document
        RETURN e.key AS key, e.name AS name, labels(e)[0] AS entity_type,
               e.summary AS summary
        ORDER BY e.name
        """
        neo4j_entities = neo4j_service.run_cypher(cypher)

        entities = []
        embedded_count = 0
        not_embedded_count = 0

        for ent in neo4j_entities:
            entity_key = ent.get("key")
            name = ent.get("name", "")
            entity_type = ent.get("entity_type", "Unknown")
            summary = ent.get("summary", "")

            if not entity_key:
                continue

            # Check if entity has embedding in vector DB
            has_embedding = False
            try:
                vector_entity = vector_db_service.get_entity(entity_key)
                has_embedding = vector_entity is not None
            except:
                has_embedding = False

            entities.append({
                "key": entity_key,
                "name": name,
                "entity_type": entity_type,
                "has_embedding": has_embedding,
                "summary": summary,
            })

            if has_embedding:
                embedded_count += 1
            else:
                not_embedded_count += 1

        return EntitiesStatusResponse(
            entities=entities,
            total=len(entities),
            embedded=embedded_count,
            not_embedded=not_embedded_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities", response_model=EntitiesListResponse)
async def list_entities(
    user: dict = Depends(get_current_user),
):
    """
    List all entities in the vector database.
    """
    try:
        # Get all entities from ChromaDB
        collection = vector_db_service.entity_collection

        try:
            all_data = collection.get()

            entities = []
            if all_data and all_data.get("ids") and len(all_data["ids"]) > 0:
                ids = all_data["ids"]
                texts = all_data.get("documents", [])
                metadatas = all_data.get("metadatas", [])

                for i in range(len(ids)):
                    entity_key = ids[i]
                    text = texts[i] if i < len(texts) else ""
                    metadata = metadatas[i] if i < len(metadatas) else {}

                    entities.append({
                        "id": entity_key,
                        "text": text,
                        "metadata": metadata or {},
                    })
        except Exception as e:
            print(f"Warning: Could not retrieve all entities: {e}")
            entities = []

        # Log the operation
        system_log_service.log(
            log_type=LogType.SYSTEM,
            origin=LogOrigin.FRONTEND,
            action="List Vector Database Entities",
            details={
                "count": len(entities),
            },
            user=user.get("username", "unknown"),
            success=True,
        )

        return EntitiesListResponse(
            entities=entities,
            total=len(entities),
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.SYSTEM,
            origin=LogOrigin.BACKEND,
            action="List Vector Database Entities Failed",
            details={
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_key}")
async def get_entity(
    entity_key: str,
    user: dict = Depends(get_current_user),
):
    """
    Get a specific entity by key.
    """
    try:
        entity = vector_db_service.get_entity(entity_key)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        return {
            "id": entity_key,
            "text": entity.get("text", ""),
            "metadata": entity.get("metadata", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
