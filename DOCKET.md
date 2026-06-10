# Docket

> **From ask to merge — in the open.**
> A ticket lifecycle + autonomous dev pipeline with a production-line view, so every
> request is visible as it moves from idea to shipped. Its quieter job: make the *cost*
> of development legible to testers, so asks get sharper over time.

**Brand**
- **Name:** Docket — a docket is the list of cases awaiting processing; it labels the
  queue naturally and rhymes with the forensic/case world the main app lives in.
- **Tagline:** *From ask to merge — in the open.*
- **Tone:** clean, transparent, a touch of case-file gravitas. Plain language for testers.
- **Sender identity (email):** `Docket <docket@…>` — e.g. subject lines like
  *"Docket: your ticket needs input"*, *"Docket: PR ready for review"*.
- **Visual direction (TBD at build):** restrained, document/case-file feel; the board is
  the hero. Decide palette + logo when Phase 1 UI starts.

---

## ▶ STATUS / NEXT  (keep this block fresh — resume point for "Continue Docket")

- **Phase:** Phase 1 (Rails) — IN PROGRESS, on branch `feat/docket` (off `main`).
- **Last completed:** Backend complete + tested.
  (1) Store/state-machine `backend/services/docket_storage.py` (tickets/ticket_events/
  notifications; legal-transition enforcement; priority+FIFO queue; activity ticker).
  (2) API `backend/routers/docket.py` → `/api/tickets/*` (meta, testers, list, queue,
  board, create, get-detail, patch, submit, transition, comment), registered in
  `routers/__init__.py` + `main.py`. (3) Auth extended in `services/testing_auth.py`:
  added `arturo` + an `_EMAILS` map (neil filled, others TODO) + `tester_email()` /
  `all_testers()` helpers. Verified via FastAPI TestClient: 401 gate, token attribution,
  submit→queued, illegal-move 400, comments, timeline, board, testers list.
- **Next action:** Scaffold the **standalone React app** (Vite) — app shell + the
  production-line **board** that reads `/api/tickets/board`, reusing the tester login.
  Decide where it builds to / how the backend serves its static bundle.
- **Blocked on:** Nothing for Phases 1–early-2. SMTP credential pending for the email
  channel only (Neil is setting up a send-from address + app password later).
- **Provisional (confirm):** priority scheme = P0–P3 (P0 highest) — used in the store now.
- **Open product questions (settle in/before Phase 1):**
  - Priority scheme (P0–P3 vs Critical/High/Med/Low) + who can set/override it.
  - Make **acceptance criteria** a required submit field (quiet lever for better stories)?
  - Shape of agent-generated **User Review instructions** (tie to acceptance criteria).

---

## How to resume ("Continue Docket")
Read this file top-to-bottom, act on **▶ STATUS / NEXT**. Do not re-litigate locked
decisions below. Update the STATUS block after each meaningful step.

---

## Locked design (decided with Neil, 2026-06-10)

**App shape**
- ONE new **standalone React app**, reuses the existing tester JWT auth
  (neil/alex/conor/arturo). Served as static by the same FastAPI; new `/api/tickets/*`
  surface. **Subsumes** today's checklist/feedback/discussion (migrate the vanilla-JS
  `backend/static/testing-hub.html` in, then retire it).
- **Storage:** **SQLite** ticket store *alongside* existing `data/testing-feedback.json`
  (the latter stays for the catalogue/checklist).

**Two zones**
- **Discussion** — item is *Open / Under Discussion*: comment, refine, set priority.
  Lives here before and after processing.
- **Production** — *"Submit for Processing"* promotes a user_item → ticket → the queue.

**Lifecycle**
```
Discussion → [Submit for Processing] →
  Queued → Assessment → Planning → In Development → Self-Review → PR (Neil's OK) → User Review → Done
              │                                                                       │
   Needs Info ┘ (hybrid gate, notify creator)               Fail → amend → Queued (iter++)
   Cross-cutting: Stalled (heartbeat), Changes Requested (PR bounce)
```
- **Queue:** priority-weighted position ("Position #3, next up") + ETA from recent cycle times.
- **Grooming gate (hybrid):** bounce big/high-priority vague asks to *Needs Info* with
  clarifying questions; best-effort small asks with documented assumptions.

**Autonomy (target = full, built with rails)**
- A thin **orchestrator OWNS state transitions** and invokes a headless agent **per phase**
  (don't trust the agent to self-report status).
- Each ticket = its own **git worktree + branch**; PR via `gh`; **NEVER auto-merges** (the
  PR review is Neil's gate); **self-review must pass before PR**.
- Per-ticket **caps** (iterations/tokens/time); **heartbeat → Stalled**; queue **kill switch**.
- **Denylist** mechanism exists but is **EMPTY for now** (agent may modify anything).
- Live **"currently working on"** ticker = the agent's streamed activity during a phase.

**Notifications** (events → recipients → channel)
- *Needs Info* → creator · *PR ready* → Neil · *User Review* → assignee · *Stalled/failed* → Neil.
- Email via **msmtp** CLI (not yet installed; `ssmtp` is deprecated). Needs an upstream
  SMTP relay / app-password — **blocks the email channel only.** Add `email` per tester.
  In-app notification badges complement email so nothing depends solely on delivery.

**The point (educational payload)**
- The board shows each card crawling the line: live activity ticker + work-history timeline,
  and **effort metrics per phase** (time-in-stage, files touched, iterations, bounces) so
  development cost becomes legible to Alex.

---

## Data model (SQLite) — initial sketch
- **tickets** — id, seed_user_item_id, title, type(bug|feature), description,
  acceptance_criteria, priority, status, substage, queue_seq, iteration, branch,
  worktree_path, pr_url, created_by, assignee, created_at, updated_at
- **ticket_events** — work history *and* audit log: id, ticket_id, ts, phase,
  actor(agent|human), kind(transition|activity|assessment|plan|comment), summary, payload.
  ("currently working on" = latest `activity` event.)
- **notifications** — id, ticket_id, recipient, channel, event, sent_at, status

---

## Build sequence (full autonomy, reached safely)
- [ ] **Phase 1 — Rails:** SQLite model + state machine + standalone app/board +
  submit/resubmit + migrate the old hub in.
  - [x] SQLite ticket store + lifecycle state machine (`backend/services/docket_storage.py`)
  - [x] API surface (`backend/routers/docket.py` → `/api/tickets/*`) + register in main.py
  - [x] Auth: add `arturo` + per-tester email + helpers (`services/testing_auth.py`)
  - [ ] Standalone React app shell + production-line board
  - [ ] Submit-for-processing / resubmit-with-amendment flows
  - [ ] Migrate old hub (checklist + feedback + discussion) in, retire vanilla-JS page
- [ ] **Phase 2 — Plumbing:** worktree-per-ticket + per-phase agent + `gh` PR + live
  progress/heartbeat + msmtp notifications.
- [ ] **Phase 3 — Turn autonomy on** behind a flag, ticket-by-ticket with caps; open the
  throttle once it behaves.
- [ ] **Phase 4 — Coaching analytics:** clarity scoring at submit, "bounced & why",
  effort dashboards.

---

## Decision log
- 2026-06-10 — Name = **Docket**. Standalone React app, subsumes old hub. SQLite store.
  Two zones. Hybrid grooming. Full autonomy w/ rails (orchestrator owns state, per-phase
  agent, worktree+gh, never auto-merge, empty denylist). Email via msmtp (cred pending).
