# Timeline & Comms Work — resume file

**Trigger:** when the user says **"continue timeline"**, read this file and resume from
the ▶ NEXT block. Update this file at every step.

Scope: Cellebrite **Timeline** (activity feed) + **Comms flyout** (rail/EventAccordion)
fixes. Prod app = `app_v2` on `main` (v1 runs as a Vite **dev server** → frontend edits
hot-reload; **backend** edits need `sudo systemctl restart owl-backend`).

Test case with the live data: `34fbbb06-4080-4ef7-b895-1fd2f0264eac` (owner = **Rico
Valentin** `phone-13015498311`; counterparty example **Jayanna Hinge** `phone-16783005434`).
Neo4j: `bolt://localhost:7687` neo4j/testpassword (driver in `../venv/bin/python`).

---

## ▶ NEXT (resume here)
**Missing writers (Notification + Voicemail) BUILT 2026-06-30 (commit `db56c5e`)** — closes
the "Missing writers" backlog item below. End-to-end pipeline + surfacing, validated against
raw XML; **inert until re-ingest** (Neil's call — no Notification/Voicemail nodes on any
live case yet, so the new chip stays hidden at count 0; backend returns 0 cleanly).
- Parser: `Voicemail` + `Notification` added to `SUPPORTED_MODEL_TYPES`.
- Writer: `_write_voicemail` → **PhoneCall** node (`call_type=Voicemail`, Incoming, From
  party CALLED owner, `voicemail_path` for provenance — audio also already surfaces as a
  standalone media file). `_write_notification` → **Notification** node (Source/Subject/
  TimeStamp/Status/URL). Both count own stats (1:1 reconcile). Junk numeric voicemail
  `Name` ("26"/"27") suppressed so it can't pollute Person names.
- ingestion.py reconcile: Voicemail/Notification entries added; **SIMData marked `nested`**
  (it aggregates many property rows into one SIMCard node — persisted<xml is EXPECTED, not
  a writer under-count bug; removes that false flag).
- Backend `neo4j_service`: `notification` event type wired into the feed branch, default
  active set, `_EVENT_TYPE_LABELS`, envelope (auto), and `get_cellebrite_event_types`
  ("Notifications"). Voicemails ride the existing `call` type (no double-count).
- Frontend `eventUtils.js`: `notification` color (rose) / icon (Bell) / label.
- DRY-RUN verified on `5e374d4f` C2 report: 39 voicemails + 3951 notifications parse with
  correct fields. Backend smoke-tested on live case 34fbbb06 → returns 0, no errors.
- Validation against more reports + `infer_owner_msisdn` interplay → confirm on re-ingest.

