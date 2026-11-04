import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from services.financial import judgement_inbox


def item(n):
    return dict(id=f'{n:08d}-0000-0000-0000-000000000000', status='corrected', case_id='c' * 36,
                rule_id='L1.glyph_cell', evidence={}, resolution_reason='wrong digit', resolved_at='2026-10-30')


class InboxConcurrencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.inbox = Path(directory.name) / 'inbox.md'
        for name, value in (('INBOX', self.inbox), ):
            patcher = mock.patch.object(judgement_inbox, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def race(self, *items):
        # Both writers pass the "already in the inbox?" check before either writes, the moment the old code raced on.
        barrier = threading.Barrier(len(items), timeout=10)

        def statement(session, it):
            barrier.wait()
            return 'statement.pdf'
        with mock.patch.object(judgement_inbox, '_statement', statement):
            threads = [threading.Thread(target=judgement_inbox.append_correction, args=(None, it)) for it in items]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)

    def test_corrections_at_the_same_moment_write_one_header_and_each_line_once(self):
        self.race(item(1), item(2))
        self.race(item(3), item(3))
        text = self.inbox.read_text()
        self.assertEqual(text.count('# Judgement corrections'), 1)
        self.assertTrue(text.startswith(judgement_inbox.HEADER))
        for n in (1, 2, 3):
            self.assertEqual(text.count(f'judgement {item(n)["id"]}'), 1)


class JobsLoginCorrectionsTests(unittest.TestCase):
    """The automated-checks login's corrections are tests, not lessons (followups m110400110314678: two live checks
    in the verification case opened the lesson job twice)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.inbox = Path(directory.name) / 'inbox.md'
        patcher = mock.patch.object(judgement_inbox, 'INBOX', self.inbox)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_jobs_login_correction_is_not_a_lesson(self):
        self.assertFalse(judgement_inbox.append_correction(None, item(1), statement='s.pdf',
                                                           actor_email='Jobs-Verify@loupe.invalid'))
        self.assertFalse(judgement_inbox.append_correction(
            None, dict(item(2), resolved_by_email='jobs-verify@loupe.invalid'), statement='s.pdf'))
        self.assertTrue(judgement_inbox.append_correction(None, item(3), statement='s.pdf',
                                                          actor_email='analyst@example.test'))
        text = self.inbox.read_text()
        self.assertNotIn(item(1)['id'], text)
        self.assertNotIn(item(2)['id'], text)
        self.assertIn(item(3)['id'], text)

    def test_missing_does_not_count_jobs_login_corrections(self):
        rows = [(item(1)['id'], 'jobs-verify@loupe.invalid'), (item(2)['id'], 'analyst@example.test')]
        session = mock.Mock()
        session.execute.return_value = rows
        self.assertEqual(judgement_inbox.missing(session), [item(2)['id']])


if __name__ == '__main__':
    unittest.main()
