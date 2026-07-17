"""Case file export endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_export import available_sections, render_case_export
from services.case_service import CaseAccessDenied, CaseNotFound, get_case_if_allowed

router = APIRouter(prefix="/api/case-export", tags=["case-export"])


class CaseExportSectionResponse(BaseModel):
    key: str
    label: str
    description: str
    default_enabled: bool
    order: int


class CaseExportSectionsResponse(BaseModel):
    sections: list[CaseExportSectionResponse]


class CaseExportRequest(BaseModel):
    case_id: UUID
    section_keys: list[str] | None = Field(
        default=None,
        description="Section keys selected by the picker. Null exports default-enabled sections.",
    )
    footer_label: str = Field(default="Confidential", max_length=80)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/sections", response_model=CaseExportSectionsResponse)
def list_case_export_sections() -> dict[str, list[dict[str, Any]]]:
    return {"sections": available_sections()}


@router.post("")
def export_case_file(
    request: CaseExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
) -> Response:
    try:
        case = get_case_if_allowed(db=db, case_id=request.case_id, user=current_user)
        exported = render_case_export(
            db,
            case=case,
            current_user=current_user,
            section_keys=request.section_keys,
            footer_label=request.footer_label,
        )
        ascii_filename = exported.filename.encode("ascii", "ignore").decode("ascii") or "case-export.pdf"
        disposition = (
            f'attachment; filename="{ascii_filename}"; '
            f"filename*=UTF-8''{quote(exported.filename)}"
        )
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        _handle_error(exc)
    raise RuntimeError("Unhandled case export error")
