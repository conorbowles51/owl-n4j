from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PublicTimestampOptInTests(unittest.TestCase):
    def test_script_requires_explicit_network_opt_in_before_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'timestamp'
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/check_public_financial_timestamp.py'),
                '--output',str(output)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,2)
            self.assertIn('Explicit --submit-synthetic is required',result.stderr)
            self.assertFalse(output.exists())
