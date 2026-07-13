# V2 Gap Assessment — what's yet to be ported from v1, and what to do about it
### The basis for the v2-as-The-Platform bridging roadmap

_2026-07-12/13. **Purpose:** v1 has been the feature development and testing environment; v2 is becoming The Platform. This report inventories every feature developed on v1 that has not (yet) made it into v2, assesses each one — port it, rebuild it, or consciously drop it — and feeds the ticket roadmap in **`V2_BRIDGING_ROADMAP.md`**._

_This replaces the first edition, which was materially wrong: it judged parity by whether the same API routes existed on both stacks, and on several surfaces the routes match while the code behind them is months apart or entirely different. This edition re-verified every major surface at the code level — each branch's actual commit history and implementation since the fork — plus live probes. Every finding says what its evidence is._

---

## 1. The story in one page

**v1** is the production system: `/home/conorbowles51/app_v2`, branch `main`, ports 8000/5173.
**v2** is the alpha candidate: `/home/conorbowles51/app-v3/owl-n4j`, branch `integration/evidence-main-reunion`, ports 8002/5174.
Both split from the same commit (`a73da708`, 2026-03-18) and then evolved **independently for four months**.

What v2 actually is: **a re-platforming of v1 as it stood around mid-May 2026, plus v2's own new architecture on top.** The v2 team took a snapshot of v1, moved storage from JSON files to Postgres, moved ingestion into a new `evidence-engine` microservice (Redis workers, ChromaDB vectors), rebuilt the evidence UI, and added new systems (agent console, timeline views, AI merge). They did **not** keep pulling in v1's ongoing work. Meanwhile v1 shipped roughly two more months of features and bug fixes — the entire financial reprocess sprint, ~131 cellebrite commits, resumable uploads, the export layer's confidentiality work, and a stream of user-reported DKT fixes.

The consequence, and the single most important fact for the roadmap:

> **Moving to v2 as it stands means shipping the platform as it was in mid-May, minus some things that were dropped in the port, plus v2's new architecture. Every v1 feature and bug fix from mid-May to July would regress — including fixes for bugs that users personally reported (the DKT tickets).**

v2's architecture is genuinely better in important ways (see §4) — this is not an argument to abandon it. It is an argument that the alpha work is mostly **porting two months of v1 onto v2**, not just fixing a handful of v2 bugs.

**Direction (decided 2026-07-13): v2 is The Platform.** All work ports forward onto v2; nothing is backported to v1. v1 is feature-frozen — production until cutover, and the reference implementation for the ports. §8 is the sequenced plan.

The second most important fact: **v2 has essentially no data.** Its flagship case has zero statement-extracted transactions and zero PhoneReports. Financial and cellebrite features cannot be QA'd on v2 at all until real data is ingested through its new pipeline — and its cellebrite ingester is missing ~19 artifact writers and the integrity gates v1 added (§3.2), so re-ingesting today would produce quietly incomplete data.

---

## 2. Where the first report was wrong (read this to know what to trust)

