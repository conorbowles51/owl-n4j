# Ingestion issues — triage & resume notes

_Owl investigation platform. Created 2026-06-24. Source: ingestion-related feedback
flagged by Alex & team (QA hub → migrated to Docket tickets)._

**Current branch:** `fix/folder-upload-surface-failures` — already in-flight work on
surfacing upload/ingestion failures. Recent commits:
- `57838d1` uploads: auto-route Cellebrite reports to the ingestion pipeline
- `7e451cb` uploads: surface failures in the single-file background path too
- `3040228` cellebrite/uploads: surface folder-upload failures + fix degenerate dedup key

**Sources of truth:**
- QA feedback: `data/testing-feedback.json` (`user_items`, all from Alex).
- Docket tickets + agent diagnoses: `/home/conorbowles51/app_v2-docket/data/docket.db`
  (tickets / ticket_events tables).

---

## The three ingestion tickets (all have agent-proposed fixes IN FLIGHT — unverified)

### DKT-34 — 31.8 GB zipped Cellebrite XML won't load/process  · P2 · status: user_review
- **Report (Alex):** zipped XML of the Cellebrite extraction in the **Timothy Valentin**
  case (re-uploaded, 31.8 GB) is not showing in the evidence tab / not showing as ready
  for processing.
- **Agent fix (on its branch, pending review):** redirect Python `tempfile.tempdir` to a
  disk-backed path (so a 31 GB zip doesn't hit RAM-backed `/tmp`), and raise nginx
  `proxy_read_timeout` / `proxy_send_timeout`.
- **Root-cause context:** classic tmpfs/OOM issue. ⚠️ The real production fix is a
  **systemd `TMPDIR` drop-in that is NOT in git** — a deploy can silently revert it.
  Also relates to the upload-throughput bottleneck (per-file rewrite of a 288 MB
  evidence.json) — folder uploads must batch JSON persistence (~every 100 files).
- **To verify / next:** confirm the tempdir + timeout fix actually carries a 31 GB file
  end-to-end (upload → ready-for-processing → evidence tab). Make the TMPDIR drop-in
  deploy-safe / captured in repo or deploy.sh. Diagnose via the owl-frontend proxy log.
- **UPDATE (2026-06-25) — investigated. The original blockers are RESOLVED; the
  real blocker is now DISK CAPACITY, an infra issue (needs Neil).**
  - ✅ tmpfs/OOM: `TMPDIR=.../data/tmp` is live (systemd `tmpdir.conf`) **and now
    captured in repo** (`deploy/setup-server.sh:132`) — the "not in git, deploy
    reverts it" risk is closed. `/tmp` is still 16G RAM tmpfs but Python tempfile
    honours TMPDIR → spools to disk.
  - ✅ Timeouts: **nginx is INACTIVE** (not in the path at all — browser → Vite
    dev `:5173` → backend `:8000`). So the nginx 500M `client_max_body_size` /
    600s timeouts are MOOT. The Vite proxy already has `proxyTimeout: 0` /
    `timeout: 0` (`frontend/vite.config.js`).
  - ✅ Pipeline is streaming-safe: upload spools via SpooledTemporaryFile→TMPDIR,
    staged in 1 MiB chunks; zip extracted entry-by-entry in 1 MiB chunks
    (zip-slip guarded, original unlinked after); XML parsed with `iterparse`
    (constant memory); final move is `os.replace` (atomic, no copy). ENOSPC→507,
    MemoryError→507 are handled (`backend/routers/evidence.py`).
  - **Disk cleanup (2026-06-25):** reclaimed ~44 GB (**49→93 GB free**) — deleted
    3 `_staging` orphans (28 GB; verified partial-duplicates of live case dirs,
    not unique media), docker build cache (9.3 GB), pip cache (6.6 GB). Live
    docker volumes (118.6 GB Neo4j/PG/Chroma) untouched; stopped `nominatim`
    container/image preserved. **Tier 2 still available** (~33 GB of stale
    backups: `app_v2_backup` 25G, `app_backup` 3.8G, `app` 3.5G) to clear 100 GB+
    for the full 3× staging a 31.8 GB zip needs.
  - ⚠️ **REAL BLOCKER — disk:** `/dev/root` was 91% full / ~49 GB free, now 81% /
    ~93 GB free after the cleanup above — but still likely tight. The
    archive path holds ~3 full copies on staging *simultaneously*: TMPDIR spool
    (~31.8 GB) + staged zip (~31.8 GB) + the extracted tree (>> 31.8 GB,
    coexists with the staged zip until extraction finishes). A 31.8 GB Cellebrite
    zip needs **100 GB+** of free staging → it will ENOSPC → HTTP 507. **No code
    change can overcome this; needs disk provisioning or a streaming
    extract-from-spool that drops the intermediate staged-zip copy.**
  - Minor code follow-up (not the blocker): `parser.py` `stream_models` clears
    end-event elements but never the iterparse root — memory can still creep over
    a multi-tens-of-GB single XML. Add `root.clear()`/`del elem` if memory growth
    is observed on a real large run.

### DKT-29 — "Unknown error" loading filtered conversations  · P0 · status: user_review
- **Report (Alex):** unknown error when loading conversations in the Comms Center after
  filtering by numbers and/or contacts.
- **Agent diagnosis:** the "Unknown error" string comes from the `fetchAPI` wrapper in
  `frontend/src/services/api.js` (~line 78) when `response.json()` can't parse the error
  body — i.e. **the backend is returning a non-JSON 500** on the filtered conversation load.
- **To verify / next:** reproduce against real case data (filter by number/contact),
  capture the actual backend 500 + traceback (journald, not the wrapped frontend string).
  Fix the backend error, don't just mask it. Likely in the comms projection path.

### DKT-33 — Messages/calls/group-chats won't load (Abraham Luna Perez)  · P0 · status: pr
- **Report (Alex):** certain WhatsApp messages, phone calls, and group chats in the
  **Abraham Luna Perez** case don't load in the Comms Center → "unknown error" on click.
- **Agent fix:** `get_comms_thread_detail` in `backend/routers/cellebrite.py` now wraps
  the Neo4j call that was throwing.
- **Root-cause context:** ties to the Cellebrite call edge model — `PhoneCall` carries
  only the counterparty edge + direction; **strict CALLED + CALLED_TO joins drop most
  calls** (thread-list synthesis still strict — known follow-up). The "unknown error" on
  group chats/calls is likely this projection throwing.
- **To verify / next:** confirm the wrap actually returns the data (not just swallows the
  error into an empty result). Check whether the strict-join issue is the real cause for
  the missing calls/group chats; if so, fix the synthesis, not just the error handling.

**Frontend surfaces:** `frontend/src/components/cellebrite/CellebriteCommsCenter.jsx`,
`CellebriteCommunicationView.jsx`. **Error wrapper:** `frontend/src/services/api.js`.

---

## ⚡ ROOT CAUSE FOUND (2026-06-24) — DKT-29 + DKT-33 are the SAME bug

Both P0s are **Neo4j store corruption**, not a code bug. The agent's "wrap the
Neo4j call" fixes would only mask the 500 into an **empty result** (losing real
data) — exactly the failure mode the resume notes warned about. Do NOT ship those.

