#!/usr/bin/env python3
"""Live coverage check of the case agent: a fixed question set per data type, asked of the live agent, scored.

The question set and expected answers are in ``scripts/agent_coverage_questions.json`` for the Verification case
(synthetic material) and, for a real case, in a file kept outside the repository because it is case material
(``/mnt/owl-data/agent-coverage/questions-real.json`` or ``$LOUPE_AGENT_COVERAGE_REAL``; read when it exists).
Expected answers were read from the data read-only; each question says from what. Results of a real case hold its
answers, so write them outside the repository too. The data types and the tools that read each one come from
the same registry as the agent's help (``backend/services/agent/capabilities.py``).

For every question: one POST /api/agent/messages/stream (read to the end, so the run finishes), then the stored run
(GET /api/agent/runs/<id>: tool calls and final answer) and the stored thread (GET /api/agent/threads/<id>: the
answer's citation check). Each question is scored on three things:

- tool: a tool of the question's type ran successfully;
- answer: every expected group matched (each group is a list of alternatives; matching ignores case and thousands
  separators);
- cited: the answer's citation check found at least one citation in the case (or the answer links a case page),
  required only where the question says so.

pass = all three; fail = neither the tool nor the answer; partial otherwise. Answers are kept in the JSON in full,
so a reader can check every automatic score by eye.

Sign-in: once per run with the jobs login (``/root/.config/loupe-jobs/login``: email, password, url); on a 401 the
file is read again and the script signs in once more. The password is never printed. At most two runs are in flight.

    python3 scripts/agent_coverage_eval.py --case verification --types phones,graph --out docs/agent-coverage/x
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import http.cookiejar
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
import importlib.util  # noqa: E402

# The registry module imports nothing from the app; it is loaded by path so the backend's dependencies (and the
# services.agent package, which imports the runner) are not needed here.
_spec = importlib.util.spec_from_file_location("agent_capabilities", HERE.parent / "backend/services/agent/capabilities.py")
CAP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CAP)

LOGIN_FILE = Path(os.environ.get("LOUPE_JOBS_LOGIN", "/root/.config/loupe-jobs/login"))
MAX_IN_FLIGHT = 2
RUN_TIMEOUT_S = 900


REAL_QUESTIONS = Path(os.environ.get("LOUPE_AGENT_COVERAGE_REAL", "/mnt/owl-data/agent-coverage/questions-real.json"))


def load_questions(files: list[str]) -> dict:
    """The question files merged: their questions, cases and case titles (a question id is unique across them)."""
    data: dict = {"questions": [], "cases": {}, "case_titles": {}, "derived_on": None}
    for f in files:
        part = json.loads(Path(f).read_text())
        data["questions"] += part["questions"]
        data["cases"].update(part["cases"])
        data["case_titles"].update(part.get("case_titles") or {})
        data["derived_on"] = data["derived_on"] or part.get("derived_on")
    ids = [q["id"] for q in data["questions"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("question ids repeat across %s" % ", ".join(files))
    return data


def read_login() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in LOGIN_FILE.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.lock = threading.Lock()
        self.relogins = 0

    def login(self) -> None:
        cfg = read_login()
        body = json.dumps({"username": cfg["email"], "password": cfg["password"]}).encode()
        req = urllib.request.Request(self.base + "/api/auth/login", data=body,
                                     headers={"Content-Type": "application/json"})
        self.opener.open(req, timeout=60).read()

    def _open(self, req, timeout):
        try:
            return self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            with self.lock:
                if self.relogins >= 1:
                    raise
                self.relogins += 1
                self.login()
            return self.opener.open(req, timeout=timeout)

    def get(self, path: str):
        return json.loads(self._open(urllib.request.Request(self.base + path), 120).read())

    def post(self, path: str, payload: dict | None = None):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload or {}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        return self._open(req, 60).read()

    def stream(self, payload: dict, timeout: int) -> dict:
        """Post the message and read the event stream to its end. Returns the run and thread ids and the end."""
        req = urllib.request.Request(self.base + "/api/agent/messages/stream", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
                                     method="POST")
        out = {"run_id": None, "thread_id": None, "end": None, "message": None}
        started = time.monotonic()
        with self._open(req, timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except ValueError:
                    continue
                kind = event.get("type")
                if kind == "run_started":
                    out["run_id"], out["thread_id"] = event.get("run_id"), event.get("thread_id")
                elif kind in ("done", "error", "cancelled"):
                    out["end"] = kind
                    out["message"] = event.get("message")
                    resp_obj = event.get("response") or {}
                    out["run_id"] = out["run_id"] or resp_obj.get("run_id") or event.get("run_id")
                    out["thread_id"] = out["thread_id"] or resp_obj.get("thread_id") or event.get("thread_id")
                    break
                if time.monotonic() - started > timeout:
                    out["end"] = "timeout"
                    break
        return out


_SEP = re.compile(r"(?<=\d)[,   ](?=\d{3}\b)")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("\u2019", "'"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    prev = None
    while prev != text:
        prev, text = text, _SEP.sub("", text)
    return text


def answer_matches(answer: str, groups: list[list[str]]) -> tuple[bool, list[list[str]]]:
    a = norm(answer)
    missing = [g for g in groups if not any(norm(alt) in a for alt in g)]
    return not missing, missing


def score(question: dict, run: dict, citation_check: dict | None) -> dict:
    type_tools = set(question.get("tools") or CAP.tools_for_type(question["type"]))
    trace = run.get("tool_trace") or []
    used = [t.get("name") for t in trace]
    ok_used = [t.get("name") for t in trace if t.get("status") == "success"]
    tool_ok = bool(type_tools.intersection(ok_used))
    answer = run.get("final_answer") or ""
    answer_ok, missing = answer_matches(answer, question["expect_all"])
    cc = citation_check or {}
    cited_n = int(cc.get("ok") or 0)
    case_links = len(re.findall(r"\]\((?:https?://[^)\s]*)?/cases/", answer))
    cited_ok = (cited_n + case_links) > 0
    cite_needed = bool(question.get("cite_required", True))
    checks = [tool_ok, answer_ok] + ([cited_ok] if cite_needed else [])
    if run.get("status") != "completed":
        verdict = "fail"
    elif all(checks):
        verdict = "pass"
    elif not tool_ok and not answer_ok:
        verdict = "fail"
    else:
        verdict = "partial"
    return {"verdict": verdict, "tool_ok": tool_ok, "answer_ok": answer_ok, "cited_ok": cited_ok,
            "cite_required": cite_needed, "citations_ok": cited_n, "case_page_links": case_links,
            "tools_used": used, "tools_of_type": sorted(type_tools), "missing": missing}


def apply_review(results: list[dict], review: dict) -> None:
    """A person's reading of an answer replaces the automatic answer score; the automatic one stays as auto_*."""
    for r in results:
        rv = review.get(r["id"])
        if not rv:
            continue
        r["auto_verdict"], r["auto_answer_ok"] = r.get("verdict"), r.get("answer_ok")
        r["answer_ok"] = bool(rv["answer_ok"])
        r["reviewed"] = rv.get("note")
        checks = [r.get("tool_ok"), r["answer_ok"]] + ([r.get("cited_ok")] if r.get("cite_required") else [])
        if r.get("status") != "completed":
            r["verdict"] = "fail"
        elif all(checks):
            r["verdict"] = "pass"
        elif not r.get("tool_ok") and not r["answer_ok"]:
            r["verdict"] = "fail"
        else:
            r["verdict"] = "partial"


