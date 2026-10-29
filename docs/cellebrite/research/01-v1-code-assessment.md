# 1. v1 Cellebrite subsystem: technical assessment

Read-only assessment of `origin/main` on 2026-10-29. Citations are `origin/main` paths. Frontend findings
come from a sub-survey; `frontend/src/services/api.js` was not exported, so frontend-to-endpoint mapping is
by name.

**Corrections and confirmations since:** the defects marked *verified* in section 10 were re-read in source
by the coordinating session (Person merge and delete path, delete-before-ingest, `CREATE` with 12-character
keys in 37 places, email body cut at 2,000 characters, stored credential flagged `is_sensitive`, device zone
hard-coded to America/New_York). The open question "where attachment references sit" is answered in report
3: in real reports they sit on the nested Attachment record (`file_id` attribute and
`attachment_extracted_path`), which v1 never reads.

---

## A. The file ingestion pipeline, end to end

### A1. How an extraction arrives

There are three entry points. Every one ends as an unpacked folder on the server.

1. **Folder upload in the browser** through `evidence.py`'s upload route (`request.form(max_files=20000)`,
   `backend/routers/evidence.py:704`). Files are streamed to staging with SHA-256 (`:578-620`), registered
   as evidence rows on a background thread, then `_maybe_autoingest_cellebrite` runs
   (`backend/services/evidence_service.py:428-442`, `:465-595`).
2. **A single .zip** (`is_archive=true`): staged, unpacked by `_extract_archive_to_staging` with zip-slip
   protection and streamed SHA-256 (`evidence.py:505-568`); top-level Cellebrite folders get one
   folder-level evidence row (`:786-808`, `_register_cellebrite_dir_record` `:222`); **the original zip is
   then deleted** (`:777`).
3. **Resumable (tus) upload:** `pre-create` checks the JWT and case permission and refuses if it cannot
   confirm them (`deploy/tus-hooks/pre-create:1-60`); `post-finish` moves the file to `<case>/_incoming` and
   starts a detached worker (`deploy/tus-hooks/post-finish:42-60`), which extracts with zip-slip protection
   (`deploy/tus-ingest-worker.py:30-47`), finds the report folder (`:49-60`), **deletes the source zip**
   (`:91-95`) and calls the same auto-route (`:104`). It hard-codes `/home/conorbowles51/app_v2/backend`
   (`:98`) and `/mnt/owl-data/...` (`:17-20`).

Manual route: `POST /api/evidence/cellebrite/process` (`evidence.py:1455-1617`) with a path-escape check,
detection, a 409 on duplicates, an in-flight check, then `threading.Thread(daemon=False)` (`:1609`).

**Formats.** Accepted: a UFED XML report folder, a zip containing one, a tus-uploaded zip. Not handled:
`.ufdr`, `.ufd` (a `git grep` for `ufdr` on `origin/main` returns nothing). The archive's SHA-256 is computed
while staging, but its upload entry is replaced by the extracted entries (`:770-772`) and the file deleted
(`:777`), so the container hash is not kept anywhere found.

### A2. Detection

`detect_cellebrite_xml` searches breadth-first up to 6 levels for `*.xml` whose first 4 KB contains
`http://pa.cellebrite.com/report/2.0`, returning the shallowest (`ingestion/scripts/cellebrite/ingestion.py:134-184`).
Separate copies exist in the router (`_is_cellebrite_report_root`, `evidence.py:162`) and the tus worker
(`tus-ingest-worker.py:49-60`). Only `*.xml` is considered; the migration plan itself notes variants such
as `.xmlExtra` slip past (`CELLEBRITE_V2_MIGRATION_PLAN.md:105,110-112`).

### A3. Parser (`ingestion/scripts/cellebrite/parser.py`)

Three separate `ET.iterparse` passes: header (`:223-426`), file index `parse_tagged_files` (`:468-652`),
records `stream_models` (`:658-759`). Nesting depth is tracked so records inside a chat are not cleared
before they are read (`:705-718`). Every top-level record type is counted before filtering, for later
reconciliation (`:726-729`).

Memory is not constant despite the docstring (`:4-5`): `parse_tagged_files` returns the full file list
(`:474,647`; one report had 92,761 files, `docs/cellebrite_coverage.md:10`), and the orchestrator collects
every parsed record into `all_models` before writing (`ingestion.py:432-436`), keeping it through the write
pass and the coordinate harvest (`:505-507,597`).

Lossy reading: only the first `<value>` of a field (`parser.py:781-783`); values whitespace-stripped
(`:783`); files without `Local Path` dropped from the index (`:646`).

### A4. File linker (`ingestion/scripts/cellebrite/file_linker.py`)

