"""Photos: what a photo's own data says, its map pins, a small picture of it, and its optional one-line caption."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import check_case_access, get_case_if_allowed
from services.photo_data import photo_detail, photo_places, set_caption

router = APIRouter(prefix="/api/photos", tags=["photos"])
THUMB_PX = 240


def _file(db: Session, file_id: UUID, case_id: UUID) -> EvidenceFile:
    file = db.get(EvidenceFile, file_id)
    if not file or file.case_id != case_id or file.deleted_at:
        raise HTTPException(status_code=404, detail="This file is not in this case.")
    return file


@router.get("/places")
def places(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    get_case_if_allowed(db=db, case_id=case_id, user=user)
    return photo_places(db, case_id)


@router.get("/{file_id}")
def detail(file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
           user: User = Depends(get_current_db_user)):
    get_case_if_allowed(db=db, case_id=case_id, user=user)
    return photo_detail(_file(db, file_id, case_id))


@router.get("/{file_id}/thumbnail")
def thumbnail(file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)):
    get_case_if_allowed(db=db, case_id=case_id, user=user)
    file = _file(db, file_id, case_id)
    from routers.evidence import _resolve_stored_path

    path = _resolve_stored_path(file.stored_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="The file is missing from storage.")
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img.draft("RGB", (THUMB_PX * 2, THUMB_PX * 2))  # JPEG decodes at a fraction of the size
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((THUMB_PX, THUMB_PX))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=70)
    except Exception:
        raise HTTPException(status_code=415, detail="This file cannot be shown as a picture.")
    return Response(out.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


class CaptionBody(BaseModel):
    caption: str | None = None


@router.put("/{file_id}/caption")
def caption(file_id: UUID, body: CaptionBody, case_id: UUID = Query(...), db: Session = Depends(get_db),
            user: User = Depends(get_current_db_user)):
    check_case_access(db=db, case_id=case_id, user=user, required_permission=("case", "edit"))
    file = _file(db, file_id, case_id)
    try:
        kept = set_caption(file, body.caption)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return dict(caption=kept)
