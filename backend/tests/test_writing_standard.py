"""Loupe's writing standard (docs/writing-standard.md): the lint, the prompt helper on every model request, and the
post-check on generated text."""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import writing_standard  # noqa: E402


def _lint_module():
    spec = importlib.util.spec_from_file_location("check_writing", ROOT / "scripts" / "check_writing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the lint -------------------------------------------------------------------------------------------------

def test_lint_catches_a_seeded_banned_word_phrase_and_internal_term():
    lint = _lint_module()
    rows = [
        {"file": "frontend_v2/src/x.tsx", "line": 1, "text": "Leverage the ledger to delve into payments."},
        {"file": "frontend_v2/src/x.tsx", "line": 2, "text": "Saved successfully. It's important to note the total."},
        {"file": "backend/routers/x.py", "line": 3, "text": "case_id is required", "internal": True},
        {"file": "frontend_v2/src/x.tsx", "line": 4, "text": "Checked against the statement's printed balances."},
    ]
    hits = lint.check(rows)
    found = {(row["line"], p.match.lower()) for row, p in hits}
    assert {(1, "leverage"), (1, "delve"), (2, "successfully"), (2, "it's important to note"), (3, "case_id")} <= found
    assert not [h for h in hits if h[0]["line"] == 4]


def test_lint_never_judges_quoted_evidence_or_links():
    problems = writing_standard.find_problems('The message read "we leverage cash" [p.2](doc://abc/2) `case_id`')
    assert problems == []


def test_backend_messages_and_reports_pass_the_lint():
    lint = _lint_module()
    hits = lint.check(lint.backend_strings())
    assert not hits, "\n".join(f"{r['file']}:{r['line']} {p.match!r}: {r['text'][:120]}" for r, p in hits)


def _node_with_typescript() -> bool:
    return bool(shutil.which("node")) and (ROOT / "frontend_v2" / "node_modules" / "typescript").exists()


@pytest.mark.skipif(not _node_with_typescript(), reason="screen lint needs node and frontend_v2/node_modules (typescript)")
def test_every_screen_string_passes_the_lint():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_writing.py")], capture_output=True, text=True,
                          timeout=1800)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-1000:]
    total = int(re.search(r"in (\d+) user-facing strings", proc.stderr).group(1))
    assert total > 10000, f"the screen extractor found only {total} strings; it has stopped reading the screens"


# --- every model request carries the standard ----------------------------------------------------------------

REQUEST_PATTERNS = re.compile(
    r"chat\.completions\.create\(|\.responses\.create\(|ChatOpenAI\(|ChatAnthropic\(|ChatGoogleGenerativeAI\("
    r"|api\.deepseek\.com/chat/completions|api\.anthropic\.com/v1/messages|:generateContent"
)
COVERED = re.compile(r"writing_standard|self\._system\(|with_writing_standard\(|reading_prompt\(")
# Functions that send a request built by a caller that already applied the standard, each with that caller.
COVERED_BY_CALLER = {
    "backend/services/llm_service.py::_call_deepseek_vision": "call_vision_json (reading_prompt)",
    "backend/services/agent/graph.py::__init__": "AgentGraphRunner: every SystemMessage is checked below",
    "evidence-engine/app/services/openai_client.py::_openai_chat_completion": "chat_completion (with_writing_standard)",
    "evidence-engine/app/services/openai_client.py::_anthropic_chat_completion": "chat_completion (with_writing_standard)",
    "evidence-engine/app/services/openai_client.py::_gemini_chat_completion": "chat_completion (with_writing_standard)",
    "evidence-engine/app/services/openai_client.py::_deepseek_chat_completion": "chat_completion (with_writing_standard)",
}


def _source_files():
    for base in (BACKEND, ROOT / "evidence-engine" / "app"):
        for path in base.rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if "/tests/" in rel or path.name.startswith("test_") or "/alembic/" in rel or "/benchmarks/" in rel:
                continue
            yield rel, path