- Paths: Windows separators normalised, resolved, escape-checked with a string `startswith`, so a sibling
  folder sharing the prefix (`/report2` against `/report`) passes (`:126-136`). Missing files are counted and
  logged (`:143-149`) with no per-file record.
- Category from Cellebrite's `Image`/`Audio`/`Video`/`Text` folder anywhere in the path, else extension
  (`:40-70`); anything else is never registered.
- Hashes: the report's SHA256 is used when present, else SHA-256 computed from disk (`:197-201`). **The
  report's MD5 is parsed (`parser.py:540-541`) but never compared with the file on disk**, and a present
  SHA256 is trusted unchecked. Coverage data shows SHA256 on 1,579 of 165,340 files and MD5 on all of them
  (`docs/cellebrite_coverage.md`).
- Deduplication by content loses attribution: within a report a second file with the same hash is skipped
  (`:204-206`), so its Cellebrite file id never gets an evidence row; across reports the existing row is
  overwritten with the new report's ids (`:332-341`). Attachment lookup matches one `cellebrite_file_id` per
  row (`backend/services/evidence_storage.py:334-357`), so the comms attachment endpoint returns 404 for
  dropped duplicates (`backend/routers/cellebrite.py:794-813`).
- Record-to-file map is keyed by the carrying record including nested ones (`:386-403`); the reverse map
  keeps only the last record per file (`:179-181`).
- Not carried onto evidence rows: file deleted state (`parser.py:498`), extraction id, original device path
  (`file_linker.py:306-329`).
- No thumbnail generation in the backend.

### A5. Neo4j writer: batching, idempotency, re-ingest

- **No batching:** every node and relationship is its own `run_query` (`neo4j_writer.py:633-636`,
  `:669-676`), each an auto-commit transaction with retry (`ingestion/scripts/neo4j_client.py:650-675`). Only
  the final CONTAINS sweep uses `apoc.periodic.iterate` (`:3592-3632`).
- **Not idempotent:** most record nodes use `CREATE`; protection is an in-memory set for one run
  (`:610-611`); random `id` per node (`:436`); keys are the record id cut to 12 characters, e.g.
  `call-{model_id[:12]}` (37 places), not scoped to the report; relationships match on `{key, case_id}`.
  MERGE is used only for PhoneReport (`:1123-1134`), Person (`:591-602`), ContactEntry (`:1436-1451`) and
  harvested/photo Locations (`:1972-1983`, `:3572-3576`).
- **Re-ingest** is only `force=true`, which runs `delete_phone_report` **before** the new ingest
  (`backend/services/cellebrite_service.py:303-316`). If the new ingest fails, the old data is gone. The delete
  is one unbatched `DETACH DELETE` of every node carrying the report key (`neo4j_service.py`).
- **Shared people destroyed:** a Person is merged per case on `{key, case_id}` and its
  `cellebrite_report_key` is set only on create (`:571-600`). Deleting phone A deletes every Person A created
  first, including those phone B's messages and calls link to.
- Evidence rows cleaned the same way (`routers/cellebrite.py:115-127`) with `except Exception: pass`
  (`:131-132`); with the hash deduplication above this can delete rows belonging to another phone.
- Duplicate check: same report key, IMEI or evidence number (`neo4j_service.py:5982-6028`), so two genuine
  extractions of one handset on different dates collide and the only option is replace. The in-flight check
  rebuilds the key as `cellebrite-{case}-{evidence}` (`evidence.py:1559-1561`) while `build_report_key` falls
  back to a device key (`ingestion.py:199-212`), so some concurrent ingests are not caught.
- Write errors counted per record (`:1163-1170`); FAILED only above 5% (`cellebrite_service.py:386-412`).

### A6. Orchestration, progress, cancellation, recovery

- In-process thread (`evidence.py:1609`) or synchronous on the upload thread when auto-routed
  (`evidence_service.py:563-570`). No queue, no worker pool.
- Progress in 7 stages (`cellebrite_service.py:20-48`); heartbeat at most every 2 s in the write loop
  (`ingestion.py:498-522`); no in-stage progress during parsing or media.
- **No cancellation**: `CANCELLED` exists (`background_task_storage.py:44`) but is never checked.
- **No resume**: on startup a watchdog marks tasks silent for 5 minutes FAILED (`backend/main.py:77-118`);
  the partial graph stays.
- SIM, identities, geotags, coordinate harvest, CONTAINS links and backfill are each wrapped in
  `try/except` logging a WARNING (`ingestion.py:532-629`); failures still end as success.

### A7. Speed and size

