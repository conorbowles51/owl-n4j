"""The backend reports the commit it was started from (deploy records a healthy one as last good)."""
import subprocess
import unittest
from unittest.mock import patch

from services import runtime_version


class RuntimeVersionTests(unittest.TestCase):
    def tearDown(self):
        runtime_version._started.update(commit=None, commit_clean=False)

    def test_reads_the_checkout_commit_once_at_startup(self):
        expected = subprocess.run(['git', '-C', str(runtime_version.PROJECT_DIR), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True).stdout.strip()
        recorded = runtime_version.record_started_commit()
        self.assertEqual(recorded['commit'], expected)
        self.assertEqual(runtime_version.started_commit(), recorded)
        # A later pull does not change what the running process reports.
        with patch.object(runtime_version, '_git', side_effect=AssertionError('read again')):
            self.assertEqual(runtime_version.started_commit()['commit'], expected)

    def test_unknown_or_malformed_commit_is_never_reported_as_clean(self):
        with patch.object(runtime_version, '_git', side_effect=RuntimeError('git unavailable')):
            self.assertEqual(runtime_version.record_started_commit(), dict(commit=None, commit_clean=False))
        with patch.object(runtime_version, '_git', side_effect=['not-a-commit', '']):
            self.assertEqual(runtime_version.record_started_commit(), dict(commit=None, commit_clean=False))
        with patch.object(runtime_version, '_git', side_effect=['b' * 40, ' M backend/main.py']):
            self.assertEqual(runtime_version.record_started_commit(), dict(commit='b' * 40, commit_clean=False))
        with patch.object(runtime_version, '_git', side_effect=['b' * 40, '']):
            self.assertEqual(runtime_version.record_started_commit(), dict(commit='b' * 40, commit_clean=True))


if __name__ == '__main__':
    unittest.main()
