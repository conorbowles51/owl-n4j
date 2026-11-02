"""Helpers for the pattern-of-life HTTP tests: the router on a throwaway app, signed in as the case's owner."""
from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def api_client(engine, case_id, as_user=None):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.pattern_of_life import router
    from routers.users import get_current_db_user

    with engine.connect() as c:
        uid, email = c.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                    "WHERE k.id = :c"), {"c": case_id}).one()
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)

    def db():
        s = Session()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_db_user] = lambda: as_user or User(
        id=uid, email=email, name="synthetic", global_role=GlobalRole.user)
    with TestClient(app) as client:
        yield client