The docstring refers to a "multi-hour ingest" (`ingestion.py:239-241`). Media registration rewrites the
whole `evidence.json` per batch of 500 under a lock (`file_linker.py:248-254,289`), admitted as "very slow"
with an environment variable to skip it (`ingestion.py:635-655`). Reverse geocoding is synchronous per
coordinate (`neo4j_writer.py:1845-1857,1961-1970,3557-3568`), off unless `GEOCODER` is set. The migration plan
records `evidence.json` at 199 MB and 232K records, 164K of them Cellebrite leaf files.

### A8. Processing of media files

Nothing automatic: rows registered `"unprocessed"` (`file_linker.py:357`). On demand,
`POST /evidence/{id}/media-analyze` runs local Whisper, or image recognition with **OpenAI vision by
default** and Tesseract optional (`evidence.py:957-1029`). AMR transcoded to Ogg; `.tts` served as MP3
(`:1830-1845`). No Cellebrite content goes to Chroma or any embedding store.

**Pipeline strengths:** streaming read; XML-versus-stored reconciliation with loud warnings for unsupported
and under-counted types (`ingestion.py:666-706`), persisted on the PhoneReport and in
`owl_ingest_report.json` (`:708-737`); zip-slip protection; tus hooks that refuse without authorisation;
staged progress; a failure-rate threshold.

---

## 2. Parser coverage

`SUPPORTED_MODEL_TYPES` has 47 entries (`parser.py:97-168`); `SKIPPED_MODEL_TYPES` is empty (`:172`); handler
map at `neo4j_writer.py:1172-1230`. Explicit no-ops: KeyValueModel, Party, ContactPhoto, ProfilePicture.
Still dropped with a warning: Recording, DeviceInfoEntry, RemoteServiceSession, MobileCard, CreditCard
(`CELLEBRITE_INGEST_AUDIT.md:22-28`); financial types unsupported (`cellebrite_coverage.md:22`). The coverage
documents are stale (2026-05-23, 3 reports; still show DictionaryWord skipped). Per-type field coverage is
mostly 75 to 90% (Call 89%, Chat 88%, Contact 83%).

**Recipients dropped:** in InstantMessage, `To` is multi-record and not captured (817 instances), likewise
`Attachment(s)` (`cellebrite_coverage.md:214-237`). The writer calls `model.get_party("To")`
(`neo4j_writer.py:1612`), which reads only single-record fields (`models.py:177-188`), so `to_party` is None
and no RECEIVED_MESSAGE edge is written (`:1649-1656`).

**Deleted and recovered:** `deleted_state` and `decoding_confidence` stored on record nodes (`:443-450`);
carving confidence on Location and CellTower; file deleted state not stored.

**Timestamps:** raw strings stored; `date`/`time` cut from the string (`ts[:10]`, `ts[11:16]`); EXIF times
converted with no offset (`parser.py:33-60`); backfill treats offset-less as UTC (`ingestion.py:815-833`);
intersection service uses `.timestamp()`, which reads offset-less strings in the server's zone
(`cellebrite_intersection_service.py:44-50,124`); date filters compare strings (`:212-217`).

**Tags:** investigator tags in the report are not read; only message labels (`neo4j_writer.py:524-539`) and
file `Tags` (a category, `parser.py:544-545`).

## 3. Data model

PhoneReport plus Person, ContactEntry, PhoneCall, Communication, Email, Location, CellTower,
WirelessNetwork, Account, Credential, AppSession, DeviceEvent and others; edges CALLED, CALLED_TO,
SENT_MESSAGE, RECEIVED_MESSAGE, PART_OF, EMAILED, SENT_TO, WAS_AT, OWNS_ACCOUNT, EXTRACTED_FROM, HAS_ENTRY,
CONTAINS. Every node tagged `case_id`, `cellebrite_report_key`, `cellebrite_id`, `source_type`
(`:433-459`). Postgres only for access control; evidence rows in `evidence.json`; nothing in Chroma.
Email bodies **cut to 2,000 characters** (`:1681`). `UserAccount.Password` stored as `credential`
(`:2010,2033`), flagged `is_sensitive`, while the Password handler drops secrets (`:2357-2392`).

Person keys: E.164 number (libphonenumber with case default region, `:112-130`), then WhatsApp JID, email,
app-plus-id, then name (`:144-208`); the name fallback merges unrelated people sharing a name. Aliases
accumulated (`:3049-3093`). Identity merge is manual, records only the actor, and cannot be undone.

Owner identity: header number, then inference from comms `Account` (`:894-944`), then a typed identifier.
The manual Process route returns 422 before inference can run when the header has no number
(`evidence.py:1502-1513`).

## 5. Provenance

