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
**Event-type coverage — core DONE** (calendar fix + 14K media files now on the timeline).
Remaining smaller items:
- **Unresolved attachments** (~23/53 sampled message attachments have no evidence record)
  + **507 media files lack `modify_time`** so aren't placed on the timeline — both are
  ingestion gaps worth a pass.
- **main thread view** `get_cellebrite_thread_detail` owner attribution (still null-sender).
- Optional: split "Files & media" into per-category filter chips (currently one chip);
  cursor-pagination doesn't cover file events (timeline uses pageLimit, so fine there —
  but the Locations/Events cursor consumers won't page files). EventTypeFilter chip could
  show a per-category icon.

Also still TODO (smaller): the **main thread view** `get_cellebrite_thread_detail`
(`neo4j_service.py` ~8860) has the SAME null-sender pattern and does NOT inject the owner —
confirm whether it shows "Unknown" for owner-sent messages and, if so, apply
`_resolve_report_owner` there too (the bubble owner attribution).

Verify each fix against the live data (case 34fbbb06) before claiming done.

---

## DONE (committed to `main`, NOT pushed/deployed)
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

## BACKLOG (raised, not started)
- **Unresolved attachments** (~23/53 sampled) + 507 media files w/o modify_time — ingestion gaps.
- **Autofill (7)** nodes exist with timestamps but have no event type (minor).
- ~~AUDIO duration=0 / won't play~~ — RESOLVED (`9495dec`).
- ~~Event-type coverage~~ — core RESOLVED (calendar + media files), see above.

## Verification
- Owner/recipient service check:
  `cd backend && ../venv/bin/python -c "from services.neo4j_service import Neo4jService; s=Neo4jService(); print(s.get_cellebrite_events('34fbbb06-4080-4ef7-b895-1fd2f0264eac', event_types=['message'], limit=5)['events'][:3])"`
- Frontend build: `cd frontend && npx vite build` (dev server also hot-reloads).
- Backend reload: `sudo systemctl restart owl-backend`.

## Key facts
- **null sender = owner-sent** (FFS exports: owner has no SENT_MESSAGE edge, isn't a
  participant). Owner identity resolved by traffic, cached per (case,report).
- Projections involved: `get_cellebrite_events` (timeline + payload + rail header),
  `get_cellebrite_event_detail` (flyout bubble), `get_event_related`/`_project_message`
  (flyout conversation), `get_cellebrite_thread_detail` (main thread view — same null-sender
  pattern, NOT yet patched; check if it also shows Unknown).
