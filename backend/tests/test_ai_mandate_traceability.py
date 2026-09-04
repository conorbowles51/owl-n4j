from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent import AgentRun, AgentThread
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.case_context import CaseMandateVersion
from postgres.models.chat import CaseRevision, ChatConversation, ChatMessage
from postgres.models.enums import GlobalRole
from postgres.models.user import User
from services.agent import storage
from services.chat_db_service import append_conversation_turn, create_conversation


TABLES = [
    User.__table__, Case.__table__, CaseMembership.__table__, CaseMandateVersion.__table__,
    CaseRevision.__table__, ChatConversation.__table__, ChatMessage.__table__,
    AgentThread.__table__, AgentRun.__table__,
]


def test_chat_and_agent_records_retain_mandate_version_and_override():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(
        email="trace@example.test", name="Trace", password_hash="x",
        global_role=GlobalRole.super_admin,
    )
    db.add(user)
    db.flush()
    case = Case(
        title="Traceability", created_by_user_id=user.id, owner_user_id=user.id,
    )
    db.add(case)
    db.flush()
    mandate = CaseMandateVersion(
        case_id=case.id, version_number=1, objective="Trace every output",
        key_questions=[], author_user_id=user.id,
    )
    db.add(mandate)
    db.flush()

    conversation = create_conversation(
        db, user=user, case_id=case.id, title="Mandate chat",
        mandate_version_id=mandate.id,
    )
    user_message, assistant_message = append_conversation_turn(
        db,
        conversation=conversation,
        revision=None,
        user_question="What happened?",
        assistant_answer="A cited answer",
        context_scope="case_overview",
        selected_entity_keys=None,
        sources=[],
        provider="openai",
        model_id="test-model",
        result_graph=None,
        cost_record=None,
        mandate_version_id=mandate.id,
        mandate_override={"perspective": "Test the contrary view"},
    )
    assert conversation.mandate_version_id == mandate.id
    assert user_message.mandate_version_id == mandate.id
    assert assistant_message.mandate_version_id == mandate.id
    assert assistant_message.mandate_override == {"perspective": "Test the contrary view"}

    thread = storage.create_thread(
        db, user=user, case_id=case.id, title="Mandate agent",
        mandate_version_id=mandate.id,
    )
    run = storage.create_run(
        db,
        thread=thread,
        user=user,
        provider="openai",
        model_id="test-model",
        input_message="Investigate",
        mandate_override={"constraints": "Do not infer beyond evidence"},
    )
    assert thread.mandate_version_id == mandate.id
    assert run.mandate_version_id == mandate.id
    assert run.mandate_override == {"constraints": "Do not infer beyond evidence"}
    db.close()
    engine.dispose()