def run_question(client: Client, question: dict, case_id: str) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    payload = {"message": question["question"], "case_id": case_id, "case_layer": question.get("layer", "all"),
               "persist": True}
    record = {"id": question["id"], "case": question["case"], "type": question["type"], "question": question["question"],
              "layer": payload["case_layer"], "expected": question["expected"], "started_at": started}
    try:
        streamed = client.stream(payload, RUN_TIMEOUT_S)
    except Exception as exc:  # the request itself failed: recorded, never dropped
        record.update(error="%s: %s" % (type(exc).__name__, exc), verdict="fail")
        return record
    record.update(run_id=streamed["run_id"], thread_id=streamed["thread_id"], stream_end=streamed["end"],
                  stream_message=streamed["message"])
    if streamed["end"] == "timeout" and streamed["run_id"]:
        try:
            client.post("/api/agent/runs/%s:cancel" % streamed["run_id"])
        except Exception:
            pass
    run, cc = {}, None
    if streamed["run_id"]:
        for _ in range(20):
            run = client.get("/api/agent/runs/%s" % streamed["run_id"])
            if run.get("status") not in ("running", "queued", "pending"):
                break
            time.sleep(15)
        thread = client.get("/api/agent/threads/%s" % streamed["thread_id"])
        for m in thread.get("messages") or []:
            if m.get("role") == "assistant" and m.get("run_id") == streamed["run_id"]:
                cc = m.get("citation_check")
    record.update(status=run.get("status"), answer=run.get("final_answer"), citation_check=cc,
                  tool_trace=[{k: t.get(k) for k in ("name", "status", "arguments", "summary", "error")}
                              for t in run.get("tool_trace") or []],
                  finished_at=datetime.now(timezone.utc).isoformat())
    record.update(score(question, run, cc))
    return record