**Ingestion coverage audit DONE 2026-06-30** — see `CELLEBRITE_INGEST_AUDIT.md` (full
per-phone breakdown). SearchedItem writer bug FIXED (`neo4j_writer._write_searched_item`:
was requiring a `Value` field location-searches lack + never read lat/lon). Under-count
warning added to `ingestion.py`. Remediation backlog (Neil's call):
- **RE-INGEST** `43f1afb1` (10 phones) + `5e374d4f` (3 phones) with current code → recovers
  ~60k version-drift artifacts (Cookie/LogEntry/DeviceConnectivity/AppsUsageLog/etc.) +
  the SearchedItem fix + the new Notification/Voicemail writers. (Cellebrite re-ingest is
  sensitive — see [[project_cellebrite_ingestion_failures]].)
- **Writer under-count bugs** still to investigate: Location (lost 1241/171/…), Contact
  (723/1155/…). ~~SIMData (−2)~~ — RESOLVED: aggregating type, not a bug (now reconciles nested).
- ~~**Missing writers**: Notification (7,040), Voicemail (76)~~ — BUILT (see top of NEXT).
  Remaining low-value missing writers: Recording / DeviceInfoEntry / etc.

The timeline/comms epic is essentially complete. Remaining OPTIONAL / flagged items:
- **SearchedItem ingestion bug** (flagged, not fixed): 34 of 71 Waze location-searches +
  ALL their geo Positions were lost at ingest (parser fix + re-ingest; v2-deferred). See
  ARTIFACT-TYPE AUDIT below. Neil's call.
- Optional: per-category "Files & media" filter chips (currently one chip).
- 507 undated media + ~75 absent attachments — both resolved as "correct/won't-fabricate".

## UNRESOLVED ATTACHMENTS (resolved 2026-06-30, commit `8f6fe4d`)
**Not an ingestion bug — absent source data.** Case-wide: 664 unique message attachment
file_ids, **75 unresolved (11%)**. Classified all 75: **0 have file bytes**; 48 have only
an empty `MediaResults/*.json` classification stub (`{"FileId":…,"Classifications":[],
"Type":null}`), 27 are bare references. The actual files are NOT in the Cellebrite export
(cloud/expired/deleted media referenced but never exported) — nothing to ingest. The UI
already flagged them (`CommsAttachment` missing branch); reworded the placeholder from the
ambiguous "Attachment unavailable" to **"Attachment not in extraction"** (+ tooltip) so
it reads as absent source data, not a tool failure. Frontend build clean.

---

## DONE (PUSHED to origin/main 2026-06-30 — HEAD `a05950c`)
Integration note: merged origin/main (had PR #101 DKT-41 + PR #102 DKT-40), kept #101's
audio fix (Ogg/Opus transcode — superseded my redundant MP3 version), then **reverted
PR #102** (`a05950c` reverts `a7e1f4a` — the agent's wrong-surface graph-filter DKT-40).
Safety backup branch: `backup/timeline-pre-push-ae874ea`. All my work verified intact
post-revert (types incl. file+calendar; owner attribution; builds clean).

- **`71c1a1b`** — zone-anchored timeline date/time filter (typed numbers stay; instants
  re-anchor on UTC↔Device flip). `cellebriteTime.js` helpers + `useTimelineWindow` hook
  across 5 timelines + scrubber picker. Unit-tested + build-clean. [[project_timeline_tz_filter_fix]]
- **`81520e0`** — timeline defaults to **oldest-first while a date filter is active**
  (begins at the filter start); manual sort toggle preserved.
- **`0da927e`** — **owner-sent message attribution + full conversation in the FLYOUT**.
  `neo4j_service._resolve_report_owner` (traffic-based owner pick, NOT the over-flagged
  `is_phone_owner`); injected in `get_cellebrite_event_detail` + `get_event_related`/
  `_project_message`; full untruncated bodies; `EventAccordion` renders them.
  VERIFIED on case 34fbbb06 → sender "Rico Valentin", recipient "Jayanna Hinge".
  [[project_cellebrite_owner_sent_attribution]]

- **`bbf18bc`** — **owner + recipient attribution in the events feed**
  (timeline rows + rail flyout header + selection payload). `get_cellebrite_events`
  message branch now pulls chat participants + injects the resolved owner;
  `_project_message` sets `sender` (actual: owner if owner-sent), `counterpart`/
  `recipients` (the other party: recipient for outgoing, owner for incoming),
  `direction`, and full `body`. `EventAccordion` attributes each conversation row by
  `it.sender`. VERIFIED on case 34fbbb06: outgoing → "Rico Valentin → Big T",
  incoming → "Big T → Rico Valentin", with numbers; flyout conversation intact.

- **`058b602`** — **main thread view owner attribution**. `get_cellebrite_thread_detail`
  (chat branch) had the same null-sender pattern: owner-sent messages returned
  `sender: None` → bubble showed "Unknown" left-aligned. Now resolves the device owner
  once per thread (`_resolve_report_owner`) and injects it (is_owner=True) when the sender
  edge is absent. Backend-only (frontend already handles is_owner). VERIFIED on
  chat-fb62e13b-940: owner-sent → "Rico Valentin" (right-aligned), received → "Jayanna Hinge".

Docket (separate, branch `feat/docket`, committed `523e6e4`, live): honest self-review
gate + readable/detailed ticket history. [[project_docket_false_pass]]

## AUDIO INVESTIGATION (resolved 2026-06-30)
**Root cause: codec, not missing files.** Voice notes resolve fine to evidence
(category=Audio, real bytes, e.g. `PART_..._Audio_Mes.amr`) but are **`.amr`**
(AMR / AMR-WB) which browsers can't decode → `<audio>` shows duration 0 and won't
play. ffmpeg 7.1.1 is installed and transcodes AMR→MP3 cleanly (verified: 25s AMR →
24.8s MP3). **Fix (commit `9495dec`):** `routers/evidence.py` `get_evidence_file` now
transcodes `.amr/.3ga/.awb/.qcp` → MP3 on first request (cached in
`data/audio_transcoded/{evidence_id}.mp3`, served as `audio/mpeg`); raw fallback if
ffmpeg fails. No frontend change needed (player already classifies category=Audio).
Cache dir writable by backend (uid 1001 = conorbowles51). Verified transcode + cache-hit.
**Sub-gap noted:** ~23/53 sampled message attachments are UNRESOLVED (no evidence
record) — some media wasn't linked at ingest. Separate ingestion issue; revisit with
the event-type coverage item.

## EVENT-TYPE COVERAGE (resolved 2026-06-30, commit `14a75d5`)
**Inventory (case 34fbbb06):** the graph has ONLY Communication/Location/PhoneCall/
Cookie/SearchedItem/Note/Meeting(9)/Autofill(7) nodes — that's all ingestion created.
Two distinct gaps found + fixed:
1. **Calendar wasn't showing** — `Meeting` nodes (the calendar) carry `start_date`/`date`
   but NO `timestamp`, and both `get_cellebrite_event_types` AND the events-feed meeting
   branch filtered `WHERE n.timestamp IS NOT NULL` → 0. Fixed: filter/order on
   `coalesce(timestamp, start_date, date)`, synthesize the row timestamp from it,
   relabel "Calendar". Verified: 9 calendar entries now surface.
2. **Files/images/videos/audio weren't on the timeline at all** — they're NOT nodes;
   they live in evidence_storage (**14,731** files: 12,169 image / 2,223 audio / 332 video;
   14,224 have device `modify_time`). Only message-attached media showed inline. Added a
   `"file"` event type projected from evidence files via new
   `Neo4jService._cellebrite_media_events` (uses `modify_time`; `attachment_file_ids`
   set so the router resolves the thumbnail/player). Wired into the feed, `getEventTypes`
   ("Files & media", 14,224), and the envelope (total now 27,376). Frontend: per-category
   icons/labels (`eventUtils` FILE_CATEGORY_*) + category-aware TimelineRow. Images render
   as thumbnails, audio as players (plays via the AMR→MP3 transcode). VERIFIED end-to-end.
   Caveats: files skipped under only_geolocated + cursor pagination (timeline uses
   pageLimit so unaffected); 507 files without modify_time are not placed.

## 507 UNDATED MEDIA (resolved 2026-06-30 — won't fabricate)
Investigated: the 507 (333 image / 174 video) have **no** `modify_time`, `creation_time`,
`capture_time`, or EXIF date (0/121 sampled images had EXIF) — they're app-cache/sticker/
web images with no device timestamp. Correctly left OFF the time-ordered timeline (placing
them at a fabricated time would be forensically false); they remain available in the Files
tab. NOTE for future: `capture_time` exists on 1,984 media but is naive **device-local**
(EDT, no TZ) whereas `modify_time` is **UTC** — they're the same instant ~1 min apart, so
`modify_time` (what the timeline uses) is the correct UTC value; do NOT naively swap to
`capture_time` (would shift those files by the 4–5h offset). `creation_time` is parsed at
ingest but dropped from the evidence record (would need re-ingest to recover; low value).

## ARTIFACT-TYPE AUDIT (2026-06-30)
Examined the raw report XML (129MB) — full `<model type>` inventory mapped to timeline:
InstantMessage/Location/Attachment/Call/Cookie/Note/CalendarEntry all ON timeline;
Party/Chat = people/thread-containers; MessageLabel(90)/StreetAddress(66)/
QuotedMessageData(16)/ContactPhoto(6)/Coordinate = no timestamp or attributes (not events).
**Autofill (7) was the one clear new timeline type → ADDED** (commit `0902b94`): feed branch +
type count + envelope + frontend icon/label (`autofill`, Keyboard icon). Rows read
"Autofill · q = Coworker · Chrome". Verified 7 events end-to-end.
**SEPARATE INGESTION BUG found (not a new type):** SearchedItem — 71 distinct Waze
location-searches in the XML (all timestamped, all with a geo Position), but only **37**
reached the graph and **0 retained lat/lon**. So ~34 searches + ALL search geo were lost at
ingestion. v1 fix would need a parser change + re-ingest (cellebrite rework is v2-deferred,
see [[project_cellebrite_v2_migration]]); logged for Neil's call.

## BACKLOG (raised, not started)
- **Autofill (7)** nodes exist with timestamps but have no event type (minor).
- ~~AUDIO duration=0 / won't play~~ — RESOLVED (`9495dec`).
- ~~Event-type coverage~~ — core RESOLVED (calendar + media files).
- ~~Unresolved attachments~~ — RESOLVED: absent source data, labeled honestly (`4797cc9`).

## Verification
- Owner/recipient service check:
  `cd backend && ../venv/bin/python -c "from services.neo4j_service import Neo4jService; s=Neo4jService(); print(s.get_cellebrite_events('34fbbb06-4080-4ef7-b895-1fd2f0264eac', event_types=['message'], limit=5)['events'][:3])"`
- Frontend build: `cd frontend && npx vite build` (dev server also hot-reloads).
- Backend reload: `sudo systemctl restart owl-backend`.

## Key facts
- **null sender = owner-sent** (FFS exports: owner has no SENT_MESSAGE edge, isn't a
  participant). Owner identity resolved by traffic, cached per (case,report).
- Owner injected (via `_resolve_report_owner`) in ALL comms projections now:
  `get_cellebrite_events` (timeline + payload + rail header),
  `get_cellebrite_event_detail` (flyout bubble), `get_event_related`/`_project_message`
  (flyout conversation), and `get_cellebrite_thread_detail` (main thread view).
