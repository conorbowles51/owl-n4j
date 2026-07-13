# V1 ↔ V2 Divergence Analysis — Workfile

> **Resume protocol:** On "continue" (or "continue divergence"), read this whole file, jump to the **▶ NEXT** block, do that unit of work, then update the status table + Findings log + move ▶ NEXT. Keep this file authoritative and current every step. Mirror durable conclusions into memory (`project_v1_v2_divergence.md`).

_Last updated: 2026-07-12 (session: grounding complete, scaffold created)_

---

## 0. Established topology (ground truth — verified, do not re-derive)

| | **v1** (legacy / feature dev) | **v2** (mature build under test) |
|---|---|---|
| Working tree | `/home/conorbowles51/app_v2` | `/home/conorbowles51/app-v3/owl-n4j` |
| Branch | `main` @ `f75fe57` (2026-07-04) | `integration/evidence-main-reunion` @ `cb0c123` (2026-07-08) |
| Backend port | `8000` (uvicorn) — **LIVE** | `8002` (uvicorn) — **LIVE** |
| Frontend port | `5173` (vite) — **LIVE** | `5174` (vite) — **LIVE** |
| Frontend folders | `frontend/` (legacy) **+** `frontend_v2/` (React) | `frontend_v2/` only (v2-only tree, no `frontend/`) |
| Extra modules | — | `evidence-engine/` (NEW), `landing/` (NEW), `INTEGRATION_PLAN.md` |

**Fork point:** both v2 branches fork from `main` at **`a73da708`** — "Add case deadlines feature" (2026-03-18). Everything after that date is divergence.

**Branch lineage (verified):**
- `main` is **389 commits** ahead of the fork on its own line (v1 feature dev continued).
- `integration/evidence-main-reunion` (the live v2) is **124 commits** ahead of the fork. It is **NOT** a linear descendant of `evidence-engine-migration` — it was built to *reunite* evidence-engine work with main features but on an independent line.
- `evidence-engine-migration` @ `0752a5c` (2026-05-21) is the older v2 line; reunion supersedes it as the deployed build.

**Divergence magnitude (main ↔ reunion, since fork):** `983 files changed, +112,117 / −135,568 lines`.
Files changed by top dir: `frontend_v2` 299 · `backend` 204 · `frontend` 147 (mostly deletions — v1-only folder) · `ingestion` 105 · `evidence-engine` 98 (new) · `landing` 31 (new) · `docs` 18.

**Scope decision:** "v1 vs v2" = **`main` vs `integration/evidence-main-reunion`**, across frontend AND backend. The 45-item checklist (below) is the *behavioral parity yardstick*; the structural tracks are the *architectural divergence map*. Note the checklist's `frontend_v2/...` paths exist on BOTH trees — parity is tested against the **live v2 at :5174**, not the frontend_v2 folder on main.

**Test case:** "Operation Silver Bridge" — case `60b9367c-…` (171 entities, 411 relationships, 29,014 txns / 23,212 usable, 300 bank statements, multi-phone Cellebrite).

**Reference docs (read as needed):**
- `docs/frontend/MIGRATION_GUIDE.md` — v1→v2 component parity table + URL map (86 lines)
- `TESTING_PLAYBOOKS.md` — 18 manual playbooks w/ API calls + expected results (2401 lines)
- `TEST_REPORT_2026-02-20.md` / `UI_TEST_REPORT_2026-02-20.md` — last known-good baselines

---

## 1. Work tracks & status

### Track A — Structural divergence (git/code-derived; no live app needed)
| # | Unit | Status | Output |
|---|---|---|---|
| A1 | Backend router/endpoint inventory diff (main vs reunion): added / removed / changed routes | NOT STARTED | |
| A2 | Backend service/module diff, incl. the new `evidence-engine/` module — what it is, what it replaces | NOT STARTED | |
| A3 | Ingestion pipeline diff (`ingestion/` 105 files) | NOT STARTED | |
| A4 | Frontend route map diff + `features/*` module inventory (v1 frontend_v2 vs v2 frontend_v2) | NOT STARTED | |
| A5 | Shared API client / auth / SSE contract diff (confirm "same backend API" claim holds) | NOT STARTED | |
| A6 | Data model / schema diff (Neo4j labels, Postgres tables, evidence.json shape) | NOT STARTED | |
| A7 | Config / deploy / docker-compose diff (`landing/`, ports, nginx) | NOT STARTED | |

### Track B — Behavioral feature parity (live: v1 :5173 vs v2 :5174, same backend contract)
Record **PASS / FAIL / DEGRADED** + one-line repro. Known-gaps (§3) are recorded, never failed.

