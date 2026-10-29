# Cellebrite rebuild, spec 03: screens

This file specifies every screen through which phone data reaches an investigator in Loupe: the three
phone-specific screens (Conversations, Extraction profile, Media) and phone data inside six existing
Loupe surfaces (case Timeline, People, a Loupe-wide Search that does not exist yet, Export, case Map,
case Graph). For each it states what the investigator can find out or do, the data it reads, every
interaction, filter and sort, how completeness is guaranteed when filters are applied, how time, names
and numbers, duplicates and record state are shown, the exact wording rules for empty, loading, error and
limited states, keyboard use, performance targets derived from the measured corpus, the API endpoints with
their request and response shapes, where the code lives in `frontend_v2/` and `backend/`, and the
acceptance tests, including one for every item of investigator feedback recorded in plan section 10.2 and
every relevant item of v1's testing checklist. It also maps every v1 Cellebrite screen capability to its
Loupe home or records why it is dropped, and scopes the fixes to existing Loupe defects that these
screens cannot ship without. It details plan sections 10 and 13 (conversations, media, validation rows)
and 10.6; it does not change any standing decision in plan section 1.

## Contents

1. Scope, dependencies and the read contract required from specs 01 and 02
2. Measurements this spec is sized against
3. Rules common to every screen
   - 3.1 Completeness under filters
   - 3.2 Time
   - 3.3 Names, numbers and perspective
   - 3.4 Duplicates
   - 3.5 Record state badges
   - 3.6 The record behind this
   - 3.7 Copy and paste
   - 3.8 Empty, loading, error and limited states; wording rules
   - 3.9 Keyboard
   - 3.10 Sensitive fields
   - 3.11 Access and case scoping
4. Shared backend: router, query module, envelope, common endpoints
5. Shared frontend: placement and conventions
6. Conversations
7. Extraction profile
8. Media
9. Case Timeline phone lens, with the single swim-lane mode
10. People with a per-phone lens
11. Loupe-wide Search, and AI chat citations to records
12. Export: PDF and RSMF
13. Case Map phone layer
14. Case Graph communication edges
15. Loupe defects that must be fixed first, and the fix scope these screens need
16. v1 to Loupe screen mapping
17. Acceptance tests for the recorded feedback
18. Build units
19. Decisions made in this file
20. Not yet established

---

## 1. Scope, dependencies and the read contract

### 1.1 What is in and out

In: everything a person sees or does with phone data after ingestion has finished. Out: intake, capture,
reconciliation, registry and generic interpretation (specs 01 and 02); the pattern-of-life views (day
view, pattern view, places over time, statement check, together and apart), which are spec 04. Here the
Map phone layer is specified as a layer (points, accuracy, flags, loading, limits); what is drawn on top
of it for pattern of life belongs to 04.

### 1.2 What this spec assumes from 01 and 02

Spec 01 (capture) stores every element of a report losslessly in Postgres with a locator. Spec 02
(registry and interpretation) derives, from that capture, the interpreted rows these screens read.
Neither sibling file existed when this file was written (`docs/cellebrite/` was empty), so the read
contract below is stated as the set of columns these screens need. Spec 02 owns the physical names and
may implement each as a table or a view; it must provide every column listed, or this file must be amended
in the same commit that diverges.