**The error (from journald, owl-backend):**
```
neo4j.exceptions.DatabaseError: {code: Neo.DatabaseError.Statement.ExecutionFailed}
{message: NOT PART OF CHAIN! RelationshipTraversalCursor[... source=786921 ... type=466 ...]}
```
Every corrupt-chain error is centred on internal node **786921** (a dense node)
and relationship **type=466** (≈ `CONTAINS`).

**What node 786921 is:** a **zombie** `PhoneReport` — `C2_06352877`, key
`cellebrite-device-352590375208133`, `case_id=a32edfa3-6d91-47ba-bd74-50e808357323`.
This is the **C2 zombie** from the 2026-05-12 tx-log corruption (see memory).

**Why it breaks the LIVE case:** case `a32edfa3` is an **orphan** — it has NO row
in Postgres `owl_db.cases` (the real registry), yet **46,828 nodes survive in
Neo4j** (the `pre-a32edfa3-cleanup-20260620` backup = a half-done cleanup that
left the graph data behind). It carries the **same** report keys
(`...208133` C2, `...710355` C3) as the live case **`5e374d4f` = "Abraham
Luna-Perez"** (DKT-33's case). The live case's comms *detail*/*envelope*/*anchor*
queries do **un-anchored relationship-type scans** (case_id only in `WHERE`, not
anchoring the traversal), so the planner physically walks the zombie's corrupt
chains → `NOT PART OF CHAIN` → 500 → frontend "Unknown error".