| Surface | First report said | Reality (this pass) |
|---|---|---|
| Financial (items 19–21) | ✅ PASS, "identical logic" | Two **different financial engines** behind identical routes. v1 has the reprocess-sprint features (`data_version` audit filter, Payments/Receipts, Money Flow perspective, per-entity PDF pages, CSV notes import); v2 has none of them. v2 has its own concepts (`mode=transactions\|intelligence`, evidence-backed flags) that v1 lacks. v2 also has **no transaction data at all**. |
| Wiretap triad (item 8) | ✅ PASS | v2's `/wiretap/process` endpoint exists but the service is a **stub returning "Legacy wiretap folder processing has been retired"**. The whole wiretap audio/transcript/.sri pipeline is dead in v2. |
| Cost ledger (item 25) | ✅ PASS | v2 **materially under-reports AI spend**: only the final chat answer is metered; classify/cypher-gen tokens are dropped, and the relationship analyzer, triage LLM, and evidence-processing calls record nothing at all. |
| Result-graph extraction (item 26) | ✅ PASS | v2's `/api/chat/extract-nodes` **fails with a 500 on every call** (a required `case_id` argument is never passed — a v1 fix that was never ported). |
| Evidence upload (item 6) | ✅ PASS | v1's proven-at-35GB tus resumable-upload stack does not exist in v2, and v2 uploads run synchronously in-request with none of v1's failure-surfacing fixes. |
| Cellebrite (items 27–32) | "code present, just no data" | The code itself is a **7-week-stale fork missing ~65% of v1's post-fork cellebrite work** (~131 of ~200 commits). Re-ingesting data does not close that gap. |
| Chat (item 22) | 🟡 "no streaming" | Streaming was the wrong question. Real deltas: v2 gains multi-turn memory + per-answer case-revision pinning; v2 loses almost all view-aware context (4 publishing views → 1) and changes chat privacy so **any case member can read another member's chats** (v1: owner-only). |

Everything in this edition is labeled **[logic-diff]** (verified by comparing actual code/commits, high confidence) or **[contract-only]** (verified only by API shape — treat as provisional). Where a first-edition verdict survives, it was re-verified, not carried over.

---

## 3. The gap inventory — v1 features not yet in v2

This is the heart of the assessment: everything developed or fixed on v1 since the fork that v2 doesn't have. Grouped by what an investigator would experience. Everything here is [logic-diff] unless marked. Each gap maps to a ticket in `V2_BRIDGING_ROADMAP.md` with a port/rebuild/drop recommendation.

### 3.1 Financial investigation
- **The reprocessed-transaction audit filter is gone.** v1's `data_version=legacy|v2` lets you separate original extractions from re-audited ones on the transaction list and PDF export. v2 has no equivalent — the entire reprocess sprint's provenance model is unrepresented.
- **Payments/Receipts semantics gone.** v1 computes sign-based Payments (negative amounts) vs Receipts (positive) and renamed the UI accordingly. v2 still shows the old "Money In / Money Out" cards with no sign convention.
- **The financial PDF lost the sprint redesign**: no Money Flow perspective section, no per-entity breakdown pages, no section picker, no embedded volume/category charts. v2 substitutes its own (also new) entity-flow-table export — a fork, not a port.
- **CSV notes import (`/upload-notes`), transaction ref IDs, auto-extract categories: gone.**
- What genuinely survives: amount-correction guards (`original_amount` set once, never clobbered; mandatory `correction_reason`), sub-transactions, categorization — verified identical at the Cypher level.
- v2's own additions (not in v1): `mode=transactions|intelligence` to separate statement-extracted from LLM-inferred financial events, legacy-model auto-detection, a tested client-side filter library.

### 3.2 Cellebrite / phone forensics — the largest gap in the codebase
v2's cellebrite (frontend + backend + ingester) is a port of v1 as of ~May 17–18. **~131 of ~200 post-fork cellebrite commits are missing.** Missing wholesale:

- **Owner attribution** (owner-sent messages show "Unknown"), **timezone-correct timelines** (timestamps are stored UTC; without the TZ work, day boundaries and filters are wrong), **multi-source duplicate collapse** (duplicate rows in evidence views).
- **Callouts + the client-report workflow** (mark key events → assembled report), the **Report tab** (per-device forensic profile + PDF), and the **Search & Discovery center**. Two of v1's 11 tabs simply don't exist (v2 has 9).
- **The cross-phone graph rebuild** (~30 commits): directional edges, flow view, time-axis layout, server-side search/subgraph, expand-neighbours. v2 has the 331-line pre-rebuild version.
- **Identity resolution**: investigator-asserted person merges (audited), person search, WhatsApp number unification, per-device contact naming with numbers alongside names — all absent. These encode explicit product decisions (per-device perspective as default, number-alongside-name).
- **~12 user-reported DKT bug fixes** (comms search misses, duplicate messages, comms-center errors) that would regress on v2.
- **Ingestion integrity**: v2's ingester is missing ~19 artifact writers (Notification, Voicemail, NetworkUsage — which it parses then silently drops — Autofill, InstalledApplication, SIMData, Journey, and more), owner-number inference for full-file-system extractions, the empty-`phone_numbers` hard-fail, the nested-XML detection fix (DKT-34), the degenerate dedup-key fix (two numberless devices collide as "duplicates"), international phone normalization (identity conflation risk), contact-alias preservation, and the under-count coverage warnings.

