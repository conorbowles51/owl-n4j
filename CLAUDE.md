# Loupe

Read this first, every session, before doing anything else. Then read
`docs/loupe-build-state.md` for where the work currently stands.

This file holds what does not change. Anything that moves week to week belongs in
the build-state file, not here. A file with stale lines in it stops being trusted,
and an untrusted file is worse than no file.

---

## What this is

Loupe is a forensic intelligence platform built for **Owl Consultancy Group**, a
private investigations firm in Washington DC. It ingests evidence of mixed kind and
condition (bank statements, phone extractions, documents, interview material) and
turns it into something an investigator can rely on and defend.

**Neil Byrne** is the founder and the only engineer. He is the person in every
session.

**Alex** is an investigator at Owl. She is not an attorney and not technical. She
receives financial material through **productions from the prosecution**; she does
not issue subpoenas and cannot ask for native formats. Rules for writing to her are
at the bottom of this file.

The financial subsystem is the centre of gravity: `backend/services/financial/`,
about 41 modules, with a test file per module in `backend/tests/`.

---

## Working agreement

These are standing instructions from Neil. They are not preferences.

- **Enterprise grade or don't ship it.** "Please please please this has to be
  thorough and correct."
- **No assumptions.** "I need you to be more exact and stop making assumptions."
  If a claim can be checked by reading the source, read the source. Never state a
  fact about the code from memory when the file is right there.
- **Chunked work.** One unit at a time, finished, tested, committed. Commit each
  completed unit as it lands rather than batching several together.
- **Never invent a user story.** Do not assert what Alex or anyone at Owl thinks,
  wants, asks, has experienced, or would otherwise have missed. If the value of a
  thing cannot be stated as a fact about the system or the domain, ask Neil. This
  rule exists because it was broken.
- **Do not start build work when told to stop.** When a non-build task is in
  progress, it halts everything else until Neil says it is done.
- **Check before defending.** When Neil challenges something as wrong, verify it
  against the source and report what is actually there, including when the answer
  is that he is right.

### Design rules already settled

- Documents arriving together do not have to be related. "This is often how
  evidence will come in until the larger case is understood."
- Do not fall back to geometry-based table detection when nothing is found. "That's
  far too simplistic an assumption to make."
- Do not hard-refuse a suspect amount. Flag it, cite it back to its source, and let
  the analyst confirm or edit. This applies to all transactions and all fields.
- When a value is corrected, both the machine reading and the correction stay in
  the system and stay visible, but it must be obvious which is real, and **only the
  corrected value is used in money flows, sums, totals and searches.**
- Proof class is computed, never set by hand, including by us. A class a person can
  raise is an opinion.

---

## Environment

The repo is mounted per session and **the absolute path changes every session**.
Resolve it once at the start; do not hardcode a path from a previous session.

- **The bash working directory resets unpredictably.** Every command must `cd` with
  an absolute path in the same invocation. Do not rely on a `cd` from a previous
  command.
- `Edit` requires a full prior `Read` of the file in the same session.
- **Do not read exit codes through a pipe.** The code you get back is the pipe's.
- Python is **3.10.12** only. No newer syntax.
- Avoid `!r` inside f-strings in `python3 -c` one-liners; quoting breaks.
- `-t` is a `unittest discover` flag only.
- The workspace denies `unlink`, which produces harmless `tmp_obj_*` warnings from
  git. `/tmp` allows `rm`.
- Case material and evidence files are **never committed**.

---

## Tests

Backend financial suite, from the repo root:

```
cd backend && env PYTHONPYCACHEPREFIX=/tmp/pyc_st PYTHONDONTWRITEBYTECODE=1 \
  PYTHONHASHSEED=0 python3 -m unittest discover -s tests -p 'test_financial_*.py' -t .
```

Baseline: **Ran 2933 tests, FAILED (errors=1)**. The single error is a long-standing
`jose` ModuleNotFoundError and is expected. Any other failure is yours.

The package surface is guarded by `backend/tests/test_financial_exports.py`. A new
module exported from `services/financial/__init__.py` must be added there.

