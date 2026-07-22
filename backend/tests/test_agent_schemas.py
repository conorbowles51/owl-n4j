import unittest
from uuid import uuid4

from pydantic import ValidationError

from services.agent.schemas import AgentMessageRequest


class AgentMessageRequestTests(unittest.TestCase):
    def test_agent_request_defers_model_selection_to_central_policy(self):
        request = AgentMessageRequest(
            message="Who is Marcus?",
            case_id=uuid4(),
        )

        self.assertIsNone(request.provider)
        self.assertIsNone(request.model)
        self.assertEqual(request.artifact_preference, "auto")
        self.assertEqual(request.case_layer, "all")
        self.assertTrue(request.persist)

    def test_agent_request_accepts_significant_case_layer(self):
        request = AgentMessageRequest(
            message="Build a report from the focused investigation",
            case_id=uuid4(),
            case_layer="significant",
        )

        self.assertEqual(request.case_layer, "significant")

    def test_agent_request_rejects_blank_message(self):
        with self.assertRaises(ValidationError):
            AgentMessageRequest(
                message="   ",
                case_id=uuid4(),
            )


if __name__ == "__main__":
    unittest.main()