def _request_functions():
    """(file::function, source) of every function that builds a model request."""
    found = []
    for rel, path in _source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if not REQUEST_PATTERNS.search(text):
            continue
        tree = ast.parse(text)
        lines = text.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = "\n".join(lines[node.lineno - 1:node.end_lineno])
                inner = [n for n in ast.walk(node) if n is not node and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                for sub in inner:  # a nested function is judged on its own
                    body = body.replace("\n".join(lines[sub.lineno - 1:sub.end_lineno]), "")
                if REQUEST_PATTERNS.search(body):
                    found.append((f"{rel}::{node.name}", body))
    return found


def test_every_model_request_goes_through_the_writing_standard():
    functions = _request_functions()
    assert len(functions) >= 10, "the request scan found too few call sites; the patterns have stopped matching"
    bypass = [name for name, body in functions if not COVERED.search(body) and name not in COVERED_BY_CALLER]
    assert not bypass, f"model requests without the writing standard (services.writing_standard): {bypass}"


def test_every_agent_system_message_carries_the_standard():
    text = (BACKEND / "services" / "agent" / "graph.py").read_text(encoding="utf-8")
    contents = re.findall(r"SystemMessage\(content=([^\n]+)", text)
    assert contents
    allowed = ("writing_standard.system_prompt(", "build_system_prompt(state)", "_final_answer_system_prompt(")
    assert all(c.startswith(allowed) for c in contents), contents
    from services.agent import graph
    assert writing_standard.MARKER in graph._final_answer_system_prompt("rules")
    prompt = graph.render_system_prompt(case_id="c1", significant=False, mandate_context_block="",
                                        artifact_preference="auto", available_artifact_context="")
    assert prompt.count(writing_standard.MARKER) == 1


def _context(provider):
    from services.llm_service import LLMExecutionContext
    with mock.patch("services.llm_service.get_chat_config", return_value={"system_context": "You are Loupe."}):
        return LLMExecutionContext(provider, "model-x", api_key="k")


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_deepseek_text_request_sends_the_standard_in_its_system_message():
    ctx = _context("deepseek")
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return _Response({"choices": [{"message": {"content": "Answer."}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    with mock.patch("services.llm_service.requests.post", side_effect=post), \
            mock.patch("services.ai_costs_service.record_metered_call"):
        ctx.call("Question?")
    system = sent["messages"][0]["content"]
    assert system.startswith("You are Loupe.") and writing_standard.MARKER in system
    assert "Words never to use" in system


def test_openai_json_request_sends_the_short_block():
    ctx = _context("openai")
    sent = {}
    usage = mock.Mock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    reply = mock.Mock(choices=[mock.Mock(message=mock.Mock(content="{}"))], usage=usage)

    def create(**kwargs):
        sent.update(kwargs)
        return reply

    ctx._client = mock.Mock()
    ctx._client.chat.completions.create.side_effect = create
    with mock.patch("services.ai_costs_service.record_metered_call"):
        ctx.call("Give JSON", json_mode=True)
    system = sent["messages"][0]["content"]
    assert writing_standard.MARKER in system and "Free-text fields" in system and "Words never to use" not in system


def test_system_prompt_is_added_once_and_reading_prompts_are_unchanged():
    once = writing_standard.system_prompt("S")
    assert writing_standard.system_prompt(once) == once
    assert writing_standard.system_prompt("S", "reading") == "S"
    assert writing_standard.reading_prompt("Read page 3") == "Read page 3"
    with pytest.raises(ValueError):
        writing_standard.system_prompt("S", "poem")


# --- the post-check ------------------------------------------------------------------------------------------

FIXTURE_ANSWER = (
    "Certainly! Here is what the ledger shows.\n\n"
    "ACME Ltd paid 12,345.67 MXN to Maria Lopez on 3 March 2024 [Statement, p.4](doc://f1/4), in order to settle "
    "invoice 88. The memo line reads \"we utilize the escrow in order to delay\". See txn://abc-123.\n\n"
    "It's important to note that 2 payments are not checked against printed balances.\n\n"
    "I hope this helps. Let me know if you want a table."
)


def test_post_check_keeps_every_fact_and_cleans_the_boilerplate():
    result = writing_standard.post_check(FIXTURE_ANSWER)
    text = result.text
    for fact in ("12,345.67 MXN", "ACME Ltd", "Maria Lopez", "3 March 2024", "(doc://f1/4)", "txn://abc-123",
                 "invoice 88", "2 payments"):
        assert fact in text
    assert re.findall(r"\d[\d,.]*", FIXTURE_ANSWER) == re.findall(r"\d[\d,.]*", text)
    assert '"we utilize the escrow in order to delay"' in text  # a quote is never reworded
    assert "to settle invoice 88" in text and ", in order to settle" not in text
    assert "I hope this helps" not in text and "Let me know" not in text and "Certainly!" not in text
    assert [p.match for p in result.flagged] == ["It's important to note"]


def test_post_check_on_empty_text():
    assert writing_standard.post_check(None).text == ""
    assert writing_standard.clean("") == ""
