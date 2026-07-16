from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.runtime_state import SystemLog
from postgres.models.user import User
from postgres.permissions import (
    EDITOR_PERMISSIONS,
    OWNER_PERMISSIONS,
    VIEWER_PERMISSIONS,
    clone_permissions,
)


NOTEBOOK_TABLES = [
    User.__table__,
    Case.__table__,
    CaseMembership.__table__,
    NotebookNote.__table__,
    NotebookNoteLink.__table__,
    SystemLog.__table__,
]


def create_test_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=NOTEBOOK_TABLES)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return engine, session_factory


def drop_test_engine(engine) -> None:
    Base.metadata.drop_all(engine, tables=NOTEBOOK_TABLES)
    engine.dispose()


def make_user(
    session: Session,
    email: str,
    global_role: GlobalRole = GlobalRole.user,
) -> User:
    user = User(
        email=email,
        name=email.split("@", 1)[0].replace(".", " ").title(),
        password_hash="hash",
        global_role=global_role,
    )
    session.add(user)
    session.flush()
    return user


def make_case(session: Session, owner: User, title: str = "Notebook Case") -> Case:
    case = Case(
        title=title,
        created_by_user_id=owner.id,
        owner_user_id=owner.id,
    )
    session.add(case)
    session.flush()
    make_membership(
        session,
        case=case,
        user=owner,
        role=CaseMembershipRole.owner,
        permissions=OWNER_PERMISSIONS,
        added_by=owner,
    )
    return case


def make_membership(
    session: Session,
    *,
    case: Case,
    user: User,
    role: CaseMembershipRole = CaseMembershipRole.collaborator,
    permissions: dict | None = None,
    added_by: User | None = None,
) -> CaseMembership:
    membership = CaseMembership(
        case_id=case.id,
        user_id=user.id,
        membership_role=role,
        permissions=clone_permissions(
            permissions if permissions is not None else VIEWER_PERMISSIONS
        ),
        added_by_user_id=(added_by or user).id,
    )
    session.add(membership)
    session.flush()
    return membership


def make_editor_membership(
    session: Session,
    *,
    case: Case,
    user: User,
    added_by: User,
) -> CaseMembership:
    return make_membership(
        session,
        case=case,
        user=user,
        permissions=EDITOR_PERMISSIONS,
        added_by=added_by,
    )


def make_viewer_membership(
    session: Session,
    *,
    case: Case,
    user: User,
    added_by: User,
) -> CaseMembership:
    return make_membership(
        session,
        case=case,
        user=user,
        permissions=VIEWER_PERMISSIONS,
        added_by=added_by,
    )
