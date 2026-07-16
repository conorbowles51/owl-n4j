import unittest
from uuid import uuid4

from postgres.models.chat import ChatConversation, ChatMessage
from routers.chat import ChatRequest
from services.chat_db_service import append_assistant_message, append_user_message


class _FakeScalarQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *_args, **_kwargs):
        return self

    def scalar(self):
        return self.db.current_sequence


class _FakeSession:
    def __init__(self):
        self.current_sequence = 0
        self.added = []

    def query(self, *_args, **_kwargs):
        return _FakeScalarQuery(self)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, ChatMessage):
            self.current_sequence = max(self.current_sequence, item.sequence_number)

    def flush(self):
        return None


class ChatRequestTests(unittest.TestCase):
    def test_chat_request_persists_by_default(self):
        request = ChatRequest(
            question="What happened?",
            case_id=uuid4(),
        )

        self.assertTrue(request.persist)

    def test_chat_request_allows_ephemeral_opt_out(self):
        request = ChatRequest(
            question="What happened?",
            case_id=uuid4(),
            persist=False,
        )

        self.assertFalse(request.persist)

    def test_chat_helpers_can_preserve_user_draft_before_assistant_response(self):
        db = _FakeSession()
        conversation = ChatConversation(
            id=uuid4(),
            case_id=uuid4(),
            owner_user_id=uuid4(),
            title="New conversation",
        )

        user_message = append_user_message(
            db,
            conversation=conversation,
            revision=None,
            user_question="What happened?",
            context_scope="case_overview",
            selected_entity_keys=[],
        )
        assistant_message = append_assistant_message(
            db,
            conversation=conversation,
            revision=None,
            assistant_answer="The provider is unavailable; your question was saved.",
            context_scope="case_overview",
            selected_entity_keys=[],
            sources=None,
            provider="openai",
            model_id="gpt-5-mini",
            result_graph=None,
            cost_record=None,
        )

        self.assertEqual(user_message.role, "user")
        self.assertEqual(user_message.sequence_number, 1)
        self.assertEqual(assistant_message.role, "assistant")
        self.assertEqual(assistant_message.sequence_number, 2)
        self.assertEqual(conversation.title, "What happened?")


if __name__ == "__main__":
    unittest.main()