**Verified facts:**
- Comms *list* (`/comms/threads`) returns 200; *detail* (`/comms/threads/{id}`,
  calls + chat-with-anchor), `/comms/envelope`, and `_anchor_window_offset` 500.
- Un-anchored calls-detail query → throws; **case-anchored** variant (expand from
  the case_id-indexed Person/PhoneCall nodes) → returns 10 calls cleanly.
- BUT the throw is **plan-dependent / non-deterministic** (same shape returned 430
  once, threw another time) → query-anchoring is an unreliable guarantee. The
  zombie subgraph is a landmine any comms plan can hit.

**The real fix:** delete the orphaned `a32edfa3` zombie subgraph (46,828 nodes).
That removes the corruption AND the duplicate C2/C3 data. Node IDs are disjoint
from the live case (live C2 report = node 833749; zombie = 786921), and a
cross-case relationship scan only fails because of the corruption, not because of
shared nodes. Constraints:
- Neo4j **5.26 Community** (no online backup / no online repair). data dir owned
  by 7474 (correct). **No dump/backup exists.**
- `DETACH DELETE` traverses rel chains → will likely throw on the corrupt
  component. Strategy: batch-delete the non-corrupt zombie nodes first, then
  delete node 786921's component by relationship-id, or take the DB offline and
  `neo4j-admin database dump` (backup) → targeted surgery.
- Also-orphaned tiny leftovers (not registered, low risk): `8f854aab`(78),
  `44226fd2`(17), `52ad1a2e`(9), `401dc46d`(7), `11994267`(2). Fold into cleanup.

### Resolution (2026-06-24)