Frontend baseline: 50 files, 246 tests, `tsc -b` returns 0, eslint returns 0. Use
`fireEvent`, not `userEvent`.

---

## Git

**Branch is `integration/evidence-main-reunion`. Never merge to main.**

**Push is blocked. Neil pushes.** Never attempt it.

**Never modify git config.** The write procedure below sets author identity per
commit instead.

Commits are written through a temporary index so the real index is never disturbed:

```
export GIT_INDEX_FILE=/tmp/loupe.index
rm -f /tmp/loupe.index
git read-tree HEAD
git add <explicit paths, never -A and never .>
git write-tree
git diff --stat HEAD <tree>          # verify before committing
GIT_AUTHOR_NAME="Neil Byrne" GIT_AUTHOR_EMAIL="thenofisamizdat@gmail.com" \
  git commit-tree <tree> -p HEAD -m "<message>"
```

Then `Read` the ref file, `Write` the new sha to
`.git/refs/heads/integration/evidence-main-reunion`, restore the index with
`cat /tmp/loupe.index > .git/index`, and verify `git status --porcelain | grep -v '^??'`
is empty.

Commit messages describe what changed and why in plain language. They are load
bearing: they are the only durable record of reasoning that survives between
sessions.

---

## Writing to Alex

Every rule here was established by having a draft rejected. They cost real time to
learn.

- **No em dashes. Anywhere.**
- No internals. No module names, no file formats, no parsers, no arithmetic, no
  floating point.
- She is an investigator, not an attorney. No rule numbers, no case citations.
  Translate a legal consequence into what it means for the work.
- She receives productions. Advice about subpoenas or asking for native formats is
  useless to her.
- **Never assert what she thinks, wants, asks, has seen, or would have missed.**
- **Do** state value: what a capability makes possible or prevents, as a fact about
  the system and the domain.
- Explain what something means **to an investigation**, not what it means as data.
  Abstract framing gets rejected: "every total silently covers a subset" means
  nothing to a reader.
- Where a failure or an outcome is mentioned, say what it means and what the user
  can do about it.
- **Never describe a visualization.** Say what the user can learn and do.
- Never lead with or dwell on the decimal-point OCR example.
- Teammate tone, not a sales pitch. Pasteable into Teams as-is.
- Structure that works: two halves, making the ledger trustworthy, then what a
  trustworthy ledger lets you do. Anything not yet built goes in a clearly separate
  section at the end, because the moment one item is aspirational the reader has to
  wonder about the rest.
- Lead-ins are bold **and** italic: `***like this.***`

---

## Session hygiene

The context window is spent mostly on reading source, which is also what makes the
work correct. So sessions end for a good reason, not because they ran out.

- Scope a session to **one build item**.
- End at a boundary: a unit landed and committed. At that point git holds most of
  the state and the handoff is cheap.
- **Write the state file before ending, not after compaction.** After compaction the
  detail needed to write it accurately is already gone.
- Do not stop mid-item with a dirty tree. If it is unavoidable, the state file must
  say exactly what was in flight.
- Signs the session is already past its stopping point: re-reading a file read
  earlier in the same session, asking Neil something he already answered, or a
  compaction having just occurred.

### After every commit, without being asked

A commit is the clean boundary, so it is the trigger. As soon as a commit lands,
before starting anything else:

1. Rewrite `docs/loupe-build-state.md`. New head and commit subject, what is now
   uncommitted, where the build order stands, anything newly parked, any question
   raised that Neil has not ruled on, any defect found and not fixed.
2. Record anything a fresh session would otherwise have to rediscover: a command
   that failed and the form that worked, a fact established by reading source, a
   decision made and its reasoning.
3. Commit the state file.
4. Then tell Neil **in bold** that the state is written and this is a good point to
   start a new session, and say in one line what the next session should pick up.

Do this even when there is plenty of window left. The point is that the handoff is
always current, so a session can be ended at any moment without losing anything. Do
not carry on into the next item first and write the state afterwards, because by then
the detail that made the state accurate is the thing that has been spent.
