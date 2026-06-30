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
**AUDIO playback — DONE** (commit below). Remaining BACKLOG:
2. **Timeline event-type COVERAGE** — surface Files/images/videos/calendar/audio/app
   events. The events feed `active` set already lists ~20 types (`neo4j_service.py:9969`)
   — so first check whether those NODES exist in the graph (ingestion) vs. just not being
   requested by the UI type filter (`EventTypeFilter` / `getEventTypes`).

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
24.8s MP3). **Fix (commit `1446e12`):** `routers/evidence.py` `get_evidence_file` now
transcodes `.amr/.3ga/.awb/.qcp` → MP3 on first request (cached in
`data/audio_transcoded/{evidence_id}.mp3`, served as `audio/mpeg`); raw fallback if
ffmpeg fails. No frontend change needed (player already classifies category=Audio).
Cache dir writable by backend (uid 1001 = conorbowles51). Verified transcode + cache-hit.
**Sub-gap noted:** ~23/53 sampled message attachments are UNRESOLVED (no evidence
record) — some media wasn't linked at ingest. Separate ingestion issue; revisit with
the event-type coverage item.

## BACKLOG (raised, not started)
- **Timeline event-type COVERAGE** — only Locations/Calls/Messages/Searches/Notes/Cookies
  surface. Add Files, images, videos, calendar events, audio, app events, etc. Touches the
  events feed `active` set (already lists many types ~`neo4j_service.py:9969`) + ingestion
  (are these nodes created?) + UI type filter. Investigate why current types are narrow.
- **AUDIO duration=0 / won't play** — voice notes show duration 0 and don't play though
  they exist in Cellebrite. Likely **ingestion**: duration not parsed, or attachment not
  linked/served. Per [[feedback_fix_pipeline_not_side_artifacts]] fix the pipeline, not a
  band-aid. Needs its own investigation (check the attachment file ids, audio metadata,
  the media-serving endpoint).

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
