# 2. v1 Cellebrite: evolution from git history

Read-only, 2026-10-29. "Path commits" are the 220 commits on `origin/main` whose paths match `*cellebrite*`;
64 more mention cellebrite only in the message and are included. Short shas cited for every claim.

**Authorship.** Neil Byrne 132 path commits; "Neil B" 57; "root" 14 (the server); "thenofisamizdat" 16, all
PR merges. conorbowles51 made one v1 commit, a merge (a6cc7156), and the v2 port. DKT-* commits were opened
by the Docket agent (330ef1fe, 03b04f23); Neil states Docket was not otherwise used. Per Neil, all committed
v1 work was directed with Alex from her use of the platform.

**Velocity (path commits per month):** April 12, May 132, June 66, July 10. Last commit touching cellebrite:
141f0cc0 on 2026-07-27.

## 1. Phases

- **Phase 1 (ingestion parser)** appears on main only in 3fcbbea8 (04-24), together with the nesting-depth
  fix, so the original elem.clear bug and fix happened off main.
- **Phase 2, multi-phone view (04-06):** 36176f33.
- **Phases 3 to 5 (04-24), one commit 3fcbbea8:** Comms Center; Location & Event Center with playback and five
  intersection detectors; geotag backfill; PoweringEvent and DeviceEvent un-skipped; CaseEntity and Files
  Explorer backend. d0183dbb finished the Phase 5 frontend.
- **Drill-downs and polish (04-25 to 05-06):** 2e01bfd4, 7983fb11, 44237c2c, 609f81fa, 4f0ec5b1 (full-text
  search), 3e6bf072 (CaseEntity renamed Profile).
- **Reader-parity and performance (05-12 to 05-17), the densest period**, following
  `.claude/plans/cellebrite-comms-geo-deep-dive.md`: indexes and phased load fbe8df0e; envelope endpoint,
  keyset pagination and rail 477685b5, c764f03c, 071820a8; Locations tab, tiles, pluggable geocoder
  cad63fd6, b31af520, 78a47eb2, e8acbeed, 85504150; unified-by-number contacts 4bc74f7f, 32671c25; rail to
  flyout 7c4d5f75; async handlers to `def` fe6d2669.
- **Ingestion hardening (05-23 to 05-27):** section 2.
- **Swim-lane timeline and Cross-Phone Graph rebuild (05-25 to 05-26):** bacd809f, 72e6bb68, 919bef5b and
  about 15 graph commits ending 5bca0a84.
- **Identity (05-25 to 05-27):** WhatsApp/phone unification 92d9cc69; manual audited merge 72dfa276;
  ContactEntry and aliases 85109478; Report tab 864d7faa.
- **Timezone model (05-28):** 55d82be1.
- **Alex-call roadmap sprints (06-04 to 06-09)** following `.claude/plans/alex-call-roadmap.md`: load-more
  639372b9; events keyset 8c45053a; report PDF d18eea77; graph flow, search, path, time axis 49105bcc,
  1b13d71c, 2395fb4a, 3828e411; virtualised timeline debb7cf9; callouts and client report 63608486,
  87ae0858; Discovery b6f5023e.
- **Tester tickets and upload pipeline (06-13 to 07-04):** DKT-20, 23, 28, 29, 31, 34, 40, 41, 42, 43;
  resumable tus 65586729; auto-route uploads 57838d1b; owner inference f4cae847; Notification and Voicemail
  writers db56c5ea.

## 2. The ingestion processor

**Upload and unpack**
- Multi-GB uploads buffered in memory and killed by Vite (04-28, 4d33701b): streamed to staging, server-side
  zip path with zip-slip protection, proxy timeouts raised.
- Staging disk full gave an opaque 500 (05-24, 9fdb8d1f): 507 for ENOSPC and MemoryError.
- A 31.8 GB zip never appeared, DKT-34 (06-23 to 06-25): 11255ce3 moved `tempfile.tempdir` off RAM-backed /tmp
  and lifted nginx limits; 9f0f3977 registered a folder record; 3b3871eb: the blocker was disk, a 1 TB data
  disk added.
- DKT-34 folder rows never worked end to end (07-27, 141f0cc0): `EvidenceRecord` lacked `is_cellebrite_folder`,
  so FastAPI stripped it; reported as data loss on a live case, nothing deleted.
