import unittest
import uuid
from types import SimpleNamespace

from services.agent import storage
from services.agent.json_utils import POSTGRES_NULL_REPLACEMENT, sanitize_text, to_jsonable, truncate_payload


class AgentJsonUtilsTests(unittest.TestCase):
    def test_to_jsonable_sanitizes_postgres_null_characters_recursively(self):
        safe = to_jsonable(
            {
                "bad\x00key": [
                    "restauraci\x00on",
                    {"nested": "value\x00with\x00nulls"},
                ],
            }
        )

        self.assertNotIn("\x00", repr(safe))
        self.assertIn(f"bad{POSTGRES_NULL_REPLACEMENT}key", safe)
        self.assertEqual(safe[f"bad{POSTGRES_NULL_REPLACEMENT}key"][0], f"restauraci{POSTGRES_NULL_REPLACEMENT}on")
        self.assertEqual(
            safe[f"bad{POSTGRES_NULL_REPLACEMENT}key"][1]["nested"],
            f"value{POSTGRES_NULL_REPLACEMENT}with{POSTGRES_NULL_REPLACEMENT}nulls",
        )

    def test_truncate_payload_sanitizes_text_before_persistence(self):
        safe = truncate_payload({"preview": "abc\x00def"}, max_text_chars=20)

        self.assertEqual(safe["preview"], f"abc{POSTGRES_NULL_REPLACEMENT}def")

    def test_agent_tool_trace_storage_sanitizes_json_and_text_columns(self):
        class FakeDb:
            def __init__(self):
                self.records = []

            def add(self, record):
                self.records.append(record)

            def flush(self):
                return None

        db = FakeDb()
        run = SimpleNamespace(id=uuid.uuid4())

        records = storage.persist_tool_trace(
            db,
            run=run,
            trace=[
                {
                    "name": "search\x00graph",
                    "arguments": {"query": "Sender\x00"},
                    "status": "success",
                    "summary": "Found bad\x00text",
                    "error": None,
                    "result_preview": {"entities": [{"summary": "restauraci\x00on"}]},
                }
            ],
        )

        record = records[0]
        self.assertEqual(record.name, f"search{POSTGRES_NULL_REPLACEMENT}graph")
        self.assertEqual(record.arguments["query"], f"Sender{POSTGRES_NULL_REPLACEMENT}")
        self.assertEqual(record.summary, f"Found bad{POSTGRES_NULL_REPLACEMENT}text")
        self.assertEqual(record.result_preview["entities"][0]["summary"], f"restauraci{POSTGRES_NULL_REPLACEMENT}on")
        self.assertNotIn("\x00", repr(record.arguments))
        self.assertNotIn("\x00", repr(record.result_preview))

    def test_sanitize_text_handles_none_as_empty_string(self):
        self.assertEqual(sanitize_text(None), "")


if __name__ == "__main__":
    unittest.main()
