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

- **WHERE THIS LIVES (read first):** Docket now has its OWN git worktree at
  **`/home/conorbowles51/app_v2-docket`** (branch `feat/docket`). Do all Docket work
  THERE — NOT in `/home/conorbowles51/app_v2` (that's the prod checkout, kept on `main`).
  This file is `app_v2-docket/DOCKET.md`. A durable systemd service **`owl-docket`** runs
  it on `0.0.0.0:8011` (its own `data/docket.db`, shares the app_v2 venv + `.env`).
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
  NOTE: no browser-driver tooling here, so the pixel render wasn't automated.
- **DURABLE WEB DEPLOY (done):** live at **http://34.139.254.219:8011/docket** (testers
  alex/arturo/conor/neil, pw `testing`) via the `owl-docket` systemd service (enabled,
  Restart=on-failure — verified it respawns on kill and survives reboot). Runs `main:app`
  from the worktree. GCP firewall rule `allow-docket-8011` opens the port. 8 demo tickets
  preserved.
- **Phase 1 COMPLETE. Phase 2 + write autonomy are LIVE (`DOCKET_AGENT_WRITES=1`).**
  The `owl-docket-agent` service auto-picks queued tickets and runs the FULL pipeline with
  real headless Claude: assess → (grooming gate) → plan → implement → self-review → commit
  → push branch → PR (compare URL). Never auto-merges. VERIFIED end-to-end live: DKT-15
  went queued→pushed branch in ~48s autonomously. Pushed demo branches on origin:
  `docket/DKT-14`, `docket/DKT-15` (unmerged; open or delete at will).
- **Runs as root** (claude creds + GitHub push key + Neil B <thenofisamizdat@gmail.com>).
  Agent reads `DOCKET_MAIN_CHECKOUT` (default /home/conorbowles51/app_v2 = owl-n4j `main`)
  as the target repo. Manage: `systemctl status|restart|stop owl-docket-agent`;
  `journalctl -u owl-docket-agent -f`. Units version-controlled in `docket/deploy/`.
- **DONE since:** write autonomy LIVE; markdown rendering; time-taken + effort metric;
  **User-Review loop closed** — agent auto-writes non-technical test instructions before PR;
  detail view shows a "Ready for you to test" panel (instructions + It-works/Send-back).
- **Phase 4 (Coaching analytics) DONE (2026-06-11):** live **clarity meter** in the New
  Ticket form (debounced `POST /api/tickets/clarity`, 0–100 score + level bar + concrete
  suggestions) and clarity score/level **stored at creation** (schema migration on init_db).
  New **Analytics tab** (`GET /api/tickets/analytics`): throughput, agent effort (time+cost),
  quality (bounce rate / resubmits / failed-review), per-tester coaching table, clarity
  distribution, and a recent **"bounced & why"** feed. Verified live on :8011 (17 tickets).
- **Next action (pick one):** (B) **Real PRs + notifications** — gh/PAT for real PR objects
  + msmtp delivery (needs a GitHub token + the SMTP cred). (C) **Real deploy** on the main
  origin (migrate hub data, retire the vanilla page). (D) board-card time/effort badge (small).
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
  - [x] Submit/resubmit flows — submit + amend-on-fail resubmit (reason + edits + priority,
        iteration bump, reason recorded on timeline; `/api/tickets/{id}/resubmit` + AmendModal)
  - [x] Migrate old hub: Checklist tab (catalogue + per-tester pass/fail/blocked + notes,
        all-testers summary, "Raise ticket" bridge). Discussion + bug/feature submission are
        covered by Docket tickets. Reuses `/api/testing/*`. NOTE: vanilla-JS `testing-hub.html`
        not deleted yet (still serves prod testers on :8000/testing) — retire at real deploy.
        NOTE: Docket's checklist writes the WORKTREE's own data/testing-feedback.json (fresh);
        prod hub's accumulated feedback/user_items not yet migrated — do at cutover.
  - [~] Deploy: DURABLE interim env live via `owl-docket` systemd service on :8011 (own
        worktree + DB). Real deploy on the main origin (deploy.sh build step + route) still TODO.
- [~] **Phase 2 — Plumbing:** orchestrator `backend/services/docket_agent.py` runs headless
  Claude per phase (stream-json → live activity ticker), drives state transitions, posts
  assessment/plan/notes to the timeline, with per-phase max-turns + budget caps + grooming
  gate + stall-on-error. Runs as the `owl-docket-agent` systemd service (root → claude creds
  + GitHub key + Neil B <thenofisamizdat@gmail.com> identity). VERIFIED live: vague P0 →
  Needs Info (real clarifying question); clear P2 → assess+plan; auto-grooms queued tickets.
  - [x] read-only phases (assessment + planning) — REAL, safe, live
  - [x] worktree-per-ticket scaffolding + commit/push/PR code paths (written)
  - [ ] msmtp delivery of the queued notifications (still needs the SMTP cred)
  - [ ] real PR *object* creation (currently push branch + compare URL; needs gh/PAT)