**Roadmap consequence: "re-ingest UFED data into v2" is not a data task. It is ~131 commits of porting first, or the re-ingested data will be silently incomplete and the app around it two months stale.**

### 3.3 Getting evidence in
- **Resumable uploads gone**: v1's tus/Uppy stack (proven on 31.8GB and 35GB uploads) has no v2 counterpart; an interrupted large upload starts over.
- **Upload robustness gone**: v2 registers uploads synchronously in-request (1-hour client timeout, no background path), without v1's per-file failure counts, whole-batch-failure detection, disk-full (507) handling, or the amber "Action needed" task for silently-skipped no-phone reports.
- **Wiretap processing is a stub** (§2). The triad routing profile exists; the pipeline behind it does not.
- What v2 gains here is real: the evidence-engine pipeline (chunk/embed/extract/consolidate, at-ingest transcription via OpenAI, vision descriptions, WebSocket job progress) is genuinely ahead of v1's in-process document pipeline. Triage logic itself is byte-identical.

### 3.4 Producing work product (the courtroom deliverables)
- **Case export, theory export, snapshot PDF: gone.** v1's 15-section HTML/PDF export (including audit log, transcriptions, rendered visualizations, and the post-fork confidentiality labels) lives in v1's legacy frontend; neither v2 nor either `frontend_v2` tree has any of it. v2's only export is its (new, good) timeline CSV/PDF export.
- **Cellebrite callouts→client report: gone** (§3.2).
- **Map locations CSV export (DKT-5): gone.**

### 3.5 Audit trail and provenance
- **User-created nodes lose provenance stamps** (`user_created`, `created_by`, `created_at`, `source:'manual'`) — v2 cannot distinguish investigator-authored nodes from ingested evidence.
- **AI spend is under-metered** (§2) — an incomplete record of what the AI was asked during an investigation.
- **System logs lost the `case_id` filter** — you can no longer scope the audit trail to a case.
- **`/api/chat/extract-nodes` is broken** — the "show me the graph behind this answer" provenance feature 500s.
- **Chat privacy changed**: v1 conversations are owner-only; v2 lets any case member read any member's conversations. Gain or loss depending on policy — but it's a silent semantics change.
- **Timeline communication rows lose party attribution** (v1 synthesizes "sender → recipient"; v2 shows raw summary).

### 3.6 Smaller regressions worth knowing
- Boolean node properties serialize as `1/0` instead of `true/false` in generated Cypher (a v1 fix ordered the type checks correctly; v2 has the pre-fix version).
- Every v2 route handler is `async def` calling the blocking Neo4j driver directly — long graph queries freeze the whole backend (v1 fixed this with sync handlers/`to_thread`).
- Reverse-geocoder runs in the slow fork-per-call mode v1 abandoned (ingest of location-dense reports will crawl), and v2's live geocoder isn't running at all.
- Stalled background tasks can't be marked failed (recovery endpoint gone); task file lists rewrite unbounded per file (v1 caps at 100).
- Note→profile linking endpoints, `/nodes-by-type`, the QA/testing hub, on-demand media AI analysis: all gone.

---

## 4. What v2 genuinely improves (the reasons to keep going)

All [logic-diff]. The alpha plan should preserve these while porting §3.

