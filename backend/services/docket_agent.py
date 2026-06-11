"""
Docket autonomous agent — the orchestrator that works tickets off the queue.

Design (see DOCKET.md): a thin orchestrator OWNS the lifecycle transitions and
invokes a headless Claude Code agent ONE PHASE AT A TIME. The agent supplies the
*content* (assessment, plan, code, review); the orchestrator drives state and
records everything on the ticket timeline so the board always shows what's
happening — including a live "currently working on" ticker fed by the agent's
tool activity.

Phases: Assessment → Planning → In Development → Self-Review → PR.
  - Assessment + Planning are READ-ONLY (Edit/Write disallowed) — always safe.
  - In Development / Self-Review / PR WRITE code + push a branch, so they are
    gated behind DOCKET_AGENT_WRITES (default off). With writes off, the agent
    grooms a ticket (assess + plan) and parks it at Planning with a note.

Guardrails: per-phase --max-turns + --max-budget-usd, a subprocess timeout, the
hybrid grooming gate (bounce vague P0/P1 asks to Needs Info; best-effort the
rest), and any failure → Stalled (never silently stuck). NEVER auto-merges.

Runs as root (has claude creds + the GitHub push key + the Neil B
<thenofisamizdat@gmail.com> commit identity). Lightweight: imports only
docket_storage (no Neo4j / embeddings).

Run a single pass (pick the top queued ticket, work it, exit):
    python -m services.docket_agent --once
Run the continuous loop:
    python -m services.docket_agent
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from services import docket_storage as dk

# --- config (env-overridable) ---
WRITES_ENABLED = os.environ.get("DOCKET_AGENT_WRITES", "0") == "1"
# Push gate: by default push when writes are on, but DOCKET_AGENT_PUSH=0 lets us
# run the full implement+review locally and HOLD the push for manual inspection.
PUSH_ENABLED = os.environ.get("DOCKET_AGENT_PUSH", "1" if WRITES_ENABLED else "0") == "1"
MODEL = os.environ.get("DOCKET_AGENT_MODEL", "sonnet")
MAIN_CHECKOUT = Path(os.environ.get("DOCKET_MAIN_CHECKOUT", "/home/conorbowles51/app_v2"))
WORKTREE_DIR = Path(os.environ.get("DOCKET_WORKTREE_DIR", "/home/conorbowles51/docket-agent-wt"))
REPO_SLUG = os.environ.get("DOCKET_REPO_SLUG", "conorbowles51/owl-n4j")
POLL_SECS = int(os.environ.get("DOCKET_AGENT_POLL", "20"))

READONLY_TOOLS = ["Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git diff:*)",
                  "Bash(ls:*)", "Bash(cat:*)", "Bash(find:*)", "Bash(grep:*)"]
WRITE_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def log(msg: str) -> None:
    print(f"[docket-agent] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Headless Claude runner
# ---------------------------------------------------------------------------

def _short(p: str) -> str:
    return p.split("/")[-1] if p else ""


def _summarize_tool(block: dict) -> str:
    name = block.get("name", "")
    inp = block.get("input", {}) or {}
    if name == "Read":
        return f"Reading {_short(inp.get('file_path', ''))}"
    if name in ("Edit", "Write", "NotebookEdit"):
        return f"Editing {_short(inp.get('file_path', ''))}"
    if name == "Bash":
        return "Running: " + str(inp.get("command", ""))[:60]
    if name in ("Grep", "Glob"):
        return f"Searching {str(inp.get('pattern', ''))[:40]}"
    if name == "Task":
        return "Delegating to a sub-agent"
    if name == "TodoWrite":
        return "Updating its plan"
    return f"Using {name}"


def run_claude(prompt: str, cwd: Path, *, allowed_tools=None, disallowed_tools=None,
               permission_mode="default", max_turns=20, max_budget_usd=2.0,
               timeout=900, on_activity=None) -> dict:
    """Invoke Claude Code headless in `cwd`, streaming progress. Returns
    {text, is_error, cost, turns, session_id}."""
    cmd = ["claude", "-p", prompt,
           "--output-format", "stream-json", "--verbose",
           "--max-turns", str(max_turns),
           "--permission-mode", permission_mode,
           "--model", MODEL]
    if max_budget_usd:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    if disallowed_tools:
        cmd += ["--disallowedTools", *disallowed_tools]

    out = {"text": "", "is_error": False, "cost": 0.0, "turns": 0, "session_id": ""}
    try:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1,
                                env=os.environ.copy())
    except FileNotFoundError:
        out["is_error"] = True
        out["text"] = "claude CLI not found on PATH"
        return out

    start = time.monotonic()
    try:
        for line in proc.stdout:
            if time.monotonic() - start > timeout:
                proc.kill()
                out["is_error"] = True
                out["text"] = out["text"] or "(phase timed out)"
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t = ev.get("type")
            if t == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use" and on_activity:
                        desc = _summarize_tool(block)
                        if desc:
                            on_activity(desc)
            elif t == "result":
                out["text"] = ev.get("result", "") or ""
                out["is_error"] = bool(ev.get("is_error"))
                out["cost"] = ev.get("total_cost_usd", 0.0) or 0.0
                out["turns"] = ev.get("num_turns", 0) or 0
                out["session_id"] = ev.get("session_id", "") or ""
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        out["is_error"] = True
    if proc.returncode not in (0, None) and not out["text"]:
        out["is_error"] = True
        try:
            out["text"] = (proc.stderr.read() or "claude failed")[:2000]
        except Exception:
            out["text"] = "claude failed"
    return out


# ---------------------------------------------------------------------------
# Worktrees
# ---------------------------------------------------------------------------

def ensure_worktree(ticket: dict) -> tuple[Path, str]:
    """Create (or reuse) a per-ticket git worktree + branch off main."""
    tid = ticket["id"]
    branch = f"docket/DKT-{tid}"
    path = WORKTREE_DIR / f"DKT-{tid}"
    WORKTREE_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path, branch
    subprocess.run(
        ["git", "-C", str(MAIN_CHECKOUT), "worktree", "add", "-B", branch,
         str(path), "main"],
        check=True, capture_output=True, text=True,
    )
    return path, branch


def workdir_for(ticket: dict) -> tuple[Path, str | None]:
    """Where the agent runs. With writes on, a per-ticket worktree; otherwise the
    read-only main checkout (Edit/Write are disallowed in read-only phases anyway)."""
    if WRITES_ENABLED:
        return ensure_worktree(ticket)
    return MAIN_CHECKOUT, None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _ctx(t: dict) -> str:
    return (f"Ticket {t['ref']} ({t['type']}, priority {t['priority']}):\n"
            f"TITLE: {t['title']}\n"
            f"DESCRIPTION: {t.get('description') or '(none)'}\n"
            f"ACCEPTANCE CRITERIA: {t.get('acceptance_criteria') or '(none)'}\n")


def assess_prompt(t: dict) -> str:
    return (
        "You are the assessment phase of an autonomous dev pipeline working on "
        "this codebase. Explore the repo (READ ONLY — do not edit anything) and "
        "assess the following request.\n\n" + _ctx(t) +
        "\nProduce a concise assessment (≈150-250 words) covering: what the change "
        "involves, the key files/areas it would touch, risks or unknowns, and "
        "whether the ask is clear enough to implement.\n"
        "End your message with EXACTLY ONE final line, either:\n"
        "  VERDICT: PROCEED\n"
        "or, if the request is too vague/ambiguous to implement well:\n"
        "  VERDICT: NEEDS_INFO || <one sentence: the specific question(s) for the requester>"
    )


def plan_prompt(t: dict, assessment: str) -> str:
    return (
        "You are the planning phase of an autonomous dev pipeline. Based on the "
        "codebase (READ ONLY) and the assessment below, write a concrete, "
        "step-by-step implementation plan: the files to change, the approach for "
        "each, and how it will be tested/verified. Be specific and ordered.\n\n"
        + _ctx(t) + "\nASSESSMENT:\n" + assessment[:2000]
    )


def implement_prompt(t: dict, plan: str) -> str:
    return (
        "You are the implementation phase of an autonomous dev pipeline. Implement "
        "the plan below in this worktree. Make focused, correct changes; follow the "
        "surrounding code's style. Do not commit or push — just edit files. When "
        "done, briefly summarise what you changed.\n\n"
        + _ctx(t) + "\nPLAN:\n" + plan[:4000]
    )


def review_prompt(t: dict) -> str:
    return (
        "You are the self-review phase. Review the uncommitted changes in this "
        "worktree against the ticket's acceptance criteria. Run any quick checks "
        "you can (compile/lint/tests). Report problems found and whether the work "
        "is ready.\n\n" + _ctx(t) +
        "\nEnd with EXACTLY ONE final line: 'REVIEW: PASS' or 'REVIEW: FAIL || <what to fix>'."
    )


import re as _re


def _strip_control(text: str) -> str:
    """Remove the trailing machine-readable 'VERDICT:'/'REVIEW:' control line so
    the stored/displayed body is clean prose."""
    return _re.sub(r"\n*\b(VERDICT|REVIEW)\s*:.*$", "", text or "",
                   flags=_re.IGNORECASE | _re.DOTALL).strip()


def parse_verdict(text: str, key: str) -> tuple[str, str]:
    """Return (verdict, detail) from a trailing 'KEY: ...' line. verdict is the
    first token (e.g. PROCEED / NEEDS_INFO / PASS / FAIL)."""
    verdict, detail = "", ""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.upper().startswith(key.upper() + ":"):
            rest = line.split(":", 1)[1].strip()
            if "||" in rest:
                v, d = rest.split("||", 1)
                verdict, detail = v.strip().upper(), d.strip()
            else:
                verdict = rest.strip().upper()
            break
    return verdict, detail


# ---------------------------------------------------------------------------
# Phase driver
# ---------------------------------------------------------------------------

def _stall(tid: int, why: str) -> None:
    log(f"DKT-{tid} STALLED: {why}")
    try:
        dk.add_event(tid, "note", summary=f"Stalled: {why}", actor="agent")
        dk.transition(tid, "stalled", actor="agent", summary=why[:120])
        t = dk.get_ticket(tid)
        dk.enqueue_notification(tid, "neil", "stalled",
                                subject=f"Docket {t['ref']}: stalled",
                                body=why[:500])
    except Exception as e:
        log(f"  (failed to record stall: {e})")


def process_ticket(t: dict) -> None:
    tid = t["id"]
    log(f"Picking up {t['ref']} — {t['title']!r} (priority {t['priority']})")
    act = lambda d: dk.set_activity(tid, d)

    try:
        workdir, _branch = workdir_for(t)
    except subprocess.CalledProcessError as e:
        return _stall(tid, f"worktree setup failed: {e.stderr or e}")

    # --- Assessment (read-only) ---
    dk.transition(tid, "assessment", actor="agent", summary="Picked up by the agent")
    act("Reading the codebase to assess the request")
    a = run_claude(assess_prompt(t), workdir, allowed_tools=READONLY_TOOLS,
                   disallowed_tools=["Edit", "Write"], permission_mode="default",
                   max_turns=15, max_budget_usd=1.5,
                   on_activity=act)
    if a["is_error"]:
        return _stall(tid, "assessment failed: " + a["text"][:200])
    verdict, questions = parse_verdict(a["text"], "VERDICT")
    dk.add_event(tid, "assessment", summary=_strip_control(a["text"]), actor="agent",
                 payload={"cost_usd": a["cost"], "turns": a["turns"]})
    log(f"  assessment done (verdict={verdict or 'PROCEED'}, ${a['cost']:.3f}, {a['turns']} turns)")

    # Hybrid grooming gate: bounce vague P0/P1; best-effort the rest.
    if verdict == "NEEDS_INFO" and t["priority"] in ("P0", "P1"):
        q = questions or "The requester needs to clarify the ask before work can start."
        dk.add_event(tid, "comment", summary=f"Needs clarification: {q}", actor="agent")
        dk.transition(tid, "needs_info", actor="agent",
                      summary="Bounced for clarification (grooming gate)")
        dk.enqueue_notification(tid, t.get("created_by", "neil") or "neil", "needs_info",
                                subject=f"Docket {t['ref']}: needs your input",
                                body=q)
        log(f"  → Needs Info (bounced): {q}")
        return
    if verdict == "NEEDS_INFO":
        dk.add_event(tid, "note", actor="agent",
                     summary="Ask is a bit vague but low-priority — proceeding best-effort "
                             f"with assumptions. Open question: {questions or 'n/a'}")

    # --- Planning (read-only) ---
    dk.transition(tid, "planning", actor="agent")
    act("Drafting an implementation plan")
    p = run_claude(plan_prompt(t, a["text"]), workdir, allowed_tools=READONLY_TOOLS,
                   disallowed_tools=["Edit", "Write"], permission_mode="default",
                   max_turns=20, max_budget_usd=1.5, on_activity=act)
    if p["is_error"]:
        return _stall(tid, "planning failed: " + p["text"][:200])
    dk.add_event(tid, "plan", summary=p["text"], actor="agent",
                 payload={"cost_usd": p["cost"], "turns": p["turns"]})
    log(f"  plan done (${p['cost']:.3f}, {p['turns']} turns)")

    if not WRITES_ENABLED:
        act("Plan ready — autonomous code-gen is disabled")
        dk.add_event(tid, "note", actor="agent",
                     summary="Assessment + plan complete. Autonomous code generation is "
                             "disabled (set DOCKET_AGENT_WRITES=1 to let the agent "
                             "implement, self-review and open a PR). Parked at Planning.")
        log(f"  writes disabled — parked {t['ref']} at Planning")
        return

    # --- In Development (writes) ---
    wt, branch = ensure_worktree(t)
    dk.transition(tid, "in_development", actor="agent")
    act("Implementing the change")
    i = run_claude(implement_prompt(t, p["text"]), wt, allowed_tools=WRITE_TOOLS,
                   permission_mode="acceptEdits", max_turns=40, max_budget_usd=5.0,
                   on_activity=act)
    if i["is_error"]:
        return _stall(tid, "implementation failed: " + i["text"][:200])
    dk.add_event(tid, "note", summary="Implemented:\n" + i["text"][:1500], actor="agent",
                 payload={"cost_usd": i["cost"], "turns": i["turns"]})
    _git(wt, ["add", "-A"])
    _git(wt, ["commit", "-m", f"DKT-{tid}: {t['title']}\n\n"
              f"Autonomous Docket implementation.\n\n"
              "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"])

    # --- Self-Review (writes off, but may run tests) ---
    dk.transition(tid, "self_review", actor="agent")
    act("Reviewing its own work + running checks")
    r = run_claude(review_prompt(t), wt, allowed_tools=WRITE_TOOLS,
                   permission_mode="acceptEdits", max_turns=25, max_budget_usd=3.0,
                   on_activity=act)
    dk.add_event(tid, "note", summary="**Self-review**\n\n" + _strip_control(r["text"])[:1500],
                 actor="agent", payload={"cost_usd": r["cost"]})
    rv, fix = parse_verdict(r["text"], "REVIEW")
    if rv == "FAIL":
        # one corrective loop back through development before giving up
        dk.transition(tid, "in_development", actor="agent",
                      summary="Self-review found issues, iterating")
        return _stall(tid, f"self-review failed (needs another pass): {fix[:160]}")

    # --- PR (push branch + record compare URL; never auto-merge) ---
    if not PUSH_ENABLED:
        dk.update_ticket(tid, branch=branch)
        dk.add_event(tid, "note", actor="agent",
                     summary=f"Local branch '{branch}' ready in {wt} — push is disabled "
                             "(DOCKET_AGENT_PUSH=0). Inspect the diff, then push manually "
                             "to open a PR.")
        dk.transition(tid, "pr", actor="agent", summary="Local branch ready (push held for review)")
        log(f"  → local branch ready (push held): {branch} @ {wt}")
        return
    act("Pushing the branch + opening a PR")
    pushed = _git(wt, ["push", "-u", "origin", branch])
    if not pushed:
        return _stall(tid, "git push failed (check GitHub auth)")
    pr_url = f"https://github.com/{REPO_SLUG}/compare/main...{branch}?expand=1"
    dk.update_ticket(tid, branch=branch, pr_url=pr_url)
    dk.transition(tid, "pr", actor="agent", summary="Branch pushed; PR ready for review")
    dk.enqueue_notification(tid, "neil", "pr_ready",
                            subject=f"Docket {dk.get_ticket(tid)['ref']}: PR ready",
                            body=pr_url)
    log(f"  → PR ready: {pr_url}")


def _git(cwd: Path, args: list) -> bool:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  git {' '.join(args[:2])} failed: {r.stderr.strip()[:200]}")
        return False
    return True


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run_once() -> bool:
    """Work the single highest-priority queued ticket. Returns True if one ran."""
    t = dk.next_in_queue()
    if not t:
        return False
    try:
        process_ticket(t)
    except Exception as e:
        _stall(t["id"], f"unexpected error: {e}")
    return True


def main() -> int:
    once = "--once" in sys.argv
    log(f"starting (writes={'ON' if WRITES_ENABLED else 'OFF'}, model={MODEL}, "
        f"once={once})")
    if once:
        ran = run_once()
        log("worked one ticket" if ran else "queue empty")
        return 0
    while True:
        try:
            if not run_once():
                time.sleep(POLL_SECS)
        except KeyboardInterrupt:
            log("stopping")
            return 0
        except Exception as e:
            log(f"loop error: {e}")
            time.sleep(POLL_SECS)


if __name__ == "__main__":
    sys.exit(main())
