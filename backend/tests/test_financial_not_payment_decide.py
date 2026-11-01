"""not_payment_statements.decide: a statement already as asked is left untouched (no decision written, no
reassessment) and says so with ``changed=False``. Invented data only."""
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

from services.financial import not_payment_statements as nps

CASE, FILE_ID = uuid.uuid4(), uuid.uuid4()
ACTOR = SimpleNamespace(user_id=uuid.uuid4(), name='Alex Reviewer')
SET_ASIDE = dict(kind=nps.KIND, status='set_aside', label=nps.LABEL)


class FakeSession:
    def __init__(self, file):
        self.results = [CASE, file]
        self.rolled_back = self.committed = False

    def scalar(self, _query):
        return self.results.pop(0)

    def flush(self):
        pass

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        self.committed = True


class DecideTests(unittest.TestCase):
    def run_decide(self, action, readings, metadata=None):
        file = SimpleNamespace(id=FILE_ID, metadata_=metadata or {})
        session = FakeSession(file)
        reads = iter(readings)
        with mock.patch.object(nps, 'ENABLED', True), \
                mock.patch('services.financial.statement_import.read_statement_import',
                           side_effect=lambda *a, **k: next(reads)), \
                mock.patch.object(nps, 'reassess_items', return_value=0) as reassess, \
                mock.patch('services.financial.import_batches.refresh_file_readiness'):
            result = nps.decide(session, case_id=CASE, evidence_file_id=FILE_ID, statement_id='s1', action=action,
                                actor=ACTOR)
        return result, file, session, reassess

    def test_putting_back_a_statement_nobody_set_aside_writes_nothing(self):
        result, file, session, reassess = self.run_decide('restore', [{'not_payment_statement': None}])
        self.assertFalse(result['changed'])
        self.assertEqual(file.metadata_, {})
        self.assertFalse(session.committed)
        reassess.assert_not_called()

    def test_putting_back_a_set_aside_statement_records_the_decision(self):
        result, file, session, reassess = self.run_decide(
            'restore', [{'not_payment_statement': SET_ASIDE}, {'not_payment_statement': None}])
        self.assertTrue(result['changed'])
        self.assertEqual(file.metadata_[nps.METADATA_KEY]['s1']['status'], 'restored')
        self.assertTrue(session.committed)
        reassess.assert_called_once()

    def test_setting_aside_a_statement_already_set_aside_writes_nothing(self):
        result, file, _session, _reassess = self.run_decide('set_aside', [{'not_payment_statement': SET_ASIDE}])
        self.assertFalse(result['changed'])
        self.assertEqual(file.metadata_, {})

    def test_setting_aside_a_put_back_statement_records_the_decision(self):
        metadata = {nps.METADATA_KEY: {'s1': dict(status='restored')}}
        result, file, _session, _reassess = self.run_decide(
            'set_aside', [{'not_payment_statement': None}, {'not_payment_statement': SET_ASIDE}], metadata)
        self.assertTrue(result['changed'])
        self.assertEqual(file.metadata_[nps.METADATA_KEY]['s1']['status'], 'set_aside')


if __name__ == '__main__':
    unittest.main()