- **Security fixes v1 needs badly**: v1's `/api/timeline` is **unauthenticated** (live-verified: any case's events without a token); v1's node update builds Cypher by string concatenation **without case scoping** (cross-case writes possible, injection-fragile); v1's node-details can return another case's node. v2 fixes all three: auth + case-scoping + parameterized, ontology-validated, **field-level-audited** edits (`manual_fields`, `last_edited_by/at`, before/after change log).
- **Postgres everywhere JSON files used to be** (evidence registry, workspace, chat, tasks, recycle bin, geocode cache) — ends the fcntl/multi-worker corruption class; the recycle bin now survives Neo4j corruption, which this deployment has actually experienced.
- **The evidence-engine pipeline** — real worker queue, vector store, at-ingest transcription/vision, job progress over WebSockets, folder-profile inheritance, per-case processing config.
- **Recycled entities excluded from all reads** — v1's PageRank/Louvain/counts include soft-deleted tombstones; v2 filters them everywhere.
- **Honest timeline totals** (true dataset count vs v1's page-size-as-total) and broader timeline coverage (multiple date fields, manual-clear respected).
- **Merge engineering**: async job with advisory locks, overlap 409s, crash recovery, partial-failure status, restore-with-rollback recycle bin. (The flip side — AI now chooses the merged fact set where the investigator used to — is a control-semantics change to decide deliberately, and the manual bulk-merge wizard is gone.)
- **Multi-turn chat with case-revision pinning** per answer, embedding cost tracking, per-request LLM context (fixes a real cross-user model-switch race in v1), the GPT-5 Responses API path.
- **The agent console** (v2-only): SSE streaming, thread history, artifact export, and a properly engineered read-only Cypher guard (allowlist, mandatory case scoping, READ_ACCESS transactions) — far stronger than the naive keyword filter both stacks use on `/api/query`.
- **Timeline views**: saved/curated views with CSV/PDF export.
- New: case-profile dossiers, notebook, triage UI, alias-aware fuzzy search, file tags/entity-linker.

---

## 5. Live bugs (reproducible today)

**Both stacks:**
- **`POST /api/graph/execute-single-query` and `/execute-batch-queries` accept arbitrary write Cypher with NO authentication.** An unauthenticated evidence-tampering vector on both backends. Worst finding of this pass; predates the fork.
- `/api/graph/locations` is unauthenticated on both.
- A single stored NaN amount zeroes the whole financial summary (`sum()`→NaN→`safe_float`→0).

**v1 live:**
- ET-Fraud financial summary shows **$0 volume / $0 avg / $0 max across 43,805 transactions** (one NaN amount; verified in Neo4j: `vol=NaN, nans=1`), and 144 unparseable amounts silently drop from every aggregate.
- `/api/timeline` unauthenticated (see §4).

**v2 live:**
- `/api/chat/extract-nodes` → 500 on every call (missing `case_id`).
- Theory timeline + investigation timeline → 500 (`DetachedInstanceError`).
- Cypher panel posts to `/api/graph/cypher` → 404 (real route `/api/query`).
- Betweenness centrality: no response in 120s on a 7.6k-node case (blocking, unbounded — and it freezes the event loop, §3.6).
- Wiretap processing returns `success: false, "retired"` (§2).

---

## 6. Silent truncation and honesty gaps (systemic, will bite on real-size cases)

| Where | What happens | User signal |
|---|---|---|
| Cellebrite intersections | 20,000-event load cap; `truncated`/`total` discarded | none |
| Cross-phone graph (v2) | hard cap 200 persons / 300 links (v1 lifted its cap with an honest counter — another unported fix) | none |
| Comms search | 200-match cap | none |
| `/api/graph` (feeds table/map/CSV export) | ~20K node cap, no `total`/`truncated` | none |
| v2 timeline client | stops after 100 pages × 2,000 rows even if a cursor remains | none |
| v2 cellebrite ingester | parses `NetworkUsage` then silently drops it; ~19 artifact types never written; no under-count warnings | none |
| System logs (both) | hard 10K-row trim deletes oldest audit rows | none |
| AI metering (v2) | triage/relationship/evidence LLM calls unmetered; Ollama leaves no row on either stack | "no row" reads as "no inference" |

---

## 7. Corrected per-feature verdicts (the 45-item yardstick)

✅ parity (re-verified) · 🟡 diverged/degraded — decide or port · 🔴 lost or broken in v2 · Basis: L = logic-diff, C = contract-only.

| # | Feature | Verdict | Basis | One-line reality |
|---|---|---|---|---|
| 1 | Login/JWT | ✅ | L | auth_service byte-identical |
| 2 | Dashboard/RBAC | ✅ | L | identical; v2 archive needs delete-perm (stricter) |
| 3 | Case settings | ✅ | L | byte-identical routers |
| 4 | Theme | ✅ | L | key is `owl-theme` |
| 5 | Command palette | 🟡 | L | scaffolding-only in both |
| 6 | Evidence upload | 🔴 | L | tus resumable + background robustness lost; sync in-request |
| 7 | Evidence previews | 🟡 | L | frames UI orphaned; on-demand media AI lost; v2 gains at-ingest transcription |
| 8 | Folder profiles/wiretap | 🔴 | L | profiles fine; wiretap pipeline is a stub |
| 9 | Triage | ✅ | L | processors byte-identical; storage→Postgres |
| 10 | Graph view/algorithms | 🟡 | L | same math, new response shapes; betweenness hangs; event-loop blocking |
| 11 | Node details | ✅ | L | pin/verify identical; v2 adds case-scoping (v1 leaks cross-case) |
| 12 | Node CRUD | 🟡 | L | v2 audited+scoped (gain) but provenance stamps + bool fix lost |
| 13 | Relationships | ✅ | L | parity |
| 14 | Merge | 🟡 | L | AI-async replaces manual; investigator control + bulk wizard lost; robustness gained |
| 15 | Cypher panel | 🔴 | L | v2 UI 404s; `/api/query` case-unscoped; unauth execute-* on BOTH |
| 16 | Timeline pagination | 🟡 | L | v2 honest totals (gain); `total` semantics incompatible; comm attribution lost |
| 17 | Map/geocode | 🟡 | L | geocoder mode regression, CSV export lost, v2 geocoder not running |
| 18 | Table | ✅ | L | v2 strictly better (fuzzy search, protected fields); /api/graph cap remains |
| 19 | Financial dashboard | 🔴 | L | different engine; sprint features lost; v2 has no txn data |
| 20 | Curation/audit | ✅ | L | correction guards verified identical |
| 21 | Financial PDF | 🔴 | L | v1 sprint design lost; v2 export is a separate fork |
| 22 | Chat | 🟡 | L | multi-turn+revisions gained; view-context & privacy semantics changed |
| 23 | Citations | ✅ | L | backfill line-identical |
| 24 | Doc-scoped chat | ✅ | L | v2 two-phase is a gain |
| 25 | Cost ledger | 🔴 | L | v2 under-meters whole subsystems |
| 26 | Result-graph extract | 🔴 | L | v2 endpoint 500s deterministically |
| 27–31 | Cellebrite suite | 🔴 | L | code 7 weeks stale (~131 commits) + zero data |
| 32 | Callouts | 🔴 | L | endpoints + workflow absent |
| 33 | Comm-hub/convoy | 🟡 | C | prototype both |
| 34 | Dossier | ✅ | L | all 8 fields, audited |
| 35 | Theories | 🟡 | L | CRUD fine; timeline 500s; export gone |
| 36 | Witnesses | ✅ | L | parity |
| 37 | Notes/tasks/deadlines | ✅ | L | deadlines byte-identical; note→profile links lost (minor) |
| 38 | Case entities/profiles | 🟡 | L | same URL, different system (Neo4j-backed vs Postgres+typed links) |
| 39 | Snapshots | 🟡 | L | capture/restore fine; PDF export lost; invisible on v2 investigation timeline |
| 40 | Case/theory export | 🔴 | L | entire layer absent |
| 41 | User management | ✅ | L | byte-identical |
| 42 | Profile management | 🟡 | L | file→DB rework; CRUD unauthenticated in BOTH |
| 43 | System logs | 🟡 | L | case filter lost; 10K trim both |
| 44 | Background tasks | 🟡 | L | mark-failed/stall recovery lost; unbounded file lists |
| 45 | Setup wizard | ✅ | L | parity |

**Tally: ✅ 16 · 🟡 17 · 🔴 12** (first edition claimed ✅ 30 · 🔴 2 — the difference is the method).

---

## 8. The Platform roadmap — porting v1 onto v2

**Decision (Neil, 2026-07-13): v2 is The Platform. Everything ports forward onto v2; nothing gets backported to v1.** v1 is feature-frozen and serves only as production until cutover, and as the reference implementation for every port below. This section is the sequenced plan; nothing here has been started.

> **The ticket-level version of this section lives in `V2_BRIDGING_ROADMAP.md`** — one ticket per gap with description, v1 reference commits, acceptance criteria, size, priority, dependencies, and a port/rebuild/decide/drop recommendation, ready to transcribe into Docket.

One standing consequence to keep in view: v1 stays live — with its unauthenticated write-Cypher endpoints, unauthenticated `/api/timeline`, and the $0-summary bug — until v2 replaces it. Every month of porting is a month those stay in production, which makes cutover speed itself a security decision.

Effort keys: **S** = hours–a day · **M** = days · **L** = 1–2 weeks · **XL** = multi-week.

### Phase 0 — make v2 safe and un-broken (all S–M; no dependencies; do first)
| Fix | Effort | Notes |
|---|---|---|
| Lock down `execute-single-query` / `execute-batch-queries` | S | Read-only caller check (2026-07-13): nothing in v2's frontend, evidence-engine, or ingestion calls them — dead code inherited from v1's case-version loader. Delete or auth+write-block. |
| Auth `/api/graph/locations` | S | Unauthenticated on v2 today. |
| NaN-guard financial aggregates | S | Filter non-finite amounts inside the Cypher aggregates and **return the excluded count** (no silent truncation). Same fix pattern serves summary, volume, entities. |
| `/api/chat/extract-nodes` 500 | S | Pass `case_id` through (v1 commit `cbf70e9` is the reference); also adds the missing case isolation. |
| Theory / investigation timeline 500 | M | `DetachedInstanceError` in `workspace_service` — eager-load or re-query inside the session. Unblocks theories and snapshot inputs. |
| Cypher panel 404 | S | Point `CypherPanel.tsx` at `/api/query`, adapt response shape; case-scope `/api/query` while in there. |
| Betweenness hang + event-loop blocking | M | Bound/async the computation; convert blocking-Neo4j `async def` handlers per v1 `fe6d266`. |

### Phase 1 — ingestion integrity gate (must land BEFORE any UFED re-ingest into v2)
Re-ingesting phone data through today's v2 ingester would produce quietly incomplete, mis-keyed data that later porting can't repair. Port from v1's `ingestion/scripts/cellebrite/` into `evidence-engine/app/pipeline/cellebrite/`:
- The ~19 missing artifact writers (Notification, Voicemail, NetworkUsage — currently parsed then dropped — Autofill, InstalledApplication, SIMData, Journey, …) — **L**
- Integrity gates: empty-`phone_numbers` hard-fail, degenerate dedup-key fix, nested-XML detection (DKT-34), under-count coverage warnings — **M**
- Identity correctness: owner-number inference (FFS extractions), libphonenumber E.164 normalization, contact-alias/ContactEntry preservation — **M–L**
- Geocoder: mode-1 + cache port (`e072fb2`) so location-dense ingest doesn't crawl; stand up the live geocoder — **S–M**

**Then** re-ingest the UFED corpus into v2 and validate against v1's counts per report (the reconciliation framework exists on both sides).

### Phase 2 — the big feature ports (parallelizable once Phase 1 is staffed)
| Port | Effort | Reference |
|---|---|---|
| Cellebrite app surfaces — 6 families: timeline 2nd wave (owner attribution, TZ, dedup, inline media), cross-phone graph rebuild, callouts + Report tab, Search & Discovery, identity merge + per-device naming, locations canvas/uncap; plus ~12 DKT fix re-applications | XL (largest single item; ~131 commits) | v1 `frontend/src/components/cellebrite/`, `backend/routers/cellebrite.py` |
| Financial sprint: `data_version` audit filter, Payments/Receipts semantics, Money Flow perspective + per-entity PDF pages + section picker, CSV notes import — reconciled with v2's `mode=transactions\|intelligence` (keep both axes; they answer different questions) | L | v1 `financial.py` + `financial_export_service.py` |
| Uploads: tus/Uppy resumable stack + background registration + failure surfacing (per-file counts, 507 on disk-full, amber "Action needed" tasks) | L | v1 `deploy/owl-tusd.service`, `evidence_service.py` |
| Case/theory/snapshot export rebuild (15 sections incl. audit log, transcriptions, visualizations, confidentiality labels). Build on v2's timeline-export service rather than porting v1's frontend-side jsPDF | L–XL | v1 `frontend/src/utils/*Export.js` for content spec |
| Wiretap pipeline: port the triad processing v2 stubbed out — or ship a deliberate, documented retirement | M–L | v1 `wiretap_service.py` + `ingest_audio.py` |

### Phase 3 — provenance & audit completeness (S–M each; some ride along with Phase 2 code)
- Node provenance stamps on user-created nodes (`ca91b9d`) + the cypher bool-serialization fix (same commit).
- Complete AI metering: record every LLM call site (relationship analyzer, triage, evidence processing, classify/cypher-gen legs) and $0 rows for Ollama.
- System-logs `case_id` filter; raise/replace the 10K-row audit trim.
- View-aware chat context re-published from the ported financial/cellebrite/table views.
- Decide chat-privacy semantics deliberately (owner-only vs case-visible) — currently a silent change.
- `total` + `truncated` on every capped surface (§6) with a visible banner.

### Phase 4 — cutover readiness
- Load the production corpus into v2; re-run the 45-item yardstick as behavioral QA (impossible today — v2 has no data).
- Scale verification: v1 500s on 571k-node cases; confirm v2's architecture actually fixes this at production size.
- Ops runbook + monitoring for the 4 new services (Redis, ChromaDB, engine API, engine worker).
- v1 decommission plan: cutover date, read-only grace period, data archival. The Phase-0 security holes exist on live v1 until this completes.

---

## 9. Method and remaining caveats

- Evidence basis: per-surface two-way commit history since the fork (`git log a73da708..HEAD` in each tree) + implementation diffs of the current files + read-only live probes on :8000/:8002/:8003. Five specialist passes (graph/entity, workspace/timeline/map/table/export, evidence/ingestion, chat/admin, cellebrite) plus a direct financial deep-dive.
- **[contract-only] residue**: v2 payload semantics on case-scoped endpoints could not be exercised with real data (v2's probe user owns no cases; v2 has little data regardless); LLM answer quality untested (shared OpenAI key over quota). Everything else is [logic-diff].
- Mutating endpoints were never called; all probes read-only.
- The 45-item yardstick's per-item detail lives in `V1_V2_DIVERGENCE_WORK.md`; raw per-surface findings (commit hashes, file:line) are preserved in the session transcripts and summarized in §3–§7.
