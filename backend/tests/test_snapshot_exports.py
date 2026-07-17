import unittest

from services.snapshot_exports import _content_hash, _snapshot_export_scope


class SnapshotExportTests(unittest.TestCase):
    def test_export_scope_excludes_non_snapshot_delivery_fields(self):
        snapshot = {
            "name": "Review snapshot",
            "case_name": "Alpha",
            "case_version": 3,
            "subgraph": {
                "nodes": [{"key": "person:alice", "name": "Alice"}],
                "links": [{"source": "person:alice", "target": "company:acme"}],
            },
            "timeline": [{"date": "2026-05-15", "description": "Interview"}],
            "notes": "Saved review note",
            "chat_history": [{"role": "user", "content": "hidden"}],
            "ai_overview": "hidden",
            "overview": {"hidden": True},
            "citations": {"hidden": True},
            "work_state": {"hidden": True},
        }

        scope = _snapshot_export_scope(snapshot)

        self.assertEqual(scope["name"], "Review snapshot")
        self.assertEqual(scope["subgraph"]["nodes"][0]["key"], "person:alice")
        self.assertEqual(scope["timeline"][0]["description"], "Interview")
        self.assertEqual(scope["notes"], "Saved review note")
        for excluded in (
            "chat_history",
            "ai_overview",
            "overview",
            "citations",
            "work_state",
        ):
            self.assertNotIn(excluded, scope)

    def test_content_hash_tracks_only_export_scope(self):
        snapshot = {
            "name": "Review snapshot",
            "subgraph": {"nodes": [{"key": "person:alice"}], "links": []},
            "timeline": [],
            "notes": "Saved review note",
            "chat_history": [{"role": "user", "content": "first"}],
        }
        altered_excluded = {
            **snapshot,
            "chat_history": [{"role": "user", "content": "second"}],
            "ai_overview": "changed",
        }
        altered_included = {
            **snapshot,
            "notes": "Changed note",
        }

        self.assertEqual(
            _content_hash(_snapshot_export_scope(snapshot)),
            _content_hash(_snapshot_export_scope(altered_excluded)),
        )
        self.assertNotEqual(
            _content_hash(_snapshot_export_scope(snapshot)),
            _content_hash(_snapshot_export_scope(altered_included)),
        )


if __name__ == "__main__":
    unittest.main()