| # | Feature (v1 → v2) | Status | Evidence / repro |
|---|---|---|---|
| 1 | Login / JWT `authToken` | NOT STARTED | |
| 2 | Dashboard + case list, RBAC | NOT STARTED | |
| 3 | Case settings (rename, membership, presets) | NOT STARTED | |
| 4 | Theme toggle (`theme` key dark/light/system) | NOT STARTED | |
| 5 | Command palette / shortcuts (v2-new, sanity only) | NOT STARTED | |
| 6 | Evidence upload (all types) + SHA256 dupe reject | NOT STARTED | |
| 7 | Evidence details + previews (PDF/audio/image OCR/video) | NOT STARTED | |
| 8 | Folder profiles + wiretap triad routing | NOT STARTED | |
| 9 | Triage pipeline progress + resumable + `/admin/tasks` | NOT STARTED | |
| 10 | Graph view (171/411), filters, PageRank/Louvain/betweenness | NOT STARTED | |
| 11 | Node details: verified_facts (source/page/quote/validated) vs ai_insights | NOT STARTED | |
| 12 | Add/edit/delete node → persists to Neo4j | NOT STARTED | |
| 13 | Create/delete relationship | NOT STARTED | |
| 14 | Merge entities (incl. bulk), no orphans | NOT STARTED | |
| 15 | Cypher panel: reads ok, writes blocked on chat path | NOT STARTED | |
| 16 | Timeline keyset pagination past 5,000-row envelope | NOT STARTED | |
| 17 | Map: geocoded plot, tile aggregation, reverse-geocode search | NOT STARTED | |
| 18 | Table: relation expansion, bulk edit, export | NOT STARTED | |
| 19 | Financial dashboard (23,212 usable txns), charts, money-flow | NOT STARTED | |
| 20 | Curation + audit trail (categorise, override, amount correction, parent/child) | NOT STARTED | |
| 21 | Financial PDF export, corrected-amount footnotes | NOT STARTED | |
| 22 | Chat SSE streaming (semantic/structural/hybrid) | NOT STARTED | |
| 23 | Citations `doc://…/N`, click→viewer at page, spot-check 3 quotes | NOT STARTED | |
| 24 | Doc-scoped chat (two-phase retrieval) | NOT STARTED | |
| 25 | Model switch + cost ledger (`/admin/usage`, Ollama=$0) | NOT STARTED | |
| 26 | Result-graph building (extraction only) | NOT STARTED | |
| 27 | UFED ingestion: 1 PhoneReport/device, idempotent re-ingest | NOT STARTED | |
| 28 | Unified contacts (E.164 dedupe, alias rollup, counts) | NOT STARTED | |
| 29 | Intersections spatial/celltower/WiFi (20K cap behaviour) | NOT STARTED | |
| 30 | Cross-phone graph (anchored; unanchored top-200 cap) | NOT STARTED | |
| 31 | Unified timeline swim lanes + cross-phone comms search | NOT STARTED | |
| 32 | Callouts (flag events; PDF prototype — record only) | NOT STARTED | |
| 33 | Comm-hub / convoy intersections (prototype, smoke only) | NOT STARTED | |
| 34 | Case-context dossier (charges/allegations/…/trial info) | NOT STARTED | |
| 35 | Theories (create/edit, theory-scoped export) | NOT STARTED | |
| 36 | Witnesses (credibility, interview + wiretap linkage) | NOT STARTED | |
| 37 | Notes / tasks / deadlines CRUD | NOT STARTED | |
| 38 | Case entities (7 types, type fields, linking) | NOT STARTED | |
| 39 | Snapshots (capture subgraph+timeline+chat+state, restore, PDF) | NOT STARTED | |
| 40 | Case/theory export (HTML+PDF, 15 sections) | NOT STARTED | |
| 41 | Admin: user management (create/disable, roles) | NOT STARTED | |
| 42 | Admin: profile management CRUD | NOT STARTED | |
| 43 | Admin: system logs (JSONL, rotation @10K) | NOT STARTED | |
| 44 | Admin: background tasks queue accuracy | NOT STARTED | |
| 45 | Setup wizard (fresh DB only) | NOT STARTED | |

---

## 2. Findings log (append-only; newest first)
_Each entry: date · track/item · verdict · evidence (API status + UI/code observation) · repro._

### 2026-07-12 · FINANCIAL RE-ANALYSIS (user flagged original report as badly wrong here — confirmed)
**Method failure identified:** original agents judged parity by endpoint existence. Financial route lists match ~1:1, but the implementations diverged in BOTH directions post-fork. Original "✅ PASS" verdicts on items 19–21 were unsound.