**SHIPPED — query-anchoring stopgap (code, validated, NOT yet deployed).** Rewrote
the comms queries in `backend/services/neo4j_service.py` to **seek the live case's
content node by its `case_id` index and expand from there**, instead of leading
with an un-anchored relationship pattern that let the planner scan a relationship
type store-wide (walking the zombie's corrupt chains). Sites fixed:
`get_cellebrite_thread_detail` (calls + emails branches), `_anchor_window_offset`,
`get_cellebrite_comms_envelope` (msg/call/email), `get_cellebrite_comms_between`
(msg/call/email). Pattern: `MATCH (c:PhoneCall {case_id})` / `(msg:Communication
{case_id})` / `(e:Email {case_id})` FIRST, then expand to the parties; split
combined `(a)-[]->(x)-[]->(b)` patterns into separate MATCHes and case-scope the
`chat` node so the planner can't fall back to a scan.

**Why this is sound, not whack-a-mole:** walking **all 778,364 live-case
relationships completes with no error** — the corruption is 100% confined to the
orphaned zombie. A query that only ever traverses live (clean) chains can't hit it.

**Verified against the live corrupt DB** (direct service calls, no server restart):
all 5 endpoints + many filter combos (from/to, participant, report+dates,
source_apps, types) return correct data, deterministic across repeated runs.
Regression-checked OPDMD28 (206K msgs / 19K calls / 82 threads — healthy) and
ET-Fraud (correctly empty). Bonus correctness fix: the old calls/emails detail
queries never constrained `c.case_id`, so they could match the zombie case's calls
that share the report key; the anchored form is correctly case-scoped.

**Deploy:** ✅ **DONE (2026-06-25).** `owl-backend.service` was restarted
**2026-06-24 20:01:34 UTC**, *after* the fix commit `c12e29c` (19:53:33 UTC) — so
the live backend (now MainPID 3425534) runs the fix. Verified healthy:
- **Zero** `NOT PART OF CHAIN` / comms-500 errors in journald since the restart
  (~a day of real traffic).
- Direct-service smoke test against the live corrupt DB, case
  **`5e374d4f-56ab-4101-af64-13df37004d61`** (Abraham Luna-Perez — note the real
  suffix `-56ab-4101-af64-13df37004d61`, NOT the `-6d91-...` the zombie carries):
  `get_cellebrite_comms_envelope` returns **44,200 comms (43,771 msg / 429 call /
  0 email), deterministic across repeated runs**; threads list returns 5. The 429
  calls are exactly the projection that used to throw `NOT PART OF CHAIN`.
- The zombie `a32edfa3` (1 PhoneReport `C2_06352877`) is **still present** —
  offline cleanup remains deferred, so the seek-anchor stopgap is still
  load-bearing. Any NEW comms query must follow the seek-anchor rule.

**Online zombie DELETION proven UNSAFE — do NOT retry online.** With the
backup-first plan authorized, I took a full file-level store backup
(`neo4j-admin` dump can choke on corrupt records, so raw copy of the stopped
store), then attempted deletion. `DETACH DELETE` of the dense corrupt PhoneReport
(786921) **succeeded but cascaded** — it freed its relationship records while
leaving its ~826 neighbours' chains dangling (`used=false` rels still chain-linked),
spreading the corruption so ~46k nodes then failed to delete. **Restored from
backup** (clean baseline: 786921 present, zombie 46,828, live 175,430 intact).
Lesson: deleting a dense corrupt node online corrupts its neighbours.

**Permanent removal = offline maintenance task (deferred).** The zombie (46,828
orphan nodes, unregistered in Postgres `cases`, invisible to the app) still carries
the corrupt chain. Removing it cleanly needs an offline rebuild: stop neo4j →
`neo4j-admin database dump`-style export of the registered cases only OR a
store-level rebuild → reload. Community 5.26 has no online repair. Tiny extra
orphans to fold in: `8f854aab`(78), `44226fd2`(17), `52ad1a2e`(9), `401dc46d`(7),
`11994267`(2). Until then the stopgap keeps the live app off the landmine; any NEW
comms query must follow the seek-anchor rule or it can re-trip the 500.

---

## Broader ingestion-health backlog (NOT from the tester tickets — known issues)

- **C2 / C5 / C6 Cellebrite re-ingests pending.** C2 zombie (121k models) corrupted the
  Neo4j tx-log on 2026-05-12; C5/C6 retries were collateral damage. Cleanup done
  2026-05-22; sequential re-ingest still pending — monitor with `docker stats`.
- **Empty `phone_numbers` PhoneReports must FAIL ingestion.** ✅ **DONE
  (2026-06-25).** Hard guard added in `create_phone_report_node`
  (`ingestion/scripts/cellebrite/neo4j_writer.py`, right after the
  `manual_owner_name` fallback, before the MERGE): if the normalised
  `phone_numbers` list is empty it raises `ValueError` → caught in
  `cellebrite_service.py:350` → task marked FAILED with a clear message, and
  (since it's the report's first write) **no partial data**. This catches the
  edge the existing `ingestion.py:283` precondition misses: raw `di.msisdn`
  present but ALL values fail `_normalise_phone` and no investigator name given.
  Audit (2026-06-25): no case currently has empty arrays — the original 3-of-7 on
  `43f1afb1` are already remediated (now 10 reports, 0 empty), so this is a
  forward-looking guard against recurrence. Not yet deployed (needs backend
  restart to take effect on new ingests).
- **Neo4j tx-log ownership.** "DEGRADED / X% failed to write" = neo4j data dir owned by
  1001 but container runs as uid 7474 → can't create a new tx-log segment on rotation.
  Fix: `chown -R 7474:7474 neo4j/data neo4j/logs`, restart. Per-entity errors live in
  `evidence_logs.json`, not journald.
- **Data-dir root ownership.** "Upload/ingest completed but no data" = root-owned files in
  the `data/` tree blocking backend (uid 1001) writes. `find data ingestion/data -uid 0`;
  real error only in journald; `chown` back to `1001:1002`.
- **Principle:** fix the pipeline, then backfill bad data via the same code path — one-off
  exports are not the end state. On v1 prefer filter stopgaps over cleaning legacy
  artifact rows (Cellebrite rework is deferred to v2).

---

## Suggested resume order
1. **DKT-29 + DKT-33 (both P0)** — reproduce in the live app, get the real backend
   tracebacks, root-cause the comms-projection 500s (likely the strict call-join +
   Neo4j projection). Verify the agent's fixes aren't just masking.
2. **DKT-34** — verify the large-file path end-to-end + make the TMPDIR fix deploy-safe.
3. **Backlog** — phone_numbers validation + the C2/C5/C6 re-ingest once the above land.

_Resume: open this file (or say "continue ingestion"). Deploy layout: v1 runs from
`app_v2/` (ports 8000/5173, branch main); diagnose slow/failed uploads via the
owl-frontend proxy log + journald._
