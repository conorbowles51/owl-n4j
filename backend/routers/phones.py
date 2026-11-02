"""Phone interpretation API, prefix ``/api/phones`` (02; placement fixed by 03 section 4.1).

Registry review queue (02 section 3.4): admin only, because the registry is global.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import require_admin
from services.phone import registry

router = APIRouter(prefix="/api/phones", tags=["phones"])

FlagState = Literal["open", "acknowledged", "mapping_needed", "mapped", "dismissed"]


class FlagTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Literal["open", "acknowledged", "mapping_needed", "dismissed"]
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/registry/flags")
def list_registry_flags(state: Optional[FlagState] = None, db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    flags = registry.list_flags(db, state)
    return {"total": len(flags), "flags": [dict(f, raised_at=f["raised_at"].isoformat(),
                                                raised_by_extraction_id=(str(f["raised_by_extraction_id"])
                                                                         if f["raised_by_extraction_id"] else None))
                                           for f in flags]}


@router.post("/registry/flags/{flag_id}/transition")
def transition_registry_flag(flag_id: int, body: FlagTransition, db: Session = Depends(get_db),
                             user: User = Depends(require_admin)):
    try:
        out = registry.transition_flag(db, flag_id, body.to, body.reason, actor_name=user.name,
                                       actor_email=user.email, actor_user_id=user.id)
    except registry.TransitionRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409 if "cannot become" in str(exc) else 422, detail=str(exc))
    db.commit()
    return out
