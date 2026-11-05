#!/usr/bin/env python3
"""Can the old backend stay up beside the schema of this release?

The rule: a release hands over from the old backend to the new one only when every pending migration is additive: it
creates tables or indexes, or adds columns the old code need not fill. The old code never reads what it does not know
and every write it makes still succeeds. Anything else (dropping, renaming, changing a column, a new constraint on an
existing table, changing rows, any operation not listed here) uses today's path, a restart: the backend that runs on
the new schema then has the new code a moment later. So does a migration this script cannot read.

Run from backend/ with the backend's interpreter; prints one line: "none", "additive <n> ..." or "unsafe <revision>:
<reason>". Read only.
"""
import ast
import re
import sys

ADDING = re.compile(r'^(create\s+table|create\s+index|create\s+unique\s+index|create\s+extension|comment\s+on)\b', re.I)


ALTER_TABLE = re.compile(r'^alter\s+table\s+(if\s+exists\s+)?(only\s+)?\S+\s+', re.I)
ADD_COLUMN = re.compile(r'^add\s+(column\s+)?', re.I)
NOT_ONLY_ADDING = re.compile(r'\b(drop|rename|constraint|type|references|unique|check|primary|exclude|generated|foreign)\b',
                             re.I)


def _clauses(body):
    """The comma-separated actions of an ALTER TABLE, ignoring commas in brackets."""
    parts, depth, current = [], 0, ''
    for character in body:
        depth += (character == '(') - (character == ')')
        if character == ',' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += character
    return [part.strip() for part in parts + [current]]


def _adds_a_column(clause):
    if not ADD_COLUMN.match(clause) or NOT_ONLY_ADDING.search(clause):
        return False
    return not re.search(r'\bnot\s+null\b', clause, re.I) or re.search(r'\bdefault\b', clause, re.I) is not None


def _adds(statement):
    """A statement that only adds: a table, an index, or columns the old code need not fill."""
    if ADDING.match(statement):
        return True
    table = ALTER_TABLE.match(statement)
    return table is not None and all(_adds_a_column(clause) for clause in _clauses(statement[table.end():]))


def _sql_strings(node, names=None):
    """The literal SQL of an op.execute argument (or the module constant it names), or None when it is computed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and names:
        return names.get(node.id)
    if isinstance(node, ast.Call) and node.args and getattr(node.func, 'attr', getattr(node.func, 'id', '')) == 'text':
        return _sql_strings(node.args[0], names)
    return None


def _module_strings(tree):
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                names[node.targets[0].id] = node.value.value
    return names


def _statements(sql):
    without_comments = re.sub(r'--[^\n]*', '', sql)
    return [part.strip() for part in without_comments.split(';') if part.strip()]


def _keyword(call, name):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_constant(node, value):
    return isinstance(node, ast.Constant) and node.value is value


def _table_name(call, position=0):
    if len(call.args) > position and isinstance(call.args[position], ast.Constant):
        return call.args[position].value
    named = _keyword(call, 'table_name')
    return named.value if isinstance(named, ast.Constant) else None


def _old_code_cannot_fill(column):
    """An added column with NOT NULL and no default: the old code's inserts would fail."""
    if not isinstance(column, ast.Call):
        return True
    if _is_constant(_keyword(column, 'unique'), True) or _is_constant(_keyword(column, 'primary_key'), True):
        return True
    return _is_constant(_keyword(column, 'nullable'), False) and _keyword(column, 'server_default') is None


class _Operations(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_FunctionDef(self, node):
        if node.name != 'downgrade':
            self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == 'op':
            self.calls.append((func.attr, node))
        self.generic_visit(node)


def problems(source):
    """Why this migration's upgrade is not additive; empty when it is. Everything outside ``downgrade`` counts,
    helpers included."""
    tree = ast.parse(source)
    names = _module_strings(tree)
    operations = _Operations()
    operations.visit(tree)
    created = {_table_name(call) for name, call in operations.calls if name == 'create_table'}
    found = []
    for name, call in operations.calls:
        if name in ('create_table', 'f'):
            continue
        if name == 'create_index':
            if _is_constant(_keyword(call, 'unique'), True) and _table_name(call, 1) not in created:
                found.append('a unique index on an existing table')
            continue
        if name == 'add_column':
            if len(call.args) < 2 or _old_code_cannot_fill(call.args[1]):
                found.append('a required column with no default')
            continue
        if name in ('create_check_constraint', 'create_foreign_key', 'create_unique_constraint'):
            if _table_name(call, 1) not in created:
                found.append(f'{name} on an existing table')
            continue
        if name == 'execute':
            sql = _sql_strings(call.args[0], names) if call.args else None
            if sql is None:
                found.append('SQL this check cannot read')
            else:
                for statement in _statements(sql):
                    if not _adds(statement):
                        found.append(f'SQL: {statement[:50]}')
                    elif re.match(r'create\s+unique', statement, re.I):
                        found.append('a unique index in SQL')
            continue
        found.append(f'op.{name}')
    return found


def verdict(paths):
    for revision, path in paths:
        with open(path, encoding='utf-8') as handle:
            found = problems(handle.read())
        if found:
            return f'unsafe {revision}: {found[0]}'
    return f'additive {len(paths)}' if paths else 'none'


def pending():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        current = [row[0] for row in session.execute(text('select version_num from alembic_version'))]
    script = ScriptDirectory.from_config(Config('alembic.ini'))
    return [(item.revision, item.path) for item in script.iterate_revisions(script.get_heads(), current)]


def main():
    try:
        print(verdict(pending()))
    except Exception as error:  # noqa: BLE001 - not known to be safe is unsafe
        print(f'unsafe unknown: the pending migrations could not be read ({type(error).__name__})')
    return 0


if __name__ == '__main__':
    sys.path.insert(0, '.')
    sys.exit(main())
