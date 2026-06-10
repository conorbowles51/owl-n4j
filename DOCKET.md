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
- **Last completed:** Backend + standalone UI scaffolded & verified.
  - Backend: store/state-machine `backend/services/docket_storage.py`; API
    `backend/routers/docket.py` → `/api/tickets/*`; auth (`testing_auth.py`: arturo +
    `_EMAILS` + helpers). Verified via TestClient.
  - UI: standalone **Vite+React+Tailwind** app in `docket/` (React 18 / Vite 5, mirrors
    the main frontend). Login (reuses tester JWT), production-line **Board** (columns =
    lifecycle; live activity ticker, queue position, priority chips, mini progress bar,
    polls `/api/tickets/board` every 4s), **TicketDetail** drawer (timeline polls every
    3s, lifecycle action buttons from the state machine, comments), **NewTicketModal**
    (acceptance-criteria is a first-class field). Build is clean; backend serves it at
    **`/docket`** via a guarded StaticFiles mount in `main.py` (verified serving).
  - Dev: `cd docket && npm run dev` (port 5175, proxies /api → :8000).
- **Live verification (done):** ran the updated backend on `127.0.0.1:8011` (Neo4j
  connected); drove the full flow over HTTP — `/docket` serves the bundle, login,
  create, submit→queued(#1), transition, comment, illegal-move 400, board grouping.
  Seeded 8 demo tickets spread across every lane (some with live activity tickers).
  NOTE: no browser-driver tooling here, so the pixel render wasn't automated — view via
  SSH tunnel to :8011 `/docket` (testers: alex/neil/conor/arturo, pw `testing`). The
  `:8011` server + `data/docket.db` demo data are EPHEMERAL test artifacts.
- **Next action:** (a) [done — see Live verification] ; (b) the
  **amend-on-fail** UX for resubmit (edit desc/test-instructions when bouncing from
  User Review); (c) migrate the **old hub** (checklist + feedback + discussion) in and
  retire `backend/static/testing-hub.html`; (d) deploy wiring (build step + nginx
  `/docket` route) — see Deploy notes below.
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
  - [x] Standalone React app shell + production-line board (`docket/`, served at /docket)
  - [~] Submit/resubmit flows — submit + fail→requeue work; amend-on-fail UX still TODO
  - [ ] Migrate old hub (checklist + feedback + discussion) in, retire vanilla-JS page
  - [ ] Deploy wiring: build `docket/dist` in deploy.sh + nginx route for /docket
- [ ] **Phase 2 — Plumbing:** worktree-per-ticket + per-phase agent + `gh` PR + live
  progress/heartbeat + msmtp notifications.
- [ ] **Phase 3 — Turn autonomy on** behind a flag, ticket-by-ticket with caps; open the
  throttle once it behaves.
- [ ] **Phase 4 — Coaching analytics:** clarity scoring at submit, "bounced & why",
  effort dashboards.

---

## Early web access (TEST — not the real deploy)
- **Live at:** http://34.139.254.219:8011/docket  (testers alex/arturo/conor/neil, pw `testing`).
- Served by an ad-hoc `uvicorn main:app --host 0.0.0.0 --port 8011` (run as conorbowles51,
  from the `feat/docket` checkout) — NOT a systemd service, so it won't survive a reboot or
  a crash. data/docket.db holds 8 demo tickets.
- **Firewall:** GCP rule `allow-docket-8011` (default network, 0.0.0.0/0, tcp:8011) — created
  2026-06-10. To revert: `gcloud compute firewall-rules delete allow-docket-8011`.
- TODO to make durable: wrap as a systemd unit (e.g. `owl-docket.service`), OR fold into the
  real deploy on :8000. Until then treat :8011 as ephemeral.

## Deploy notes (TODO — not yet wired)
- **Build step:** deploy must run `cd docket && npm ci && npm run build` to produce
  `docket/dist`, which `backend/main.py` mounts at `/docket` (the mount is skipped if the
  bundle is absent, so the backend still boots without it).
- **Reverse proxy:** the prod nginx must route `/docket` (and `/docket/assets/...`) to the
  backend (same target as `/api`). Until then, reach it only via the backend origin
  directly (e.g. `:8000/docket`).
- **DB:** `data/docket.db` is created automatically on first import; it's gitignored.

## Decision log
- 2026-06-10 — Name = **Docket**. Standalone React app, subsumes old hub. SQLite store.
  Two zones. Hybrid grooming. Full autonomy w/ rails (orchestrator owns state, per-phase
  agent, worktree+gh, never auto-merge, empty denylist). Email via msmtp (cred pending).
