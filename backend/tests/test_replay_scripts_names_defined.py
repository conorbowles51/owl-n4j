"""Every name a replay script's functions read is defined in that function, at module level or as a builtin.
R10 probe, 11 Nov 22:33: financial_agent_fit_replay.main() used _financial_session, storage and uuid, imported only
inside prepare(); the run spent 542 k DeepSeek tokens and then crashed before writing its answer. Fails on that code."""
import ast
import builtins
import os
import symtable
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ('financial_agent_fit_replay.py', 'financial_agent_trace_replay.py', 'financial_agent_collapse_check.py')


def undefined_names(path: str) -> list[str]:
    src = open(path).read()
    top = symtable.symtable(src, path, 'exec')
    module_names = set(top.get_identifiers())
    missing = []

    def walk(table, scope_name):
        for child in table.get_children():
            for sym in child.get_symbols():
                name = sym.get_name()
                if (sym.is_global() and sym.is_referenced() and name not in module_names
                        and not hasattr(builtins, name)):
                    missing.append('%s.%s:%s' % (scope_name, child.get_name(), name))
            walk(child, '%s.%s' % (scope_name, child.get_name()))

    walk(top, os.path.basename(path))
    return missing


class ReplayScriptNamesTests(unittest.TestCase):
    def test_no_function_reads_an_undefined_name(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                self.assertEqual(undefined_names(os.path.join(BACKEND, 'scripts', name)), [])


if __name__ == '__main__':
    unittest.main()
