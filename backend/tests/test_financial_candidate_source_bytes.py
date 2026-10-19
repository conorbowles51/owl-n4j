import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from services.financial import candidate_source_bytes as module
from services.financial.candidate_store import CandidateStoreError
from tests import test_financial_candidate_store as fixtures


class CandidateSourceBytesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CandidateStoreTests()
        self.fixture.setUp()
        self.directory = tempfile.TemporaryDirectory(prefix="loupe-neilbyrne-bytes-")
        self.path = Path(self.directory.name) / "synthetic.pdf"
        self.data = b"%PDF-1.4\nsynthetic source bytes\n"
        self.path.write_bytes(self.data)
        f = self.fixture
        f.evidence.sha256 = hashlib.sha256(self.data).hexdigest()
        f.evidence.stored_path = "trusted-storage-key"
        f.db.commit()
        f.mapping["source_revision"] = f.revision()
        self.saved = f.save()
        self.candidate = UUID(self.saved["candidates"][0]["id"])
        self.resolver = Mock(return_value=self.path)

    def tearDown(self):
        self.fixture.tearDown()
        self.directory.cleanup()

    def verify(self, **updates):
        params = dict(case_id=self.fixture.case, candidate_id=self.candidate, resolve_path=self.resolver)
        params.update(updates)
        return module.verify_candidate_source_bytes(self.fixture.db, **params)

    def test_matching_bytes_do_not_modify_original_or_resolve_candidate(self):
        result = self.verify()
        self.assertTrue(result["file_bytes_verified"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["byte_count"], len(self.data))
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())
        self.resolver.assert_called_once_with("trusted-storage-key")
        self.assertEqual(self.fixture.read(self.saved), {k: v for k, v in self.saved.items() if k != "created"})
        self.assertFalse(self.fixture.db.new or self.fixture.db.dirty)
        self.assertFalse(self.saved["original"]["file_bytes_verified"])

    def test_wrong_case_and_unknown_candidate_never_resolve_a_path(self):
        for update in (dict(case_id=uuid4()), dict(candidate_id=uuid4())):
            with self.assertRaises(CandidateStoreError) as error:
                self.verify(**update)
            self.assertEqual(error.exception.status_code, 404)
        self.resolver.assert_not_called()

    def test_stale_geometry_refused_before_file_access(self):
        self.fixture.geometry.payload = []
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.verify()
        self.resolver.assert_not_called()

    def test_changed_recorded_digest_refused_before_file_access(self):
        self.fixture.evidence.sha256 = "b" * 64
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.verify()
        self.resolver.assert_not_called()

    def test_changed_actual_bytes_refused_even_when_database_is_unchanged(self):
        self.path.write_bytes(b"%PDF-1.4\na different source\n")
        with self.assertRaisesRegex(CandidateStoreError, "do not match"):
            self.verify()

    def test_missing_file_and_resolver_failure_do_not_disclose_paths(self):
        self.path.unlink()
        for failure in (None, OSError("private path /secret")):
            self.resolver.side_effect = failure
            with self.assertRaises(CandidateStoreError) as error:
                self.verify()
            self.assertEqual(str(error.exception), "Source file is unavailable for byte verification.")

    def test_unresolved_source_is_refused(self):
        self.resolver.return_value = None
        with self.assertRaises(CandidateStoreError):
            self.verify()

    def test_fifo_refused_without_waiting_for_a_writer(self):
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaisesRegex(CandidateStoreError, "regular file"):
            self.verify()

    def test_size_limit_refused_before_read(self):
        with patch.object(module, "MAX_SOURCE_BYTES", len(self.data) - 1):
            with self.assertRaises(CandidateStoreError) as error:
                self.verify()
        self.assertEqual(error.exception.status_code, 422)

    def test_multi_chunk_hash_matches_without_loading_whole_file(self):
        with patch.object(module, "_CHUNK_BYTES", 3):
            self.assertEqual(self.verify()["sha256"], hashlib.sha256(self.data).hexdigest())

    def test_mutation_during_read_is_refused_even_if_digest_would_match(self):
        original_fstat = os.fstat
        calls = 0

        def changing_stat(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                with self.path.open("ab") as writer:
                    writer.write(b"changed after reading")
            return original_fstat(fd)

        with patch.object(module.os, "fstat", side_effect=changing_stat):
            with self.assertRaisesRegex(CandidateStoreError, "changed during"):
                self.verify()
