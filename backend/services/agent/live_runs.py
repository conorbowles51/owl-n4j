"""An agent run that outlives its web request, and says in plain words what it is doing while it works.

Before (measured 8 Nov 2026, live run 8df85211, BNB2): a run executed inside its streaming request, so leaving the page
ended it; a batch of tool calls (51 s + 6 s + 56 s) showed nothing new for up to 109 s; Stop was held in the memory of
the one web worker that received it, while the backend runs two.

Now:
- ``LiveRun`` is the run's channel. A daemon thread (``pump``) drives the run's event generator to its end whether or
  not anyone is listening; the streaming response only reads the channel, so a closed tab stops the reading, never
  the run. The run's own database session is closed by the thread when the run ends.
- ``progress_for_tool`` / ``progress_thinking`` / ``progress_writing`` give the plain line for each step ("Checking
  the accounts held by Jose Alejandro Reyes Zeind"). The runner calls the run's ``on_progress`` as each tool call
  starts and before each model turn, so a long batch shows each call as it starts.
- Progress is written to ``agent_runs.extra_metadata['progress']`` by the run's heartbeat
  (``services.agent.run_settle.RunHeartbeat``) at once when it changes, so a person who comes back (another tab, the
  other worker) reads the same run's progress from ``GET /api/agent/runs/{id}``.
- The heartbeat also reads the run's status every ``POLL_SECONDS``: a Stop written by the other worker
  (status ``cancelled``) stops this worker's run within seconds.

Decisions (lx-agentlive, 8 Nov 2026):
- D-a1 Progress lives in the run's metadata JSON, not a new column: no migration, and the run detail already carries
  it. Reverse if progress needs querying across runs.
- D-a2 Re-attaching is polling ``GET /api/agent/runs/{id}`` every 2 s, not a second event stream: two web workers do
  not share memory, and the database is what both read. Reverse if runs move to a shared queue.
- D-a3 A run whose heartbeat is older than ``STALE_SECONDS`` (45 s; beats every 10 s on its own connection, so a
  living run is never that late) is shown as stopped with Retry. The sweep that settles it as interrupted keeps its
  own 90 s (services.agent.run_settle.STALE_AFTER).
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

log = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 5      # a reader with nothing new gets a "progress" ping at least this often
STALE_SECONDS = 45         # a heartbeat older than this: the run's worker is gone (D-a3)
_CLOSED = object()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: Any, limit: int = 70) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value if str(v).strip()]
        if not items:
            return None
        text = ", ".join(items[:3]) + (f" and {len(items) - 3} more" if len(items) > 3 else "")
    else:
        text = str(value).strip()
    if not text:
        return None
    # A party or record reference ("party:7baa…", a bare uuid) means nothing to a reader.
    if re.fullmatch(r"(?:[a-z_]+:)?[0-9a-f]{8}-[0-9a-f-]{27,}", text):
        return None
    text = re.sub(r"^[a-z_]+:(?=\S)", "", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _first(args: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = _short(args.get(key))
        if text:
            return text
    return None


# Present tense, plain words, one line per tool family. A tool not named here still gets a plain line (_fallback).
_TOOL_LINES: dict[str, tuple[str, str]] = {
    # name: (line with a subject "{s}", line without one)
    "get_case_overview": ("Reading the case overview", "Reading the case overview"),
    "search_graph_entities": ("Searching people, companies and accounts for “{s}”",
                              "Searching people, companies and accounts"),
    "get_entity_details": ("Reading what the case holds on {s}", "Reading an entity's details"),
    "get_entity_neighborhood": ("Looking at who and what is connected to {s}", "Looking at connections"),
    "find_paths_between_entities": ("Tracing how {s} are connected", "Tracing connections between entities"),
    "run_readonly_cypher": ("Querying the case graph", "Querying the case graph"),
    "inspect_graph_schema": ("Checking what kinds of records the graph holds",
                             "Checking what kinds of records the graph holds"),
    "search_case": ("Searching the whole case for “{s}”", "Searching the whole case"),
    "search_documents": ("Searching the documents for “{s}”", "Searching the documents"),
    "search_exact_words": ("Looking for the exact words “{s}” in the documents",
                           "Looking for exact words in the documents"),
    "get_financial_transactions": ("Reading the payments for {s}", "Reading the payments"),
    "analyze_financial_transactions": ("Adding up the payments for {s}", "Adding up the payments"),
    "get_financial_coverage": ("Checking the accounts held by {s}", "Checking which accounts and statements the case holds"),
    "get_money_between": ("Reading the money between {s}", "Reading the money between two parties"),
    "get_statement_continuity": ("Checking the statements of {s} for gaps", "Checking the statements for gaps"),
    "get_account_mentions": ("Finding accounts named in the evidence but not held: {s}",
                             "Finding accounts named in the evidence but not in the financial records"),
    "get_trades": ("Reading the trades for {s}", "Reading the trades"),
    "get_money_signal_leads": ("Looking for money leads in {s}", "Looking for money leads"),
    "get_money_signal_matches": ("Matching money mentions to payments for {s}", "Matching money mentions to payments"),
    "get_person_phones": ("Finding the phones of {s}", "Finding whose phones the case holds"),
    "get_dossier": ("Reading the dossier on {s}", "Reading a dossier"),
    "phone_coverage": ("Checking which phones the case holds", "Checking which phones the case holds"),
    "phone_messages": ("Reading phone messages about {s}", "Reading phone messages"),
    "phone_contact_summary": ("Reading the phone contacts of {s}", "Reading phone contacts"),
    "phone_find_people": ("Finding {s} in the phones", "Finding people in the phones"),
    "phone_places": ("Reading phone locations for {s}", "Reading phone locations"),
    "phone_money_readings": ("Reading money mentioned in the phones for {s}", "Reading money mentioned in the phones"),
    "phone_colocation_results": ("Checking when {s} were in the same place", "Checking who was in the same place"),
    "phone_record": ("Opening a phone record", "Opening a phone record"),
    "request_clarification": ("Preparing a question for you", "Preparing a question for you"),
}
_SUBJECT_KEYS = ("account_holders", "person", "party", "name", "entity_name", "query", "words", "search", "subject",
                 "dossier", "party_a", "names", "entity_keys", "account", "phrase", "title")


def _fallback(name: str) -> str:
    if name.startswith("propose_"):
        return "Preparing a suggestion for you to review"
    if name.startswith("phone_"):
        return "Reading the phone evidence"
    if "financial" in name or "money" in name or "ledger" in name or "statement" in name:
        return "Reading the financial records"
    if "timeline" in name:
        return "Reading the timeline"
    if "map" in name or "place" in name or "location" in name:
        return "Reading places on the map"
    if "document" in name or "passage" in name:
        return "Reading the documents"
    return "Looking through the case records"


def tool_line(name: str | None, args: dict[str, Any] | None) -> str:
    safe = name or ""
    args = args or {}
    lines = _TOOL_LINES.get(safe)
    if not lines:
        return _fallback(safe)
    subject = _first(args, *_SUBJECT_KEYS)
    if safe == "get_money_between":
        a, b = _short(args.get("party_a")), _short(args.get("party_b"))
        subject = f"{a} and {b}" if a and b else None
    if safe == "find_paths_between_entities":
        a = _first(args, "source", "source_key", "start", "from_entity")
        b = _first(args, "target", "target_key", "end", "to_entity")
        subject = f"{a} and {b}" if a and b else None
    if subject and "{s}" in lines[0]:
        return lines[0].format(s=subject)
    return lines[1]


def progress_for_tool(*, step: int, name: str | None, args: dict[str, Any] | None, index: int = 1,
                      batch: int = 1) -> dict[str, Any]:
    line = tool_line(name, args)
    return {"phase": "tool", "step": step, "title": line, "batch_index": index, "batch_size": batch,
            "since": now_iso()}


def progress_thinking(*, step: int) -> dict[str, Any]:
    title = ("Reading the question and planning the first step" if step == 0
             else f"Reading what step {step} found and deciding the next step")
    return {"phase": "thinking", "step": step, "title": title, "since": now_iso()}


def progress_writing(*, step: int) -> dict[str, Any]:
    return {"phase": "writing", "step": step, "title": "Writing the answer from what was found", "since": now_iso()}


def progress_starting() -> dict[str, Any]:
    return {"phase": "starting", "step": 0, "title": "Starting", "since": now_iso()}


class LiveRun:
    """The channel between a run's worker thread and whoever is reading it now (maybe nobody)."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=2000)
        self.progress: dict[str, Any] = progress_starting()
        self.started_monotonic = time.monotonic()
        self.started_at = now_iso()
        self.run_id: str | None = None
        self._listeners_gone = threading.Event()
        self.on_progress_change: Callable[[dict[str, Any]], None] | None = None

    def push(self, event: dict[str, Any]) -> None:
        if self._listeners_gone.is_set():
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:  # nobody reading for 2000 events: the reader has gone; progress is in the database
            self._listeners_gone.set()

    def set_progress(self, progress: dict[str, Any]) -> None:
        self.progress = dict(progress)
        if self.on_progress_change:
            try:
                self.on_progress_change(self.progress)
            except Exception as exc:  # noqa: BLE001 - progress never stops a run
                log.warning("Agent run progress note failed: %s", exc)
        self.push(self.progress_event())

    def progress_event(self) -> dict[str, Any]:
        return {"type": "progress", "run_id": self.run_id, "progress": self.progress,
                "elapsed_seconds": round(time.monotonic() - self.started_monotonic, 1),
                "server_time": now_iso()}

    def close(self) -> None:
        try:
            self._queue.put_nowait(_CLOSED)
        except queue.Full:
            pass

    def reader_left(self) -> None:
        self._listeners_gone.set()
        # Drain so the worker's puts never block on a full queue.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def read(self, *, keepalive: float = KEEPALIVE_SECONDS) -> Iterator[dict[str, Any]]:
        """Every event the run pushes, with a progress ping when nothing new arrives for ``keepalive`` seconds."""
        while True:
            try:
                event = self._queue.get(timeout=keepalive)
            except queue.Empty:
                yield self.progress_event()
                continue
            if event is _CLOSED:
                return
            yield event


def pump(events: Iterator[dict[str, Any]], live: LiveRun, *, on_end: Callable[[], None] | None = None,
         name: str = "agent-run") -> threading.Thread:
    """Drive ``events`` to the end on a daemon thread, pushing each into ``live``; ``on_end`` runs after it."""

    def run() -> None:
        try:
            for event in events:
                live.push(event)
        except Exception as exc:  # noqa: BLE001 - the generator records its own failures; this is a last word
            log.exception("Agent run worker ended with an error")
            live.push({"type": "error", "run_id": live.run_id, "message": str(exc)})
        finally:
            live.close()
            if on_end:
                try:
                    on_end()
                except Exception:  # noqa: BLE001
                    log.exception("Agent run worker cleanup failed")

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread


def stale(heartbeat_at: datetime | None, *, now: datetime | None = None) -> bool:
    if heartbeat_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
    return (current - heartbeat_at).total_seconds() > STALE_SECONDS