- Resumable uploads (06-25): tus/Uppy 65586729, 71d7b15b; auth and case ACL 716b622f; StrictMode fix
  2d117c3a; post-finish detached worker d51287e4.
- Raw folder uploads sat until someone clicked process (06-21, 57838d1b): auto-ingest, conservatively.
- Folder upload marked COMPLETED with 100% failed and errors only to print() (06-21, 30402281).

**Detection and duplicates**
- "Unknown Device" (05-06, 4c73e60e): model read only from the Bluetooth name; fixed with DeviceInfoSelected*;
  same-IMEI duplicate detection, 409 unless force.
- Re-ingest created a second PhoneReport (05-06): stopgap 89ebd87d, MERGE on (case_id, key) 056ac357.
  A uniqueness constraint was blocked by Neo4j `/data` permissions (index creation failed silently).
- Wipe missed the PhoneReport itself, giving a false 409 (05-23, f96d9cf6).
- Degenerate key `cellebrite-unknown-unknown` (06-21, 30402281): `build_report_key` with IMEI/MSISDN fallback.

**Parse and write coverage, the largest problem area (data dropped silently, repeatedly)**
- Per-type XML-versus-persisted reconciliation (05-13, 33d7c76a): the tool that exposed the rest.
- Coverage overhaul (05-23, 2996176f) against UFEDLib's 56 classes: EXIF matched non-existent item names (122
  GPS photos and 1,307 capture times lost); `_extract_timestamp` recovered 15,995 VisitedPage times;
  Call.Status had dropped 7,881 values; SIMData rewritten; CONTAINS links added.
- DictionaryWord reversed the same day: 2996176f skipped it; ee75a58f found real typed emails, amounts and a
  date of birth in it ("the 'autocomplete noise' call was wrong").
- NetworkUsage writer and refusal of reports with no owner identity (05-23, 2c0428ef).
- About 62k app and movement events silently dropped, 10 types never in SUPPORTED (05-25, ce26c9f3); an
  UNKNOWN-TYPE guard added because "the failure mode hid these for weeks".
- Photo geotags only reached the graph via media registration: 365 photos in the case, 0 in the graph
  (05-25, b47e60fd); `:CbNode` label added because edges did an AllNodesScan each.
- About 25k WiFi coordinates dropped (05-27, 09bd9a8c): 44k to 68k locations.
- First saved name won, "conflated contacts" (05-27, 85109478): ContactEntry and `name_aliases`.
- Phone keys: US regex replaced by libphonenumber E.164 (05-24, 8e730a44), forcing re-ingest; the regex had
  let Facebook IDs through (32671c25).
- Empty `phone_numbers` broke every comms view on 3 of 7 reports in one case (06-25, 35fe75a5): hard fail.
- Full-file-system extractions have no MSISDN (06-27, f4cae847): three-tier owner resolution.
- SearchedItem 37 of 71 persisted (06-30, 1b8a32c8).
- Notification and Voicemail writers (06-30, db56c5ea).
- Still open at 1b8a32c8: Location, Contact and SIMData under-counts; no writers for Recording,
  DeviceInfoEntry, RemoteServiceSession, MobileCard, CreditCard.

**Neo4j write reliability**
- Naive/aware timestamp TypeError in backfill (04-24, bf3568ed).
- Reverse geocoder forked a pool per lookup, under 1 model/s (05-25, e072fb21).
- `run_query` bypassed retry; one transient drop lost 2,450 entities (9.6%) (05-24, c010ef9b).
- 2026-05-12: an ingest zombied the JVM at 4G heap and corrupted the transaction log; heap to 8G with
  ExitOnOutOfMemoryError (2996176f).
- A deleted case left 46,828 orphaned nodes with a corrupt relationship chain (c12e29cb, 06-24), first
  misdiagnosed as a cursor bug (faf0a499); offline cleanup deferred.

**Job, progress, recovery**
- Multi-worker JSON stores (2996176f, f96d9cf6, 1986995e): a stale-cache DELETE wiped 93k rows; tasks
  disappeared per worker; a rename race killed an ingest; a root-owned lock file killed four ingests. Fixed
  with fcntl locks, mtime refresh, atomic writes.