**Two independent post-fork financial projects:**
- **v1-only (absent in v2):** `data_version=legacy|v2` audit-v2 reprocessed-txn filter (list + PDF export; d03757b); Payments/Receipts sign-based semantics + rename (c4fe355); Money Flow perspective section (c4fe355); per-entity breakdown pages in PDF (05c51af, 52d1d53); section-picker + chart-embedded 1,088-line export design; `/upload-notes` CSV import + txn ref IDs + auto-extract categories (7dbbe46); sync-def event-loop fix (fe6d266). v1 UI renamed cards; v2 UI still says "Money In/Money Out".
- **v2-only (absent in v1):** `mode=transactions|intelligence` dual dataset keyed on `is_evidence_backed_transaction`/`financial_model_version=2`/`financial_view_mode`; `uses_legacy_financial_model` auto-detect; from-scratch 482-line HTML export (provenance labels, txn grouping, entity-flow section — design never existed in main history); frontend `EntityFlowTables.tsx`, tested `filter-transactions` lib, `date-utils`, mode toggle.
- **True parity (verified at logic level):** amount-correction guard (`original_amount` preserved on first correction, identical Cypher), correction_reason, sub-transactions, categorize/batch endpoints, MANUAL_FROM/MANUAL_TO override edges (both).

**Live bugs found (both stacks share `safe_float` NaN→0):**
- **v1 LIVE: ET-Fraud (7e3b2c4a) `/api/financial/summary` = $0 volume / $0 avg / $0 max over 43,805 txns.** Root cause verified in Neo4j: 1 stored NaN amount poisons `sum()`/`max()` → NaN → `safe_float` flattens to 0. Plus 144 unparseable amounts silently excluded from all aggregates. Repro: cypher `count=43805, vol=NaN, unparsed=144, nans=1`.
- **v2 latent:** same query shape + same `safe_float`; one NaN amount will zero v2's summary identically.
- **v2 data-state:** flagship case (Godoy 042cfaee) has **0 evidence-backed transactions**; default mode shows an empty dashboard; `mode=intelligence` = 12 LLM events ($7,130). No statement data has ever been ingested to v2 — financial cannot be QA'd there until it is.

