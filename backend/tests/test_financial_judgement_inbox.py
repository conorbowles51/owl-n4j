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


if __name__ == '__main__':
    unittest.main()
