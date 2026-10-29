"""The activity trail: admin view across cases, and per-file provenance for case members."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from postgres.session import get_db
from postgres.models.user import User
from routers.case_access import authorize_case
from routers.users import get_current_db_user, require_admin
from services import activity_trail

router = APIRouter(prefix='/api/activity', tags=['activity'])


@router.get('')
def list_activity(case_id: UUID | None = Query(None), user: str | None = Query(None, max_length=255),
                  action: list[str] = Query([]), since: datetime | None = Query(None), until: datetime | None = Query(None),
                  limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Who did what, from where. Admins only; newest first."""
    return dict(**activity_trail.list_events(db, case_id=case_id, user=user, action=action or None,
                                             since=since, until=until, limit=limit, offset=offset),
                actions=activity_trail.ACTIONS, origins=activity_trail.ORIGINS)


class ProvenanceRequest(BaseModel):
    file_ids: list[UUID] = Field(default_factory=list, max_length=2000)


@router.post('/files')
def file_provenance(body: ProvenanceRequest, case_id: UUID = Query(...),
                    user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Uploaded by / added to Financial by, for files the person can see in this case."""
    authorize_case(db, case_id, user, ('case', 'view'))
    return dict(case_id=str(case_id), files=activity_trail.file_provenance(db, case_id=case_id, file_ids=body.file_ids))
