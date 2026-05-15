import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.triage import TriageCase, TriageHashSet, TriageStage, TriageTemplate
from services.triage.hash_lookup_service import HashLookupService
from services.triage.template_service import TemplateService
from services.triage.triage_storage import TriageStorage


TRIAGE_TABLES = [
    TriageCase.__table__,
    TriageStage.__table__,
    TriageTemplate.__table__,
    TriageHashSet.__table__,
]


class TriageStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=TRIAGE_TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=TRIAGE_TABLES)
        self.engine.dispose()

    def test_case_stage_lifecycle(self):
        storage = TriageStorage(session_factory=self.SessionLocal)

        case = storage.create_case(
            name="Laptop triage",
            description="Quick look",
            source_path="C:/evidence/laptop",
            created_by="analyst@example.com",
        )

        self.assertEqual(case["status"], "created")
        self.assertEqual(case["created_by"], "analyst@example.com")
        self.assertEqual([s["type"] for s in case["stages"]], ["scan", "classify", "profile"])
        self.assertEqual(case["scan_stats"]["total_files"], 0)

        listed = storage.list_cases(owner="analyst@example.com")
        self.assertEqual([item["id"] for item in listed], [case["id"]])
        self.assertEqual(storage.list_cases(owner="other@example.com"), [])

        updated = storage.update_case(
            case["id"],
            status="scan_complete",
            scan_cursor="Users/alice",
            scan_stats={
                "total_files": 12,
                "total_size": 4096,
                "os_detected": "windows",
            },
        )
        self.assertEqual(updated["scan_cursor"], "Users/alice")
        self.assertEqual(updated["scan_stats"]["total_files"], 12)
        self.assertEqual(updated["scan_stats"]["os_detected"], "windows")

        scan_stage = next(s for s in updated["stages"] if s["type"] == "scan")
        stage = storage.update_stage(
            case["id"],
            scan_stage["id"],
            status="completed",
            files_total=12,
            files_processed=12,
        )
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["files_processed"], 12)

        custom = storage.add_stage(
            case["id"],
            name="Extract text",
            stage_type="custom",
            config={
                "processor_name": "text_extractor",
                "config": {"max_pages": 10},
                "file_filter": {"category": "documents"},
            },
        )
        self.assertEqual(custom["order"], 3)
        self.assertEqual(custom["config"]["processor_name"], "text_extractor")

        self.assertTrue(storage.remove_stage(case["id"], custom["id"]))
        self.assertIsNone(storage.get_stage(case["id"], custom["id"]))

        self.assertTrue(storage.delete_case(case["id"]))
        self.assertIsNone(storage.get_case(case["id"]))
        self.assertFalse(storage.delete_case(case["id"]))

    def test_templates_and_hash_sets_are_postgres_backed(self):
        storage = TriageStorage(session_factory=self.SessionLocal)
        templates = TemplateService(session_factory=self.SessionLocal)
        hashes = HashLookupService(session_factory=self.SessionLocal)

        case = storage.create_case(
            name="Desktop triage",
            source_path="/evidence/desktop",
            created_by="analyst@example.com",
        )
        storage.add_stage(
            case["id"],
            name="Browser parse",
            stage_type="custom",
            config={
                "processor_name": "browser_parser",
                "config": {"max_entries": 25},
                "file_filter": {"category": "databases"},
            },
        )

        second_case = storage.create_case(
            name="Second desktop",
            source_path="/evidence/desktop2",
            created_by="analyst@example.com",
        )
        with self.SessionLocal() as db:
            template = templates.save_template(
                case["id"],
                "Browser workflow",
                "Parse browser databases",
                "analyst@example.com",
                db=db,
            )
            self.assertEqual(template["stage_count"], 1)
            self.assertEqual(templates.list_templates(db=db)[0]["name"], "Browser workflow")

            created = templates.apply_template(template["id"], second_case["id"], db=db)
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0]["config"]["processor_name"], "browser_parser")
            self.assertTrue(templates.delete_template(template["id"], db=db))
            self.assertEqual(templates.list_templates(db=db), [])

        valid_hash = "a" * 64
        invalid_hash = "not-a-sha256"
        count = hashes.add_custom_hash_set(
            "known-bad-test",
            [valid_hash, invalid_hash, valid_hash.upper()],
            created_by="analyst@example.com",
        )
        self.assertEqual(count, 1)
        self.assertEqual(hashes.list_custom_sets(), [{"name": "known-bad-test", "count": 1}])
        self.assertEqual(hashes.lookup_custom_bulk([valid_hash]), {valid_hash: ("known-bad-test", "custom_match")})


if __name__ == "__main__":
    unittest.main()