- [~] **Phase 3 — Turn autonomy on** behind `DOCKET_AGENT_WRITES`: 0 (default) = grooming
  only (assess+plan, read-only); 1 = implement → self-review → push branch → PR.
  - [x] Write path VERIFIED supervised (DKT-14, WRITES=1 PUSH=0): agent implemented a clean
        idiomatic diff (stacked `@router.get` alias), committed as Neil B
        <thenofisamizdat@gmail.com>, self-reviewed vs acceptance criteria, held the push.
  - [x] `DOCKET_AGENT_PUSH` gate (default = WRITES) to hold the push for manual inspection.
  - [ ] Decide push policy / open the first real PR; then consider enabling writes on the
        live service (currently still WRITES=0 = grooming only).
- [x] **Phase 4 — Coaching analytics:** clarity scoring at submit (live meter +
  stored at creation, `score_clarity`/`/clarity`), analytics dashboard (`analytics()`/
  `/analytics` + `Analytics.jsx` tab): throughput, effort (time+cost), quality
  (bounce/resubmit/failed-review), per-tester table, clarity distribution, "bounced & why".

---

## Web access — DURABLE early-access env (`owl-docket` service)
- **Live at:** http://34.139.254.219:8011/docket  (testers alex/arturo/conor/neil, pw `testing`).
- **Isolation:** runs from its OWN git worktree `/home/conorbowles51/app_v2-docket` (branch
  `feat/docket`), so prod (`/home/conorbowles51/app_v2`, kept on `main`) is untouched. Shares
  the app_v2 venv + `.env` (read-only); has its OWN `data/docket.db` + `data/tmp`.
- **Service:** `owl-docket.service` (`/etc/systemd/system/owl-docket.service`) — User
  conorbowles51, `uvicorn main:app --host 0.0.0.0 --port 8011 --workers 1`, Restart=on-failure,
  enabled (survives reboot). Manage: `sudo systemctl {status,restart,stop} owl-docket`;
  logs: `journalctl -u owl-docket -f`.
- **Firewall:** GCP rule `allow-docket-8011` (default network, 0.0.0.0/0, tcp:8011), 2026-06-10.
  Revert: `gcloud compute firewall-rules delete allow-docket-8011`.
- **Cost note:** this is a full `main:app` instance (Neo4j + embeddings load at startup,
  ~2.4 GB RSS) — heavy for a ticket app. Box has no swap (see host-OOM memory). A lighter
  Docket-only ASGI entrypoint is possible later but needs `routers/__init__` to stop eager-
  loading the heavy stack. Acceptable for now.
- **To retire / supersede:** `systemctl disable --now owl-docket`, delete the firewall rule,
  `git worktree remove /home/conorbowles51/app_v2-docket` — once Docket folds into the real
  deploy.

## Autonomous agent (Phase 2) — `owl-docket-agent`
- **Code:** `backend/services/docket_agent.py`. Orchestrator OWNS transitions; invokes
  headless `claude` once per phase (`claude -p --output-format stream-json --verbose
  --max-turns N --max-budget-usd X --permission-mode … --model sonnet`), parses tool_use
  events → `set_activity()` ticker, parses the final `result` for the phase content.
- **Phases:** Assessment (read-only) → grooming gate → Planning (read-only) → [gated]
  In Development → Self-Review → push branch + PR. Read-only phases disallow Edit/Write.
- **Grooming gate (hybrid):** assess prompt ends with `VERDICT: PROCEED` or
  `VERDICT: NEEDS_INFO || <question>`. Vague **P0/P1** → bounced to Needs Info + notify;
  vague lower-priority → proceed best-effort with a recorded assumption note.
- **Guardrails:** per-phase `--max-turns` + `--max-budget-usd`, subprocess timeout, any
  failure → **Stalled** + notify. NEVER auto-merges (stops at PR).
- **Autonomy flag:** `DOCKET_AGENT_WRITES` (service env). `0` = grooming only (LIVE now).
  `1` = full implement→review→push→PR (paths written, **not yet tested e2e**). To enable:
  edit `docket/deploy/owl-docket-agent.service` (or the installed unit), set `=1`,
  `systemctl daemon-reload && restart owl-docket-agent`. Test on ONE low-risk ticket first.
- **Other env:** `DOCKET_AGENT_MODEL` (sonnet), `DOCKET_MAIN_CHECKOUT` (target repo to work
  in; default the owl-n4j `main` checkout), `DOCKET_WORKTREE_DIR`, `DOCKET_AGENT_POLL`.
- **Known gaps:** real PR-object creation needs `gh`/PAT (currently push + compare URL);
  notifications are queued in the DB but msmtp delivery isn't wired (needs SMTP cred);
  tickets about Docket ITSELF need the target checkout pointed at the feat/docket worktree
  (default targets owl-n4j main).

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
