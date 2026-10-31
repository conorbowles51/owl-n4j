"""Request speed: page views posted by the browser, and the admin Speed page."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from postgres.session import get_db
from postgres.models.user import User
from routers.auth import get_current_user
from routers.users import require_admin
from services import request_speed

router = APIRouter(prefix='/api/request-speed', tags=['request-speed'])


class PageView(BaseModel):
    page: str = Field(max_length=64)
    method: str = Field(max_length=8)
    case_id: str | None = Field(None, max_length=64)
    ms: float
    # Browser figures for the view (navigation, resources, long tasks, memory, connection);
    # services.request_speed.page_detail checks each one.
    detail: dict[str, float | int | str | None] | None = Field(None, max_length=32)


class PageViews(BaseModel):
    views: list[PageView] = Field(default_factory=list, max_length=50)


@router.post('/page-views', status_code=202)
def page_views(body: PageViews, request: Request, token: dict = Depends(get_current_user)):
    """Time from opening a page to its data being shown, measured in the browser. Queued, never awaited."""
    email = token.get('username')
    routes = request.app.router.routes

    def route_of(path):
        return request_speed.route_template(routes, path)
    accepted = sum(request_speed.enqueue_page_view(v.page, v.method, v.case_id, v.ms, email, v.detail, route_of)
                   for v in body.views)
    return dict(accepted=accepted)


@router.get('/summary')
def speed_summary(days: int = Query(1, ge=1, le=30), case_id: UUID | None = Query(None),
                  kind: str | None = Query(None, pattern='^(api|page)$'),
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Per route: count, p50, p95, max over the last days; the slow requests kept. Admins only."""
    return request_speed.summary(db, days, case_id=str(case_id) if case_id else None, kind=kind)
