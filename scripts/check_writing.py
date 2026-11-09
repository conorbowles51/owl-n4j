#!/usr/bin/env python3
"""Lint every user-facing string against Loupe's writing standard (docs/writing-standard.md).

Reads the banned words, phrases and internal terms from shared/writing-standard.json (the same source the model
prompts and the post-check use). Checks:
  * screens: every user-facing string in frontend_v2/src (JSX text, readable attributes, toasts, readable object
    properties), extracted by scripts/writing_strings.cjs with the TypeScript parser;
  * backend messages people see: HTTPException details and the text of the report generators listed in the JSON.
Exit 1 with one line per hit (file:line, kind, match, text); exit 0 when clean. ``--count`` prints totals only;
``--backend-only`` skips the screens (no node needed).
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from services.writing_standard import find_problems, standard  # noqa: E402


def _exempt(file: str, match: str) -> bool:
    for rule in standard().get("lint_exempt", []):
        if rule["file"] == file and ("match" not in rule or match in rule["match"]):
            return True
    return False


def screen_strings(target: str | None = None):
    cmd = ["node", str(ROOT / "scripts" / "writing_strings.cjs")] + ([target] if target else [])
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        yield json.loads(line)


def _const_text(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return " … ".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _http_details(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "HTTPException":
            cands = [k.value for k in node.keywords if k.arg == "detail"] + list(node.args[1:2])
            for c in cands:
                t = _const_text(c)
                if t:
                    yield c.lineno, t


def _docstring_nodes(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _report_text(tree):
    """Prose constants in a report generator: strings with at least three words (not docstrings)."""
    docs = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if id(node) in docs:
            continue
        t = _const_text(node) if isinstance(node, (ast.Constant, ast.JoinedStr)) else None
        if t and len(t.split()) >= 3:
            yield node.lineno, t


def _is_query(text: str) -> bool:
    import re
    return bool(re.search(r"\b(SELECT|MATCH|INSERT|UPDATE|DELETE|MERGE|RETURN)\b", text))


def backend_strings():
    files = sorted((ROOT / "backend" / "routers").glob("*.py")) + sorted((ROOT / "backend" / "services").rglob("*.py"))
    reports = set(standard().get("report_generators", []))
    for path in files:
        rel = str(path.relative_to(ROOT))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for line, text in _http_details(tree):
            yield {"file": rel, "line": line, "kind": "error", "text": text, "internal": True}
        if rel in reports:
            for line, text in _report_text(tree):
                # Internal terms in report prose: on once the exhibit caveats speak without proof-class codes
                # ("report_internal_terms" in the JSON); query text (SQL, Cypher) is never prose.
                internal = bool(standard().get("report_internal_terms")) and not _is_query(text)
                yield {"file": rel, "line": line, "kind": "report", "text": text, "internal": internal}


def check(rows):
    hits = []
    for row in rows:
        for p in find_problems(row["text"], internal_terms=row.get("internal", True)):
            if not _exempt(row["file"], p.match):
                hits.append((row, p))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--backend-only", action="store_true")
    ap.add_argument("--screens", help="a file or folder under frontend_v2/src instead of all of it")
    args = ap.parse_args(argv)
    rows = list(backend_strings())
    if not args.backend_only:
        rows += list(screen_strings(args.screens))
    hits = check(rows)
    if not args.count:
        for row, p in hits:
            print(f"{row['file']}:{row['line']}: {p.kind} '{p.match}' in: {row['text'][:160]}")
    by_kind = {}
    for row, p in hits:
        by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
    print(f"writing standard: {len(hits)} hit(s) in {len(rows)} user-facing strings {by_kind}", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