def markdown(results: list[dict], data: dict, label: str) -> str:
    lines = ["# Agent coverage check: %s" % label, "",
             "Questions and expected answers: the coverage question files (derived %s). Scored "
             "automatically: tool of the type used, every expected part in the answer, citations in the case "
             "(where required). Answers are in the JSON beside this file; an answer marked * was read by a person and its "
             "automatic answer score corrected (the note is in the JSON)." % data.get("derived_on"), ""]
    order = [t["id"] for t in CAP.DATA_TYPES]
    for case in ("verification", "real"):
        rows = [r for r in results if r["case"] == case]
        if not rows:
            continue
        lines += ["## %s (%s)" % (data["case_titles"][case], data["cases"][case]), "",
                  "| Type | Pass | Partial | Fail | Questions (verdict: tool/answer/cited, run id) |",
                  "|---|---|---|---|---|"]
        for t in order:
            rs = [r for r in rows if r["type"] == t]
            if not rs:
                continue
            n = {v: sum(1 for r in rs if r.get("verdict") == v) for v in ("pass", "partial", "fail")}

            def cell(r):
                yn = lambda b: "y" if b else "n"
                cite = yn(r.get("cited_ok")) if r.get("cite_required") else "-"
                mark = "*" if r.get("reviewed") else ""
                return "%s %s: %s/%s%s/%s `%s`" % (r["id"], r.get("verdict"), yn(r.get("tool_ok")),
                                                    yn(r.get("answer_ok")), mark, cite, r.get("run_id") or r.get("error"))
            lines.append("| %s | %d | %d | %d | %s |" % (CAP.BY_ID[t]["label"], n["pass"], n["partial"], n["fail"],
                                                        "<br>".join(cell(r) for r in rs)))
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--questions", action="append", default=None,
                    help="question files (repeatable); default: the repository's file and the real-case file if it "
                         "exists")
    ap.add_argument("--case", choices=["verification", "real", "all"], default="all")
    ap.add_argument("--types", default="", help="comma-separated type ids (default: all)")
    ap.add_argument("--ids", default="", help="comma-separated question ids (default: all)")
    ap.add_argument("--base-url", default=None, help="default: url from the login file, else http://127.0.0.1:8002")
    ap.add_argument("--out", required=True, help="output path without extension (.json and .md are written)")
    ap.add_argument("--concurrency", type=int, default=MAX_IN_FLIGHT)
    ap.add_argument("--dry-run", action="store_true", help="list the questions that would run")
    ap.add_argument("--review", default=None, help="with --rescore: a JSON of a person's reading of answers the "
                    "automatic score got wrong, {question id: {answer_ok, note}}; the automatic score is kept beside it")
    ap.add_argument("--rescore", default=None, help="score a results JSON again against the question file, "
                    "without asking anything (writes --out)")
    args = ap.parse_args(argv)
    files = args.questions or [str(HERE / "agent_coverage_questions.json")] + (
        [str(REAL_QUESTIONS)] if REAL_QUESTIONS.exists() else [])
    data = load_questions(files)
    args.questions = files
    qs = data["questions"]
    if args.case != "all":
        qs = [q for q in qs if q["case"] == args.case]
    if args.types:
        wanted = set(args.types.split(","))
        unknown = wanted - set(CAP.BY_ID)
        if unknown:
            ap.error("unknown types: %s" % ", ".join(sorted(unknown)))
        qs = [q for q in qs if q["type"] in wanted]
    if args.ids:
        qs = [q for q in qs if q["id"] in set(args.ids.split(","))]
    if args.rescore:
        old = json.loads(Path(args.rescore).read_text())
        old["results"] = [r for r in old["results"] if r["id"] in {q["id"] for q in qs}]
        by_id = {q["id"]: q for q in data["questions"]}
        for r in old["results"]:
            q = by_id.get(r["id"])
            if q is None or not r.get("run_id"):
                continue
            run = {"status": r.get("status"), "final_answer": r.get("answer"), "tool_trace": r.get("tool_trace")}
            r.update(score(q, run, r.get("citation_check")))
            r.pop("reviewed", None)
        if args.review:
            apply_review(old["results"], json.loads(Path(args.review).read_text()))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        old["rescored_at"] = datetime.now(timezone.utc).isoformat()
        out.with_name(out.name + ".json").write_text(json.dumps(old, indent=1, ensure_ascii=False))
        out.with_name(out.name + ".md").write_text(markdown(old["results"], data, out.name))
        return 0
    if args.dry_run:
        for q in qs:
            print(q["id"], q["type"], q["question"])
        return 0
    base = args.base_url or read_login().get("url") or "http://127.0.0.1:8002"
    client = Client(base)
    client.login()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    lock = threading.Lock()

    def save():
        doc = {"schema": "loupe.agent.coverage_results/1", "base_url": base, "questions_file": args.questions,
               "written_at": datetime.now(timezone.utc).isoformat(), "asked": len(qs), "answered": len(results),
               "results": sorted(results, key=lambda r: [x["id"] for x in qs].index(r["id"]))}
        out.with_name(out.name + ".json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        out.with_name(out.name + ".md").write_text(markdown(doc["results"], data, out.name))

    with cf.ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, MAX_IN_FLIGHT))) as pool:
        futures = {pool.submit(run_question, client, q, data["cases"][q["case"]]): q for q in qs}
        for fut in cf.as_completed(futures):
            r = fut.result()
            with lock:
                results.append(r)
                save()
            print("%s %s %s run=%s" % (r["id"], r.get("verdict"), r.get("tools_used"), r.get("run_id")), flush=True)
    save()
    counts = {v: sum(1 for r in results if r.get("verdict") == v) for v in ("pass", "partial", "fail")}
    print("done: %d questions, %s" % (len(results), counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
