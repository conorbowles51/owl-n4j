from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case_context import (
    CaseContext,
    CaseContextTemplate,
    CaseContextTemplateField,
    CaseContextValue,
    CaseMandateVersion,
)
from postgres.models.case_profile import CaseProfile
from postgres.models.user import User
from services.mandate_context_service import (
    CaseContextValidationError,
    mandate_context_service,
)


TABLES = [
    User.__table__,
    CaseContextTemplate.__table__,
    CaseContextTemplateField.__table__,
    CaseContext.__table__,
    CaseMandateVersion.__table__,
    CaseContextValue.__table__,
]


def make_user(db) -> User:
    user = User(
        email=f"{uuid4()}@example.test",
        name="Investigator",
        password_hash="not-used",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    generic = CaseContextTemplate(key="generic", name="General", is_builtin=True)
    typed = CaseContextTemplate(key="typed", name="Typed", is_builtin=False)
    session.add_all([generic, typed])
    session.flush()
    typed.fields = [
        CaseContextTemplateField(template_id=typed.id, field_key="title", label="Title", field_type="short_text", choices=[], position=0),
        CaseContextTemplateField(template_id=typed.id, field_key="started", label="Started", field_type="date", choices=[], position=1),
        CaseContextTemplateField(template_id=typed.id, field_key="risk", label="Risk", field_type="single_choice", choices=["low", "high"], position=2),
    ]
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_typed_values_and_template_isolation(db):
    case_id = uuid4()
    user = make_user(db)
    result = mandate_context_service.update_context(
        db,
        case_id=case_id,
        user=user,
        payload={
            "case_summary": "A general investigation",
            "active_template_key": "typed",
            "custom_values": {"title": "Operation North", "started": "2026-09-01", "risk": "high"},
        },
    )
    assert result["custom_values"]["risk"] == "high"

    with pytest.raises(CaseContextValidationError, match="do not belong"):
        mandate_context_service.update_context(
            db,
            case_id=case_id,
            user=user,
            payload={"active_template_key": "generic", "custom_values": {"risk": "low"}},
        )

    with pytest.raises(CaseContextValidationError, match="ISO date"):
        mandate_context_service.update_context(
            db,
            case_id=case_id,
            user=user,
            payload={"active_template_key": "typed", "custom_values": {"started": "tomorrow"}},
        )


def test_versions_are_immutable_and_override_is_request_only(db):
    case_id = uuid4()
    user = make_user(db)
    first = mandate_context_service.create_version(
        db,
        case_id=case_id,
        user=user,
        payload={"objective": "Establish what happened", "key_questions": ["Who authorised it?"]},
    )
    second = mandate_context_service.create_version(
        db,
        case_id=case_id,
        user=user,
        payload={"objective": "Establish responsibility", "key_questions": []},
    )
    assert first["version_number"] == 1
    assert second["version_number"] == 2
    assert db.query(CaseMandateVersion).filter_by(id=UUID(first["id"])).first().objective == "Establish what happened"

    resolved = mandate_context_service.resolve(
        db,
        case_id=case_id,
        version_id=first["id"],
        override={"perspective": "Test the contrary account"},
    )
    assert "Test the contrary account" in resolved.block
    assert resolved.version.objective == "Establish what happened"
    assert str(mandate_context_service.active_version(db, case_id=case_id).id) == second["id"]
    assert mandate_context_service.metadata(db, case_id=case_id, version_id=first["id"])["is_stale"] is True


def test_chat_and_agent_can_share_the_exact_rendered_context(db):
    case_id = uuid4()
    user = make_user(db)
    version = mandate_context_service.create_version(
        db,
        case_id=case_id,
        user=user,
        payload={"objective": "Identify material contradictions", "key_questions": []},
    )
    chat_context = mandate_context_service.resolve(db, case_id=case_id, version_id=version["id"])
    agent_context = mandate_context_service.resolve(db, case_id=case_id, version_id=version["id"])
    assert chat_context.block == agent_context.block
    assert "supporting and contradicting material" in chat_context.block