- Parallel double ingest (05-23): 409 for a running report key.
- Live progress, write_errors, FAILED above 5%, startup watchdog (f96d9cf6).
- Naive-UTC heartbeat showed "STALLED" (f96d9cf6, 1986995e).
- "At 100%" through a 40-minute tail (06-25, 39429aaa): 7-stage checklist.
- Honest worker log and "Action needed" state (06-27, 1f63e3d5).

**File linking and media**
- 188k rows for 93k files (2996176f): upsert on (case_id, sha256).
- 288 MB of JSON rewritten per file on folder upload (2996176f): batched.
- Standalone media registration for skip-media ingests (05-27, 2a98a3d0).
- 2,079 `.tts` audio files dropped (07-01, fc20c209): trust Cellebrite's category folder.
- Voice notes would not play: b61da998 and 9495dec5 (ffmpeg transcodes).
- On-demand transcription and vision with caching (05-27, ed6146eb); no bulk OCR or embedding ever.

## 3. Other reversals and lessons

- Timeline dropped newer events: sorted ascending then capped at 5000 (05-06, aeb3e598).
- Caps again and again: locations 5000 (09bd9a8c); graph cut at 600 with a "capped" badge that misreported
  (5bca0a84); unified contacts query wedged the pool (f525e134), then a 5000 cap.
- Location decimation reversed the same day (0111bb49 then dc5103e1: "keep EVERY point").
- UI reversals: participants picker (96db22cc); rail to flyout (7c4d5f75); email threading parked (a4f17c69).
- Dedup recurred: 9439f73c, 0704f664, 3cf58bfb, 330ef1fe.
- Timezones (55d82be1): data was UTC; rendering was inconsistent.
- Comms queries: unscoped recipient joined across cases (03b04f23); `collect()[0]` broke on Neo4j 5 with
  errors swallowed (1ac07cd6); DKT-42 took three attempts, the third finding an un-lowercased search
  haystack (5b854590).
- Reverted and never re-landed: DKT-40 PR #102 (a05950cd); DKT-43 comms tally (1ee78cf4, f75fe572).

## 4. Churn and abandoned work

| File | Path commits |
|---|---|
| `backend/routers/cellebrite.py` | 43 |
| `CellebriteCommsCenter.jsx` | 35 |
| `CellebriteCrossPhoneGraph.jsx` | 30 |
| `CellebriteTimeline.jsx` | 24 |
| `neo4j_writer.py` | 21 |
| `CellebriteLocations.jsx` | 19 |
| `ingestion.py` | 17 |

`neo4j_service.py` (one monolith) was touched 84 times by grep. 18 of 52 roadmap codes are never cited in a
commit (S1-01, S2-21, S2-22/23 among them). `INGESTION_ISSUES.md` lists pending re-ingests and the zombie
graph cleanup and says "Cellebrite rework is deferred to v2".

## 5. The Loupe port

conorbowles51 copied the code on 2026-05-15 to 05-23 (c343d17f, 87a44c1e, 2781e354, 49d5ff9f, 3c849888), no
message bodies. HEAD's merge-base with main is a73da708 (03-18); none of the 220 v1 commits are ancestors of
HEAD. 130 of the 220 land after 05-23. Missing from Loupe's engine pipeline: `_extract_timestamp`, `:CbNode`,
geotag and coordinate harvest, ContactEntry and aliases, owner inference, `build_report_key`, empty-number
guard, write_errors, unknown-type guard, DictionaryWord, Notification, Voicemail, libphonenumber. Present:
nesting-depth parsing and retry.

## 6. Lessons

1. Reconcile every type, XML against persisted, and fail loudly from day one.
2. Do not call data noise without reading it.
3. Identity first: one normaliser, deterministic report key, guaranteed owner, aliases.
4. Idempotent writes: natural keys, upsert files by hash, one ingest per report, retries.
5. Durable job state in a transactional store, not shared JSON files.
6. Staged progress, heartbeat, watchdog and an honest end state.
7. Never cap silently.
8. Scope every query by case and anchor it on an index; deleting a case removes its graph.
9. Large uploads are infrastructure.
10. Media is its own track.

Not determined: where the original Phase 1 parser and its fix were committed; whether uncited roadmap
items shipped under other names; why DKT-40 and DKT-43 were reverted; whether the 06-25 empty-number guard
was deployed.