All `*_uid` values are stable across re-ingest of the same extraction (plan 6.2: "Loading the same
extraction twice is a no-op"). `extraction_id` is the id of one ingested report (one phone extraction).

| Contract view | One row per | Columns these screens need |
|---|---|---|
| `pv_extraction` | ingested extraction | `extraction_id uuid`, `case_id uuid`, `label text` (C1, C2 ...), `state text` (ingested, partial, failed, replaced), `owner_identity_key text null`, `owner_basis text` (extracted, inferred, manual), `device` jsonb (manufacturer, model, os), `report_version text`, `producer text`, `extraction_type text`, `selection` jsonb (IsSelectiveExtraction, IsPartialData, IsStoppedByUser, IsTriageExtraction as captured, chosen types and ranges if present), `time_zone` jsonb (the report's `timeZoneConfigurations` values verbatim), `device_zone text null` with `device_zone_basis text` (see 3.2), `container_sha256`, `report_sha256`, `ingested_at`, `reconciliation_state text` |
| `pv_record` | captured record (any type, top level or nested) | `record_uid`, `extraction_id`, `cellebrite_id text`, `model_type text`, `parent_record_uid null`, `deleted_state text` (as captured: Intact, Deleted, Trash, Unknown, or null), `decoding_confidence text null`, `source_index text null`, `file_id text null`, `is_carved bool` (02 defines from the capture), `locator` jsonb (01's locator) |
| `pv_comm_event` | message, call, email, voicemail, chat activity | `event_uid`, `record_uid`, `extraction_id`, `case_id`, `kind text` (message, call, email, voicemail, chat_activity), `thread_key text`, `app text null` (SourceApplication or Source as captured), `direction text` (incoming, outgoing, unknown), `sort_instant timestamptz null`, `time_field text` (which field supplied it, e.g. TimeStamp), `body text null` (complete, never cut), `subject text null`, `status text null`, `call_duration_s numeric null`, `call_status text null`, `video bool null`, `dup_group_uid text` (3.4), `dup_rule_version int`, `interpretation_level text` (generic, reviewed; plan 1.5) |
| `pv_comm_party` | party on an event | `event_uid`, `identity_key text`, `role text` (From, To, General, as captured; or owner_implicit when 02 supplies the owner side), `name_in_record text null`, `identifier_raw text null`, `is_phone_owner bool null`, `date_read`, `date_delivered`, `date_played` (timestamptz null each) |
| `pv_thread` | conversation thread | `thread_key`, `extraction_id`, `app`, `thread_kind text` (chat, sms_group, call_log, email_folder), `chat_type text null` (OneOnOne, Group, Broadcast, Unknown), `title_in_record text null`, `first_instant`, `last_instant`, `event_count int`, `party_identity_keys text[]` |
| `pv_identity` | identifier across the case (E.164 number, app user id, email) | `identity_key`, `case_id`, `kind text` (phone, app_user, email, other), `value_normalised text`, `value_display text`, `person_id uuid null` (reviewed People link, section 10) |
| `pv_identity_name` | name a given phone holds for an identity | `identity_key`, `extraction_id`, `name text`, `basis text` (contact_entry, contact, name_in_record), `record_uid`, `time_created`, `time_modified` |
| `pv_time` | every captured TimeStamp value | `record_uid`, `field_path text`, `instant timestamptz null`, `original_text text`, `original_offset_minutes int null`, `offset_present bool` |
| `pv_timeline_entry` | timeline entry (plan 6.4: one per TimeStamp field) | `entry_uid`, `record_uid`, `extraction_id`, `case_id`, `model_type`, `field_path`, `field_meaning text null` (reviewed meaning, plan 11.2 rule 2), `instant timestamptz null`, `activity_class text` (interaction, device_state, passive, unknown; plan 11.2), `summary text`, `identity_keys text[]` |
| `pv_location_point` | positioned record | `point_uid`, `record_uid`, `extraction_id`, `case_id`, `lat double`, `lon double`, `accuracy_m double null`, `accuracy_basis text` (gps_horizontal, precision_field, none), `source_kind text` (gps, wifi, cell, app, photo, account, unknown), `affiliation text null` (DeviceLocationAffiliation as captured), `instant timestamptz null`, `end_instant timestamptz null` |
| `pv_file` | tagged or carved file | `file_uid`, `extraction_id`, `cellebrite_file_id`, `category text` (as captured: Image, Audio, Video, Text, Archives, Document, Application, Configuration, Database, Uncategorized), `local_path text`, `size bigint null`, `md5 text null`, `sha256 text null`, `verification text` (match, mismatch, missing, unverified), `deleted_state text null`, `is_carved bool`, `taken_instant timestamptz null`, `exif` jsonb null |
| `pv_attachment_link` | link from a record to a file | `record_uid`, `file_uid null`, `mechanism text` (tagged_file, jump_target, attachment_field; plan 3.4), `extracted_path text null`, `resolved bool` |
| `pv_text` | searchable string value | `record_uid`, `extraction_id`, `case_id`, `field_path`, `value text`, `value_folded text` (3 rules in 11.3), `is_sensitive bool` |
| `pv_coverage` | (type, field) per extraction | `extraction_id`, `model_type`, `field_name`, `field_kind`, `records int`, `interpretation text` (reviewed, generic, captured_only) |

If 02 decides the owner side of a call is implicit (v1's calls carried one Person edge; see v1 memory
note `project_cellebrite_call_one_edge.md`), `pv_comm_party` must still return a row for the owner with
`role = owner_implicit`, so no screen joins two parties and silently drops calls. That defect is the
recorded cause of "Comms Center showing one call where the Timeline shows many" (same memory note).

---

## 2. Measurements this spec is sized against

All figures from `server_catalog.jsonl` (14 server phones, counts of every model, nested included) unless
marked v1-report (top-level counts from `owl_ingest_report.json`) or local (the C3, C9, C8 structural
stats in `c3.json`, `c9.json`, `c8.json`).

| Measure | Value | Source |
|---|---|---|
| Largest phone by top-level models | 338,715 (C1 of the 3-phone case) | v1-report `total_xml_models` |
| Largest phone by all models | 967,543 (same phone) | catalog |
| InstantMessage, all phones | 377,648; with a TimeStamp value 370,754, so **6,894 without one** | catalog `InstantMessage.TimeStamp` |
| InstantMessage with a Body | 308,807 | catalog |
| Messages per case | 10-report 263,077; 3-phone 104,139; 1-phone 10,432 | catalog summed |
| Messages on one phone, max | 186,787 in 4,491 chats (C6 of the 10-report case) | catalog |
| Chats per case, max | 7,584 (10-report) | catalog summed |
| Calls per case, max | 23,967 (10-report); per phone max 13,573 | catalog |
| Emails per phone, max | 10,890 | catalog |
| Party records | 634,942; `Role` From/General/To; `IsPhoneOwner` on 460,315 | catalog, enums |
| Timestamp-bearing records per case, Party excluded | 10-report 768,316; 3-phone 881,646 | catalog: types with a TimeStamp field |
| Location records per case | 10-report 45,547 (catalog types with TimeStamp) / 3-phone 17,010; per phone max 42,607 | catalog |
| `Location.GpsHorizontalAccuracy` present | 12,728 of 63,784 Location records | catalog |
| `DeviceLocationAffiliation` values | Extracted, Synced, Unknown | enums |
| Tagged files per phone (local) | C3 43,043; C9 29,536; C8 11,663 read (`NodeCount` attribute states 72,849) | local |
| Files whose local path is absent on disk (local) | C3 229; C9 80; C8 9,929 | local `file_lp_present - file_lp_exists` |
| MD5 / SHA256 present (local) | MD5 on 100%; SHA256 on 224, 80, 3 | local |
| Attachment records | 136,345; per phone max 40,241 | catalog |
| Deleted states seen (local) | Intact, Deleted, Trash, Unknown; files also null | local `mt_deleted`, `file_deleted` |
| `decoding_confidence` values seen (local) | High only | local `confidence` |
| Longest single value (local) | 155,838 characters (C3); 108,918 (C8); 37,075 (C9) | local `maxtext` |
| Message sources on one record type (local, C3 top-level InstantMessage) | Android CallLog database 173, IMS Service 28 | local `mt_source` |
| Time zone configuration (local) | C3 convert-to-UTC on, selected zone Africa/Abidjan; C9 convert-to-UTC off, America/New_York; C8 none captured | local `tz` |
| ScrambledMessageData | 7,958 on 3 phones | catalog |
| v1 ingest duration, longest | 292 minutes (C2 of the 3-phone case) | v1-report |

What these numbers force:

- The existing case Timeline loads every event into the browser and gives up beyond 100 pages of 2,000
  (`frontend_v2/src/features/timeline/hooks/use-timeline-data.ts:44-59`). One phone case alone carries
  768,316 to 881,646 timestamp-bearing records. Phone data therefore cannot enter the Timeline through the
  existing client-side full load; section 9 specifies a server-windowed lens.
- 6,894 messages carry no time. The current Timeline drops dateless events on the server
  (`backend/services/neo4j/timeline_service.py:115`, `"sort_date IS NOT NULL"`) and in the browser with
  only a console warning (`use-timeline-data.ts:113-118`). Phone screens must show them (3.1).
- A thread list for the largest case (7,584 chats plus call and SMS pseudo-threads) fits in one response;
  a message stream for the largest phone (186,787 messages) does not, so streams are windowed against an
  exact index (3.1).
- A single value can be 155,838 characters; export and display must not cut it (section 12).

---

## 3. Rules common to every screen

### 3.1 Completeness under filters

The recorded feedback (plan 10.2) asks for three things: the full result when filters are applied, the
same count in every screen for the same question, and scrolling that does not stop. v1's own record is
that silent truncation was found by the investigator (`v1_memory/feedback_no_silent_truncation.md`) and
that the Comms Center and Timeline disagreed because they used different joins
(`project_cellebrite_call_one_edge.md`).

Rules:

1. **One query module per kind of result.** Every screen that lists communication events (Conversations,
   Timeline phone lens, Search pivot, Export, Graph edge detail, People counts) calls the same backend
   function `services/phone/streams.py::query_comm_events(filter)` with the same `StreamFilter` (4.3). No
   screen writes its own join. The same holds for timeline entries (`query_timeline_entries`) and
   location points (`query_location_points`). Acceptance test A3 asserts equal counts across screens.
2. **Index first, rows second.** A list is opened by an *index* call that returns the exact total under
   the filter, the per-day counts in the display zone, the count with no time, and a `snapshot` token.
   Rows are then fetched in *windows* addressed by `(day, offset_in_day, limit)` against the same
   snapshot. The virtual list is sized to the exact total from the first paint, so the scrollbar is the
   whole result. There is no "Load more" control anywhere.
3. **Snapshot.** `snapshot` is `sha256(filter canonical JSON + max(ingest/decision sequence) for the case)`.
   A window request with a stale snapshot returns HTTP 409 with `{"detail": "stale_snapshot"}` and the
   client re-reads the index. This stops a list from shifting under the reader when a correction or a
   new phone lands mid-scroll.
4. **Full load where it fits.** When the filtered total is at most `FULL_LOAD_ROWS = 5,000`, the client
   fetches every window immediately after the index (sequential requests of 1,000 rows), so the whole
   result is in memory, in-page find (Ctrl+F) works, and "Select all" needs no further fetch. Above that,
   windows are fetched as they come into view, two windows ahead and one behind. 5,000 is chosen because a
   message row averages under 1 KB of JSON with its parties (a body is complete but most bodies are
   short; the longest measured is 155,838 characters and is paged within the row, not truncated), so 5,000
   rows stay under about 5 MB, which a browser holds comfortably; *reverse if* measured row size on the
   corpus says otherwise (20.3).
5. **Rows without time are never dropped.** They form a final group, "No time recorded", with its count in
   the index and in every total. Sorting newest first puts the group first.
6. **Every total states what it counts.** The header shows events, and when duplicates are collapsed the
   records behind them (3.4): "1,204 messages (1,260 records; 56 repeated copies shown once)".
7. **A limit is always stated.** If any part of a result is not shown (a map viewport, a cluster, an
   export option, a sensitive field), the screen says so with the number and how to see the rest (3.8).
   A server function that cannot return a complete answer raises `IncompleteResult` with the reason; the
   router returns HTTP 200 with `complete: false` and `limits: [...]`, never a short list silently.
8. **Scroll that stops is a defect, not a state.** A window request that fails shows an inline row at the
   failed position: "These messages could not be loaded. Retry." and the rest of the list stays usable.
   Window requests are retried once automatically after 2 seconds.

### 3.2 Time

What is shown, everywhere a phone time appears:

- **Day and 12-hour time, with the zone named.** Row: `3:07 PM`. Day header: `Tuesday, March 14, 2023`
  followed by the zone, `Eastern Time (UTC-4)`. The offset is computed for that day, so a day crossing a
  daylight-saving change shows both offsets: `Eastern Time (UTC-4 until 2:00 AM, then UTC-5)`. Detail
  views and every copied or exported line carry the full form: `Tue, Mar 14, 2023, 3:07:12 PM EDT`.
- **Seconds** are shown in detail, copy and export, and in the row on hover. Rows show minutes to keep
  them scannable.
- **Locale:** `en-US` explicitly, never the browser default, so two people looking at the same row see the
  same text. Formatting uses `Intl.DateTimeFormat("en-US", {timeZone, hour12: true, ...})`. Owl is a
  Washington DC firm (CLAUDE.md); *reverse if* Neil asks for another locale.
- **Original value on demand.** Clicking or focusing the time and pressing `o` opens a popover:

  ```
  Shown as        Tue, Mar 14, 2023, 3:07:12 PM EDT
  In the report   2023-03-14T19:07:12.000+00:00          (exact text from the report)
  Offset stored   +00:00 (the report converted this time to UTC)
  Field           TimeStamp on InstantMessage
  Zone used       Eastern Time, America/New_York: the phone's time zone as stated in the report
  ```

  `In the report` is `pv_time.original_text` verbatim. When the stored value has no offset the line reads
  "No offset in the report. Loupe has not assumed one." and the row is flagged (below).
- **Zones.** A zone selector on every phone screen with three choices:
  1. *Phone's time zone* (default on single-phone views): `pv_extraction.device_zone`. Its basis is shown in
     the selector. If 02 cannot establish it (`device_zone` null), this choice is disabled with the reason
     "This phone's time zone is not stated in the report." and the view falls back to the case zone.
  2. *Case time zone* (default on multi-phone views): a case setting (`case_display_settings.time_zone`,
     section 4.6). Its default when unset: the phones' `device_zone` if every phone in the case has the same
     one; otherwise `UTC`, and the header says "Phones in this case are in different or unknown time
     zones. Times are shown in UTC."
  3. *UTC*.
  The constant America/New_York that v1 used (`frontend/src/components/cellebrite/shared/cellebriteTime.js:22`
  on `origin/main`; plan 4.6) is not carried over. The v1 note `project_cellebrite_timestamps_utc.md` records
  that the device zone "is NOT stored"; the measured C9 report stores convert-to-UTC off with a selected
  zone, and C3 stores convert-to-UTC on with a selected zone of Africa/Abidjan, which is the examiner's
  setting rather than evidence of the device's zone. How 02 derives `device_zone` is 02's; this file only
  requires that the basis be shown and that no constant is used.
- **Day grouping** is computed on the server in the selected zone with `zoneinfo`, never by slicing an
  ISO string (the cause of v1's day boundary at 8 PM, per `project_cellebrite_timestamps_utc.md`).
- **Flags on time:** `No time recorded` (instant null); `No offset in report` (offset absent); `Time
  field: LastVisited (latest visit only)` where 02 supplies a reviewed meaning (plan 11.2 rule 2).
- **Sort** is by instant, then `event_uid`, so equal times have a stable order across reloads and screens.

Shared implementation: `frontend_v2/src/lib/evidence-time.ts` exports `formatRowTime`, `formatDayHeader`,
`formatFull`, `zoneLabel`, all taking `(instantIso, zone)`; and `backend/services/phone/time_display.py`
exports the same rules for exports. Both have tests against the same fixture table (17, T-time).

### 3.3 Names, numbers and perspective

**Every line that names a participant shows the name and the identifier**, in the form the recorded
feedback gives (plan 10.2): `Name (number) -> Name (number)`.

Display of one participant, `ParticipantLabel`:

| Situation | Shown |
|---|---|
| Name and phone number | `Maria Lopez (+1 202-555-0143)` |
| Name and app identifier, no number | `Maria L (WhatsApp id 5521...@s.whatsapp.net)` shown in full; never shortened |
| Name and email | `Maria Lopez (maria@example.com)` |
| No name | `(no name on this phone) (+1 202-555-0143)` |
| The phone's owner | `Owner of C3: Name (+1 202-555-0100)`; when the owner number is not in the extraction, `Owner of C3 (number not in the extraction)` |
| Owner number supplied by hand at intake | as above with the badge `Number entered by hand` |
| Identifier present but cannot be normalised | the captured value verbatim, with `Not a recognised number format` on hover |

The numbers above are illustrative formats, not evidence. Phone numbers are displayed from
`pv_identity.value_display` (E.164 grouped for reading); the captured value is on hover and in the record
view. The arrow is drawn as `→` on screen with `aria-label="to"` and written as `->` in copied text and
exports, matching the recorded form. Group messages: `Name (number) -> Group "Title" (12 members)`, with the
members listed on expand, each in the same form.

**Perspective.**

- *Phone's view* (the default): a participant's name is the name **the phone the record came from**
  holds for that identifier: first a contact entry on that phone (`pv_identity_name.basis =
  contact_entry` or `contact`), else the name written in the record itself (`name_in_record`), else
  "(no name on this phone)". In a list that mixes phones (a case-wide timeline), each line uses its own
  phone's names; the line carries the phone label (C3) so the perspective of every line is visible. This
  is the v1 rule recorded in `feedback_cellebrite_perspective_primary.md` (per-device names, default) and
  the recorded feedback "if I'm looking through a phone's lens, then I want to see how that phone views
  the world" (plan 10.2).
- *Case view* (one click: the `Names: This phone / Case` toggle, key `p`): the name is the reviewed People
  name (`pv_identity.person_id` resolved through section 10); identifiers with no reviewed person keep the
  phone's view. Every line in case view has a small marker `Case name`; hovering lists each phone's name
  for that identifier: `C3: Maria L; C7: Mom; C9: (no name)`.
- The toggle changes labels only. It never merges rows, never changes counts, and never changes which
  events a participant filter matches. Linking identities so that a participant filter also matches the
  person's other identifiers is a separate, explicit filter option `Include this person's other numbers
  and accounts` (off by default; v1 had the same default after correction, per
  `feedback_cellebrite_perspective_primary.md`).

### 3.4 Duplicates

v1 collapsed a message recorded three times across sources (Native Messages, IMS Service, Android
CallLog) into one row with a "+N sources" chip, and kept genuinely different messages apart (v1
checklist items `dedup-collapse`, `dedup-sources-chip`, `dedup-no-false-merge`,
`backend/services/testing_checklist.py:101-112` on `origin/main`). Measured: the C3 sample's top-level
InstantMessages come from two sources (Android CallLog database 173, IMS Service 28).

Rule (computed by 02 into `pv_comm_event.dup_group_uid`, version in `dup_rule_version`; this file defines
version 1):

- Two events are copies when all of these are equal: `extraction_id` (never across phones; cross-phone
  matching is plan 12 approach 2), `kind`, `direction`, the sender identity key, the sorted set of
  recipient identity keys, `sha256(NFC(body))` (or of `subject` + body for email; or `call_duration_s` and
  `call_status` for calls), and `sort_instant` at the precision recorded. A null `sort_instant` never
  matches anything.
- The group's displayed row is the copy with the most populated fields; ties by lowest `record_uid`.
- **Visible, never silent.** The row carries a chip `Found 3 times` (UI copy); clicking it lists each copy
  with its source, record id and a link to its record. The total says how many records were collapsed
  (3.1 rule 6). A toggle `Show every copy` (off by default) lists every record as its own row; counts then
  equal records.
- Nothing is deleted or hidden from search, export or the record view. Export states whether copies were
  collapsed (section 12).
- Whether equal-to-the-second is the right precision is measured before build (20.1).

### 3.5 Record state badges

Badges are words, not colours alone. Each has a tooltip giving the captured value.

| Badge (UI copy) | When | Captured value shown on hover |
|---|---|---|
| `Deleted` | `deleted_state = Deleted` | `deleted_state: Deleted` |
| `In trash` | `deleted_state = Trash` | `deleted_state: Trash` |
| `Deletion state unknown` | `deleted_state = Unknown` on the event itself (not on its parties, where Unknown is the norm: C3 Party 7,448 of 7,504) | as captured |
| `Recovered by carving` | `pv_record.is_carved` | carving origin per 02 |
| `May come from another device` | `affiliation = Synced`, or a `UserMapping` value 02 marks as synced (plan 11.2 rule 3) | the field and value |
| `Decoding confidence: <value>` | `decoding_confidence` present and not `High` | as captured |
| `App: WhatsApp` | always, from `app` | `SourceApplication` and `Source` |
| `No time recorded`, `No offset in report` | 3.2 | |
| `File missing from production`, `File does not match its hash`, `File not checked` | attachment `verification` | stored and computed hashes |
| `Unreadable message` | ScrambledMessageData present on the event | |
| `Read by owner`, `Played by owner` | owner party `date_read` / `date_played` | the timestamps, formatted as 3.2 |
| `Generic reading` | `interpretation_level = generic` | "Loupe has not yet reviewed how this record type maps to messages. Fields are read by their names." |

### 3.6 The record behind this

Every row, point, file, edge record and search hit has an action `Open the record behind this` (key `r`).
It opens the **Record panel**, a right-side sheet (`frontend_v2/src/features/phones/components/RecordPanel.tsx`),
reading `GET /api/phones/records/{record_uid}` (4.4). It shows:

1. Header: phone label, record type, Cellebrite record id, and the report file name with its SHA-256.
2. State: deleted, carved, decoding confidence, source index, interpretation level.
3. Every field in capture order, each with name, field kind, data type and every value (not only the
   first, plan 3.1), nested records expandable to any depth, attributes listed.
4. Every TimeStamp with its original text beside the formatted value (3.2).
5. Linked files by all three mechanisms (plan 3.4), each with its verification state; an image or audio
   file opens in the existing `DocumentViewer` (`frontend_v2/src/components/ui/document-viewer.tsx:54-90`).
6. Where the production includes a source database and 02 can locate the row, `Open source row`; where it
   does not, the sentence "The production does not include the app database this record was read from."
   (plan 13, validation row). Only C8 has a database folder among the local samples (plan 13).
7. Actions: `Copy record as text`, `Copy record id`, `Show in Conversations`, `Show on Timeline`, `Show on
   Map` (when positioned).

Absence follows the pattern of `SourceHighlight` (`frontend_v2/src/features/financial/components/SourceHighlight.tsx:10-20,80-159`):
each kind of absence has its own sentence, and none is collapsed into "unavailable":

| Absence | Sentence |
|---|---|
| Record has no file reference | "This record does not refer to a file." |
| Reference present, file not in production | "The report refers to a file that is not in the production." |
| File present, hash differs | "The file in the production does not match the hash in the report." with both hashes |
| File present, report gave no hash | "The report gave no hash for this file, so it could not be checked." |
| Field captured but not interpreted | "Captured, not yet interpreted." (still shown with its values) |

### 3.7 Copy and paste

The recorded feedback asks for copy and paste in timelines (plan 10.2).

- Row text is selectable (`user-select: text`); dragging across rows selects text across rows. Virtual
  rows outside the viewport are not in the DOM, so a native selection can only span visible rows. For more,
  use row selection:
- Row selection: click the row's checkbox or press `Space`; `Shift+Click` and `Shift+Arrow` extend;
  `Ctrl/Cmd+A` selects every row in the filtered result (the whole total, not the rendered ones).
- `Ctrl/Cmd+C` with rows selected, or the toolbar `Copy N`, writes two clipboard formats:
  - `text/plain`, one line per event:
    `Tue, Mar 14, 2023, 3:07:12 PM EDT | C3 | WhatsApp | Maria Lopez (+1 202-555-0143) -> Owner of C3: Name (+1 202-555-0100) | <full body>`
    Multi-line bodies keep their line breaks, indented by two spaces. Attachments are listed as
    `[attachment: filename, category]`. Flags as `[Deleted]`.
  - `text/html`, a table with the same columns, so pasting into Word or Outlook keeps columns.
- Selections above `FULL_LOAD_ROWS` fetch the missing windows first and show "Preparing 12,345 messages
  to copy" with progress; copying is never refused. The copied text ends with one line stating the filter
  and zone: `Copied from Loupe, case <name>, filter: ..., times in Eastern Time.`
- `Copy record as text` (record panel) writes every field as `name: value` lines.

Implementation: `frontend_v2/src/features/phones/lib/copy-rows.ts` (pure functions, unit tested), used by
Conversations, Timeline lens and Search.

### 3.8 Empty, loading, error and limited states; wording rules

Wording rules for all UI copy in this file:

- No em dashes. Use a full stop, colon or parentheses.
- Plain words; no internal names (no "record_uid", "extraction", "projection", "registry" in body copy;
  "record id" is allowed in the record panel because it is the Cellebrite id an examiner can look up).
- Say what happened, what it means for the investigation, and what the person can do.
- Numbers with thousands separators; "1 message", "2 messages".
- Never imply absence of activity from absence of data (plan 11.2 rule 4): "No messages in this period
  on this phone" never "Nothing happened".

States every list and panel implements, with the exact copy:

| State | Copy |
|---|---|
| Loading the index | skeleton rows plus "Counting matching messages" |
| Index loaded, windows loading | the header total is shown immediately; placeholder rows in place |
| No phone in the case | "No phone extractions have been added to this case. Add one from Evidence." with a link |
| Filter matches nothing | "No messages match these filters." followed by the active filters as removable chips and `Clear filters` |
| Phone present, kind absent | "C3's report contains no calls." (from `pv_coverage`, which distinguishes "not in the report" from "filtered out") |
| Phone still ingesting | "C3 is still being read (62%). Results will be incomplete until it finishes." and every total carries `(incomplete)` |
| Phone ingest failed or partial | "C8's report could only be partly read. Results from C8 are incomplete. See Extraction profile." |
| Window failed | "These messages could not be loaded. Retry." |
| Index failed | "The message list could not be loaded. Retry. If this keeps happening, tell Neil the time it happened." |
| Stale snapshot | "New data arrived while you were reading. The list has been refreshed and kept your place." |
| Limited (any 3.1 rule 7 case) | "Showing 5,000 of 12,431 points in this area. Zoom in or narrow the dates to see each one." |

### 3.9 Keyboard

Consistent with the existing Timeline bindings (`frontend_v2/src/features/timeline/hooks/use-keyboard-navigation.ts:63-114`:
`j`/`k`, arrows, `Enter`/`Space`, `Escape`, `[`/`]`, `/`) and the global shortcuts
(`frontend_v2/src/hooks/use-global-shortcuts.ts:18-52`: Cmd/Ctrl+K, Escape, Cmd/Ctrl+1..8 views).

| Key | Action |
|---|---|
| `j` / `ArrowDown`, `k` / `ArrowUp` | next / previous row |
| `PageDown`, `PageUp`, `Home`, `End` | by screen; first / last row of the whole result |
| `[` / `]` | previous / next day |
| `g` then type a date, `Enter` | jump to that day |
| `Enter` | open the selected thread or row detail |
| `r` | open the record behind this |
| `o` | original time value popover |
| `p` | toggle names: this phone / case |
| `Space` | select or deselect row |
| `Shift+j/k`, `Shift+Arrow` | extend selection |
| `Ctrl/Cmd+A`, `Ctrl/Cmd+C` | select all in result; copy selection (3.7) |
| `/` | focus the filter search box |
| `Ctrl/Cmd+K` | Loupe-wide search (section 11) |
| `Escape` | close panel, then clear selection |

Every action has a visible control; keys are accelerators only. Focus is visible on every row. The
virtual list keeps focus on the same event when windows load (focus is tracked by `event_uid`, not index).

### 3.10 Sensitive fields

Plan 12.1 rule 4: saved passwords, keyboard dictionary, autofill, credentials and card numbers are
captured, shown with care and excluded from exports by default. Screens here: `pv_text.is_sensitive`
values are masked in lists and search snippets (`Saved password (hidden). Show`), revealed per value on
click, each reveal recorded through the audit log with the user and record; excluded from copy unless
revealed; excluded from exports unless the export option `Include sensitive fields` is ticked, which the
export manifest records.

### 3.11 Access and case scoping

Every endpoint takes `case_id` and calls `get_case_if_allowed` (`backend/services/case_service.py:149`) as
the timeline router does (`backend/routers/timeline.py:141`); every SQL statement filters on `case_id`
(plan 5 lesson 7). A record, file or thread uid from another case returns 404, not 403, so ids do not leak
existence across matters.

---

## 4. Shared backend

### 4.1 Placement

| Path | Holds |
|---|---|
| `backend/routers/phones.py` | `APIRouter(prefix="/api/phones", tags=["phones"], dependencies=[Depends(get_current_db_user)])`, registered in `backend/main.py` beside `cellebrite_router` (`backend/main.py:248`), which is removed when this lands |
| `backend/services/phone/streams.py` | `query_comm_events`, `index_comm_events`, `window_comm_events`, `query_timeline_entries`, `query_location_points` |
| `backend/services/phone/filters.py` | `StreamFilter` (pydantic v2), canonical JSON and snapshot hash |
| `backend/services/phone/labels.py` | participant label resolution (3.3) |
| `backend/services/phone/time_display.py` | 3.2 for the server (exports) |
| `backend/services/phone/fold.py` | text folding for search (11.3) |
| `backend/services/phone/records.py` | record panel payload |
| `backend/services/phone/exports/{pdf.py,rsmf.py,jobs.py}` | section 12 |
| `backend/tests/test_phone_*.py` | one test file per module, following the financial suite convention |

All Python is 3.10 (CLAUDE.md, Environment). The prefix is `/api/phones` so the new router can be built
beside the existing `/api/cellebrite` router (`backend/routers/cellebrite.py:28`) and the old one removed in
one later commit.

### 4.2 Envelope

Every list response:

```json
{
  "case_id": "uuid",
  "snapshot": "hex64",
  "complete": true,
  "limits": [],
  "counts": {"events": 1204, "records": 1260, "collapsed_copies": 56, "no_time": 3},
  "items": []
}
```

`limits` entries: `{"kind": "viewport" | "cluster" | "sensitive_hidden" | "phone_incomplete", "shown": int,
"total": int, "message": "UI copy per 3.8"}`. `complete` is false whenever `limits` is non-empty or any
phone in scope is not fully ingested.

### 4.3 `StreamFilter`

```json
{
  "case_id": "uuid",
  "phones": ["extraction_id"],
  "threads": ["thread_key"],
  "participants": ["identity_key"],
  "participant_mode": "any | all | between",
  "expand_person_identities": false,
  "apps": ["WhatsApp"],
  "kinds": ["message", "call", "email", "voicemail", "chat_activity"],
  "directions": ["incoming", "outgoing", "unknown"],
  "deleted_states": ["Intact", "Deleted", "Trash", "Unknown", null],
  "flags": {"carved": null, "synced": null, "has_attachment": null, "unreadable": null},
  "from_instant": "2023-03-01T00:00:00-05:00",
  "to_instant": "2023-03-31T23:59:59.999-04:00",
  "include_no_time": true,
  "text": {"query": "string", "exact_characters": false},
  "collapse_copies": true,
  "names": {"mode": "phone | case"},
  "zone": {"mode": "phone | case | utc", "phone": "extraction_id or null"},
  "sort": "oldest_first | newest_first"
}
```

Empty or omitted arrays mean "no restriction". `between` requires exactly two participants and matches
events where one is sender and the other a recipient, either way.

**Group messages under `between` (settled 2026-10-29, aligned with 02's edge definition):** a further
filter key `"group_scope": "direct | include_groups"`, default `direct`. With `direct`, `between`
matches only events in one-to-one threads and direct calls. The response always carries
`group_totals` (`{threads, events}`) for group threads in which both participants are members, and
the screen states it under the list: "Also in 3 group chats (412 messages). Include them". Choosing it
sets `include_groups`, which adds group events in which one of the two is the sender and the other a
member. The Graph edge for a pair counts `direct` only and shows the group figure separately (02);
test A3 compares totals under the same `group_scope` on every surface, and adds a case for each value.
*Reverse if* reviewing real cases shows group traffic is the main channel between pairs. Date inputs from the UI are dates in the
selected zone; the client converts them to instants at the zone's day start and end before sending, so
the server never compares date strings (plan 4.6 records that v1 compared strings).

### 4.4 Common endpoints

| Method and path | Request | Response |
|---|---|---|
| `GET /api/phones?case_id=` | | `{"phones": [PhoneSummary]}`; `PhoneSummary` = `{extraction_id, label, owner: ParticipantLabel, device: {manufacturer, model, os}, state, ingest_progress: 0..1 or null, device_zone, device_zone_basis, counts: {messages, calls, emails, locations, files, timeline_entries}}` |
| `GET /api/phones/records/{record_uid}?case_id=` | | `RecordDetail` (3.6): `{record_uid, extraction: {id, label, report_filename, report_sha256}, model_type, cellebrite_id, state: {...}, fields: [Field], attributes: {...}, times: [{field_path, instant, original_text, offset_present}], files: [FileLink], source_row: {available: bool, reason}, interpretation_level}`; `Field` = `{name, kind, data_type, values: [any], children: [RecordDetail]}` |
| `GET /api/phones/files/{file_uid}/content?case_id=` | `Range` header supported | the bytes, `Content-Type` from capture or sniffed; 404 with `{"detail": "file_not_in_production"}` when absent |
| `GET /api/phones/files/{file_uid}/thumbnail?case_id=&size=256` | | JPEG or PNG thumbnail, cached under the case storage; 404 `no_thumbnail` for non-visual files |
| `GET /api/phones/identities?case_id=&q=&limit=50&cursor=` | | identity picker: `{items: [{identity_key, kind, value_display, names: [{phone_label, name, basis}], person: {id, display_name} or null, event_count}], next_cursor, total}` |

### 4.5 Stream endpoints (used by Conversations, Timeline lens, Search pivot, Export)

| Method and path | Request body | Response |
|---|---|---|
| `POST /api/phones/streams/index` | `StreamFilter` | envelope with `items: [{"day": "2023-03-14", "count": 42, "offsets": "UTC-4"}]`, plus `zone: {name, label, basis}` and `no_time_count` |
| `POST /api/phones/streams/window` | `{"filter": StreamFilter, "snapshot": "hex64", "day": "2023-03-14" or null for no-time, "offset": 0, "limit": 200}` | envelope with `items: [StreamRow]`; 409 `stale_snapshot` |
| `POST /api/phones/streams/locate` | `{"filter": StreamFilter, "snapshot", "event_uid"}` | `{"day", "offset"}` so any screen can open a stream scrolled to one event |

`limit` max 1,000. `StreamRow`:

```json
{
  "event_uid": "string",
  "record_uid": "string",
  "kind": "message",
  "phone": {"extraction_id": "uuid", "label": "C3"},
  "app": "WhatsApp",
  "thread": {"thread_key": "string", "title": "string or null"},
  "direction": "outgoing",
  "time": {"instant": "2023-03-14T19:07:12Z", "row": "3:07 PM", "full": "Tue, Mar 14, 2023, 3:07:12 PM EDT",
           "offset_present": true, "time_field": "TimeStamp"},
  "from": ParticipantLabel,
  "to": [ParticipantLabel],
  "body": "complete text or null",
  "subject": null,
  "call": {"duration_s": 63, "status": "Established", "video": false},
  "attachments": [{"file_uid": "string", "filename": "string", "category": "Image", "verification": "match",
                   "mechanism": "attachment_field"}],
  "flags": ["Deleted", "Recovered by carving"],
  "copies": {"count": 3, "record_uids": ["..."], "apps": ["Native Messages", "IMS Service", "Android CallLog database"]},
  "owner_read": {"date_read": "instant or null", "date_played": "instant or null"},
  "interpretation_level": "reviewed"
}
```

`ParticipantLabel`:
`{"identity_key", "name", "name_basis": "contact_on_this_phone | name_in_record | case_person | none",
"identifier": {"kind": "phone | app_user | email | other", "display", "captured"}, "is_owner": bool,
"owner_basis": "extracted | inferred | manual | null", "case_names": [{"phone_label", "name"}]}`.
`case_names` is only filled in case-name mode. Formatted time strings are computed on the server so screen,
copy and export agree byte for byte; the client also has `evidence-time.ts` for client-side formatting
(day headers, original-value popover) tested against the same fixtures.

### 4.6 Case display settings

New table, Alembic migration in `backend/postgres/alembic/versions/`:

```
case_display_settings
  case_id      uuid primary key references cases(id) on delete cascade
  time_zone    text not null   -- IANA name, validated with zoneinfo.ZoneInfo
  updated_by   uuid not null references users(id)
  updated_at   timestamptz not null default now()
```

`GET/PUT /api/phones/settings?case_id=`; the PUT is recorded in the audit log with old and new values. The
Case settings page (`frontend_v2/src/features/cases/components/CaseSettingsPage.tsx`) gains a "Time zone
for phone data" field.

### 4.7 Indexes required on 02's storage

| On | Index | Serves |
|---|---|---|
| comm events | `(case_id, extraction_id, sort_instant, event_uid)` | per-phone streams, day index |
| comm events | `(case_id, thread_key, sort_instant, event_uid)` | thread view |
| comm events | `(case_id, sort_instant, event_uid)` | case-wide streams |
| comm parties | `(identity_key, event_uid)` and `(event_uid)` | participant filters |
| texts | `GIN (value_folded gin_trgm_ops)` | search (pg_trgm is already enabled: `backend/postgres/alembic/versions/20260721_add_evidence_document_texts.py:25`) |
| timeline entries | `(case_id, instant, entry_uid)`, `(case_id, extraction_id, instant)` | Timeline lens |
| location points | GiST on `point(lon, lat)` or PostGIS if 02 adopts it; plus `(case_id, instant)` | Map layer |

The day index is computed with `date_trunc('day', sort_instant AT TIME ZONE :zone)` grouped and counted in
one statement over the index; the window is `WHERE <filter> AND sort_instant >= :day_start AND sort_instant
< :day_end ORDER BY sort_instant, event_uid OFFSET :offset LIMIT :limit`. The offset is bounded by one
day's count, so deep scrolling never scans earlier days (v1's checklist item `nav-keyset-fast` asked for
the same property). The maximum events in one day on one phone is not yet measured (20.2).

---

## 5. Shared frontend

### 5.1 Placement

Follows the existing feature layout (`frontend_v2/src/features/<feature>/{api.ts, components/, hooks/,
lib/, stores/}`, as in `features/timeline` and `features/financial`), lazy routes in
`frontend_v2/src/app/routes.tsx:12-47,156-172`, and `fetchAPI` from `frontend_v2/src/lib/api-client.ts:20-89`.
Response shapes are validated with zod as financial does (`frontend_v2/src/features/financial/lib/source-citation.ts:1-20`).

| Path | Holds |
|---|---|
| `src/features/phones/api.ts` | typed calls for every endpoint in sections 4, 6-8 |
| `src/features/phones/schemas.ts` | zod schemas for `StreamRow`, `ParticipantLabel`, envelope, `RecordDetail` |
| `src/features/phones/hooks/use-stream.ts` | index plus window loading, snapshot handling, full-load rule (3.1) |
| `src/features/phones/components/StreamList.tsx` | the one virtual list (TanStack `useVirtualizer`, as `features/timeline/components/EventStream.tsx:41-47`) used by Conversations, Timeline lens and Search results |
| `src/features/phones/components/{ParticipantLabel,TimeCell,OriginalTimePopover,RecordPanel,StateBadges,CopiesChip,ZoneSelector,NamesToggle,PhonePicker}.tsx` | shared pieces |
| `src/features/phones/lib/{copy-rows.ts,filter-url.ts}` | copy formats; filter in the URL so any view is linkable |
| `src/lib/evidence-time.ts` | 3.2 |
| `src/features/conversations/` | section 6 |
| `src/features/extraction-profile/` | section 7 |
| `src/features/media/` | section 8 |
| `src/features/search/` | section 11 |
| existing `src/features/timeline`, `dossiers`, `map`, `graph` | gain lens, panel, layer, edges |

The existing `src/features/cellebrite/` (15,815 lines) and its route (`routes.tsx:38-42,163`) are removed
in the same commit that adds the new routes.

### 5.2 Routes and navigation

| Route | Page |
|---|---|
| `/cases/:id/conversations` | Conversations |
| `/cases/:id/phones` | Extraction profile (list of phones; `/cases/:id/phones/:extractionId` one phone) |
| `/cases/:id/media` | Media |
| `/cases/:id/cellebrite` | `Navigate` to `phones`, so old links still land |

Sidebar (`frontend_v2/src/components/ui/sidebar.tsx:60-66`): the "Cellebrite" item (`shortcut: "6"`) becomes
three items in the same group: `Conversations` (`MessagesSquare`, shortcut 6), `Phones`
(`Smartphone`), `Media` (`Images`). The global shortcut list (`use-global-shortcuts.ts:34-43`) replaces
`"cellebrite"` with `"conversations"` so Ctrl/Cmd+6 still opens the phone screen people use most. The three
items show only when the case has at least one phone (`GET /api/phones` non-empty), so a case with no phone
does not gain three empty screens.

### 5.3 Tests

- Unit (`*.test.ts(x)`, jsdom, project `unit` in `frontend_v2/vitest.config.ts:22-36`): pure libs
  (`evidence-time`, `copy-rows`, `filter-url`, fold mirror), hooks with mocked `fetchAPI`
  (`vi.mock("@/lib/api-client", ...)` as `FinancialTimeline.browser.test.tsx:23-26`), components with
  `fireEvent` (CLAUDE.md: not `userEvent`).
- Browser (`*.browser.test.tsx`, Chromium, project `browser`, `vitest.config.ts:37-52`): anything that
  depends on real layout: virtual list sizing and scroll to the end of a 200,000-row mocked index, copy to
  clipboard, focus retention, PDF preview.
- Backend: `backend/tests/test_phone_<module>.py`, unittest, SQLite where possible like
  `test_financial_transaction_query`; trigram and timezone SQL that SQLite cannot run are tested against
  Postgres in a `@skipUnless(POSTGRES_URL)` class and listed in the build-state file.

---

## 6. Conversations

### 6.1 Purpose

Read every message, call, email and voicemail on one phone, several phones, or the whole case, as threads
or as one stream for a person or a pair of people across apps; see who wrote to whom with names and
numbers; see what was deleted, unreadable, carved or repeated; open the record behind any line; copy or
export exactly what is on screen.

### 6.2 Layout and modes

Three panes: filter bar (top), thread list (left, resizable with `react-resizable-panels`, already a
dependency), stream (right). Two modes, switched by tabs above the thread list:

- **Threads**: pick a thread on the left; the stream shows that thread.
- **People**: pick one person or two (a pair); the stream shows every event involving them across all
  apps and phones in scope, in time order, each line labelled with phone and app. This is plan 13's
  "one stream per person or pair across apps and phones". The left pane lists participants instead of
  threads, with counts.

### 6.3 Data

| Call | When |
|---|---|
| `GET /api/phones?case_id` | page load: phone picker, zone defaults |
| `POST /api/phones/conversations/threads` body `StreamFilter` (threads ignored) | thread list; always the complete list in one call (sized: at most 7,584 chats per case plus pseudo-threads) |
| `POST /api/phones/conversations/participants` body `StreamFilter` | participant list for People mode; complete in one call; rows `{label: ParticipantLabel, events, first_instant, last_instant, phones: [label], apps: [app]}` |
| `POST /api/phones/streams/index` and `/window` | the stream |
| `GET /api/phones/records/{uid}` | record panel |

Thread list row: `{thread_key, phone_label, app, chat_type, title: string, participants: [ParticipantLabel]
(first 5, with participant_count), first_instant, last_instant, event_count (under the filter),
event_count_total (unfiltered), deleted_count, has_unreadable}`. Thread title in phone names: the
`title_in_record` if present, else the participants' names joined with ", ". A thread with events matching
the filter is listed; a thread with none is not, and the header says "312 of 4,491 conversations have
messages matching these filters".

### 6.4 Filters

All in the filter bar, all reflected in the URL (`filter-url.ts`), all shown as removable chips:

| Filter | Control | Notes |
|---|---|---|
| Phones | multi-select of `PhoneSummary`, each with owner label | default: all phones; a single-phone entry point (from Phones) pre-selects one |
| Participants | identity picker (`/api/phones/identities`), each option a `ParticipantLabel` with all phone names | mode any / all / between; `Include this person's other numbers and accounts` |
| Apps | multi-select from the distinct `app` values in scope, each with count | |
| Kinds | messages, calls, emails, voicemail, group activity | |
| Direction | incoming, outgoing, unknown | |
| Dates | from and to, as dates in the selected zone, with times optional | converted to instants (4.3) |
| State | deleted, in trash, carved, may come from another device, unreadable, has attachment | tri-state each: any / only / exclude |
| Text | contains, folded per 11.3; `Exact characters` toggle | matches body, subject, attachment filename |
| Copies | `Show every copy` | 3.4 |

### 6.5 Sorting

Threads: last activity (default), first activity, message count, name. Stream: oldest first (default,
conversations read forward) or newest first. Sort choice persists per case in `localStorage`, as v1's
`nav-sort-toggle` did (v1 checklist line 77-78).

### 6.6 Stream row

```
3:07 PM   C3 · WhatsApp                                                    [Deleted] [Found 3 times]
          Maria Lopez (+1 202-555-0143) -> Owner of C3: Name (+1 202-555-0100)
          Full message text, every line, wrapped. Long bodies over 2,000 characters show the first
          2,000 with "Show all 155,838 characters" which expands in place (the text is already loaded).
          [image thumbnail] [voice note 0:42 play]
```

Calls: `Call, 1 min 3 s, answered` (status words map from `TelephonyCallStatus`: Established answered,
Missed missed, Rejected declined, Canceled cancelled, BusyLine busy, Voicemail went to voicemail,
NotEstablishedUnknownReason not connected, Unknown status not recorded). Video calls say `Video call`.
Emails: subject in bold, full body, `To`, `Cc` and every recipient (plan 4.5: v1 dropped multi-party `To`).
Group activity: `Name (+1...) added Name (+1...)` from `ChatActivityAction`.

Media plays and displays inline: images as thumbnails (opens `DocumentViewer`), audio with a play control
that fetches bytes only on play (v1 checklist `media-voice-preload`). Missing or mismatched files show the
3.6 sentence in place of the thumbnail.

### 6.7 Interactions

- Select thread or person: loads index and windows; keeps the filter.
- Click a participant label: menu `Show all with this person`, `Show this pair`, `Open in People`, `Copy
  name and number`.
- Click time: original value popover (3.2).
- `Found N times`: list of copies.
- Row menu: `Open the record behind this`, `Show on Timeline` (opens Timeline lens at this instant with the
  same participants), `Show on Map` (nearest location points on the same phone within the hour, a 04
  feature linked here), `Add to Workspace` (existing workspace entry flow), `Copy`.
- Jump to date (`g`), day navigation (`[`/`]`).
- Export (section 12) from the toolbar: exports exactly the current filter.
- Toolbar always shows: total (3.1 rule 6), zone selector, names toggle, `Show every copy`, sort.

### 6.8 Performance targets

| Operation | Target (p95, server on the production host) | Basis |
|---|---|---|
| Thread list, largest case | 800 ms, payload under 4 MB | 7,584 chats; ~450 bytes per row |
| Stream index, largest phone unfiltered | 500 ms | 186,787 messages + 13,573 calls on C6, grouped by day over the index |
| Window of 200 rows | 200 ms | offset within one day only |
| First paint of rows after selecting a thread | 1 s | index + first window |
| Scroll | no blank rows held longer than 300 ms at normal scroll speed; 60 frames per second | prefetch two windows ahead |

Backend tests assert the query plans use the indexes in 4.7 (`EXPLAIN` without a sequential scan on the
events table) on a generated Postgres fixture of 200,000 events.

### 6.9 Acceptance tests (Conversations)

| Id | Test |
|---|---|
| C-1 | With a mocked index of 186,787 rows the virtual list's scroll height equals 186,787 rows and `End` shows the last row with no "load more" control in the DOM (browser) |
| C-2 | Filter total equals the sum of day counts plus `no_time_count` (backend) |
| C-3 | A message without a timestamp appears under "No time recorded" and is counted (backend + unit) |
| C-4 | A call with only one party edge in 02's data still appears with the owner side labelled (backend; guards the v1 one-call defect) |
| C-5 | Thread list for a fixture of 7,584 threads is returned in one response with `complete: true` |
| C-6 | Every rendered row contains a name and an identifier for each participant, or the explicit no-name form (unit, over a fixture covering every row of the 3.3 table) |
| C-7 | Switching names toggle changes labels and nothing else: same event_uids in the same order, same counts |
| C-8 | Long body of 155,838 characters is delivered whole in the row payload and expands in place without a request |
| C-9 | Stale snapshot (409) re-reads the index and keeps the focused event_uid in view |

---

## 7. Extraction profile

### 7.1 Purpose

Know, for each phone, what the production is and is not: whose phone it is and how that was established;
the device; what the report says was selected or left out; whether the export arrived whole; whether the
files match their hashes; how much is deleted; which record types Loupe interprets, reads generically or
only holds; and where to go to see any of it. This is what an investigator needs before relying on an
absence, and what lets them state the limits of the phone evidence.

### 7.2 Data

`GET /api/phones/{extraction_id}/profile?case_id=` returns:

```json
{
  "phone": PhoneSummary,
  "owner": {"label": ParticipantLabel, "basis": "extracted | inferred | manual", "evidence": [{"record_uid", "field", "value_display"}]},
  "device": {"manufacturer", "model", "os", "imei_or_ids": [{"name", "value"}], "source_record_uids": []},
  "report": {"filename", "form": "ufdr | folder | zip | split_sections", "report_version", "producer",
             "extraction_type", "container_sha256", "report_sha256", "report_md5_stated", "report_md5_matches": true,
             "extraction_start", "extraction_end", "time_zone_settings": {"verbatim": {}}, "device_zone", "device_zone_basis"},
  "selection": {"is_selective": "True | False | not stated", "is_partial": "...", "stopped_by_user": "...",
                "triage": "...", "chosen_types": [], "chosen_ranges": []},
  "completeness": {"reconciliation": "exact | failed", "truncated_sections": [{"section", "detail"}],
                   "stated_vs_read": [{"what": "files", "stated": 72849, "read": 11663}]},
  "files": {"total": 43043, "by_category": {"Image": 33584}, "verification": {"match": 0, "mismatch": 0, "missing": 229, "unverified": 0},
            "sha256_present": 224},
  "deleted": [{"model_type", "intact", "deleted", "trash", "unknown"}],
  "coverage": [{"model_type", "records", "interpretation": "reviewed | generic | captured_only", "fields": [{"name", "kind", "records", "interpretation"}]}],
  "data_periods": [{"signal", "first_instant", "last_instant", "records"}]
}
```

Every value above comes from 01's capture or 02's interpretation; none is typed in. The C8 case is the
reason for `stated_vs_read`: its report attribute states `NodeCount` 72,849 while 11,663 file entries were
readable from the cut-off `.xmlTagged` section (local measurement); whether `NodeCount` counts exactly the
file entries is to be confirmed by 01 (20.4).

### 7.3 Layout and interactions

`/cases/:id/phones` lists phones as rows: label, owner label, device, report form and version, ingest
state, the three headline counts (messages, calls, locations) and a completeness word: `Complete`,
`Partly read`, `Still reading`, `Failed`. A row opens `/cases/:id/phones/:extractionId` with sections:

1. **Whose phone**: owner label, how established (`Read from the device information in the report`,
   `Worked out from messages the phone sent` with the records listed, or `Entered by hand at intake by
   <user> on <date>`).
2. **Device and report**: device fields; report file, form, version, producer, extraction type and period;
   SHA-256 of what was received; the report's own MD5 and whether it matched.
3. **What the production says it contains**: the selection flags verbatim with plain meaning ("The examiner
   chose which data to extract. Absence of a type may mean it was not chosen."), chosen types and ranges.
4. **Did it arrive whole**: reconciliation result; any truncated section; stated versus read.
5. **Files**: totals by category; verification counts, each a link to Media filtered to that state.
6. **Deleted and recovered**: table by type, each count a link to Conversations or Timeline filtered.
7. **What Loupe reads** (coverage map, plan 6.5): one row per record type with records and a state word
   (`Interpreted`, `Read generically`, `Held, not yet read`), expandable to fields. Each type links to its
   generic list (plan 6.4: "Every type gets a generic list and detail view").
8. **When there is data**: per signal type, first and last time and count (plan 11.2 rule 4), so "no data"
   is visible as a period.

Actions: `Copy profile as text`; `Export profile as PDF` (section 12, same renderer). Profile page for a
phone still ingesting shows progress from 01's job state and every count marked `(so far)`.

### 7.4 Acceptance tests (Extraction profile)

| Id | Test |
|---|---|
| P-1 | For a fixture extraction, every number on the page equals the corresponding count query over the contract views |
| P-2 | A split-section fixture with a truncated file index shows `Partly read` and the stated and read counts |
| P-3 | An owner entered by hand is labelled as such everywhere the owner label appears (unit over `ParticipantLabel`) |
| P-4 | Missing-file count links to Media with `verification=missing` and the list total equals the count |
| P-5 | The selection flags render verbatim plus the plain meaning; "not stated" when the attribute is absent |

---

## 8. Media

### 8.1 Purpose

See the pictures, video, audio and documents on each phone, by phone, app and kind; know for each file
whether it is intact and matches its hash, where it came from and which messages carried it; play voice
notes and video; and turn a voice note or a screenshot into searchable text on request, with the machine
output labelled and the original always beside it (plan 1.9).

### 8.2 Data

| Call | Request | Response |
|---|---|---|
| `POST /api/phones/media/index` | `MediaFilter` | envelope; `items: [{"day", "count"}]` by taken or message time in the zone, plus `no_time_count`, `by_category`, `by_app` |
| `POST /api/phones/media/window` | `{filter, snapshot, day, offset, limit<=500}` | `items: [MediaItem]` |
| `GET /api/phones/media/{file_uid}?case_id=` | | `MediaDetail` |
| `POST /api/phones/media/{file_uid}/derive` | `{"kind": "transcript | ocr", "case_id"}` | `202 {"job_id"}`; reuses the evidence-engine queue (plan 6.1) and local models (plan 1.8) |
| `GET /api/phones/media/{file_uid}/derived?case_id=` | | `[{"kind", "text", "model", "model_version", "created_at", "created_by", "segments": [...]}]` |

`MediaFilter`: `{case_id, phones, apps, categories, verification, deleted_states, carved, linked_to_message:
true|false|null, participants, from_instant, to_instant, include_no_time, sort}`.

`MediaItem`: `{file_uid, phone_label, category, filename, size, taken_or_sent: {instant, full,
basis: "exif_taken | message_time | file_time | none"}, verification, deleted_state, is_carved, app,
message_count, thumbnail_url or null, has_derived: ["transcript"]}`.

`MediaDetail` adds hashes (stated and computed), local path in the production, every linking message as a
`StreamRow`, all three link mechanisms with which one found it, EXIF fields as captured, and derived texts.

### 8.3 Interactions

- Grid (default) and list views, both virtualized; the grid sizes to the exact total like 3.1.
- Filter bar: phones, apps, categories (from the captured category, plan 5 lesson 9), state
  (verification, deleted, carved), linked to a message or not, participants (files carried by messages with
  them), dates.
- Open an item: right panel with the file (image, `<video>`, `<audio>` with seeking; PDF and text in
  `DocumentViewer`), hashes, state badges, linked messages (each opens Conversations at that message),
  `Open the record behind this`.
- `Read text in this image` / `Transcribe this audio`: starts a job; the panel shows `Reading text (local
  model)` then the text with the label `Machine-generated by <model> <version> on <date>. The original is
  above.` Derived text enters search (11.2) as its own kind, tagged machine-generated.
- Audio that the browser cannot play (container or codec) is transcoded on demand to a playable copy kept
  beside the original (plan 5 lesson 9); the player says `Playing a converted copy. The original file is
  unchanged.` Which formats the corpus holds is not yet measured (20.5).
- Selection and `Copy file list` (filename, phone, category, time, hashes, state, one per line);
  `Download originals` as a zip with a manifest of hashes.

### 8.4 Performance targets

| Operation | Target | Basis |
|---|---|---|
| Index, largest phone | 500 ms | 43,043 files in C3 locally; server max not measured for files, attachments max 40,241 |
| Window of 500 items | 300 ms | |
| Thumbnail, cached | 100 ms; first generation 1 s per image, generated in a background job after ingest so most are cached | |

### 8.5 Acceptance tests (Media)

| Id | Test |
|---|---|
| M-1 | A file linked only through the Attachment record's `attachment_extracted_path` (plan 3.4: chats/, contacts/, photos/) shows its message |
| M-2 | A file absent from the production renders the 3.6 sentence, is counted under `missing`, and is not shown as a broken image |
| M-3 | Derived text displays model and version and the original stays visible; search finds the derived text with the machine-generated tag |
| M-4 | Grid total equals the profile's file count for the same phone |

---

## 9. Case Timeline phone lens

### 9.1 Purpose

See phone activity on the same timeline as money and documents: what happened on each phone around a
payment, a filing or an interview date, with the phone's names, numbers and badges on every line, the
full result under filters, and one swim-lane view to compare phones, people or kinds of activity side
by side.

### 9.2 Why a lens and not more timeline nodes

The existing Timeline loads the whole case into the browser and stops at 200,000 events
(`use-timeline-data.ts:44-59`), dates and times are strings cut to minutes on the server
(`timeline_service.py` `SORT_TIME_CYPHER`, `substring(..., 0, 5)`) and interpreted in the browser's own
zone (`frontend_v2/src/features/timeline/lib/timeline-utils.ts:56-66`), times show as 24-hour `HH:MM`
(`timeline-utils.ts:50-54`), and dateless events are dropped (2). A phone case holds up to 881,646
timestamp-bearing records. So phone entries are not written as Neo4j timeline nodes; they are read from
`pv_timeline_entry` through the windowed API and merged into the existing stream day by day. Existing
non-phone events keep their current path unchanged.

### 9.3 Data

| Call | Request | Response |
|---|---|---|
| `POST /api/phones/timeline/index` | `TimelineLensFilter` | envelope, `items: [{"day", "count", "by_lane": {"lane_key": count}}]`, `no_time_count`, `lanes: [{"key", "label", "count"}]` |
| `POST /api/phones/timeline/window` | `{filter, snapshot, day, offset, limit<=1000}` | `items: [TimelineLensRow]` |

`TimelineLensFilter` = `StreamFilter` plus `{"model_types": [], "activity_classes": ["interaction",
"device_state", "passive", "unknown"], "lane_by": "phone | person | activity_class | kind"}`.
`TimelineLensRow` = `{entry_uid, record_uid, phone, model_type, field_path, field_meaning, time, summary,
participants: [ParticipantLabel], flags, activity_class, lane_key, comm: StreamRow or null}`; for
communications `comm` carries the full row so the lens shows the same text as Conversations.

### 9.4 Merge with existing events

The page keeps its current data hook for case events (`use-timeline-data.ts`). When the lens is on, the
day list is the union of the existing events' days (computed in the browser, as today) and the lens
index's days; each day's rows are the existing events of that day (in memory) followed by the lens rows of
that day fetched by window, merged by instant. Existing events without a time sort by their date at the
end of the day, labelled `No time` as today. The header total is `case events + phone entries` with each
part stated: "2,140 case events and 48,912 phone entries".

The lens's own dateless rows form the final "No time recorded" group (3.1 rule 5). The existing
Timeline's dateless events, dropped today, are a defect fixed in 15.6.

### 9.5 Controls

Added to `frontend_v2/src/features/timeline/components/TimelineToolbar.tsx` and `FilterSidebar.tsx`:

- `Phones` lens toggle and phone picker (default: off, so a case's existing Timeline is unchanged until
  someone turns phones on; when the case has phones the toggle shows their count).
- Lens filters: phones, participants (with `between`), kinds of record (record types grouped as
  Messages and calls, Locations, Device activity, Web and searches, Apps, Accounts, Other), activity class
  (plan 11.2), state badges, text.
- Zone selector and names toggle (3.2, 3.3) apply to phone rows; existing events keep their current
  display, and the zone selector applies to them only once 15.6 lands.
- `Full load`: under any lens filter whose total is at most `FULL_LOAD_ROWS`, every row is fetched
  immediately (3.1 rule 4), which is the recorded request "when filters are at play, the timeline should
  load in full" (plan 10.2). Above that, windows load as they come into view with the exact total shown;
  never a "Load more" control.

### 9.6 The single swim-lane mode

v1 had two swim-lane components (`CellebriteTimelineSwimLane.jsx` and `comms/CommsCrossTypeSwimLane.jsx`
on `origin/main`) and fixed copy-paste twice (plan 10.5). Loupe has one: `TimelineLanes.tsx` in
`src/features/timeline/components/`, opened by a `Stream / Lanes` switch.

- Lanes are chosen by `lane_by`: one lane per phone (default), per person (from the participant filter,
  up to the people selected), per activity class, or per kind of record. Case events form their own lane
  `Case events` (money, documents, notes) always present when the case has any.
- The horizontal axis is time in the selected zone; the visible span is chosen with zoom (day, week,
  month, all) and pan; the vertical axis is lanes. Each lane shows counts per time bucket from the index
  (`by_lane` per day, or per hour when the span is two days or less, from
  `POST /api/phones/timeline/buckets` `{filter, snapshot, from, to, bucket: "hour" | "day"}` returning
  `{lanes: [{key, buckets: [{start, count}]}]}`).
- Clicking a bucket shows its rows in the stream below the lanes, using `StreamList`, so copy, record view,
  badges and names behave identically in both modes.
- Lanes show where a phone has no data as a hatched band labelled `No data` using `data_periods` from the
  profile (plan 11.2 rule 4), distinct from `No matching entries`.

### 9.7 Acceptance tests (Timeline lens)

| Id | Test |
|---|---|
| T-1 | With the lens on and a filter of two participants, the total equals the Conversations total for the same filter and kinds (A3) |
| T-2 | A filter with 4,000 matching rows loads all 4,000 without scrolling (network log shows the windows; DOM shows no load-more) |
| T-3 | Lens rows show day header and 12-hour time with zone; the original popover shows the report text |
| T-4 | Lanes mode and stream mode copy the same text for the same selected entries |
| T-5 | Turning the lens off restores the existing Timeline unchanged (snapshot of the existing page) |
| T-6 | A phone with no data in a period shows `No data` in its lane for that period, distinct from zero matches |

---

## 10. People with a per-phone lens

### 10.1 Purpose

One place to see who a person is across phones and money: every number and account they use, how each
phone names them, how much each phone was in contact with them and when, and which bank counterparties they
are linked to, with every link reviewed by a person and reversible. It replaces v1's Unified Contacts,
shared-contacts panel, Overview contacts and graph people (plan 10.5).

### 10.2 Where it lives

The existing Dossiers page (`/cases/:id/dossiers`) is Loupe's people surface: a dossier has
`canonical_entity_key`, `contacts` with `kind: "phone" | "email" | "address"` and links
(`frontend_v2/src/features/dossiers/api.ts:75-117`). Two additions:

1. **`Phone identities` tab** on `DossiersPage.tsx`: the identity registry (plan 13, identity
   consolidation). One row per identity (`pv_identity`): identifier, kind, each phone's name for it
   (`C3: Maria L; C7: Mom`), events per phone, first and last contact, linked person (dossier) or
   `Not linked`.
2. **`On the phones` panel** in `DossierDetailSheet.tsx`: for the dossier's linked identities, per phone:
   the names that phone holds, when the contact was created and changed (`Contact.TimeCreated`,
   `TimeModified`, measured present on 4,996 and 979 records), message, call and email counts in each
   direction, first and last contact, and `Open conversations` (Conversations People mode for this person,
   filtered to that phone).

### 10.3 Linking identities to people

- **Suggestions** with stated reasons (plan 13): same normalised number; same app account id; same email;
  a phone contact name equal after folding (11.3) to a dossier name *and* a shared number. Each suggestion
  lists its reasons and the records behind each. Names alone never produce a suggestion (names collide;
  `feedback_cellebrite_number_alongside_name.md`).
- **Decisions** go through a decision log with a named actor, both states kept (plan 6.6;
  `backend/services/financial/decisions.py:252-262` is the pattern: the event is written before the state
  changes). Actions: `Link to this person`, `Not the same person` (stored so the suggestion does not
  return), `Unlink`, `Split` (move identities out of a person). Every action is reversible from the
  history list on the dossier.
- **Bank counterparties**: suggestions to link a phone identity to a financial counterparty come only
  through the reviewed identity path (`backend/services/financial/account_identity.py`,
  `identity_graph.py`; plan 6.6), are shown on the dossier as `Suggested, not reviewed` until a person
  confirms, and never alter ledger rows. Money mentioned in messages stays narrative (plan 6.6, 12.1 rule 5).
- **Proof class is computed** (CLAUDE.md design rules): a person can link identities; no person can raise
  how strongly something is proven.

### 10.4 Data

| Call | Purpose |
|---|---|
| `GET /api/phones/identities?case_id&q&phone&linked=true|false&cursor&limit` | registry list; complete counts; `total` exact |
| `GET /api/phones/identities/{identity_key}?case_id` | detail: names per phone with records, counts per phone and direction, first/last, suggestions |
| `GET /api/phones/people/{dossier_id}/phones?case_id` | the dossier panel |
| `GET /api/phones/identity-suggestions?case_id&status=open` | suggestions with reasons |
| `POST /api/phones/identity-decisions` | `{case_id, decision: "link" | "reject" | "unlink" | "split", identity_keys: [], dossier_id, reason}`; returns the decision row; 409 if the state changed since the client read it |

### 10.5 Acceptance tests (People)

| Id | Test |
|---|---|
| U-1 | An identity named differently on two phones shows both names, each with its phone label, and never a single merged name in phone view |
| U-2 | Linking then unlinking leaves counts, names and Conversations results as before, and both decisions appear in history with the actor |
| U-3 | A suggestion is never produced from a name match alone |
| U-4 | Message counts in the dossier panel equal Conversations totals for the same person and phone (A3) |

---

## 11. Loupe-wide Search

### 11.1 Purpose

Find any word, name, number or account across everything in the case (phone messages, emails, contact
names, other phone records, documents and transcripts) typed the way a person types it, with every match
counted and reachable, and the results usable by the AI chat with citations to the exact record.

There is no global search today. The Cmd/Ctrl+K shortcut dispatches `owl:toggle-command-palette`
(`frontend_v2/src/hooks/use-global-shortcuts.ts:18-24`) and nothing listens for it (the only
`commandPaletteOpen` uses are store fields in `src/stores/app.store.ts:5,13,20` and `src/stores/ui.store.ts`);
document text search is a `LIKE` over lowercased content
(`backend/services/evidence_text_search_service.py:166`) that does not fold decorative letters and cannot
see phone records.

### 11.2 Coverage

| Group | Source | Hit opens |
|---|---|---|
| Messages, calls and emails | `pv_text` for comm event fields joined to `pv_comm_event` | Conversations at that event |
| People and identifiers | `pv_identity`, `pv_identity_name`, dossier names | People |
| Other phone records | `pv_text` for any other type (notes, searches, visited pages, calendar, accounts ...) | record panel; Timeline lens if timed |
| Documents and transcripts | existing `evidence_document_texts` (`backend/postgres/models/evidence.py:204-226`) | `DocumentViewer` at the page |
| Machine-generated text from media | derived texts (8.2) | Media item |

Financial ledger search is not in this unit (19, D-14).

### 11.3 Matching

- **Default:** case-insensitive substring match after folding both the query and the text. Folding:
  1. Unicode NFKC (maps mathematical, fullwidth, circled, superscript and similar styled letters to plain
     letters: the measured complaint in plan 10.2).
  2. A supplementary table for styled letters NFKC leaves alone, kept in `services/phone/fold.py` with a
     test per range: negative circled and negative squared Latin capitals (U+1F150 to U+1F169, U+1F170 to
     U+1F189), regional indicator letters (U+1F1E6 to U+1F1FF), small capitals (for example U+1D00 ᴀ,
     U+0299 ʙ), and others found by the corpus measurement in 20.6.
  3. Remove zero-width and variation selectors (U+200B to U+200D, U+FE0E, U+FE0F) and combining marks
     after NFD, so `Jose` finds `José`.
  4. Case fold (`str.casefold()`); collapse whitespace.
  5. Phone numbers: a query that is mostly digits also matches identities whose digits contain it, so
     `2025550143` finds `+1 (202) 555-0143`.
- **`Exact characters`** toggle turns all folding off except case.
- No typo-tolerant or fuzzy matching by default; a fuzzy match is not what a person typed.
- The same `fold()` runs at ingest (02 fills `value_folded`) and at query; a mirror in
  `frontend_v2/src/features/search/lib/fold.ts` highlights matches in the browser, and both are tested
  against one shared fixture file `backend/tests/fixtures/fold_cases.json` read by both suites.
- Existing documents: a migration adds `content_folded` to `evidence_document_texts` (filled by a
  backfill job using the same `fold()`), with a trigram index like the existing one
  (`20260721_add_evidence_document_texts.py:52-54`); highlight offsets map back to the original text
  through a stored offset map so the citation points at the original characters.

### 11.4 Results

`GET /api/search?case_id&q&exact=false&groups=messages,people,records,documents,media&phones=&from=&to=`
returns:

```json
{
  "query": "string", "folded_query": "string", "complete": true,
  "groups": [
    {"group": "messages", "total": 1874, "items": [SearchHit], "next_cursor": "..."}
  ]
}
```

`SearchHit` = `{kind, title, snippet: {before, match, after} from the original text, phone_label, time,
participants: [ParticipantLabel], record_uid or evidence_file_id, open: {screen, params}}`. Each group
returns its exact total and the first 20 hits; `GET /api/search/group?case_id&q&group&cursor&limit<=200`
pages the rest, sorted by time (messages, records) or relevance-free name order (people, documents) so the
order is reproducible. `Show all 1,874 in Conversations` opens Conversations with the text filter, which is
the full stream with 3.1 guarantees.

UI: a command dialog (the existing `cmdk` wrapper `frontend_v2/src/components/ui/command.tsx`) opened by
Cmd/Ctrl+K and a search box in the case header, rendering grouped results with totals; `Enter` opens the
best group in its screen. Component: `src/features/search/components/SearchDialog.tsx`, mounted in
`src/app/layouts/CaseLayout.tsx` and listening for `owl:toggle-command-palette`.

### 11.5 AI chat and agent citations to records

- New link scheme `rec://<record_uid>` (and `rec://<record_uid>#<field_path>`), parsed in
  `frontend_v2/src/components/ui/markdown.tsx` beside `doc://` (`markdown.tsx:5-25,66-78`) and in
  `src/lib/summary-sources.ts:20`, opening the record panel.
- Phone passages given to the chat carry `[C3 WhatsApp message, Tue, Mar 14, 2023, 3:07 PM EDT,
  rec://...]` headers, so the model cites a record, not a page.
- The chat prompt line that tells the model to "use page 1" when no page is known
  (`backend/services/llm_service.py:503`) is changed: cite `rec://` for phone records; cite `doc://file/N`
  only with a known page; otherwise cite `doc://file` with no page, which opens the document at its start
  and shows "No page was given for this citation."
- Workspace AI citations (`frontend_v2/src/features/workspace-ai/api.ts:19-29`, `source_anchor`) gain
  `{"record_uid"}` anchors; `WorkspaceAIPanel.tsx:73-110,150-171` opens the record panel when the anchor is
  a record and `DocumentViewer` otherwise.

### 11.6 Performance targets

| Operation | Target | Basis |
|---|---|---|
| Grouped first page with exact totals, largest case | 1.5 s p95 | 263,077 message bodies plus other strings in the 10-report case; trigram GIN on folded text |
| Group page of 200 | 400 ms | |
| Queries under 3 characters | no trigram; exact identifier lookup only; the dialog says "Type at least 3 letters to search text." | trigram index cannot serve shorter strings efficiently |

### 11.7 Acceptance tests (Search)

| Id | Test |
|---|---|
| S-1 | A display name written in mathematical script letters is found by typing it in plain letters (the plan 10.2 case), in messages, contact names and identity names |
| S-2 | Each supplementary fold range has a passing test; `Exact characters` turns folding off |
| S-3 | `2025550143` finds an identity stored as `+1 (202) 555-0143` |
| S-4 | Group total equals the number of hits reachable by paging the group, and equals the Conversations total for the same text filter |
| S-5 | Highlights fall on the original characters in the snippet, including after folding changed the string length |
| S-6 | A chat answer citing a phone message renders a link that opens the record panel; a citation with no page never shows "p.1" |
| S-7 | Agent answers open documents and records from their links (15.5) |

---

## 12. Export: PDF and RSMF

### 12.1 Purpose

Hand counsel or a colleague exactly what is on screen: a filtered conversation, a pair of people over a
period, or a timeline, with every message complete, dates as shown on screen, every character drawn, the
names and numbers, the badges, and enough reference to find every line again in Loupe or in the original
report. RSMF puts the same conversation into counsel's review platform without slicing it by day.

The recorded failure (plan 10.2) was: message text cut, a date shifted by a day, decorative letters printed
as boxes. Loupe's own Timeline PDF today names system fonts only
(`backend/services/timeline_view_service.py:780`), the backend image installs no fonts
(`backend/Dockerfile:1-12`), and it silently caps linked entities at 12 and notebook notes at 4 per event
(`timeline_view_service.py:712,718`).

### 12.2 Jobs and endpoints

Exports run as jobs so size never forces a cap.

| Method and path | Request | Response |
|---|---|---|
| `POST /api/phones/exports` | `{"case_id", "format": "pdf | rsmf", "source": "stream | timeline_lens", "filter": StreamFilter or TimelineLensFilter, "options": ExportOptions}` | `202 {"export_id"}` |
| `GET /api/phones/exports/{export_id}?case_id` | | `{"state": "queued | rendering | done | failed", "progress": 0..1, "counts": {...}, "file": {"filename", "size", "sha256"} or null, "error": string or null}` |
| `GET /api/phones/exports/{export_id}/file?case_id` | | the file, `Content-Disposition` as the timeline export builds it (`backend/routers/timeline.py:302-306`) |
| `GET /api/phones/exports?case_id` | | export history for the case |

`ExportOptions`: `{"title", "include_attachments": "thumbnails | list | none", "include_record_ids": true,
"include_sensitive": false, "collapse_copies": true, "page_size": "letter | a4", "zone": {...}, "names": {...}}`.

Table `phone_exports`: `export_id uuid pk, case_id uuid not null fk, created_by uuid not null fk users,
created_at timestamptz, format text, source text, filter jsonb, options jsonb, snapshot text, state text,
progress real, counts jsonb, filename text, size bigint, sha256 text, storage_path text, error text`. The
filter and snapshot are stored so an export can be reproduced and its content explained. Queue: the
evidence-engine arq pattern (plan 6.1).

### 12.3 PDF content

1. Cover: case name, title, generated by and when, Loupe build, export id, SHA-256 of the file in the export
   history (computed after render, so it is listed in Loupe rather than printed in the PDF itself).
2. **What this export contains**, in plain words: phones, participants, apps, kinds, dates and zone, names
   mode, whether repeated copies are collapsed and how many, sensitive fields included or not, and totals
   (3.1 rule 6). Any limit (an incomplete phone) is stated here.
3. Body: grouped by day (day header as 3.2 with zone), each event as on screen: time with seconds, phone,
   app, `Name (number) -> Name (number)`, full body, attachments (thumbnails or list), badges as words,
   `Found 3 times` with the sources, and the record id in small type (`Record C3-1234567`).
4. Appendix: participants (every identifier and each phone's name for it); and **Characters that could
   not be drawn** if any (below).

Rendering: WeasyPrint (`backend/requirements.txt:123`, `weasyprint==68.1`), from HTML built by
`services/phone/exports/pdf.py`, using `time_display.py` for every time so the PDF shows the same text as the
screen for the same instant and zone. No text is cut: bodies wrap and break across pages (CSS
`overflow-wrap: anywhere`, no `max-height`, no `text-overflow`). The 155,838-character value is the size
test.

**Fonts.** Bundled under `backend/assets/fonts/` with their licences (all SIL OFL): Noto Sans, Noto Sans
Math (mathematical alphanumeric letters), Noto Sans Symbols and Symbols 2, Noto Emoji (monochrome; color
emoji support in WeasyPrint is not established, 20.7), and the Noto Sans scripts the corpus measurement
finds (20.6), declared with `@font-face` and one `font-family` fallback chain. Before rendering, the job
collects every code point in the export and checks each against the bundled fonts' character maps
(`fontTools`, a WeasyPrint dependency); any code point no font covers is rendered as a visible
`[U+1F9FF]` token instead of a box, and listed with counts in the appendix "Characters that could not be
drawn", so nothing is lost silently.

### 12.4 RSMF

Relativity Short Message Format: one `.rsmf` file per conversation (a thread, or a person or pair stream)
for the full filtered period, never one per day (plan 13). Built by `services/phone/exports/rsmf.py`
from the same `query_comm_events` rows: participants with display name and identifiers (phone view or case
view names as chosen), conversations with platform (`app`) and type (direct or group), events with
timestamps in UTC, direction, body, attachments with their files, deleted flag, and custom fields carrying
phone label, record id and badges. A manifest lists every file with SHA-256. The exact field names and
the container layout follow Relativity's published RSMF specification, which must be read and cited
before build (20.8). The export validates its own output against that specification's validator if one is
available, else against a JSON schema written from the specification.

### 12.5 Acceptance tests (Export)

| Id | Test |
|---|---|
| E-1 | A message of 155,838 characters appears complete in the PDF text layer (extracted with `pypdf`, which the suite already has transitively) |
| E-2 | A message at 11:30 PM Eastern on a date appears under that date in the PDF, identical to the on-screen day header and time string for the same zone (the shifted-day failure) |
| E-3 | Mathematical script, fullwidth, circled and emoji characters render with glyphs from bundled fonts; an unassigned or uncovered code point appears as a `[U+...]` token and in the appendix |
| E-4 | PDF event count equals the export's stated total equals the on-screen total for the same filter |
| E-5 | Sensitive values are absent unless the option is set, and the cover says which |
| E-6 | RSMF for a 3-day conversation is one file, not three; every event and attachment present; validates against the schema |
| E-7 | No list in the PDF is cut (no entity, participant or note cap) |

---

## 13. Case Map phone layer

### 13.1 Purpose

See where each phone reported being, with how uncertain each position is, what kind of source produced it,
whether it was recovered by carving or may come from another device, and the time; filter by phone,
person, period and source; open the record behind any point. The pattern-of-life views drawn on this layer
(places over time, trajectories and playback, together and apart) are spec 04.

### 13.2 Data

Existing map data comes from `GET /api/graph/locations` (`backend/routers/graph.py:659-690`), which returns
every geocoded entity in the case with no limit, called from
`frontend_v2/src/features/map/hooks/use-map-data.ts:146-147`. Phone points (up to 45,547 per case in
Location records, plus coordinates nested in other records) do not go through it; they are read from
`pv_location_point`:

| Call | Request | Response |
|---|---|---|
| `POST /api/phones/map/points` | `{"case_id", "bbox": [w, s, e, n], "zoom", "filter": {phones, participants, source_kinds, affiliations, carved, from_instant, to_instant, include_no_time}}` | envelope; `items` either `Point` (when the viewport holds at most `MAP_POINTS_MAX = 5,000`) or `Cluster` `{lat, lon, count, bbox}` with exact counts; `limits` states clustering |
| `POST /api/phones/map/summary` | same filter, no bbox | `{"total", "positioned", "not_positionable": [{"reason", "count"}], "by_source": {...}, "bbox"}` |

`Point`: `{point_uid, record_uid, phone_label, lat, lon, accuracy_m, accuracy_basis, source_kind,
affiliation, instant, time: {...}, model_type, flags}`.

`not_positionable` names what cannot be drawn and why: `Cell tower records without a position (902 across 5
phones: the production gives tower identifiers only, plan 11.1)`, `No coordinates`. Cell and WiFi positions
come only from offline reference data when loaded (plan 1.8); until then they are counted here, never sent
to a lookup service.

### 13.3 Display and interactions

- A `Phones` layer toggle in `MapToolbar.tsx`, with per-phone colour and a legend listing phone labels and
  owners.
- Each point is drawn with its uncertainty: a circle of radius `accuracy_m` when known; a point with a
  dashed outline and the label `Accuracy not recorded` when not (51,056 of 63,784 Location records have no
  `GpsHorizontalAccuracy`; whether `Precision` gives a usable radius is 02's mapping).
- Popup: phone, time (3.2), source kind, accuracy, affiliation badge (`May come from another device`),
  carved badge, `Open the record behind this`, `Show on Timeline`.
- Filters: phones, people (points from records involving them), source kinds, affiliation, carved, dates.
- The summary bar always shows `Showing 1,204 of 1,260 positioned records. 56 cannot be placed (why).`
- 5,000 is chosen because MapLibre renders that many individual circle features interactively on the
  hardware Loupe targets, and clustering above it keeps the counts exact; *reverse if* measured rendering
  on Owl's machines says otherwise.

### 13.4 Acceptance tests (Map)

| Id | Test |
|---|---|
| G-1 | A viewport with 12,431 points returns clusters whose counts sum to 12,431 and a `limits` entry; the UI shows the 3.8 limited sentence |
| G-2 | A point without accuracy is drawn with the dashed style and its label; a point with accuracy draws the radius |
| G-3 | Cell tower records without a position are counted under `not_positionable` and never sent to any network service (backend test asserts no outbound HTTP during the request) |
| G-4 | Turning the phone layer on does not change `/api/graph/locations` results (phone points are not graph locations) |

---

## 14. Case Graph communication edges

### 14.1 Purpose

See who was in contact with whom across all phones, and how that sits beside the money: one link per pair
with its counts and sums ("14 calls, 230 messages, $8,400 in 6 payments", plan 13), sliceable by time,
each link opening to the records behind it.

### 14.2 Projection policy

Individual messages and calls are not graph nodes (377,648 messages). The graph receives, per case:

- one node per identity that took part in at least one communication event (owners included), labelled in
  case-name mode with the phone names on hover; identities that appear only in contact books stay in
  People, so contact lists (up to 13,053 on one phone) do not flood the canvas;
- one `COMMUNICATED` relationship per unordered identity pair with properties `messages_ab`, `messages_ba`,
  `calls_ab`, `calls_ba`, `emails_ab`, `emails_ba`, `first_instant`, `last_instant`, `phones` (labels whose
  records support it), rebuilt from Postgres (plan 1.6);
- `person_id` on identity nodes linked to dossiers, so a person's identities can be shown collapsed into the
  person when the case-name toggle is on.

Money edges come from the existing financial flows; the combined edge label is computed by the graph
endpoint, not stored.

The number of communicating identities per case is not measured (20.9); the graph endpoint fix in 15.3
applies regardless.

### 14.3 Interactions

- Edge click: side panel with counts by kind and direction, first and last contact, by phone, and the money
  summary; `Open these messages` opens Conversations People mode for the pair (`between`), so the counts
  match (A3); `Open these payments` opens the ledger filtered to the linked counterparties.
- Time slider: recomputes edge counts for a window through
  `POST /api/phones/graph/edges {case_id, from_instant, to_instant, identity_keys?}` returning
  `{edges: [{a, b, counts..., first, last}]}`; the canvas restyles without reloading nodes.
- Carried from v1 (16): flow view with arrows and thickness by volume and direction, trace path between
  two people, drill (re-anchor on a person), expand neighbours, edge detail never empty.

### 14.4 Acceptance tests (Graph)

| Id | Test |
|---|---|
| R-1 | Edge counts equal Conversations totals for the pair with `between` (A3) |
| R-2 | Deleting one of two phones that share an identity leaves the identity and the other phone's edges (plan 7 phase 4 done-when) |
| R-3 | A time-sliced edge count equals the Conversations total for the pair in that window |

---

## 15. Loupe defects that must be fixed first

Each item: what is wrong (verified), why these screens depend on it, and the fix scope needed here.

### 15.1 Reports page has no backend

`frontend_v2/src/features/reports/hooks/use-reports.ts:26,35,49` calls `/api/reports`; no router in
`backend/main.py:202-251` serves it. **Scope here:** phone exports do not use the Reports page; their
history is listed in the export dialog and on the Extraction profile (12.2). The Reports page itself is
not fixed in this work; the sidebar entry (`sidebar.tsx:79`) is left as is. *Reverse if* Neil wants
exports listed under Reports: then the Reports page reads `GET /api/phones/exports` and becomes a list of
export jobs.

### 15.2 No global search

11.1. **Scope:** section 11 in full, including folding of existing document text (11.3) and mounting the
dialog on the existing Cmd/Ctrl+K event.

### 15.3 Map and Graph load the whole case uncapped

`GET /api/graph` takes `limit: Optional[int] = None` (`backend/routers/graph.py:402`) and the Graph page's
call sets it only when the caller passes one (`frontend_v2/src/features/graph/api.ts:103-118`);
`GET /api/graph/locations` has no limit (`graph.py:659-690`). **Scope:** (a) phone data never enters these
two paths except as the aggregated identities and edges of 14.2 (test G-4); (b) `GET /api/graph` returns
`total_nodes`, `returned_nodes`, `truncated` and the Graph page states the limit with the 3.8 sentence
when a limit applies; (c) the default for a case containing phones is the top 2,000 nodes by degree with
that sentence, *reverse if* measured node counts (20.9) fit unlimited.

### 15.4 Chat tells the model to cite page 1

`backend/services/llm_service.py:503`. **Scope:** 11.5.

### 15.5 Agent answers' links do nothing

`frontend_v2/src/features/agent/components/AgentPage.tsx:1236-1239` and `:2453-2456` render `Markdown`
without `onOpenDocument`, so `doc://` links fall through to a plain `<a target="_blank">`
(`frontend_v2/src/components/ui/markdown.tsx:66-90`). **Scope:** pass `onOpenDocument` and the new
`onOpenRecord` in both places, with a `DocumentViewer` and `RecordPanel` mounted in `AgentPage`; test S-7.

### 15.6 Timeline drops and misreads time

Dateless events are dropped (`timeline_service.py:115`; `use-timeline-data.ts:113-118`); time is cut to
minutes and shown as 24-hour text (`timeline-utils.ts:50-54`); timestamps are interpreted in the browser's
zone (`timeline-utils.ts:56-66`). **Scope here:** the phone lens does not depend on these (it has its own
rows), but the lens and existing events share one page, so: (a) existing events display through
`evidence-time.ts` (day, 12-hour, zone) when the event carries a full instant, and keep their current text
with `Time as entered` when it carries only a date and `HH:MM`; (b) dateless existing events are listed in
the "No time recorded" group instead of being dropped. Changing how existing events store time is out of
scope.

### 15.7 Silent caps in the Timeline PDF

`timeline_view_service.py:712` (`connections[:12]`) and `:718` (`notebook_notes[:4]`). **Scope:** the
phone PDF (12) has no caps; the two lines are changed to list all items, since a combined export can
include case events (test E-7).

### 15.8 Query panel and `/api/query`

Recorded in plan 10.6. **Scope:** none of these screens may call `/api/query`; Search is a new read-only,
case-scoped endpoint (11.4).

---

## 16. v1 to Loupe screen mapping

Source: the v1 frontend on `origin/main`, `frontend/src/components/cellebrite/**` (28,660 lines), read
through a verified copy (the scratchpad copy of `CellebriteView.jsx`, `CellebriteCommsCenter.jsx` and
`utils/cellebritePdfExport.js` are byte-identical to `git show origin/main:`). All paths in this section
are relative to `origin/main`. v1 has 11 tabs (`frontend/src/components/cellebrite/CellebriteView.jsx:26-51`);
the default is Overview (`:63`).

### 16.1 Screen to screen

| v1 tab | Loupe home (plan 10.5) |
|---|---|
| Overview | Extraction profile (7); drill tables become Conversations filters (6) |
| Report | Extraction profile (7) and Export (12) |
| Search & Discovery | Loupe-wide Search (11) |
| Comms Center | Conversations (6) |
| Contacts (unified) | People, Phone identities tab (10) |
| Locations | Case Map phone layer (13); playback and trajectories in spec 04 |
| Location & Events | Timeline phone lens (9) for the list and table; Map (13) for the map; intersections become Together in spec 04 |
| Files | Media (8) |
| Cross-Phone Graph | Case Graph communication edges (14) |
| Timeline | Timeline phone lens (9) |
| Communications | Conversations People mode (6.2) and People (10) |

### 16.2 Capabilities carried over

| v1 capability (origin/main) | Loupe | Change |
|---|---|---|
| Phone selector with All, Solo, saved per case (`shared/PhoneSelector.jsx:20,63,130,166`) | `PhonePicker` on every phone screen | also on Search, Graph and Export, which lacked it in v1; selection lives in the URL (shareable) rather than localStorage |
| Number always beside name, "(unnamed)" for bare numbers (`shared/PersonName.jsx:37,56-67`) | `ParticipantLabel` (3.3) | number grouped for reading, captured value on hover; owner label; arrow form from plan 10.2 |
| Per-device "saved as" names as alias chips, max 8 then "+N" (`shared/AliasChips.jsx:18,21`) | names toggle and case-name hover (3.3); People per-phone names (10) | phone's own name is the default label rather than a chip beside a global name; no cap on names listed |
| Time zone selector Device / UTC saved per case (`shared/cellebriteTime.js:21-25`, `shared/CellebriteTimezone.jsx:23,47,87`) | `ZoneSelector` (3.2) | Device zone is read from the extraction, not the constant `America/New_York` (`cellebriteTime.js:22`); case zone added; 12-hour instead of `hourCycle: 'h23'` (`cellebriteTime.js:32`); weekday on every row's day and in every copy, not only day headers |
| Day-grouped list with weekday header (`CellebriteTimeline.jsx:1087-1097`) | `StreamList` day headers | header carries zone and offset (v1 checklist `tl-tz-offset`) |
| Newest/oldest sort saved per case (`CellebriteTimeline.jsx:100-115`) | 6.5, 9.5 | same |
| Envelope endpoints giving true totals (`CellebriteCommsCenter.jsx:510`; `CellebriteEventCenter.jsx:377`) | index call (3.1) | index also gives per-day counts that address windows, so totals and rows cannot disagree |
| Scrubber histogram with window (`shared/TimelineScrubber.jsx`, 2,000 buckets max at `:680`) | Lanes mode buckets (9.6) and the day index | bucket count is derived from the span, not capped |
| Thread list with thread dedup by report, app, type and participant subset (`CellebriteCommsCenter.jsx:549,1178`) | Conversations thread list (6.3) | complete in one call; no participant-subset folding (it merges distinct threads; 19, D-9) |
| Deep message search jumping to first match (`CellebriteCommsCenter.jsx:588`) | Conversations text filter + Search pivot (11.4) | every match counted and reachable, not the first 300 |
| Message bubble with From -> To, time, app, phone chip (`comms/CommsMessageBubble.jsx:145-160,220-229`) | stream row (6.6) | |
| Deleted badge when `deleted_state` is not intact (`comms/CommsMessageBubble.jsx:65-66,188-193`) | badges (3.5) | Deleted, In trash and Unknown are distinguished |
| Participants filter Split (From/To) or Any (`comms/CommsParticipantsFilter.jsx:198-228`) | participant filter any / all / between (4.3) | no 50-per-page paging in the picker; search-as-you-type over all identities |
| Type pills, apps popover, attachment toggle, date chips (`comms/CommsCompactToolbar.jsx:89-222`) | filter bar (6.4) | dates are instants in the chosen zone, not strings |
| Cross-type stream "List / Lanes" by cursor (`comms/CommsCrossTypeTimeline.jsx:59,115,250-373`) | Conversations People mode (6.2) and the single Lanes mode (9.6) | one lanes component instead of two |
| Timeline swim lane with "Apply as filter" and "Open in Comms" (`CellebriteTimelineSwimLane.jsx:365-383`) | Lanes mode (9.6): bucket click filters the stream; row menu opens Conversations | |
| Inline media, voice notes fetched only on play (v1 checklist `media-voice-inline`, `media-voice-preload`) | 6.6 | |
| Message dedup "+N sources" (v1 checklist `dedup-*`, `backend/services/testing_checklist.py:101-112`) | 3.4 | never across phones; total states records collapsed; `Show every copy` |
| Overview device cards, edit device name (`CellebriteOverview.jsx:138,168,198-210`) | Extraction profile (7.3) | label edit recorded with actor; detected name kept beside it |
| Delete a phone report (`CellebriteOverview.jsx:187,421`) | Extraction profile action, backed by 01/02's staged replace and membership delete | must not delete shared identities (plan 4.1, test R-2) |
| Reconciliation panel (`CellebriteOverview.jsx:276,541`) | Extraction profile section 4 (7.3) | element-level, not per-type |
| Merge identities dialog (`overview/MergeIdentitiesDialog.jsx:33,53`; `shared/rail/UnifiedContactAccordion.jsx:91-106`) | People decisions (10.3) | through a decision log with actor; reversible; split; suggestions with reasons |
| Unified contacts rollup by canonical number (`CellebriteUnifiedContacts.jsx:54-56,151-165`) | Phone identities tab (10.2) | no 1,000-row cap (`:56`); exact total |
| Contact frequency table and shared-contacts panel (`CellebriteCommunicationView.jsx:64,248-256,337-343`) | Phone identities tab columns and filter `On more than one phone` | |
| Report per-device summary (`CellebriteReport.jsx:30,147-153`) | Extraction profile, PDF of profile (7.3) | |
| Star callouts into the report PDF (`CellebriteTimeline.jsx:341-392`; `utils/cellebritePdfExport.js:337-341`) | `Add to Workspace` on every row (6.7) | the Workspace already holds pinned findings; a second starring system is not built |
| Discovery: one search across types, type toggles, open in native tab (`CellebriteDiscovery.jsx:104,147-174,228-238`) | Search (11) | no 10-per-type limit (`:84`); exact group totals; folding |
| Files tree by category, app, path (`CellebriteFilesExplorer.jsx:116`) | Media filters (8.3) | |
| Files filters: EXIF capture date, geotag (`CellebriteFilesExplorer.jsx:281-329`) | Media date filter on `taken_instant`; `Has position` filter | |
| File detail: tags, entity link, relevant, pin, download (`files/FileDetailPanel.jsx:128-218`) | Media detail: `Add to Workspace`, `Link to person` (via People), download original | tags and relevance belong to Evidence; not duplicated |
| Media analysis panel (`files/MediaAnalysisPanel.jsx:55,66`) | Media `Read text` / `Transcribe` (8.3) | local models by default (plan 1.8); v1 sent images to OpenAI by default (plan 4.8) |
| Cross-phone graph with edge-type chips, depth, capped badge (`CellebriteCrossPhoneGraph.jsx:89-113,239,840`) | Case Graph (14) | aggregated edges with counts and money |
| Trace path between two people, PathFlowPanel (`CellebriteCrossPhoneGraph.jsx:1690-1707`; `shared/PathFlowPanel.jsx:47-48,82-83`) | 14.3, on Loupe's existing `/api/graph/shortest-paths` (`frontend_v2/src/features/graph/api.ts:244`) | hop and per-hop limits stated on screen |
| Edge click shows messages both ways (`shared/rail/GraphEdgeAccordion.jsx:69-70,102`) | 14.3 `Open these messages` | full stream instead of 200 per direction, which v1 did not state |
| Timeline layout, expand neighbours, open in Timeline or Comms (`CellebriteCrossPhoneGraph.jsx:1813-1842,2413-2516`) | 14.3 | |
| Subgraph event stream (`shared/SubgraphEventStream.jsx:64,93`) | Conversations People mode with several participants (`any`) | no 300-event cap |
| Locations tiles vs raw points, canvas above 3,000 (`CellebriteLocations.jsx:615-619`; `events/EventMapPanel.jsx:468`) | Map points and clusters (13) | threshold 5,000 with exact cluster counts |
| Event detail with visitors within 150 m (`events/EventDetailDrawer.jsx:520`) | spec 04 (Together) | accuracy-aware, not a fixed radius |
| Related events within 24 h (`shared/rail/EventAccordion.jsx:73`) | `Show on Timeline` at the instant (6.7) | the timeline around the instant, not 30 items |
| Status bar Total / Displayed / Selected (`shared/CellebriteStatusBar.jsx:88`) | list header totals (3.1 rule 6) and selection count (3.7) | |
| `/` focuses search (`shared/CellebriteSearchInput.jsx:120-128`) | 3.9 | |
| Search operators `from:`, `to:`, `app:`, `before:`, `after:`, `near:` (`utils/cellebriteSearch.js:20-44`) | structured filters (6.4) | the operators are not carried as syntax; every operator has a filter control, and the URL carries the filter |

### 16.3 Capabilities dropped, with reason

| v1 capability | Reason |
|---|---|
| Separate Overview, Report, Communications and Discovery tabs | merged per plan 10.5; one date-filter fix had to be applied to five timeline hosts in v1 |
| Two swim-lane components (`CellebriteTimelineSwimLane.jsx`, `comms/CommsCrossTypeSwimLane.jsx`) | one Lanes mode (9.6); the two differed in data, arcs and loading |
| PerspectivePill breadcrumb of people frames (`shared/PerspectivePill.jsx:26,49,76-92`) | replaced by the participant filter in the URL and browser history; the breadcrumb was a second filter state that other tabs read through a context |
| NameActionMenu "Add to perspective" / "Replace perspective" (`shared/NameActionMenu.jsx:103,113`) | same reason; Drill, In Graph and Filter Comms survive as the participant menu (6.7) |
| Browse / Read mode (`CellebriteCommsCenter.jsx:134-147`) | one stream layout; the row shows full text, which is what Read mode added |
| Client-side search over loaded rows (`utils/cellebriteSearch.js:63,246,387`) | searched only what was loaded, so results depended on how far a person had scrolled; replaced by server search (11) |
| Media strip limited to 3 thumbnails (`comms/CommsMediaStrip.jsx:44`) | every attachment shown in its row |
| Cross-phone arcs in swim lanes (`utils/crossPhoneResolver.js`) | cross-phone message matching is plan 12 approach 2, which needs its corpus measurement first (plan 12.1 rule 1); arcs return with it |
| Add a user-authored node from the phone graph (`CellebriteCrossPhoneGraph.jsx:1778,2599`) | the Case Graph already has node creation (`frontend_v2/src/features/graph/api.ts:197`) |
| jsPDF report in the browser (`utils/cellebritePdfExport.js:134,163,369`) | built-in fonts only and date cut to 10 characters (`:69`), the recorded failure; replaced by the server PDF (12) |
| Hard limits listed by the inventory: thread view 500 with no load-more and an unqualified total (`comms/CommsThreadView.jsx:87,255`), Timeline 5,000 per type (`CellebriteTimeline.jsx:57`), Locations raw 500,000 (`CellebriteLocations.jsx:242`), graph edge rail 200 (`shared/rail/GraphEdgeAccordion.jsx:69-70`), tile rail 200 (`shared/rail/LocationTileAccordion.jsx:56`), subgraph stream 300 (`shared/SubgraphEventStream.jsx:93`) | replaced by 3.1; the last four were not stated to the user |
| `select-none` on event table rows (`events/EventsTable.jsx:280`) | copy and paste (3.7) |
| Dead components with no importer: `comms/CommsDeviceSelector.jsx`, `comms/CommsEntityFilter.jsx`, `comms/CommsContactDrawer.jsx`, `CellebritePhonesSection.jsx`; unused `cellebriteAPI.getTimeline` (`frontend/src/services/api.js:2789`) | not reachable in v1 |
| Unused normaliser `utils/normalizeText.js:3` (anyAscii) | folding is specified in 11.3 and runs on the server; anyAscii transliterates across scripts, which changes letters rather than styles |
| Intersection methods spatial, cell tower, WiFi, comm hub, convoy with sliders (`events/IntersectionPanel.jsx:5`; `events/IntersectionMethodCard.jsx:74`) | rebuilt as Together in spec 04 (plan 10.5), respecting accuracy; v1 compared cell tower with GPS at 250 m and capped silently at 20,000 (plan 4.7) |
| Playback bar speeds and keys (`locations/PlaybackBar.jsx:26,138-159`) | spec 04 |

---

## 17. Acceptance tests for the recorded feedback

Each item of plan 10.2 has at least one test that must pass before phase 5 is done (plan 7, phase 5:
"Alex's testing-hub items each have a passing test"). The v1 checklist items (`backend/services/testing_checklist.py`
on `origin/main`) that concern these screens are mapped below. The verdicts and filed items themselves,
read from `/home/conorbowles51/app_v2/data/testing-feedback.json` on the server on 2026-10-29 (titles only;
case names omitted), are listed in 17.0 so every one has a named test.

### 17.0 What was recorded in the v1 testing hub (2026-06-09 and 10)

Checklist verdicts (13 checklist items, one verdict on a filed item):

| Checklist id | Verdict | Theme | Test |
|---|---|---|---|
| `tl-device-local-name` | fail | phone's own names | A1 |
| `tl-time-hover` | fail ("only shows time. not the day"; 12-hour asked) | readable dates | A6, A7 |
| `tl-to-from-numbers` | partial ("[name] (#####) -> [name] (####)") | who to whom | A2 |
| `dedup-collapse` | fail | duplicates | A14 |
| `media-smooth-scroll` | fail ("scroll doesn't keep loading") | complete results | A5 |
| `nav-load-more-events` | fail (load more under filters) | complete results | A4 |
| `nav-load-more-comms-files` | fail | complete results | A4 |
| `tl-inline-body`, `media-voice-inline`, `tl-tz-offset`, `media-voice-preload`, `nav-virtualized-rows`, `nav-sort-toggle` | pass | carried over; regression tests in 17.2 | 17.2 |

Filed items (12):

| Kind | Title as filed | Test |
|---|---|---|
| bug | contacts in communications/timeline need to be shown from the perspective of the phone | A1 |
| bug | make all users/accounts searchable by text (decorative Unicode name not found by plain typing) | A8 |
| bug | Comms Timeline Window Needs to be Bigger | A15 |
| feature | Ability to Export Data to PDF (filtered conversation or timeline between people and dates) | A12 (with A9 to A11) |
| bug | cannot copy/paste in Comms Timeline | A13 |
| bug | Messages in Comms Timeline have duplicates | A14 |
| bug | Comms Timeline doesn't load all events; the scroll doesn't continue | A5 |
| bug | Comms timeline is not showing all comms already filtered (only one phone shown) | A3 |
| bug | Timeline PDF doesn't display message in full and dates are wrong; decorative letters print as squares | A9, A10, A11 |
| bug | Comms Center not displaying all calls (Timeline shows many, Comms Center one) | A3 |
| bug | Copy/Paste Not working in timeline view either | A13 |
| bug | unknown error when loading conversations after filtering for numbers or contacts | A16 |

If the A-ids above do not match the theme rows in 17.1 exactly, 17.1 governs and this table is corrected
to it during the screens build unit.

### 17.1 Plan 10.2 themes

| Id | Theme (plan 10.2) | Test | Layer |
|---|---|---|---|
| A1 | The phone's own view of the world | Fixture: one identity saved as name X on C3 and name Y on C7, plus a message of each phone involving it. In Conversations, Timeline lens, Search hits, Graph edge panel, People and the PDF, the C3 line shows X and the C7 line shows Y in phone view; in case view both show the dossier name with the per-phone names on hover; event ids, order and counts identical in both modes | backend + unit + browser |
| A2 | Who to whom, with name and number | For every row kind (message, call, email, voicemail, group activity) and every row of the 3.3 table, the rendered text and the copied text contain `<label> -> <label>` where each label has a name or the explicit no-name form and an identifier or the owner form. A row with an implicit owner side still shows both sides | unit over `ParticipantLabel`, `copy-rows`; backend over `labels.py` |
| A3 | Complete results when filtered: same count everywhere | Fixture with calls whose owner side is implicit (C-4) and duplicates: for the filter "participants X and owner, between, March", totals from Conversations index, Timeline lens index (kinds restricted to communications), Search group total for the participant's number restricted to comm events, Graph edge counts, People dossier panel and PDF stated total are equal | backend (one test calling every endpoint) |
| A4 | Complete results when filtered: no load more | 4,000-row filtered result: every row present after load without user scrolling; 200,000-row index: scrollbar sized to all rows and `End` reaches the last; DOM never contains a "Load more" control | browser (C-1, T-2) |
| A5 | Complete results when filtered: scroll that does not stop | A window request that fails returns an inline retry row and scrolling past it continues to load later windows; a 409 stale snapshot refreshes and keeps the focused event | browser (C-9) |
| A6 | Readable dates: day and 12-hour time | Fixture table `backend/tests/fixtures/time_cases.json` shared by `test_phone_time_display.py` and `evidence-time.test.ts` (T-time): instants around midnight, both daylight-saving changes in America/New_York, a non-US zone, UTC, no offset, no time. Expected strings for row, header and full forms; same strings on screen, in copy and in the PDF | backend + unit |
| A7 | Readable dates: zone shown, original on demand | Every day header names the zone and offset; the popover shows `pv_time.original_text` byte for byte | unit + browser |
| A8 | Search that matches what a person types | S-1 and S-2: a display name in mathematical bold script, fullwidth, circled, negative squared and small-capital letters is found by plain typing in messages, contact names and identities; accents fold; `Exact characters` turns folding off | backend + unit (shared fold fixture) |
| A9 | Faithful export: full text | E-1 (155,838 characters complete in the PDF text layer) and E-7 (no list caps) | backend |
| A10 | Faithful export: correct date | E-2 (11:30 PM Eastern lands on the same day as on screen) | backend |
| A11 | Faithful export: every character drawn | E-3 (bundled fonts; uncovered code points shown as tokens and listed) | backend |
| A12 | Faithful export: filtered conversation or timeline between two people and dates | Export of `between` two identities over a date range has exactly the on-screen events (E-4) and states the filter on its cover | backend |
| A13 | Basics: copy and paste in timelines | In Conversations, Timeline lens stream and Lanes mode, selecting 3 rows and pressing Ctrl/Cmd+C writes `text/plain` and `text/html` with day, 12-hour time, zone, phone, app, labels and full body; `Ctrl/Cmd+A` then copy covers the whole filtered total; native text selection works within visible rows | browser |
| A14 | Basics: duplicate messages | Three copies of one message from Native Messages, IMS Service and Android CallLog database on one phone show as one row `Found 3 times` listing the three sources; two different messages at the same second stay separate; the same message on two phones stays two rows; totals state records collapsed; `Show every copy` shows three rows | backend + unit |
| A15 | Reading space: the communications timeline uses the space it is given | At 1280x800 and 1920x1080, with the timeline panel expanded, the panel's scroll container fills the panel height with no unused band below it; resizing the panel resizes the list; row count visible grows with height | browser |
| A16 | Filtered loads never fail with an unexplained error | For every filter combination of participants by number, by contact, by identity and by dossier (including identities with no number and numbers with no contact), the Conversations index returns 200; a backend failure returns the 3.8 error wording with a retry and a reference id, never "unknown error" | backend (parametrised) + browser |

### 17.2 v1 checklist items mapped

| v1 item id (`testing_checklist.py`) | Loupe test |
|---|---|
| `tl-inline-body` | C-8 (full body in the row, expandable over 2,000 characters) |
| `tl-to-from-numbers`, `tl-comms-numbers` | A2 |
| `tl-device-local-name` | A1 |
| `tl-time-hover` | A7 (full form on hover and in the popover) |
| `tl-tz-offset` | A6, A7 (offset in header, daylight-saving day shows both) |
| `media-voice-inline`, `media-voice-preload` | unit: audio element has no `src` until play is pressed; browser: plays inline |
| `media-image-thumbs`, `media-image-lightbox` | unit: thumbnail rendered from `thumbnail_url`; click opens `DocumentViewer` |
| `media-smooth-scroll` | 6.8 scroll target measured in a browser test with 200 media rows |
| `nav-virtualized-rows` | browser: variable-height rows (long bodies, media) do not overlap after windows load |
| `nav-sort-toggle` | unit: sort persists per case and flips day groups and rows |
| `nav-jump-to-day` | browser: `g` + date scrolls to that day's header using the index |
| `nav-load-more-events`, `nav-load-more-comms-files` | replaced by A4 (no load-more exists) |
| `nav-keyset-fast` | backend: window query plan uses the day-bounded offset (4.7) |
| `nav-no-invalid-date` | C-3 and A6 (no time and no offset render words, never "Invalid Date") |
| `nav-empty-error-states` | unit: each 3.8 state renders its exact copy |
| `dedup-collapse`, `dedup-sources-chip`, `dedup-no-false-merge` | A14 |
| `flow-arrows`, `flow-particles`, `flow-legend`, `flow-direction-counts`, `flow-connection-unchanged` | R-1 plus unit: edge direction from `*_ab`/`*_ba` counts; default view unchanged |
| `edge-click-detail`, `edge-detail-not-empty` | R-1, R-3 |
| `flow-event-stream` | Conversations People mode with several participants (16.2) |
| `flow-time-layout`, `flow-trace-path`, `flow-drill` | 14.3 unit tests on the Graph page |
| `search-by-attribute`, `disc-address-search` | backend: a street address string in a Location record is found by Search (records group) |
| `search-subgraph`, `search-pull-onto-canvas`, `search-expand-neighbours`, `graphbug-*` | existing Graph page search; not changed by this spec beyond 15.3 |
| `search-pivot`, `disc-pivot-comms`, `disc-pivot-tabs`, `disc-show-in-graph` | S-4 plus unit: each `SearchHit.open` navigates to the screen with the filter in the URL |
| `disc-tab-exists`, `disc-search-all-types`, `disc-grouping`, `disc-type-filter`, `disc-phone-scope`, `disc-more-counts` | S-4 (groups with exact totals; phone scope filter) |
| `report-device-cards`, `report-export-pdf` | P-1 and profile PDF |
| `report-star-callout`, `report-callouts-in-pdf`, `report-visualization-slot` | dropped (16.3: Workspace instead) |
| `node-add`, `node-distinct-style`, `node-provenance`, `node-bool-serialization` | existing Graph node creation; not in scope |
| `reg-comms-type-filter`, `reg-comms-combined-filters` | backend: every combination of kinds, participants, apps and attachment flag narrows as the intersection of the single filters |
| `reg-events-playback` | spec 04 |

---

## 18. Build units

Each unit is finished, tested and committed before the next (CLAUDE.md, chunked work). Units 1 to 3 need
02's contract views over at least the C3 and C9 captures.

| # | Unit | Done when |
|---|---|---|
| 1 | Shared backend: `filters.py`, `time_display.py`, `labels.py`, `streams.py` index/window/locate, `records.py`, `/api/phones` router, case display settings migration | backend tests for 3.1 rules 2-6, A2, A6 and C-2 to C-5 pass |
| 2 | Shared frontend: `evidence-time.ts`, `schemas.ts`, `use-stream.ts`, `StreamList`, `ParticipantLabel`, `TimeCell`, `OriginalTimePopover`, `RecordPanel`, badges, `copy-rows.ts` | unit and browser tests A4, A5, A6, A7, A13 pass |
| 3 | Conversations screen, routes, sidebar change, removal of `features/cellebrite` and `/api/cellebrite` | C-1 to C-9, A1, A14 |
| 4 | Extraction profile | P-1 to P-5 |
| 5 | Search with fold, document folding backfill, dialog on Cmd/Ctrl+K, `rec://` citations, chat prompt fix (15.4), agent links (15.5) | S-1 to S-7, A8 |
| 6 | Timeline phone lens, Lanes mode, Timeline fixes 15.6 | T-1 to T-6, A3 for the lens |
| 7 | Export jobs: PDF, fonts, coverage check; Timeline PDF caps (15.7) | E-1 to E-5, E-7, A9 to A12 |
| 8 | People: Phone identities tab, dossier panel, suggestions, decisions | U-1 to U-4 |
| 9 | Media | M-1 to M-4 |
| 10 | Map phone layer | G-1 to G-4 |
| 11 | Graph edges and graph cap statement (15.3) | R-1 to R-3, A3 complete |
| 12 | RSMF (plan phase 6) | E-6, after 20.8 |

Units 1 to 8 belong to plan phase 5; 9 to 12 to phases 6 and 9 as the plan orders them. The corpus
measurements in 20.1 to 20.3 and 20.6 run before unit 1 and are recorded in this file.

---

## 19. Decisions made in this file

Each is a decision the plan did not already settle, with its reason and what reverses it.

| Id | Decision | Reason | Reverse if |
|---|---|---|---|
| D-1 | Lists load as an exact index (total, per-day counts, no-time count) then windows by (day, offset in day); no "Load more" anywhere | gives the full scrollbar and exact totals with bounded queries at 186,787 messages per phone; v1's keyset paging still showed partial lists | windows cannot meet 6.8 targets on the production host |
| D-2 | `FULL_LOAD_ROWS = 5,000`: at or below, every row is fetched immediately | meets "load in full" under filters while keeping memory near 5 MB | measured row size (20.3) makes 5,000 rows too large or allows more |
| D-3 | A snapshot token on every list; stale windows return 409 | a correction or a new phone mid-scroll would otherwise shift rows silently | never; cheap and protective |
| D-4 | One backend query function per result kind shared by every screen | v1's Comms Center and Timeline disagreed because of different joins | none |
| D-5 | Phone timeline entries and location points are read from Postgres through the lens and layer, not projected as Neo4j timeline or map nodes | the existing Timeline stops at 200,000 events and the map endpoint is uncapped; one phone case holds up to 881,646 timestamped records | 02 or a later measurement shows a graph projection that the existing pages can carry |
| D-6 | Locale fixed to en-US, 12-hour with zone abbreviation; seconds in detail, copy and export | the recorded request; one rendering for everyone; the firm is in Washington DC | Neil asks for another locale |
| D-7 | Zone choices: phone, case, UTC; case zone is a new case setting defaulting to the phones' shared zone or UTC | v1's constant zone was wrong for some phones; mixed-zone cases need one day grouping | 02 establishes per-phone zones are always present and Neil prefers per-row zones |
| D-8 | Phone view names come from the phone the record came from, line by line, even in case-wide lists; case view is a label change only | plan 10.2 and v1's perspective-first rule; a toggle that changed results would break A3 | none |
| D-9 | Duplicate rule v1: same phone, kind, direction, sender, recipients, body hash and instant; never across phones; thread participant-subset folding not carried | matches v1's tested rule while keeping cross-phone matching for approach 2; subset folding merged distinct threads | measurement 20.1 shows equal-second matching misses copies or merges distinct messages |
| D-10 | Arrow on screen `→`, in copied text and exports `->` | matches the form in the recorded feedback and pastes cleanly | none |
| D-11 | Search folding default: NFKC + supplementary styled-letter table + accents + case; `Exact characters` turns it off; no fuzzy matching; no homoglyph or transliteration folding | finds what a person types without matching different letters | Neil wants accents significant by default |
| D-12 | Digit-only queries also match identity digits | numbers are typed in many formats | none |
| D-13 | Search lives in a Cmd/Ctrl+K dialog mounted on the existing unused event, plus a header box | the shortcut already exists and does nothing | none |
| D-14 | Financial ledger is not a Search group in this unit | the ledger has its own filtered views and the plan names messages, documents and people | Neil wants one box for everything; then add a ledger group reading the existing ledger query |
| D-15 | Record citations use a new `rec://<record_uid>` scheme; chat stops defaulting to page 1 | a phone record has no page; plan 10.3 names untraceable AI answers as the main criticism | none |
| D-16 | Exports are server jobs rendered with WeasyPrint and bundled Noto fonts; uncovered characters print as `[U+XXXX]` tokens with an appendix | the recorded failure was boxes and cut text; the backend image has no fonts | color emoji become a requirement and WeasyPrint cannot draw them |
| D-17 | Star callouts are not rebuilt; `Add to Workspace` covers pinning | the Workspace already models findings | Neil wants a phone-only highlight list |
| D-18 | Navigation: the Cellebrite item becomes Conversations (Ctrl/Cmd+6), Phones and Media, shown only when the case has a phone | three phone screens per plan 10.5; no empty screens on other cases | none |
| D-19 | People additions live in the Dossiers page (tab and panel), not a new page | dossiers are Loupe's existing people surface | Neil wants a separate People page |
| D-20 | Identity suggestions never come from a name match alone | names collide; numbers are the disambiguator (v1 memory note) | none |
| D-21 | Graph shows identities with at least one communication, aggregated pair edges; top 2,000 nodes by degree with a stated limit on phone cases | 377,648 messages and contact books up to 13,053 would swamp the canvas | measurement 20.9 shows the full set renders |
| D-22 | `MAP_POINTS_MAX = 5,000` points per viewport, clusters with exact counts above | interactive rendering with exact counts | rendering measured on Owl's machines differs |
| D-23 | Reports page is not fixed here; export history lives in the export dialog and profile | Reports has no backend and is separate work | Neil wants exports under Reports |
| D-24 | Sensitive values masked in lists, revealed per value with an audit entry, excluded from copy and export by default | plan 12.1 rule 4 | none |
| D-25 | Router prefix `/api/phones`, feature folders `phones`, `conversations`, `extraction-profile`, `media`, `search` | lets the new code be built beside `/api/cellebrite` and swapped in one commit | none |
| D-26 | Long bodies show 2,000 characters with an in-place expand, the full text already loaded | keeps rows scannable without truncating data | none |

---

## 20. Not yet established

| Id | Question | How it will be settled |
|---|---|---|
| 20.1 | Whether duplicate copies share the instant exactly or differ by a second or more, and how often | read-only corpus count of groups under D-9 at exact, 1 s and 2 s tolerance on C3, C9 and the server phones; recorded here before unit 1 |
| 20.2 | The most events in one day on one phone (bounds the in-day offset in 4.7) | corpus count after 02 lands |
| 20.3 | Average and 99th-percentile JSON size of a `StreamRow` | measured on the C3 and C9 captures; sets D-2 |
| 20.4 | Whether `NodeCount` on the report root equals the number of file entries (C8: 72,849 stated, 11,663 read) | 01 compares on C3 and C9, where the file index is complete (C3 `NodeCount` 43,043 equals 43,043 files; C9 29,536 equals 29,536), and documents the C8 reading |
| 20.5 | Which audio and video containers and codecs the corpus holds and which browsers cannot play | file-type count over tagged files |
| 20.6 | Which scripts and styled-letter ranges occur in the corpus text (fonts to bundle; supplementary fold table) | code-point histogram over captured strings, counts only, no content |
| 20.7 | Whether WeasyPrint 68.1 renders color emoji fonts | spike before unit 7 |
| 20.8 | Relativity's RSMF field names and container layout | read Relativity's published RSMF specification and cite it in this file before unit 12 |
| 20.9 | Communicating identities and pair edges per case | count after 02 lands; sets D-21 |
| 20.10 | Resolved 2026-10-29: verdicts and filed items listed in 17.0 | |
| 20.11 | Resolved 2026-10-29: device zone comes only from the device setting in report metadata or a decision (01 section 9.3, 02); the examiner's selected zone is shown as such and never places events | |
| 20.12 | Whether `Precision` on Location gives a usable accuracy radius | spec 02 mapping review |
| 20.13 | The performance targets in 6.8, 8.4, 11.6 and 13.3 are targets, not measurements | each unit's tests measure them on a generated fixture of the stated size and on the server corpus before the unit is called done |