### 2026-07-12 · RE-VERIFICATION SWEEP COMPLETE → REPORT SECOND EDITION SHIPPED
All 5 agents returned; `V1_V2_DIVERGENCE_REPORT.md` fully rewritten (second edition; first edition's endpoint-existence method invalidated). Corrected tally: ✅16 · 🟡17 · 🔴12 (was ✅30 · 🔴2). Headline reframe: **v2 = re-platform of a ~2026-05-17 v1 snapshot; ~2 months of v1 work missing** (cellebrite ~131/200 post-fork commits absent incl. owner attribution/TZ/dedup/callouts/identity-merge + ~19 ingestion writers; financial sprint absent; tus uploads absent; wiretap service a "retired" stub behind a live route; export layer absent). Verdict flips vs 1st ed.: items 6, 8, 19, 21, 25 (v2 under-meters AI spend incl. whole unmetered subsystems), 26 (extract-nodes 500s — unported case_id fix). New live findings: **unauthenticated write-Cypher `/api/graph/execute-single-query`+`/execute-batch-queries` on BOTH stacks** (P0 security); v1 `/api/timeline` unauthenticated; v1 ET-Fraud summary $0-over-43,805-txns (NaN poisoning, 1 NaN + 144 unparseable; v2 latent-identical); v2 genuine gains verified (audited case-scoped node edits, Postgres recycle bin, honest timeline totals, agent console cypher guard, evidence-engine pipeline). Roadmap reframed: pick port-v1→v2 (recommended) vs backport-arch→v1 vs alpha-on-v1; P0 = security holes + NaN fix + cellebrite decision + v2 broken endpoints.

### 2026-07-12 · RECON — critical pre-analysis findings
- **F1 (CRITICAL, alpha-blocker) — Disjoint databases.** v1 and v2 run entirely separate Postgres (5432 vs 5434) + Neo4j (7687 vs 7688). v1 Neo4j = **1,496,075 nodes / 8 real cases**; v2 Neo4j = **19,242 nodes / 7 different cases**. No case_id overlap. The playbook case "Silver Bridge / 60b9367c" exists in NEITHER (stale ID). ⇒ True data-identical A/B testing is impossible; v2 has NOT received the production case data. Track B pivoted to per-stack contract/feature parity.
- **F2 (CRITICAL) — ~100× node collapse for the same investigation.** OPDMD28 (Godoy Lemus): v1 `43f1afb1` = 734,094 nodes vs v2 `042cfaee` = 7,638 nodes (21,236 links). Either v2 uses a radically different graph model (txns/comms no longer materialized as nodes) or ingestion is incomplete — Track A3 is determining which via label breakdown.
- **F3 — Auth works via minted JWT.** Both `neil` users are `super_admin`. Playbook creds stale. Tokens minted with HS256 secret `supersecretchange` (config default, identical both backends) → `t1.txt`/`t2.txt` in scratchpad. Real login passwords unknown (bcrypt in Postgres).
- **F4 — OpenAPI surface:** v1 = 269 paths, v2 = 274 paths (snapshots saved). Endpoint-level diff in progress (Track A1).
- **F5 — v1 archived cases return empty graph.** `43f1afb1` (archived) → `/api/graph` returns `{nodes:[],links:[]}` despite 734k Neo4j nodes; use non-archived cases (ET-Fraud 7e3b2c4a, Abraham 5e374d4f) for v1 behavioral tests.
- **F6 — MIGRATION_GUIDE marks ALL 30+ features "✅ Ported"** and claims "exact same backend API." Being verified against reality — v2 is a separate backend process (:8002), so parity failures can be v2-backend regressions, not just frontend.

### Analysis run status (11 agents dispatched 2026-07-12)
Track A: A1 backend-diff · A2 frontend-diff · A3 data/ingest/deploy. Track B: B1 auth/shell/admin · B2 evidence · B3 graph/cypher · B4 timeline/map/table · B5 financial · B6 chat · B7 cellebrite · B8 workspace. Awaiting completion → synthesize into §4 report.

- 2026-07-12 · Scaffold · Grounding complete. Topology, fork point, divergence magnitude, live services all verified (see §0).

---

## 3. Known v2 gaps — RECORD, never fail as parity regressions
- Reports module (`/cases/:id/reports`) — chart-generation stub (guide says "ported"; treat as stub).
- Multi-turn chat memory — each question independent; history stored but unused.
- Chat feedback loop — no "answer is wrong" mechanism.
- View-context injection — backend done, frontend partial.
- Real-time co-editing — last-write-wins; presence indicator (CaseHeaderBar) but no locking.
- Silent truncation — 20K-event intersection cap, 5,000-row timeline envelope, 200-person unanchored cross-phone graph: no user-facing warning yet. **Log observed behaviour for must-fix list.**
- Bates numbering / chain-of-custody ledger / SAR export — not implemented anywhere.

---

## 4. Final report deliverables (assemble when tracks complete)
1. Per-checklist-item table: `# | Feature | PASS/FAIL/DEGRADED | Evidence | Repro`.
2. (a) v1 behaviour missing in v2 not already in §3. (b) Anything that silently drops/truncates data. (c) Top 5 issues ranked by **forensic-integrity risk**, not cosmetic severity.
3. Structural divergence summary (Track A): frontend + backend architecture deltas.

---

## ▶ NEXT
**SECOND-EDITION REPORT SHIPPED (2026-07-12, evening).** First-edition report was invalidated (endpoint-existence method missed logic-level divergence — user caught it via the financial section). Re-verified all surfaces with two-way post-fork commit diff + logic diffs (5 agents + direct financial deep-dive). **`V1_V2_DIVERGENCE_REPORT.md` is now the corrected, readable, confidence-labeled roadmap basis.** Tally ✅16 · 🟡17 · 🔴12.

**DECISION (Neil, 2026-07-13): v2 IS THE PLATFORM.** Port v1's post-fork work onto v2; **nothing gets backported to v1**. All remediation lands in `/home/conorbowles51/app-v3/owl-n4j`.

**SCOPE (Neil, 2026-07-13): REPORT ONLY — do not build or fix anything.** Purpose clarified by Neil: v1 was the dev/test environment; the work = assess v2's gaps (features yet to be ported), decide port/rebuild/drop per gap, get v2 to enterprise level. Deliverables (BOTH SHIPPED 2026-07-13):
1. **`V1_V2_DIVERGENCE_REPORT.md`** — human-readable gap assessment (reframed; §3 = gap inventory, §8 = phased plan).
2. **`V2_BRIDGING_ROADMAP.md`** — ticket backlog: 52 tickets (BRG-001…052) across 9 epics, each with v1 reference commits, acceptance criteria, size, PORT/REBUILD/FIX/DECIDE/DROP recommendation + suggested sprint sequencing. 9 DECIDE tickets need Neil before work starts; conscious-drop list included.

If resuming: no code work authorized yet. Next expected step = Neil reviews the roadmap → decision meeting on the 9 DECIDE tickets → tickets transcribed into Docket → Sprint 0 (E1 security/stability) begins on authorization. Read-only caller-check note: nothing in v2 calls `execute-single-query`/`execute-batch-queries` (dead code from v1's case-version loader); verify v1 legacy frontend usage before deleting.
