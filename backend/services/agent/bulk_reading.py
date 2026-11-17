"""Bulk model reading: a model reads a whole scope in chunks and returns what bears on the question.

One call replaces dozens of narrow lookups. The scope is a conversation or phone window, a document, or any list of
cited records. Every returned item keeps the cite of a record that was in the chunk the model read; a cite the model
invented is dropped and counted. The result says how much was read, what was not, and which model read it. What the
model returns is a model reading, never a person's confirmation.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

CHUNK_CHARS = 12000
MAX_CHUNKS = 40
MAX_ITEM_CHARS = 3000
PHONE_PAGE = 100

Reader = Callable[[str], tuple]  # prompt -> (text, usage)

_PROMPT = """You read records for an investigator and pick out every record that bears on the question.

Question: {question}

Each record starts with its cite in square brackets. Return JSON only:
{{"relevant": [{{"cite": "<the cite exactly as given>", "why": "<one sentence: what the record shows and how it bears on the question>"}}]}}

Rules:
- Include a record when it bears on the question, including when it points against what the question assumes.
- Quote nothing you cannot see. Use only cites that appear in the records below.
- Say nothing about records that do not bear on the question. An empty list is a correct answer.

Records:
{records}
"""


def render_item(item: dict[str, Any]) -> str:
    text = str(item.get("text") or "").strip()
    if len(text) > MAX_ITEM_CHARS:
        text = text[:MAX_ITEM_CHARS] + " [cut: record longer than %d characters]" % MAX_ITEM_CHARS
    return "[%s] %s" % (item["cite"], text)


def chunk_items(items: list[dict[str, Any]], max_chars: int = CHUNK_CHARS) -> list[list[dict[str, Any]]]:
    chunks, cur, size = [], [], 0
    for item in items:
        n = len(render_item(item)) + 1
        if cur and size + n > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(item)
        size += n
    if cur:
        chunks.append(cur)
    return chunks


def _parse(text: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        start, end = str(text).find("{"), str(text).rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            return None
    rel = data.get("relevant") if isinstance(data, dict) else None
    return [r for r in rel if isinstance(r, dict)] if isinstance(rel, list) else None


def read_items(items: list[dict[str, Any]], question: str, reader: Reader, *, chunk_chars: int = CHUNK_CHARS,
               max_chunks: int = MAX_CHUNKS, model_words: str | None = None, of: int | None = None) -> dict[str, Any]:
    """Read ``items`` (each ``{"cite", "text"}``) in chunks. ``of`` is the scope's true size when ``items`` is a
    clipped part of it, so the shortfall is stated."""
    chunks = chunk_items(items, chunk_chars)
    todo, skipped = chunks[:max_chunks], chunks[max_chunks:]
    relevant: dict[str, dict[str, Any]] = {}
    invented = failed = read = 0
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    for part in todo:
        known = {i["cite"] for i in part}
        prompt = _PROMPT.format(question=question, records="\n".join(render_item(i) for i in part))
        try:
            text, used = reader(prompt)
        except Exception:
            logger.exception("Bulk reading chunk failed")
            failed += len(part)
            continue
        usage["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens"):
            usage[k] += int((used or {}).get(k) or 0)
        found = _parse(text)
        if found is None:
            failed += len(part)  # an unreadable answer is an unread chunk, never "nothing relevant"
            continue
        read += len(part)
        for r in found:
            cite = str(r.get("cite") or "").strip()
            if cite not in known:
                invented += 1
                continue
            relevant.setdefault(cite, {"cite": cite, "why": str(r.get("why") or "").strip()})
    unread = sum(len(c) for c in skipped) + failed
    total = of if of is not None else len(items)
    beyond = max(0, total - len(items))
    coverage = "Read %d of %d records in %d chunk%s%s." % (
        read, total, len(todo), "" if len(todo) == 1 else "s", " (%s)" % model_words if model_words else "")
    limits = []
    if failed:
        limits.append("%d records were in chunks the model could not answer; they are unread." % failed)
    if skipped:
        limits.append("%d records were beyond the %d-chunk limit; read them in a narrower scope." % (
            sum(len(c) for c in skipped), max_chunks))
    if beyond:
        limits.append("%d more records are in the scope but were not loaded; narrow the scope or read from the "
                      "next offset." % beyond)
    if invented:
        limits.append("%d returned cites were not among the records read and were dropped." % invented)
    return {"relevant": list(relevant.values()), "records_read": read, "records_in_scope": total,
            "records_unread": unread + beyond, "chunks": len(todo), "dropped_invented_cites": invented,
            "limitation": " ".join(limits) or None, "coverage": coverage, "usage": usage,
            "none_found_words": ("No record in the %d read bears on the question." % read)
            if not relevant and read and not unread and not beyond else None,
            "model_reading": "These are a model's readings of the records, each with the record's own cite. "
                             "A person has not confirmed them."}


def phone_items(conn, case_id, *, people=(), mode="any", start=None, end=None, phones=(), kinds=(), search=None,
                include_groups=True, offset=0, max_items=1500) -> tuple[list[dict[str, Any]], int, int | None]:
    """The messages and calls of a phone scope as cited items, paged to the end or to ``max_items``."""
    from services.agent import phone_tools
    items, total, off = [], 0, offset
    while len(items) < max_items:
        page = phone_tools.messages(conn, case_id, people=people, mode=mode, start=start, end=end, phones=phones,
                                    kinds=kinds, search=search, include_groups=include_groups, offset=off,
                                    limit=min(PHONE_PAGE, max_items - len(items)))
        if page.get("available") is False:
            raise ValueError(str(page.get("reason") or "That phone scope cannot be read."))
        total = int(page.get("total_matching") or 0)
        for r in page.get("items") or []:
            who = r.get("from") or "unknown"
            to = ", ".join(r.get("to") or [])
            head = "%s %s %s on %s" % (r.get("time") or "no time", r.get("kind"), r.get("direction") or "", r.get("phone"))
            body = r.get("body") or r.get("call") or r.get("subject") or ""
            extra = " (recovered deleted copy: sent by %s)" % who if r.get("recovered_deleted") else ""
            att = " attachments: %s" % ", ".join(r["attachments"]) if r.get("attachments") else ""
            items.append({"cite": r["rec"], "text": "%s | from %s to %s | %s%s%s" % (head, who, to, body, extra, att)})
        off = page.get("next_offset")
        if off is None:
            break
    return items, total - offset, off


def document_items(db, case_id, evidence_file_id, *, page_offset=0, max_pages=400) -> tuple[list[dict[str, Any]], int, int | None]:
    """The stored pages of one document as cited items."""
    from services.agent.source_read_tools import read_document_text
    items, total, off, revision = [], 0, page_offset, None
    while len(items) < max_pages:
        data = read_document_text(db, case_id, evidence_file_id, page_offset=off, page_limit=10,
                                  expected_revision=revision)
        revision, total = data.get("revision"), int(data.get("total") or 0)
        for p in data.get("pages") or []:
            items.append({"cite": p["cite"], "text": p.get("text") or ""})
        off = data.get("next_offset")
        if off is None:
            break
    return items, total - page_offset, off


def _model_reader(session, case_id, user_id):
    """The case agent's own model as a Reader, with its cost recorded; returns (reader, words)."""
    from postgres.models.cost_record import CostJobType
    from services.ai_costs_service import CostOperationKind, record_cost
    from services.ai_model_policy import get_workload_model
    from services.ai_provider_credentials import get_provider_api_key
    from services.llm_service import LLMExecutionContext
    provider, model_id = get_workload_model(session, "agent")
    api_key = get_provider_api_key(session, provider)
    if not api_key:
        raise ValueError("No %s key is configured, so a model cannot read this scope." % provider)

    def read(prompt):
        call = LLMExecutionContext(provider, model_id, api_key=api_key)
        text = call.call(prompt, temperature=0.1, json_mode=True, timeout=300)
        usage = call.last_usage or {}
        if any(usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            record_cost(db=session, job_type=CostJobType.AI_ASSISTANT, provider=provider, model_id=model_id,
                        operation_kind=CostOperationKind.CHAT_COMPLETION, prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"), total_tokens=usage.get("total_tokens"),
                        case_id=case_id, user_id=user_id, description="Bulk reading of a scope",
                        extra_metadata={"bulk_reading": True})
        return text, usage
    return read, "read by %s" % model_id


def make_bulk_reading_tools(context):
    from typing import Literal
    from pydantic import BaseModel, Field
    from langchain_core.tools import StructuredTool

    class ReadScopeArgs(BaseModel):
        question: str = Field(..., description="What to look for, in words a reader can apply to each record.")
        scope: Literal["phone", "document"] = Field(..., description=(
            "phone: the messages and calls of a phone window; document: every stored page of one evidence file."))
        people: list[str] = Field(default_factory=list, description="phone: identity keys or names; empty for everyone.")
        phones: list[str] = Field(default_factory=list, description="phone: labels such as C5; empty for every phone.")
        start: str | None = Field(None, description="phone: first day (YYYY-MM-DD) or instant.")
        end: str | None = Field(None, description="phone: last day (YYYY-MM-DD, inclusive) or instant.")
        evidence_file_id: str | None = Field(None, description="document: the evidence file id.")
        offset: int = Field(0, ge=0, description="Continue from next_offset of an earlier result.")

    def read_scope_with_model(question, scope, people=(), phones=(), start=None, end=None,
                              evidence_file_id=None, offset=0):
        from services.agent.tools import _financial_session
        if context.significant_scope:
            return context.result("read_scope_with_model", {}, status="error",
                                  summary="Bulk reading is unavailable in Significant-only mode.",
                                  error="Switch to All data to read a whole scope.")
        import uuid
        try:
            with (context.ledger_session_factory or _financial_session)() as db:
                cid = uuid.UUID(context.case_id)
                reader, words = _model_reader(db, cid, context.user_id)
                if scope == "phone":
                    items, left, nxt = phone_items(db.connection(), cid, people=tuple(people), start=start, end=end,
                                                   phones=tuple(phones), offset=offset)
                else:
                    if not evidence_file_id:
                        raise ValueError("A document scope needs evidence_file_id.")
                    items, left, nxt = document_items(db, cid, evidence_file_id, page_offset=offset)
                out = read_items(items, question, reader, model_words=words, of=max(left, len(items)))
        except ValueError as exc:
            return context.result("read_scope_with_model", {}, status="error", summary=str(exc), error=str(exc))
        out["scope"] = scope
        out["next_offset"] = nxt
        return context.result("read_scope_with_model", out,
                              summary="%s %d relevant." % (out["coverage"], len(out["relevant"])))

    return [StructuredTool.from_function(
        read_scope_with_model, name="read_scope_with_model", args_schema=ReadScopeArgs,
        description=("For: having a model read ALL of a scope (a phone window's messages and calls, or one whole "
                     "document) in chunks and return every record that bears on a question, each with its own cite "
                     "and why. States how much was read and what was not; page on with next_offset. One call "
                     "replaces dozens of narrow lookups. The result is a model reading, not a confirmed fact. "
                     "Not for: counting, or finding a known word (use the search tools)."))]