Kept: Cellebrite record id on every node, shown in the event drawer; examiner, case and evidence numbers,
IMEI and report version on PhoneReport; SHA-256, Cellebrite file id and device path for files. Not kept:
`extraction_id` and `source_index` (parsed, `parser.py:772-773`, never written); report XML hash; container
hash; `<images>` and `HashSetsInfo` cleared unread (`parser.py:377-386`); MD5 never checked. The PDF report
carries no hashes, ids or deleted state. **Verdict:** a fact traces to a Cellebrite record id, not to a
verified extraction or source file.

## 6. Analysis features

About 45 endpoints; 11 tabs (`CellebriteView.jsx:27-51`): Overview, Report (PDF), Discovery, Comms Center,
Unified Contacts, Locations, Location & Events, Files, Cross-Phone Graph, Timeline, Communications.

Intersections, on demand, five methods: spatial within 250 m and 600 s (`cellebrite_intersection_service.py:100-195`);
shared cell tower (`:201-300`); WiFi by BSSID else SSID (`:306-392`); comm hub (`:398-597`); convoy (`:600-`).
Limits: at most 20,000 events loaded (`:89`) from a newest-first per-type feed (`neo4j_service.py:10462-10697`)
with no notice; location accuracy ignored; SSID fallback false-matches common networks; WiFi times are
first-seen or last-connection, not associations (`neo4j_writer.py:2289-2295`).

UI time: "Device" zone hard-coded to America/New_York and the default (`cellebriteTime.js:21-25`); several
views group by UTC date while showing times in the selected zone. Caps without notice: thread view 500 items
while showing the full total (`CommsThreadView.jsx:87,255`); graph edge rail 200 (`GraphEdgeAccordion.jsx:69-70,104`).

## 8. Tests

`tests/test_cellebrite_owner_inference.py` (5 unit tests) and `tests/test_cellebrite_timeline_e2e.py` (one
end-to-end test needing live Neo4j and the C3 folder). No parser, linker, writer idempotency, intersection,
router or frontend tests.

## 9. The two v1 documents

`CELLEBRITE_INGEST_AUDIT.md` (refers to fixes of 2026-06-30): reconciliation across 14 phones; whole types
with no writer (17,082 ActivitySensorData, 16,311 LogEntry, 10,115 Cookie, 8,960 AppsUsageLog, 7,040
Notification and others); under-counting writers (Contact 2,025 lost, Location 1,463, SearchedItem 715 fixed
2026-06-30, SIMData 2 per phone); still missing Recording, DeviceInfoEntry, RemoteServiceSession,
MobileCard, CreditCard. Locations without coordinates are skipped (`neo4j_writer.py:1755-1756`).

`CELLEBRITE_V2_MIGRATION_PLAN.md` (last updated 2026-05-06): keep streaming parse, per-node report key,
PhoneReport upsert, person-key order, pre-ingest collision check, background tasks, on-demand
intersections, Cellebrite record ids; fix 164K leaf evidence rows, the single-XML assumption, tagged files
in memory, no schema version, the 20K intersection cap, silent timeline truncation, one attachment lookup per
message, heavy browser state, end-to-end-only tests. Every component "Not started". Two claims in it are
wrong about the code: "constant memory" and "MERGE-based writer".

## 10. Honest assessment

**Strengths:** 47 types with alias-tolerant field reading (`neo4j_writer.py:394-431`); self-auditing
reconciliation; careful owner identification (`parser.py:436-462`); correct E.164 and WhatsApp JID handling;
aliases kept; deleted state and decoding confidence kept; zip-slip protection; tus hooks that refuse without
authorisation; a rich investigator UI.

**Weaknesses, most severe first:**
1. *Verified.* Data destruction across phones (shared Person deletion; evidence rows with overwritten keys).
2. *Verified.* Replace deletes before writing; non-idempotent `CREATE` with 12-character unscoped keys; no
   cancel or resume.
3. No integrity chain (container deleted unhashed; MD5 never checked; SHA256 trusted; extraction hashes
   discarded; no extraction id on records; PDF without provenance).
4. Silent or lossy reads (multi-record `To` dropped; *verified* email bodies cut to 2,000; first value only;
   content-duplicate attachments unresolvable; five types dropped).
5. Time handling inconsistent (*verified* New York hard-code; offset-less read two ways; string date compare).
6. Intersection evidence quality (silent 20K cap, accuracy ignored, SSID false matches).
7. Security (*verified* credentials stored, flagged sensitive; images to OpenAI by default; prefix path check).
8. Scale (all records in memory; one transaction per node and edge; `evidence.json` rewrites; multi-hour runs).
9. Maintainability (three detection copies; hard-coded deploy paths; in-flight key mismatch; manual route
   blocks owner inference; tests nearly absent).
