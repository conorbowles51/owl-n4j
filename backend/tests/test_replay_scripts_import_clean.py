"""A test that imports a replay script to reach a helper must not turn its own process read-only. Head 080c7be0:
test_agent_fit_replay_score and test_agent_trace_replay_cache imported scripts that set PGOPTIONS read-only and
replaced socket.getaddrinfo on import; 970 later tests in the same run refused CREATE DATABASE/SCHEMA. Fails on the
code before: importing either script changed both. Each import runs in a fresh interpreter."""
import ast
import json
import os
import re
import subprocess
import sys
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ('financial_agent_fit_replay.py', 'financial_agent_trace_replay.py', 'financial_agent_collapse_check.py')

PROBE = r'''
import importlib.util, json, os, socket, sys
before = (os.environ.get('PGOPTIONS'), socket.getaddrinfo)
spec = importlib.util.spec_from_file_location('probe', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
on_import = dict(pgoptions=os.environ.get('PGOPTIONS'), socket_same=socket.getaddrinfo is before[1])
mod.guard_process() if hasattr(mod, 'guard_process') else mod.fit_replay.guard_process()
pg_once = os.environ.get('PGOPTIONS')
guard = socket.getaddrinfo
mod.guard_process() if hasattr(mod, 'guard_process') else mod.fit_replay.guard_process()
try:
    socket.getaddrinfo('api.openai.com', 443)
    refused = False
except OSError as exc:
    refused = 'may not be called' in str(exc)
print(json.dumps(dict(on_import=on_import, guarded=pg_once, twice_same=os.environ.get('PGOPTIONS') == pg_once
                      and socket.getaddrinfo is guard, refused=refused)))
'''


class ReplayScriptImportTests(unittest.TestCase):
    def run_probe(self, name):
        env = {k: v for k, v in os.environ.items() if k != 'PGOPTIONS'}
        out = subprocess.run([sys.executable, '-c', PROBE, os.path.join(BACKEND, 'scripts', name)], cwd=BACKEND,
                             env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_importing_a_replay_script_leaves_sessions_writable_and_sockets_alone(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                got = self.run_probe(name)
                self.assertEqual(got['on_import'], dict(pgoptions=None, socket_same=True))

    def test_a_replay_run_still_guards_its_process_once(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                got = self.run_probe(name)
                self.assertEqual(got['guarded'], '-c default_transaction_read_only=on')
                self.assertTrue(got['twice_same'])
                self.assertTrue(got['refused'])

    def test_no_test_imports_a_script_that_guards_its_process_on_import(self):
        """Any script a test reaches (by file path or by module name) sets no PGOPTIONS and replaces no
        socket.getaddrinfo at module level; the replay scripts that do are only ever run, never imported."""
        scripts = {f[:-3] for f in os.listdir(os.path.join(BACKEND, 'scripts')) if f.endswith('.py')}
        tests_dir = os.path.join(BACKEND, 'tests')
        reached = set()
        for name in os.listdir(tests_dir):
            if name.endswith('.py'):
                text = open(os.path.join(tests_dir, name), encoding='utf-8').read()
                reached |= scripts & set(re.findall(r'\w+', text))
        offenders = []
        for script in sorted(reached):
            tree = ast.parse(open(os.path.join(BACKEND, 'scripts', script + '.py'), encoding='utf-8').read())
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    target = ast.unparse(node.targets[0])
                    if target in ("os.environ['PGOPTIONS']", 'socket.getaddrinfo'):
                        offenders.append(f'{script}: {target}')
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
