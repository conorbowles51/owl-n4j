import unittest
from uuid import uuid4

from routers.chat import ChatRequest


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


if __name__ == "__main__":
    unittest.main()
