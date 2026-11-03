# 05. Investigative approaches and closing the gaps

Purpose. This file specifies, to build level, the thirteen investigative approaches accepted in plan
section 12, three more drawn from investigative practice in spec 07 section 14 (approaches 14 to 16), the
shared results layout every approach uses, and the gap-closing work of plan section 13 (validation against the raw data, media AI and
translation, identity consolidation as the approaches depend on it, and combined communication and money
link analysis). For each approach it states what the investigation can establish, the exact report types
and fields it rests on (with counts and the number of phones carrying them), the method with thresholds,
what the investigator receives, what undercuts a reading, how sensitive fields are handled, the read-only
measurement that must be run before it is built, its dependencies on the sibling specifications, and its
acceptance tests. It corrects several field attributions in the plan's section 12 table, records new
measurements taken on the three local samples for this file, and ends with a build order in which every
unit is gated on its measurement.

Sibling specifications are referred to abstractly: **01 capture** (intake, lossless capture, locators,
reconciliation), **02 interpretation and identity** (registry, generic interpretation, reviewed mappings,
identifier registry and merges), **03 screens** (Conversations, Extraction profile, Media, phone lenses in
shared screens), **04 pattern of life** (activity strength, timestamp meanings, attribution flags,
data-availability bands, day view, statement check, places).

## Contents

1. Sources, phone labels and what was measured for this file
2. Corrections to the plan's section 12 table
3. Shared framework for every approach (tables, jobs, endpoints, results, decisions, coverage, sensitivity, results layout)
4. Approach 1: money signals on the phone
5. Approach 2: cross-phone message reconciliation
6. Approach 3: deletion and concealment timeline
7. Approach 4: knowledge and awareness
8. Approach 5: who used which phone
9. Approach 6: other devices and accounts in play
10. Approach 7: what was typed, even if deleted
11. Approach 8: media spread across phones
12. Approach 9: intent and research
13. Approach 10: plans and self-reported places
14. Approach 11: relationships over time
15. Approach 12: extraction comparison
16. Approach 13: incident window
    16a. Approach 14: common contacts · 16b. Approach 15: directional from/to frequency matrix ·
    16c. Approach 16: number switching
17. Section 13: closing the gaps
    17.1 Raw record view · 17.2 Source database view · 17.3 Independent re-parse (ALEAPP, iLEAPP) ·
    17.4 Local media pipeline · 17.5 Translation · 17.6 Image search by description ·
    17.7 Identity consolidation as the approaches use it · 17.8 Combined communication and money edges
18. Build order, dependencies and measurement gates
19. Decisions made in this file (not settled by the plan)
20. Not yet established

---

## 1. Sources, phone labels and what was measured for this file

### 1.1 Phone labels

Phones are labelled by case and by the C-number in the report file name. Case labels:

| Label | Case | Phones |
|---|---|---|
| A-C1a, A-C1b, A-C2 ... A-C9 | the 10-report case | A-C1a is the C1 report whose extraction is dated 2023-01; A-C1b is the C1 report whose extraction is dated 2022-11. Whether they are one device is not established (plan 12). |
| B-C1, B-C2, B-C3 | the 3-phone case | |
| 1P | the 1-phone case | |

The three local samples are copies of server phones of the 10-report case: local **C3 = A-C3** (same file
name), local **C9 = A-C9** (same file name), local **C8 = A-C8** (same extraction name; the local copy is a
different export: report version 8.5, report date 2025-09-18, split sections, whereas the server report is
dated 2026-05-06; both carry 2,829 InstantMessage and 3,770 Attachment records).

### 1.2 Data used

- `measurements/catalogue-14-phones.json`: per phone, record type counts and `(type, field, kind, valueType counts)` for
  value-bearing fields (`field`, `multiField`). It does **not** record which nested model sits under which
  parent field. Aggregated for this file with a script (`measurements/scripts/s05/agg.py`) into totals and phone
  counts; every "N on P phones" below comes from that aggregation.
- `c3.json`, `c9.json`, `c8.json`: structural statistics, including nested model field names
  (`<modelField>From`, `<multiModelField>To`, `<multiModelField>Messages`, `<multiModelField>ActivityLog`).
- New read-only measurements on the three local samples, run for this file. Every script streams with
  `iterparse`, prints counts only, and stores only salted SHA-256 prefixes (salt generated per run, kept in
  a private scratch directory, never in the repo). Scripts: `measurements/scripts/s05/measure.py`, `cross.py`, `attmd5.py`,
  `ids.py`, `fileid.py`, `fmeta.py`, `dbfiles.py`, `chatmedia.py`.

### 1.3 Measurements taken for this file (local samples, 10-report case)

| # | Measure | A-C3 | A-C9 | A-C8 |
|---|---|---|---|---|
| M1 | InstantMessage records (all, nested included) | 2,917 | 3,421 | 2,829 |
| M2 | by Type: Sms / Mms / AppMessage | 378 / 52 / 2,487 | 36 / 0 / 3,385 | 461 / 111 / 2,257 |
| M3 | messages carrying `SMSC` | 129 | 16 | 11 |
| M4 | distinct `SMSC` values | 14 | 10 | 3 |
| M5 | messages whose `SMSC` equals the sender Party identifier | 0 | 0 | 0 |
| M6 | messages whose sender Party identifier is 3 to 6 digits (short code) | 83 | 4 | 80 |
| M7 | of M6, body contains a currency-amount pattern | 13 | 0 | 15 |
| M8 | all messages whose body contains a currency-amount pattern | 27 | 2 | 15 |
| M9 | Email records / with an amount pattern in subject or body | 294 / 203 | 2 / 0 | 108 / 58 |
| M10 | InstantMessage deleted_state | Intact 2,917 | Intact 3,413, Trash 7, Deleted 1 | Intact 2,027, Deleted 802 |
| M11 | `SelfDestructDuration` non-zero | field absent | field absent | 0 of 2,829 |
| M12 | InstalledApplication category values seen (PA's labels) | type absent | type absent | includes Finance 1, FakeGPS 1, HideFilesPictures 2, CleanMobile 2 |
| M13 | DictionaryWord records / containing a digit | absent | 640 / 3 | 4,648 / 97 |
| M14 | owner identifiers (Party `IsPhoneOwner` = true, distinct) | 6 | 5 | 10 |
| M15 | Attachment records / resolved to a tagged file with MD5 | 456 / 404 | 874 / 759 | 3,770 / 83 |
| M16 | EXIF in tagged-file metadata (A-C3 only measured): capture time / camera make and model / GPS | 181 / 152 / 23 of 43,043 files | | |

Cross-phone measurements (same three phones):

| # | Measure | A-C3 & A-C9 | A-C3 & A-C8 | A-C9 & A-C8 |
|---|---|---|---|---|
| X1 | owner identifiers of the first phone seen as a party on the second (both directions) | 0 of 6; 3 of 5 | 0 of 6; 0 of 10 | 2 of 5; 1 of 10 |
| X2 | party identifiers in common | 12 | 26 | 21 |
| X3 | messages with equal normalised body: distinct (length ≥ 10, ≤ 3 occurrences per phone) / common / short | 7 / 289 / 31 | 14 / 178 / 27 | 76 / 515 / 52 |
| X4 | of distinct-body pairs, within 300 s of each other | 0 | 0 | **18** |
| X5 | of X4: direction complementary (sender's copy outgoing, recipient's incoming) | | | 18 |
| X6 | of X4: deleted_state differs between the two copies | | | 0 |
| X7 | of X4: time difference, median / MAD / exactly zero | | | 0 s / 0 s / 18 of 18 (all AppMessage) |
| X8 | `InstantMessage.Identifier` equal across the pair (by source app) | 17 (all "Android CallLog database") | 0 | 1 (Telegram) |
| X9 | `Chat.Id` equal across the pair | 19 | 40 | 15 |
| X10 | all tagged files: shared MD5 | 7,030 (6,612 Image) | 243 | 532 |
| X11 | attachment-linked files only: shared MD5 | 0 | 0 | 4 |

What these establish, stated once here and used below:

- **`SMSC` is the SMS service centre, not the sender.** It never equals the sender identifier (M5) and takes
  few distinct values per phone (M4). Bank short-code senders are found from the sender Party identifier (M6).
- **Message `Identifier` and `Chat.Id` are local keys**, not shared across phones. Equal values occur
  (X8, X9) in volumes and sources that indicate collisions of small local row numbers ("Android CallLog
  database", "Native Messages"), not the same message. They must never be used as a cross-phone join key.
- **App-message timestamps matched across phones are identical to the second** (X7, 18 of 18), which is the
  signature of a server-assigned time. Such matches corroborate the message but say nothing about either
  device's clock.
- **Whole-file hash overlap is dominated by system and application files** (X10) and collapses when
  restricted to files that are message attachments (X11). Media spread must use attachment-linked and
  camera files only.

---

## 2. Corrections to the plan's section 12 table

| # in plan | Plan says | What the catalogue and measurements show | Correction |
|---|---|---|---|
| 1 | `InstantMessage.SMSC` for bank short codes | `SMSC` is the SMS service centre (M3 to M5). `SMSC` occurs on 33,698 messages on 8 phones. | Short codes come from the sender: `InstantMessage` → `<modelField>From` → `Party.Identifier` (543,330 values, 14 phones), with `Type` ∈ {Sms, Mms}. |
| 1 | `CreditCard`, `MobileCard` as card records | `CreditCard`: **1 record**, B-C3 only (`Company`, `NameOnCard`, `CreditCardNumber`, `ExpirationDate`, `DateLastUsed`). `MobileCard`: 4 records on 4 phones (A-C1a, A-C2, B-C1, B-C2), fields `Description`, `PurchaseTime`, `ModifyTime`, `Type` (only value seen: `Unknown`). | `CreditCard` is a card record. `MobileCard` is not shown to be a payment card; it is carried as a captured type and enters approach 1 only after a reviewed mapping says what it is. |
| 1 | `InstalledApplication.Categories` | multiField, 2,989 values on 8 phones. PA's own category labels (M12). | Correct as stated; note 8 of 14 phones. |
| 3 | `InstantMessage.DateDeleted` | **1 value in the corpus** (B-C1). | Not a usable source of deletion time. Deletion time is bounded, not read (section 6). |
| 3 | `DeletionReason`, `SelfDestructDuration` | `DeletionReason` 153 values on 3 phones (B-C1, B-C2, B-C3), values `UserDeleted`, `UserViewed`. `SelfDestructDuration` 68,258 on 2 server phones (1P, B-C1) plus all 2,829 messages of the local A-C8 export, all zero there (M11). | As stated, with phone coverage. |
| 3 | `InstalledApplication.DeletedDate` | 5 values, A-C4 only. | As stated, one phone. |
| 3 | `ScrambledMessageData` (7,958) | Only field is `Label`. 7,958 on 3 phones, all in the 10-report case (A-C1a 427, A-C2 17, A-C1b 7,514). | Meaning (undecryptable or placeholder message) not established; see section 20. |
| 3, 4 | `ChatActivity` actions | 1,052 on 5 phones; fields `Action` and `<modelField>Participant`; a timestamp (`SystemMessageTimeStamp`) on 302 records on 2 phones only. | Who performed an action and when is mostly absent. |
| 6 | `WirelessNetwork.SSId` | 173 values on 11 phones. `BSSId` 25,484 on 7 phones. | BSSID is the main WiFi signal; SSID is sparse. |
| 6 | `RemoteServiceSession.UserAgent` | 6 records, B-C1 only. | One phone. |
| 8 | `ApplicationUsage.LastScreenshot` | Data type `Guid`, 16 records, 1 phone. | It is a reference, not a time. Not used until its meaning is established. |
| 8 | EXIF | Not a record field. EXIF items sit in tagged-file metadata, section `MetaData` (`EXIFCaptureTime`, `EXIFCameraMaker`, `EXIFCameraModel`, `ExifEnumGPSLatitude` ...), M16. | Read from the file index. |
| 9 | `VisitedPage.UsagePattern` | 13 values on 3 phones. `Title` 5,675 of 100,801 pages; `VisitCount` 34,120; `LastVisited` 70,147. `SearchedItem.TimeStamp` 3,083 of 13,067. | Most searches carry no time. |
| 10 | Calendar entries with locations | `CalendarEntry.Location` **3 values, 1 phone**. 1,000 entries on 11 phones; `RepeatRule` 255. | Calendar is mostly time and subject, rarely place. |
| 11 | `Contact.Notes` | multiField, 4,569 values on 9 phones. `TimeCreated` 4,996 on 8; `TimeModified` 979 on 6. | No rename history exists in the data; only the name at extraction and the last modification time. |
| 12 | "report header identifiers" | Hardware identifiers (`IMEI`, `ICCID`, `IMSI`, `MSISDN`, `DeviceInfoAndroidID`, `Bluetooth MAC Address`, `Mac Address`, `Factory number`) appear in report metadata for A-C3 only among the three local reports; A-C9 and A-C8 carry none (`meta_items` in `c3.json`, `c9.json`, `c8.json`). | Device identity often has to be inferred from content (section 15). |
| 7 | `DictionaryWord` | 14,260 on 4 phones (A-C5 6,540, A-C8 4,648, A-C7 2,432, A-C9 640); fields `Word`, `Frequency`, `UsagePattern` (A-C8); **no timestamp**. | Typed words cannot be placed in time. |

---

## 3. Shared framework for every approach

### 3.1 Inputs taken from siblings (interfaces assumed, named abstractly)

| Interface | From | What this file needs |
|---|---|---|
| Record address | 01 / 02 | `record_uid` (uuid, 02 section 1.2) plus `field_path` (and value index where a field repeats), addressing any captured value, top-level or nested. Report record ids are not unique (01 section 1.3) and are never an address; workspace links use `target_id = record_uid`. |
| Captured record read | 01 | All fields, values and data types; model attributes (`deleted_state`, `decoding_confidence`, `extractionId`, `source_index`, `file_id`, `labels`, `isrelated`, `originalId`); parent chain for nested models; resolved files with hash verification state. |
| Instants | 01 / 04 | Every TimeStamp as instant (UTC), original offset, original string, and a flag where the offset was absent (plan 6.7). Approaches never parse raw strings themselves. |
| Message view | 02 | Interpreted messages: sender and recipient party records, owner flag, platform family, source app, chat record, body, attachments, deleted_state, timestamps by meaning. |
| Identifier registry and merges | 02 | Normalised identifier keys (E.164, app ids, emails, usernames, folded display names), reviewed merges with undo, and the owner identity of each extraction. |
| Activity strength, timestamp meanings, attribution, availability bands | 04 | Per event class (interaction, device state, passive, unknown), the meaning of each timestamp field, Synced or Extracted attribution, and per phone per signal the periods with data. |
| Extraction profile | 01 / 03 | `IsSelectiveExtraction`, `IsPartialData`, selected types and ranges, extraction start and end, device metadata items, report version and producer. |

If a sibling names these differently, the sibling's names win; the semantics above are what this file depends on.

### 3.2 Where code lives

Decision: approaches are pure functions over captured and interpreted records, one module per approach,
in `backend/services/phone_analysis/` (backend is Python 3.10; no newer syntax), following the
flat-module-per-capability convention of `backend/services/financial/`. Tests in
`backend/tests/test_phone_analysis_<module>.py`. Router `backend/routers/phone_analysis.py`, prefix
`/api/phone-analysis`, with the same authentication dependency as `routers/financial_ledger.py:96-101`.
Frontend in `frontend_v2/src/features/phone-analysis/`. Media and re-parse work runs in the evidence
engine (Python 3.12, `evidence-engine/pyproject.toml:5`). *Reverse if* 01 or 02 fix a different package
root for phone code; then this package moves under it unchanged.

| Module | Approach |
|---|---|
| `framework.py` | runs, results, coverage, directions, sensitivity, decisions (this section) |
| `money_signals.py`, `institution_directory.py`, `money_parse.py` | 1 |
| `message_reconciliation.py`, `clock_offset.py` | 2 |
| `deletion_timeline.py` | 3 |
| `awareness.py` | 4 |
| `device_users.py` | 5 |
| `other_devices.py` | 6 |
| `typed_words.py` | 7 |
| `media_spread.py`, `perceptual_hash.py` | 8 |
| `intent.py` | 9 |
| `plans.py` | 10 |
| `relationships.py` | 11 |
| `extraction_comparison.py` | 12 |
| `incident_window.py` | 13 |
| `common_contacts.py` | 14 |
| `contact_matrix.py` | 15 |
| `number_switching.py` | 16 |
| none (uses `backend/services/phone/link_edges.py`, 02 section 11.1) | 17.8; 05-S10 wires the approach screen to 02-U16 |
| `measurements.py` | the gate measurements of every approach |

### 3.3 Tables (Postgres, Alembic migration in `backend/postgres/alembic/versions/`)

`phone_analysis_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `case_id` | uuid not null, fk `cases.id` on delete cascade | every query scoped by case (plan 5.7) |
| `approach` | varchar(40) not null, check in the approach codes below | |
| `approach_version` | varchar(20) not null | module version constant; a change of algorithm is a new version |
| `parameters` | jsonb not null | every threshold actually used, by name |
| `parameters_sha256` | char(64) not null | over canonical JSON (sorted keys, no whitespace) |
| `input_manifest` | jsonb not null | extraction ids with their capture hashes, mapping versions, identity-merge log head, ledger snapshot sha256 (approach 1, 17.8) |
| `input_revision` | char(64) not null | sha256 over `input_manifest` canonical JSON |
| `status` | varchar(16) not null, check in (`queued`,`running`,`completed`,`failed`,`cancelled`,`superseded`) | |
| `requested_by` | varchar(320) not null | named actor |
| `counts` | jsonb | records read per type, results per kind |
| `coverage` | jsonb not null default `{}` | section 3.6 |
| `error` | text | named failure, never blank on `failed` |
| `created_at`, `started_at`, `finished_at` | timestamptz | |

Unique `(case_id, approach, approach_version, input_revision, parameters_sha256)`: requesting the same run
twice returns the existing run (idempotent). A run on changed inputs is a new row; the previous run becomes
`superseded` and stays readable.

Approach codes: `money_signals`, `message_reconciliation`, `deletion_timeline`, `awareness`,
`device_users`, `other_devices`, `typed_words`, `media_spread`, `intent`, `plans`, `relationships`,
`extraction_comparison`, `incident_window`, `common_contacts`, `contact_matrix`, `number_switching`,
`link_edges`, `reparse_comparison`.

`phone_analysis_results`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `run_id` | uuid not null fk runs on delete cascade | |
| `case_id` | uuid not null | denormalised for scoping |
| `result_key` | char(64) not null | sha256 over the approach code and the sorted locators and ledger ids the result rests on; equal inputs give equal keys across runs, so decisions carry over (3.7) |
| `kind` | varchar(48) not null | per approach, enumerated in each section |
| `strength` | varchar(24) not null | computed by the approach's rule; never written by a request |
| `measures` | jsonb not null | numbers the result is built from (counts, offsets, scores, p-values) with units |
| `directions` | jsonb not null | `{"supports": [...], "undercuts": [...]}`, each item `{code, detail, locators}` (3.5) |
| `sensitive` | boolean not null default false | true when any field it shows is in the sensitive set (3.8) |
| `period_start`, `period_end` | timestamptz | for time filters |

Unique `(run_id, result_key)`. Index `(case_id, kind)`, `(case_id, period_start)`.

`phone_analysis_result_records`

| Column | Type | Notes |
|---|---|---|
| `result_id` | uuid fk results on delete cascade | |
| `extraction_id` | uuid null | null when the row is a ledger row |
| `record_uid` | uuid null | 02 section 1.2; null when the row is a ledger row |
| `field_path` | varchar(512) null | e.g. `From/Party/Identifier` |
| `ledger_transaction_id` | uuid null | `financial_transactions.id` |
| `role` | varchar(40) not null | e.g. `sender_copy`, `recipient_copy`, `alert`, `ledger_row`, `evidence` |

Primary key `(result_id, coalesce(extraction_id,…), record_uid, field_path, ledger_transaction_id, role)` as a
unique index with `NULLS NOT DISTINCT` is not available on every Postgres version in use; decision: use a
surrogate `id` pk and a unique index over `md5` of the concatenated nullable columns.

`phone_analysis_measurements`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `scope` | varchar(16) check in (`case`,`corpus`) | corpus measurements are run by Neil on the reference corpus and recorded too |
| `case_id` | uuid null | |
| `approach` | varchar(40) | |
| `measure_version` | varchar(20) | |
| `result` | jsonb | counts only; never content, never identifiers (salted hashes only where a join needs them, and the salt is discarded) |
| `gate` | varchar(16) check in (`build`,`do_not_build`,`inconclusive`) | computed from the thresholds in the approach's section |
| `recorded_at`, `recorded_by` | | |

### 3.4 Jobs and endpoints

Runs execute on their own arq queue and worker settings (`arq:phone-analysis`, an `AnalysisWorkerSettings`
on the `PdfReviewWorkerSettings` pattern, `evidence-engine/app/worker.py`), one job at a time
(`max_jobs = 1`) under the phone worker's memory cap (01 section 10.2), as job kind `analysis`, with
checkpoints per extraction and cooperative cancel. An analysis never queues behind an ingest and an
ingest never queues behind an analysis (the phone capture worker has `max_jobs = 1`, 01 D14). *Reverse
if* measured host memory cannot hold both workers. A run never writes to captured records, interpreted records, the ledger
or the graph; its only writes are the three tables above.

| Method and path | Body or query | Returns |
|---|---|---|
| `POST /api/phone-analysis/runs` | `{case_id, approach, parameters?}` (unknown parameter names refused with 422) | run row; 200 if an identical run exists, 202 when queued |
| `GET /api/phone-analysis/runs` | `case_id`, `approach?` | runs, newest first |
| `GET /api/phone-analysis/runs/{run_id}` | | run with `coverage`, `counts`, `parameters` |
| `POST /api/phone-analysis/runs/{run_id}/cancel` | | run |
| `GET /api/phone-analysis/runs/{run_id}/results` | `case_id`, `kind?`, `strength?`, `from?`, `to?`, `phone?`, `identity?`, `offset`, `limit` (max 500) | `{total, offset, limit, items}`; `total` is always the full count under the filter (plan 10.2 "complete results when filtered") |
| `GET /api/phone-analysis/results/{result_id}` | `case_id` | result, records (with locators that open the raw record, 17.1), directions, decisions |
| `POST /api/phone-analysis/results/{result_id}/decisions` | `{case_id, decision: "confirmed"\|"rejected", reason}` | updated decisions |
| `POST /api/phone-analysis/measurements` | `{case_id, approach}` | measurement row |
| `GET /api/phone-analysis/measurements` | `case_id?`, `approach?` | rows |
| `GET /api/phone-analysis/coverage` | `case_id`, `approach` | the coverage statement (3.6) without running anything |

Errors: 404 for a run or result not in the case (never 403, so ids do not leak across cases); 409 when a
decision names a result of a superseded run (the client reloads the current run, whose result with the same
`result_key` carries the decision); 422 for unknown parameters or out-of-range thresholds; 503 with a named
reason when a dependency (for example 02's identity registry) has not been built for the case.

### 3.5 Both directions

Every result carries `directions.supports` and `directions.undercuts`. Codes are a closed set per approach
(listed in each section). Common codes:

| Code | Meaning |
|---|---|
| `synced_attribution` | a record the reading rests on has `DeviceLocationAffiliation = Synced` or `UserMapping` naming a synced source (04) |
| `clock_offset_unknown` | the reading depends on comparing two devices' times and no offset estimate exists (section 5) |
| `selective_extraction` | the extraction profile says the production is selective or partial, or the type was not selected |
| `no_data_period` | a period the reading depends on has no data for the signal (04 availability bands) |
| `decoding_confidence_low` | `decoding_confidence` other than High on a record used (all 17 reports measured High so far: `c3.json`, `c9.json`, `c8.json` `confidence`) |
| `deleted_or_carved` | a record used is Deleted, Trash or carved |
| `identity_unreviewed` | the reading joins identities that are equal only by normalised identifier, not by a reviewed merge |

A result never states an inference about a person's state of mind. It states what the records show.

### 3.6 Coverage

`coverage` on every run: per phone, `{carries_signal: bool, records: n, first, last, gaps: [[from,to]...],
selected_in_extraction: bool|null, reason_absent: "type_absent"|"not_selected"|"field_absent"|null}` for
each type and field the approach rests on. The screen shows it above every result list as a sentence
built from the data, for example: "Notifications exist on 2 of 14 phones (B-C1, B-C2). Results below
cover those phones only." (UI copy: no em dashes.)

### 3.7 Decisions on results

A person confirms or rejects a result. Decision: record it through `services/financial/decisions.py:252`
(`record(...)`) so there is one audit chain with a named actor, adding `AdjudicationSubject.phone_analysis_result`
and `AdjudicationDecision.confirm_phone_result` / `reject_phone_result` (the subject enum is closed,
`postgres/models/enums.py:112-130`, so this is a migration of its check constraint). The decision is keyed on
`result_key`, so a rerun on identical inputs shows the earlier decision, and a rerun whose inputs changed
the result shows "decided on an earlier reading" with both readings. A decision never changes `strength`
or any computed field. *Reverse if* 02 defines a phone decision log; then decisions go there with the same
semantics.

### 3.8 Sensitive fields

Sensitive set (captured in full per standing decision 3, shown with care, excluded from exports and from AI
by default):

| Type.field | Corpus presence |
|---|---|
| `Password.Data` | 7,555 values, 10 phones |
| `Password.GenericAttribute` | 1,621 values, 5 phones |
| `UserAccount.Password` | 25, 8 phones |
| `WirelessNetwork.Password` | 26, 2 phones |
| `Cookie.Value` | 13,593, 10 phones |
| `CreditCard.CreditCardNumber` | 1, B-C3 |
| `Autofill.Value` | 70, 6 phones |
| `DictionaryWord.Word` | 14,256, 4 phones |
| `KeyValueModel.Value` | 395,831, 13 phones (contents unknown per key; sensitive until a reviewed mapping shows a key's values hold no credential) |

This list and 02 section 5.5 are one list (`mappings/data/sensitive_fields.json`).

Rules: values render masked (`••••` plus, for card and account numbers, the last four characters) until a
person presses Reveal; each reveal is logged (actor, time, locator, field) in an append-only
`phone_sensitive_reveals` table; sensitive values are never placed in the shared text store or search index
by default, never sent to any model, never included in exports unless the export dialog's explicit option
is chosen (and the export manifest then lists every revealed field). Approaches that need to compare a
sensitive value (approach 1 card endings, approach 7 typed words) compare inside the backend and return only
the match and the masked display.

### 3.9 Shared results layout

Every approach screen uses one layout, built from the cb-ux shared kit (07 section 5), in this order:

1. **What it does**: one plain sentence stating the question the approach answers (its section's first
   subsection) and what it does not show.
2. **Run**, with progress: records read per phone against the total, and Cancel (3.4). A run on unchanged
   inputs opens the existing result (3.3 idempotency).
3. **The coverage sentence** (3.6), built from the data, above the results.
4. **Results with the total** under the filter (`total` from 3.4), never a clipped list presented as whole.
5. **The record panel** (03 section 3.6) for any result, opening the records behind it (17.1).
6. **Add to…** on one result, a selection or the whole filtered total (07 section 6.2).
7. **Confirm or reject** with a typed reason (3.7); the decision never changes a computed field.

Every result is labelled **"Lead for enquiry"**: an investigative result that points to records to examine,
not an evaluation of probative value (research note 09 section 5, investigative versus evaluative output).
The label travels with the result into findings and exports (07 J-17).

Test AP-1: for each approach screen, the seven parts appear in this order; the coverage sentence equals the
`coverage` of the run; the stated total equals the result count under the filter; every result carries
"Lead for enquiry"; a reject without a reason is refused.

---

## 4. Approach 1: money signals on the phone

### 4.1 Question it answers

1. Which financial events does the phone record (bank and payment alerts, card and transfer messages, bank
   emails), and does each one correspond to a transaction in the ledger built from the financial records in
   the case?
2. Which financial institutions, accounts and cards does the phone show to exist (apps, alerts, emails,
   saved logins, visited banking pages, card records) that are not among the accounts in the financial
   records in the case?

Both are statements about records. A phone alert is an assertion by an app on the phone; it is p4 and
never a ledger row (plan 12.1 rule 5).

### 4.2 Data it rests on

| Signal | Types and fields | Corpus |
|---|---|---|
| S1 notifications | `Notification`: `Source`, `ServiceIdentifier` (app package), `Subject`, `Body`, `TimeStamp`, `Status`, `Type`, `Notes` | 7,881 on 2 phones (B-C1 3,089, B-C2 4,792). None in the 10-report or 1-phone case. |
| S2 SMS and MMS from short codes or alphanumeric senders | `InstantMessage` with `Type` ∈ {Sms, Mms}; sender = `<modelField>From` → `Party.Identifier`; `Body`, `TimeStamp`, `Status`, `Folder` | Party.Identifier 543,330 on 14 phones. Short-code senders measured: A-C3 83, A-C9 4, A-C8 80 (M6); with amounts 13, 0, 15 (M7). |
| S3 bank and payment emails | `Email`: `<modelField>From` Party identifier (address, domain), `Subject`, `Body`, `Snippet`, `TimeStamp`, `Account`, `Folder`, `Labels` | 25,727 on 12 phones. Amount pattern in A-C3 203 of 294, A-C8 58 of 108 (M9; not all financial). |
| S4 finance apps | `InstalledApplication`: `Identifier`, `Name`, `Categories`, `PurchaseDate`, `InstallDate`, `DeletedDate`, `Version` | 3,507 on 8 phones; Categories 2,989 values on 8 phones. |
| S5 banking and exchange cookies | `Cookie`: `Domain`, `CreationTime`, `LastAccessTime`, `Expiry`, `RelatedApplication`, `Source` (`Value` sensitive, unused) | 14,967 on 10 phones. |
| S6 saved logins and accounts | `Password`: `Service`, `Server`, `Account`, `AccessGroup`, `Label`, `Type`, `DateCreated`, `DateModified` (`Data` sensitive, unused); `UserAccount`: `ServiceType`, `ServiceIdentifier`, `Username`, `Name`, `TimeCreated` | Password 8,595 on 10 phones; UserAccount 391 on 13. |
| S7 visited banking pages | `VisitedPage`: `Url` host, `Title`, `LastVisited`, `VisitCount`; `WebBookmark` | 100,801 on 12 phones. |
| S8 card records | `CreditCard`: `Company` (`CreditCardCompany`: Visa seen), `NameOnCard`, `CreditCardNumber` (sensitive), `ExpirationDate`, `DateLastUsed`; `Autofill` `Key`/`Value` where the key names a card or account field | CreditCard 1 (B-C3); Autofill 70 on 6. |
| S9 money in conversations | `InstantMessage` `AppMessage` bodies with an amount | M8: 27, 2, 15 on the local phones. |

`MobileCard` is excluded until a reviewed mapping defines it (section 2).

### 4.3 Method

#### 4.3.1 Institution directory (reviewed reference data)

A versioned data set, `backend/services/phone_analysis/data/institution_directory.v<N>.json`, plus a
case-level table `phone_institution_aliases` for additions a person makes in a case.

| Field | Example shape (not real data) | Use |
|---|---|---|
| `institution_id` | `inst:<slug>` | |
| `display_name` | | |
| `country` | ISO 3166-1 alpha-2 | short codes are national |
| `app_packages` | Android package ids, iOS bundle ids | S1 `ServiceIdentifier`, S4 `Identifier`, S5 `RelatedApplication` |
| `web_domains` | registrable domains | S3 sender domain, S5 cookie domain, S6 `Service`/`Server`, S7 host |
| `sms_senders` | short codes and alphanumeric sender ids, per country | S2 |
| `email_domains` | | S3 |
| `kind` | bank, card issuer, payment app, remittance, exchange, crypto exchange, lender | lead grouping |
| `currencies` | ISO 4217 | default currency when the text gives only a symbol |
| `templates` | per institution and channel, the parse rules of 4.3.2 | |
| `review` | `{reviewed_by, reviewed_at, source_note}` per entry | an entry without review is not used |

Decision: entries are drafted from public app-store and domain information (AI may draft), and each is
used only after a person has reviewed it, as for reviewed mappings (plan 6.5). The directory holds no
evidence and no case identifiers, so it can be committed. `phone_institution_aliases(case_id, institution_id,
channel, value_normalised, reason, actor, created_at)` lets a person record "this short code is this bank in
this case" with a reason; it is case-scoped and never committed.

Matching rules: domain match on registrable domain (public-suffix aware) after lowercase; package match
exact; short code exact digits within the phone's country (country from the extraction profile, else the
owner E.164 country; if neither is known the match is reported as `country_unknown` and lowered one
strength level); alphanumeric sender match is case-insensitive exact.

#### 4.3.2 Parsing a signal into a money reading

`money_parse.parse(text, *, institution, phone_country) -> MoneyReading | None`, pure and deterministic:

1. Normalise: NFKC, fold decorative Unicode to plain letters (same fold as 03 search), collapse whitespace.
   Keep the original text and the offsets into it.
2. Amounts: patterns for symbol or ISO code before or after a number; grouping and decimal separators read
   by locale: if the institution directory or the number itself makes the separator unambiguous
   (two digits after the final separator and a different separator earlier) use it; otherwise the amount is
   `ambiguous_separator` and not converted. Integer arithmetic only; minor units from the currency's
   exponent (`services/financial/money.py`).
3. Currency: ISO code in the text; else symbol plus a single currency from the institution entry; `$` with
   no institution or with an institution listing more than one `$` currency is `currency_unknown`.
4. Direction cue words per template (debit: purchase, payment, withdrawal, sent, charged; credit: deposit,
   received, credited, refund), language-specific lists in the template. No cue: `direction_unknown`.
5. Account or card reference: reuse `services/financial/account_mentions.py:16-21` (`REFERENCE`) and its
   normaliser (`account_mentions.py:24-26`), and additionally the template's own ending pattern (for example
   "ending in 1234", "x1234", "*1234"). A reference with four or fewer visible digits is `partial`
   (`account_mentions.py:69`).
6. Counterparty text: the template's merchant or payee span if defined; else none.
7. Event date: the record's instant converted to the device zone's calendar date (04), plus the original
   string. Where the text states a date, it is captured too and both are shown.
8. Output `MoneyReading{amount_minor?, currency?, direction?, account_ref?, counterparty_text?, event_instant,
   stated_date?, flags[], spans[]}`. A reading with no amount is not produced. A reading with a defect is
   produced with its flags (flag, don't refuse); it cannot become a testable claim until a person supplies
   the missing value, and the supplied value is stored beside the machine reading (CLAUDE.md design rule on
   corrections).

Templates are data, versioned with the directory. Signals with no matching template go through the generic
rules above with `template = generic`, which lowers strength (4.3.6).

#### 4.3.3 From reading to p4 claim

Each reading with amount and currency becomes a `services.financial.correlation.Claim`
(`correlation.py:465-505`):

| Claim field | From |
|---|---|
| `claim_id` | uuid5 over the record locator and the reading (deterministic, as `claim_comparison.py:44`) |
| `amounts` | `AmountRange(low = high = amount)` |
| `dates` | `DateRange(event_date − 1 day, event_date + 7 days)` (decision below) |
| `quote` | the exact text of the field the amount was read from (required non-empty, `correlation.py:500-505`) |
| `source_document_id` | the evidence file id of the production the extraction came from |
| `locator` | the record locator plus field path |
| `payer` / `payee` | debit: payer = the bound account's holder, payee = counterparty text; credit: the reverse; unknown direction: both `None` |
| `speaker` | the institution display name and channel ("notification", "SMS", "email") |
| `proof_class` | not passed; the class is computed: `assign_proof_class(SourceShape.unstructured_narrative)` returns p4 (`proof_class.py:185-186`) and the Claim constructor refuses anything else (`correlation.py:489-495`) |

Date window decision: an alert is sent at or near authorisation; the ledger orders a row by its chosen
chronology date (value date first, then labelled fallbacks: `claim_comparison.py:66-67` limitation text,
and `financial_transactions.transaction_date`, `posted_date`, `ordering_date` at
`postgres/models/financial.py:819-823`). Posting can follow authorisation by several days and the device
zone can put the alert on the previous calendar day relative to the bank. The window is therefore
`[event_date − 1, event_date + 7]`. *Reverse if* the lag distribution measured on corroborated pairs (4.5,
M-1d) shows 95 percent within a narrower or wider span; the window is a run parameter, recorded on every
result.

Materiality decision: alerts state the transaction amount exactly, so the run uses
`Materiality(basis_points=0, floor_major_units=0)` for the corroboration pass, then a second pass with the
module default (`correlation.py:408-412`, ten per cent, floor one unit) over claims still unresolved, whose
corroborations are reported as kind `near_amount` with `NOTE_AMOUNT_OUTSIDE_STATED_RANGE`
(`correlation.py:277`). Foreign-exchange conversions and fees are the case this second pass exists for.
*Reverse if* review of near-amount results shows they are mostly wrong pairings.

#### 4.3.4 Binding a claim to ledger accounts

1. Candidate accounts: all `financial_accounts` of the case.
2. Institution filter: the reading's institution is compared with `institution_name`
   (`postgres/models/financial.py:431`) by `services/financial/field_proposals.py:150-151`
   (`institution_key`) and the same-institution rule beside it.
3. Ending filter: when the reading has an account or card reference, compare its digits with the account's
   `identifier_as_printed` (`financial.py:432`) and reviewed identifiers using
   `field_proposals.account_match` (`field_proposals.py:180-190`): `full` or `masked` (at least
   `MIN_MASKED_DIGITS = 4` visible digits agreeing as a suffix, `field_proposals.py:88`). Where card
   statements recorded per-section card endings (`statement_import_card.py:80-85`,
   `statement_import.py:410`), a row-level ending is compared as well; whether that ending is persisted on
   admitted transaction rows is not established (section 20), and until it is, binding is account-level only.
4. Outcomes: exactly one account → `bound`; several → `ambiguous` (tested against each, never merged);
   none and the institution matches an account → `institution_held_account_unseen`; none at all →
   `not_in_productions` (this feeds 4.3.7, not correlation).

A masked ending never becomes an account identifier: `account_identity.py:30-31` refuses masked values
("masked references remain investigation leads"). This approach respects that by producing leads only.

#### 4.3.5 Matching to the ledger

For each bound or ambiguous claim, and each candidate account:

1. Ledger rows: the account's effective rows only. Effective means admitted and not superseded, the same
   filter `account_mentions.py:80-86` applies (`ledger_status = 'admitted'`, `superseded_by_id IS NULL`,
   `proof_class` in `LEDGER_CLASSES`). Corrected values are therefore the ones compared (CLAUDE.md:
   only the corrected value is used in sums and searches); the row's machine reading stays visible on the
   ledger side as it is today.
2. Build `LedgerEntry` rows as `claim_comparison.py:47-53` does from `ledger_timeline`, skipping rows whose
   chronology basis is ordering-date-only (listed as `date_unavailable_ids`, as there).
3. Coverage. Phase 1a (first build): no contradiction. Coverage is passed as the account with no span, as
   `claim_comparison.py:55-59` does, so an absence yields `unresolved` and never `contradicted`. Phase 1b:
   coverage from `services/financial/continuity.py:528` (`read_account_continuity`) through
   `correlation.py:704` (`coverage_from_continuity`), with `unverified` periods from reconciliation status.
   `coverage_from_continuity` has no production caller today (only the export in
   `services/financial/__init__.py:849`), so phase 1b includes building and testing that join; it is a
   separate unit (18).
4. Call `correlate(claim, entries, coverage=..., materiality=...)` (`correlation.py:1312`). The outcome,
   candidates, notes and tolerance are stored in `measures`; `strength` is the outcome name.
5. Phone-specific undercuts added to every non-corroborated outcome: `authorization_may_not_post` (an alert
   can describe an authorisation that was declined, reversed or never settled), `alert_amount_may_exclude_fees`,
   `binding_by_ending_only` (when the binding was masked), `institution_from_sender_only`.

Correlation never promotes (`correlation.py:14-24`): a corroborated alert stays p4, gains a link to the
ledger row, and the row gains nothing but the link.

#### 4.3.6 Strength of a money reading (computed)

| Strength | Rule |
|---|---|
| `institution_template` | reviewed institution, channel matched (package, short code or email domain), template parse with amount, currency and direction |
| `institution_generic` | reviewed institution matched, generic parse |
| `unattributed` | no institution matched (S9 conversation messages, unknown senders) |

Strength is shown on every claim and is a filter; it never gates correlation.

#### 4.3.7 Account-discovery leads

`money_signals.leads(case_id)` groups evidence by `(institution_id, account_ref_normalised or null)`:

1. Evidence classes, computed from the signal type:

| Class | Signals |
|---|---|
| `transactional` | S1, S2, S3 readings with an amount (an event on an account) |
| `account` | S6 saved login or account for the institution; S8 card record; S3 statement or account notice email with an account reference and no amount |
| `presence` | S4 app installed; S5 cookie; S7 page visit; S3 marketing email |

2. Status against the financial records, computed exactly as `account_mentions.account_references` does for
   payment descriptions (`account_mentions.py:75-123`): `possible_statement` when an account with at least
   one statement period matches (institution and, where present, ending), `referenced_only` when only a
   referenced account (created through `account_identity.save_identity` with `referenced_only`,
   `account_identity.py:144-147`) matches, `no_statement_found` otherwise. Institution-only evidence matches
   any account at that institution.
3. Lead strength = the highest evidence class present; ties listed with all evidence.
4. A lead lists: institution, account reference as printed (masked to the last four characters when it is a
   card or account number), first and last time seen, count per evidence class, each evidence record, and
   the status sentence. Example UI copy (no em dashes): "This phone holds 14 alerts from [institution] for
   an account ending 1234, from [date] to [date]. No statement for an account ending 1234 at [institution]
   is among the financial records in this case." For presence-only: "This phone had the [institution] app
   installed and visited its website. No account at [institution] is among the financial records in this
   case."
5. Leads never say what to request or from whom. The correlation module's internal vocabulary mentions
   subpoenas (`correlation.py:184-188`); none of it reaches this screen's copy.
6. A full account number seen on the phone (an email or autofill carrying a complete number) is shown as
   such; a person may then record a referenced account through the existing reviewed identity path, which
   requires a complete number (`account_identity.py:70-71`) and records the decision with an actor
   (`account_identity.py:153-155`). Nothing is created automatically.

### 4.4 What the investigator gets

- **Phone money events** list: every reading, with source (notification, SMS, email, chat), institution,
  amount as read, currency, direction, account reference, time (device zone, 12-hour, original one click
  away), strength, flags, outcome (corroborated, near amount, unresolved with reason), and a link to the
  matched ledger row by its `ref_id` (`services/financial/references.py`). Opens to the raw record (17.1).
- **On the ledger side**: a corroborated transaction shows "Also recorded on phone B-C1: notification at
  [time]" with a link; its class is unchanged.
- **Accounts the records do not include**: the lead list of 4.3.7, filterable by status and evidence class.
- **Case Timeline** (03): readings appear in the money lane, labelled p4 and "from the phone".

### 4.5 What undercuts it, both directions

Supports: template match, reviewed institution, exact amount, ending bound to one account, corroboration.
Undercuts: `authorization_may_not_post`, `currency_unknown`, `ambiguous_separator`, `country_unknown`,
`binding_by_ending_only`, `synced_attribution` (an email or notification can belong to an account synced
from another device: 04's attribution flag), `selective_extraction` (notifications may not have been
selected), notification retention (Android notification history is short-lived; absence of alerts in a
period is not absence of transactions), `identity_unreviewed`.

### 4.6 Sensitive fields

`Password.Data`, `Cookie.Value`, `CreditCard.CreditCardNumber`, `Autofill.Value` are never read by the
parser. Card and account numbers from S8 are compared in the backend for the ending match and returned
masked to the last four characters. Leads and claims built from S6 show service and account name only.

### 4.7 Measurement first

`measurements.money_signals(case_id | corpus)`, read-only, counts only:

| Id | Count | Per |
|---|---|---|
| M-1a | Notification records; distinct `ServiceIdentifier`; those whose `ServiceIdentifier` is in the reviewed directory | phone |
| M-1b | records whose body parses to an amount with currency, by signal S1 to S3, S9 | phone |
| M-1c | readings bound to exactly one ledger account; ambiguous; unbound | case |
| M-1d | of bound readings, corroborated at zero materiality; lag in days (ledger chronology date minus event date), distribution | case |
| M-1e | leads by status and evidence class | case |

Local evidence so far: short-code SMS with amounts exist on two of three local phones (M7: 13 and 15);
Notification exists only in the 3-phone case. Gate: **build** if, on any case with financial records, at least
20 readings bind to an account (M-1c) or at least one `no_statement_found` lead of class `transactional` or
`account` exists (M-1e). **Do not build** the correlation half if M-1c is zero on every case; the lead half
is still built if M-1e has any `account` or `transactional` lead. None of the three phone cases exists in Loupe (their ids are v1 case ids and no
Loupe case has a matching name), so approach 1's first run waits for the answer on where the phones are
loaded (CB-INDEX question 3); the 3-phone case (notifications) is the first candidate once it is in a case
with financial records.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-1b, readings with an amount and currency: S1 notifications 9 (P13) and 3 (P14); S2 short-code SMS 1 to 42
per phone on 11 phones; S3 email up to 4,899 (P10); S9 app messages up to 502 (P13). M-1a: Notification only on
P13 (3,951, 21 distinct `ServiceIdentifier`) and P14 (3,089, 19). M-1a against the reviewed directory and M-1c
to M-1e need the ledger and the Loupe case: `cb-crossev` measures them before this gate is marked.

**Loupe result (`measurements` m1.1 on live, release 6538f238, 2026-11-03; `measurements/g/`):**

| Case | Phones; ledger rows | M-1a notifications / distinct `ServiceIdentifier` / in the reviewed directory | M-1b | M-1c | M-1d | M-1e | Gate |
|---|---|---|---|---|---|---|---|
| reference 88e01b57 (C3) | 1; 0 | 0 / 0 / 0 | S3 34 | not measurable: no ledger | not measurable | not measurable | inconclusive |
| reference 7006c0ab (C9) | 1; 0 | 0 / 0 / 0 | 0 | not measurable: no ledger | not measurable | not measurable | inconclusive |
| reference 574a9752 (C9) | 1; 0 | 0 / 0 / 0 | 0 | not measurable: no ledger | not measurable | not measurable | inconclusive |
| phones-only 4aa79795 (synthetic) | 3; 0 | 0 / 0 / 0 | 0 | not measurable: no ledger | not measurable | not measurable | inconclusive |
| training d9945277 (synthetic) | 2; 65 | 16 / 1 / 0 | S1 16 | 16 bound, 0 ambiguous, 0 unbound | 16 corroborated; lag 0 days on all 16 | `possible_statement` transactional 1 | do not build (synthetic) |

The directory holds 11 entries and none is reviewed (a review is a person's act), so M-1a against the reviewed
directory is 0 on every case; the training alerts bind by the account ending, not by the directory. No live case
holds both real phones and a ledger: the three reference cases hold one phone each and no financial records, and
the 3-phone case with notifications (P13, P14) is not loaded in Loupe. Gate on real data: **not measurable: no case
with both**. The build stays (05-S3). The training figures are synthetic: they show the path works end to end
(each alert linked to its ledger row) and are not a basis for the gate. The reference cases are measured
read-only and not stored in `phone_analysis_measurements`, because writes on them are outside this job's run
rules; the two synthetic cases are stored.

### 4.8 Dependencies

01 (records, locators, file ids of the production), 02 (message view; owner identity; identifier registry
for counterparty text), 04 (device-zone calendar date; synced attribution), financial subsystem modules
cited above.

### 4.9 Acceptance tests (`backend/tests/test_phone_analysis_money_signals.py`)

1. A notification fixture from a reviewed institution with "purchase", amount, currency and "ending 1234"
   produces one reading with strength `institution_template`, a Claim whose class is p4, and binds to the one
   ledger account whose printed identifier ends 1234.
2. The same alert against a ledger row of equal amount whose chronology date is event date + 3 corroborates;
   the ledger row's `proof_class` is unchanged after the run.
3. A `$` alert from an institution whose entry lists two `$` currencies yields `currency_unknown`, no Claim,
   and a flagged reading.
4. "1.234,56" with an institution whose locale uses comma decimals reads 123456 minor units; "1,234" with
   no locale information is `ambiguous_separator`.
5. A short-code SMS whose `SMSC` equals a bank's number but whose sender is a personal number is **not**
   matched to the bank (sender Party identifier is the key).
6. Phase 1a: a bound claim with no matching row is `unresolved`, never `contradicted`, with
   `authorization_may_not_post` in undercuts.
7. Two accounts ending 1234 at one institution: the reading is `ambiguous`, tested against both, merged into
   neither.
8. A cookie for a reviewed bank domain with no account at that bank in the case yields a `presence` lead with
   status `no_statement_found`; adding a statement for an account at that bank changes the status to
   `possible_statement` on rerun.
9. A corrected ledger amount (superseding row) is the one compared; the superseded row is not a candidate.
10. A card record's number never appears unmasked in any API response unless a reveal is recorded; the
    reveal row names actor and locator.
11. Rerunning with identical inputs returns the same run id; changing the ledger snapshot creates a new run
    and supersedes the old one; a decision on a result carries over by `result_key`.
12. UI copy for leads contains no em dash and none of the words "subpoena", "request", "obtain".

---

## 5. Approach 2: cross-phone message reconciliation

### 5.1 Question it answers

For two phones in the case, which messages appear on both (sender's copy and recipient's copy), which appear
on only one, which are deleted on one side only, and what each match says about the two devices' clocks.

### 5.2 Data it rests on

`InstantMessage` (377,648 on 14 phones): `Body` (308,807), `TimeStamp` (370,754), `Type`
(`InstantMessageType`: AppMessage, IMessage, Mms, Sms), `Source`/`SourceApplication` (374,707), `Platform`,
`Status` (200,686), `DateDelivered` (20,801 on 5); `<modelField>From` and `<multiModelField>To` Party
(`Identifier`, `Name`, `IsPhoneOwner` 460,315 on 14, `Role`); `<modelField>Attachment` and
`<multiModelField>Attachments` (Attachment 136,345 on 14; file MD5 through `file_id`, M15); model attribute
`deleted_state`. `Chat` (9,789 on 14) with `<multiModelField>Participants` and `<multiModelField>Messages`;
`ChatType` (Broadcast, Group, OneOnOne, Unknown) on 4 phones only. `Party.DateRead`/`DateDelivered` per
recipient (approach 4).

### 5.3 Method

#### 5.3.1 Candidate pairs of phones

Every pair of extractions in the case where at least one of: an owner identity of one appears as a party on
the other (X1), or the two share at least one party identity (X2). Pairs with neither are listed as
"no shared participants" and not matched. Two extractions of one device (approach 12) are excluded from
this approach.

#### 5.3.2 Matching keys

Per message `m` on phone X, a match on phone Y must satisfy:

| Key | Rule |
|---|---|
| K1 platform family | equal family: `sms` (Sms, Mms), `imessage`, or the app (`SourceApplication` normalised: WhatsApp, Telegram, Signal, Messenger, Instagram, Snapchat, ...). iMessage to SMS fallback is not matched across families. |
| K2 direction | complementary: on X the sender is X's owner identity and on Y the sender is not Y's owner, or the reverse. Uses 02's owner identity, not the raw flag alone. |
| K3 participants | the sender identity on Y equals X's owner identity, and Y's owner identity is among m's recipients (or m's chat is a group whose participants include Y's owner). Equality by reviewed merge or by exact normalised identifier; the second carries `identity_unreviewed`. |
| K4 content | normalised body equal, or for media messages an attachment MD5 equal. Body normalisation: NFKC, fold decorative Unicode (as 03 search), casefold, remove zero-width characters, collapse whitespace, trim. Emoji kept. |
| K5 time | `abs((t_Y − t_X) − offset_XY) ≤ τ`; before an offset is known `offset_XY = 0` and the search window is ±24 h for offset estimation only. |

Never keys: `InstantMessage.Identifier` and `Chat.Id` (X8, X9: local values that collide).

#### 5.3.3 Tiers

| Tier | Keys satisfied | Notes |
|---|---|---|
| `matched_strong` | K1 K2 K3 K4 K5 | |
| `matched_content_time` | K1 K4 K5, participants not resolvable (one side's identity missing) | `identity_unreviewed` |
| `offset_candidate` | K1 K3 K4, time outside τ but within ±24 h | used to estimate offset; not reported as a match until the offset is applied |

Distinctiveness: a body whose normalised form occurs more than 3 times on either phone, or is shorter than
10 characters, matches only at `matched_strong` (all of K1 to K5). Reasoning: X3 shows common and short bodies
outnumber distinct ones by about seven to one between A-C9 and A-C8 (515 + 52 against 76); without
participant and time agreement they pair unrelated messages.

#### 5.3.4 Assignment

Within one phone pair and one platform family, candidates form a bipartite graph. Assign greedily by
increasing `abs((t_Y − t_X) − offset_XY)`, one-to-one per pair of phones. Ties (equal score, two candidates)
are left unassigned and reported as `ambiguous_pair` with both candidates. Group messages: a message sent by
X's owner to a group can match one copy on each other phone; assignment is per phone pair, so one sender copy
can be matched once on each recipient phone.

#### 5.3.5 Clock offset per phone pair

1. Partition `offset_candidate` and matched pairs by `(pair, platform family, timestamp class)` where the
   timestamp class is `server_stamped` when at least 90 percent of the pairs in the partition have
   `abs(Δ) < 1 s`, else `device_stamped`. X7 (18 of 18 exactly zero for app messages) is the reason this
   split exists.
2. For `device_stamped` partitions with n ≥ 5: `offset = median(Δ)`, spread = `1.4826 × MAD(Δ)`; report
   n, median, spread and the inter-quartile range. n < 5: "too few pairs to estimate".
3. Drift: if n ≥ 20 over at least 30 days, fit Theil-Sen slope of Δ against time; report seconds per day with a
   bootstrap 95 percent interval (1,000 resamples, fixed seed for reproducibility).
4. `server_stamped` partitions report "times set by the service; no information about either device's clock".
5. τ = max(120 s, 3 × spread) once an offset exists; 120 s before. *Reverse if* measurement M-2c shows
   device-stamped pairs with spreads above 40 s are common, in which case τ is per partition only.

The offset is a reading about the two records, stored on the run. It never alters any timestamp; 04 and 13
may show it beside times.

#### 5.3.6 Outcomes per message

| Kind | Rule |
|---|---|
| `both_sides` | matched; carries both locators |
| `deleted_one_side` | matched and `deleted_state` differs (Intact vs Deleted or Trash) |
| `one_side_only` | no match on the counterpart phone; reasons attached (below) |
| `recovered_from_other_side` | X's copy is Deleted or carved and Y's copy is Intact: the content is shown from Y's copy, labelled with Y's locator |
| `ambiguous_pair` | tie |

Reasons attached to `one_side_only` (each computed, several can apply): counterpart has no data for that app
in that period (04 availability band); counterpart's extraction ended before the message time; counterpart's
extraction did not select that type; counterpart's conversation with the sender has a gap covering the time
(approach 3 hole detection); counterpart identity not resolved; message is in a group the counterpart
left before the time (ChatActivity `ParticipantLeft`/`ParticipantRemoved` where present).

### 5.4 What the investigator gets

In Conversations (03): a per-message badge "Also on B-C2" or "Only on this phone" with the reasons, and a
"Show both copies" view side by side with each phone's names and times. A per-pair summary: matched counts by
tier and platform, one-side-only counts with reasons, deleted-one-side count, clock offset statement.
Messages recovered from the other side appear in the conversation in place, marked "From B-C2's copy".

### 5.5 Undercuts

`clock_offset_unknown`; `server_stamped` (corroborates the message, not the device times); multi-device
accounts (a message sent from a linked computer or tablet appears on the phone as outgoing although the phone
was not used: 04 attribution where available); edits (`Label` `Edited` exists: an edited message may differ in
body between copies); recalled messages (`Label` `Recalled`); media recompression (attachment MD5 differs
between sender and recipient for apps that recompress; K4 by hash then fails, so a media message may be
`one_side_only` when both copies exist; approach 8's perceptual tier is listed as a possible match, never as
a match).

### 5.6 Measurement first

| Id | Count |
|---|---|
| M-2a | per phone pair in each case: owner-identity cross-appearance (X1) and shared parties (X2) |
| M-2b | per pair: candidate pairs by tier, by platform family |
| M-2c | per pair and partition: n, timestamp class, median Δ, spread |
| M-2d | deleted-one-side and recovered-from-other-side counts |

Local result: one pair of three (A-C9 & A-C8) has 18 distinct-body matches, all app messages, server-stamped,
none deleted on one side. Gate: **build** if the 10-report case (45 phone pairs, C(10,2), or 44 if the two C1 extractions prove to be one device;
measured on the server) yields at
least 100 `matched_strong` pairs in total or at least 10 `deleted_one_side`/`recovered_from_other_side`
results; the local three-phone figure (18) alone is **inconclusive**.

**Server result (stage A3, `measurements/a3/README.md` section 9):** in the 10-report case, 494 message pairs with an equal distinct body (at least 10 characters) within 300 s
across 8 phone pairs (P04 and P08 259, P04 and P06 74, P05 and P08 73), 82 of them with `deleted_state` differing
between the copies; 3-phone case 571 (P13 and P14 564). Gate **changed**: the volume exists; the tiered count
(`matched_strong`, M-2b to M-2d) needs 02's identities and is measured by `cb-crossev`.

**Loupe result (`measurements` m2.1 on live, 2026-11-03; `measurements/g/`):** M-2b to M-2d are **not measurable**
on real data: each live case with a real phone holds one phone (no pair). The tiers (`matched_strong`) are approach
2's and approach 2 is not built, so M-2b by tier is not measurable on any case. Untiered, on the synthetic cases:
training (1 pair) M-2a 1 owner identity seen on the other phone and 6 shared parties, M-2b 0 body-and-time pairs,
M-2d 0; phones-only (3 pairs) shared parties 6 to 8, M-2b 0, M-2d 0. The A3 server figures above (494 and 82; 571)
stand as the volume evidence; the gate stays **changed** until approach 2's tiers exist.

**Tiered server result (`cb-approaches`, 2026-11-03, `measurements/scripts/a2_tiers.py`, counts in
`measurements/a2/tiers-10-report.json`):** the 10 reports read one at a time with the keys of 5.3.2 (owner
identities from header MSISDN values and parties the report flags as the phone owner; clock offset 0 and τ 120 s,
so device-stamped pairs further apart are not counted and the figures are a lower bound). 38 of the 45 phone pairs
are candidates (5.3.1). M-2b: **814 `matched_strong`** over 6 phone pairs (A-C2 and A-C6 496, A-C5 and A-C6 163,
A-C6 and A-C3 81, A-C1a and A-C6 43, A-C8 and A-C9 26, A-C8 and A-C2 5); 20 `ambiguous_pair`. M-2d: **186
`deleted_one_side`** (A-C5 and A-C6 143, A-C1a and A-C6 43). M-2c: A-C8 and A-C9 all server-stamped; the other
five pairs device-stamped. The two C1 extractions share no match. Gate: **build** (814 of 100 needed; 186 of 10).
*Reverse if* a rerun with 02's computed owners instead of the report's owner flags gives under 100 strong matches
and under 10 deleted on one side.

**Built (`cb-approaches`, 05-S5, `message_reconciliation` version 2.2, screen "Messages across phones").** Keys
K1 to K5, tiers, assignment with ties left out, clock offsets per pair, family and timestamp class (with drift),
and the outcomes `both_sides`, `deleted_one_side` (recovered from the other copy), `one_side_only` with reasons
`counterpart_extraction_ended` and `counterpart_app_no_data`, `ambiguous_pair` and `clock_offset`. Acceptance
tests 5.8.1 to 5.8.9 pass. Measure m2.2 counts the tiers in Loupe. The per-message badge in Conversations (5.4)
is not built yet.

### 5.7 Dependencies

01, 02 (owner identity, identifier registry, message view, platform family normalisation), 04 (availability
bands, attribution), approach 3 (gap detection, optional), approach 8 (perceptual tier, optional).

### 5.8 Acceptance tests

1. Fixture pair: one SMS on X outgoing to Y's owner number, same body on Y incoming from X's owner, Δ = 40 s:
   `matched_strong`.
2. Same with equal `InstantMessage.Identifier` but different bodies: not matched.
3. Body "ok" appearing 50 times on each phone with participants and times agreeing: matched; with
   participants unresolved: not matched.
4. Five device-stamped pairs with Δ of 290, 300, 305, 310, 900 s: offset 305 s, spread from MAD, the 900 s
   pair not assigned once τ applies.
5. Eighteen app pairs with Δ = 0: partition `server_stamped`; no device offset reported.
6. Group message from X to a group with Y and Z: matched once on Y and once on Z.
7. Two candidates on Y at equal distance: `ambiguous_pair`, no assignment.
8. X copy Deleted, Y copy Intact: `recovered_from_other_side` with Y's locator; X's record unchanged.
9. Y extraction ends before X's message time: `one_side_only` with reason `counterpart_extraction_ended`.

---

## 6. Approach 3: deletion and concealment timeline

### 6.1 Question it answers

What the records show was deleted or made unreadable, when it can be placed in time, which conversations
lost a larger share of their messages than the phone's norm, which deletions a setting or feature accounts
for, and how these sit against key dates set by the investigator.

### 6.2 Data it rests on

| Source | Fields | Corpus |
|---|---|---|
| Record state | model attribute `deleted_state` (Intact, Deleted, Trash, Unknown) on every type | M10; C8 IM Deleted 802 of 2,829; Chat Deleted 23 of 94 (`c8.json` `mt_deleted`) |
| Explicit deletion time | `InstantMessage.DateDeleted` | 1 (B-C1) |
| Deletion reason | `InstantMessage.DeletionReason` (UserDeleted, UserViewed) | 153 on 3 (3-phone case) |
| Disappearing settings | `InstantMessage.SelfDestructDuration` (TimeSpan); `Label` value `SelfDestruct` | 68,258 on 2 server phones; local A-C8 all zero (M11) |
| Recalled | `Label` value `Recalled` | count not established |
| App removal | `InstalledApplication.DeletedDate` | 5 on A-C4 |
| Concealment-capable apps | `InstalledApplication.Categories` values `HideFilesPictures`, `FakeGPS`, `CleanMobile` | A-C8 2, 1, 2 (M12) |
| Device wipe | `DeviceEvent.EventType = Wipe` with `StartTime` | enum value seen; count not established |
| Power | `PoweringEvent` (On, Off) | 128 on 5 |
| Unreadable messages | `ScrambledMessageData` (`Label` only) | 7,958 on 3 |
| References to missing messages | `ReplyMessageData` (10,673 on 12), `QuotedMessageData` (10,297 on 2) nested in messages | |
| Group membership | `ChatActivity.Action` | 1,052 on 5 |
| Carved | carved records and `carvedFiles` section (01) | |

### 6.3 Method

1. **Deletion events.** For every record with `deleted_state` ∈ {Deleted, Trash}: an event with an interval
   `[earliest, latest]`: earliest = the record's own latest timestamp (message time, chat `LastActivity`);
   latest = `DateDeleted` if present, else extraction start time. Narrowing (each recorded as the reason):
   (a) an intact reply or quote to the deleted message on the same phone written after earliest does not
   narrow (the reply can survive deletion); (b) the counterpart's copy on another phone (approach 2) does not
   narrow either; (c) a device wipe event after earliest makes the wipe the latest bound only when the record
   is from storage the wipe would clear, which is not established, so wipes are shown beside, not used as
   bounds. Result: most deletions are placed only between message time and extraction; the screen says so.
2. **Explained deletions.** A deleted message is `explained_by_setting` when `SelfDestructDuration` is
   non-zero or `Label` includes `SelfDestruct`; `explained_by_view_once` when `DeletionReason = UserViewed`;
   `user_deleted` when `DeletionReason = UserDeleted`; `recalled_by_sender` when `Label` includes `Recalled`;
   else `unexplained`. A conversation is `auto_delete_active` over the span where at least one intact or
   deleted message carries a non-zero `SelfDestructDuration`.
3. **Missing referenced messages.** For each `ReplyMessageData`/`QuotedMessageData`, resolve the referenced
   message within the same chat (by the referenced id the nested record carries, by quoted body and time
   otherwise). Not found on the phone → `referenced_message_absent`: proof that a message existed that the
   extraction does not hold. Found on the counterpart phone → linked.
4. **Selective clearing score** per conversation `c` on phone P and source app A:
   - `d_c` = deleted messages / all messages in `c` (intact + deleted + carved attributed to `c`).
   - `d_0` = the same ratio over all conversations of app A on P excluding `c`.
   - Binomial upper tail `p = P(X ≥ deleted_c | n_c, d_0)`; Benjamini-Hochberg across conversations of the
     phone at q = 0.05.
   - Hole detection: inter-arrival times of intact messages in `c`; a hole is a gap longer than the 99th
     percentile of `c`'s own gaps and longer than 7 days, bounded by intact messages on both sides, inside
     the phone's data-availability band for app A (04). Holes with a counterpart copy inside them (approach
     2) are `hole_confirmed_by_counterpart`.
   - Result kinds: `selective_clearing` when BH-significant with n_c ≥ 20; `hole`; `hole_confirmed_by_counterpart`.
   - Explained deletions (step 2) are excluded from `deleted_c` and reported alongside. Reasoning: a
     conversation with disappearing messages on would otherwise always score as selectively cleared.
5. **Concealment context.** Install, purchase or deletion dates of apps in the concealment-capable categories,
   wipes, power-offs, and `ScrambledMessageData` counts per chat, on the same timeline.
6. **Key dates.** The investigator adds anchor dates (from Workspace or typed); the timeline shows events and
   intervals relative to them. Overlap of a deletion interval with an anchor is shown as "could have occurred
   before or after [anchor]" unless the interval lies wholly on one side.

### 6.4 What the investigator gets

A deletion timeline per phone and across phones: intervals (bars from earliest to latest), explained and
unexplained counts, conversations ranked by selective-clearing score with the numbers behind it, holes,
references to absent messages (each opening to the reply that proves it), concealment-capable apps and
wipes, anchors. Every item opens to its records.

### 6.5 Undercuts

Auto-delete settings and view-once (step 2); app housekeeping (some apps delete media or old messages
automatically; not distinguishable without app-specific mapping); carving recovers only some deleted
records, so `d_c` is a lower bound on deletion; differences in what each source app's decoder recovers
(deleted counts are not comparable across apps, hence the per-app baseline); `selective_extraction`;
`no_data_period`.

### 6.6 Measurement first

| Id | Count |
|---|---|
| M-3a | per phone and type: deleted_state counts (already in `c*.json` for local phones) |
| M-3b | messages with non-zero `SelfDestructDuration`; `Label` value counts (SelfDestruct, Recalled, Scrambled) |
| M-3c | `DeletionReason` value counts; `DeviceEvent` Wipe count |
| M-3d | reply and quote records whose referenced message is absent on the phone |
| M-3e | conversations with n ≥ 20 and at least one deletion; holes |

Local: A-C8 has 802 deleted messages and no disappearing setting (M10, M11). Gate: **build** if at least
three phones in the corpus each have at least 50 deleted messages or M-3d is non-zero on any phone.
A-C8 alone meets the first half on one phone; server measurement decides.

**Server result (stage A3, `measurements/a3/README.md` section 9):** deleted messages on 7 phones exceed 50 (P14 11,579, P10 7,974, P08 3,894, P03 968, P02 802, P07 195, P05
51); replies and quotes whose referenced message is absent (M-3d) on 6 phones (P14 1,648, P13 239, P10 38, P01
4, P04 2, P07 2). `Label` values: only `Default` (P01 and P14); no SelfDestruct, Recalled or Scrambled. Wipe
events: 1 each on P02, P07, P13. Conversations with at least 20 messages and a deletion (M-3e): 0 to 68 per
phone (P10 68, P14 48). Gate **pass**: build.

**Built (`cb-approaches`, 05-S6, `deletion_timeline` version 3.2, screen "Deleted and hidden").** Measure m3.2
replaces m3.1: m3.1 read `Label` and `DeletionReason` from the text table, which holds String fields only, so M-3b and
M-3c were always 0 on every case; m3.2 reads named sets and TimeSpans from the captured record body and adds M-3d
(referenced messages absent) and holes from the approach's own functions. The gate stands on the A3 server result
above (7 phones over 50 deleted messages; M-3d on 6 phones).

### 6.7 Dependencies

01 (deleted state, carved records), 02 (chat membership of messages), 04 (availability bands), approach 2
(optional confirmation of holes).

### 6.8 Acceptance tests

1. A deleted message at time t on an extraction starting at E with no `DateDeleted`: interval [t, E] and the
   sentence "deleted at some time between [t] and the extraction".
2. Same message with `SelfDestructDuration` 7 days: `explained_by_setting`; excluded from the clearing score.
3. Conversation of 40 messages with 20 deleted on a phone whose baseline is 2 percent: `selective_clearing`
   with p and BH-adjusted q in `measures`.
4. A reply whose quoted message is absent: `referenced_message_absent`, opening to the reply.
5. A 30-day gap inside an availability band with intact messages either side: `hole`; the same gap outside
   the band: no hole.
6. A Wipe event is shown and never used as an interval bound.

---

## 7. Approach 4: knowledge and awareness

### 7.1 Question it answers

When the phone's owner read or played a message, how long the owner took to reply, which correspondents'
messages were read without a reply, and who administered groups and changed their membership, as far as the
records show.

### 7.2 Data it rests on

`Party.DateRead` 19,716 on 11 phones; `Party.DatePlayed` 2,347 on 3 (1P, B-C1, B-C3); `Party.DateDelivered`
20,672 on 8; `InstantMessage.DateDelivered` 20,801 on 5; `InstantMessage.Status` (`MessageStatus`: Default,
Delivered, Opened, Read, Sent, Unread, Unsent) 200,686 on 14; `Party.IsGroupAdmin` 227,148 on 13; `ChatActivity`
1,052 on 5 (`Action`: ChatImageChanged, ChatNameChanged, ParticipantAdded, ParticipantJoined, ParticipantLeft,
ParticipantRemoved, Unknown; `<modelField>Participant`; `SystemMessageTimeStamp` 302 on 2).

### 7.3 Method

1. **Read and play events.** For incoming messages: the owner's Party in `To` with `DateRead`/`DatePlayed` gives
   the owner's read time; for outgoing: each recipient Party's `DateRead`/`DateDelivered` gives the
   recipient's. Which Party a read time belongs to is from the Party record it sits on (02 maps this per app
   version; generic interpretation otherwise, labelled as such).
2. **Reply latency.** In a one-to-one conversation, for each incoming message `i`, the reply is the first
   outgoing message `o` after `i` and before the next incoming message from the same sender (a run of incoming
   messages counts once, latency from the last of the run). Latency = `t_o − t_i`; read-to-reply =
   `t_o − DateRead_i` where present. Per correspondent: median and inter-quartile range, n.
3. **Read without reply.** Incoming messages with an owner read time and no reply within 48 hours and no
   outgoing message in the conversation within 48 hours. Per correspondent: count and share. The 48 hours is
   a parameter. *Reverse if* the latency distribution (step 2) of the case has its 95th percentile beyond
   48 hours, in which case the window is that percentile.
4. **Unread.** Incoming with `Status = Unread` at extraction.
5. **Group roles.** Per group chat: current admins (Party `IsGroupAdmin = true` among participants at
   extraction), membership changes (`ChatActivity`) with time when `SystemMessageTimeStamp` exists and the
   affected participant; the actor is shown only where the record names one (in the corpus the only party on
   the activity is `Participant`; whether that is actor or subject is not established, so it is labelled
   "participant named").

### 7.4 What the investigator gets

In Conversations: read and played times on each message (owner's and recipients'), reply latency per message.
A per-correspondent awareness table: messages received, read, read without reply, median latency. Group panel:
admins at extraction, membership changes with times where known.

### 7.5 Undercuts

Read receipts depend on app settings (a user can turn them off; absence of `DateRead` is not absence of
reading); reading on a linked device sets the read state on the phone (`synced_attribution`); notification
previews let a message be seen without being marked read; `DatePlayed` coverage is 3 phones; server-side times
versus device times (approach 2).

### 7.6 Measurement first

M-4a: per phone, share of incoming messages with an owner `DateRead`, with `DatePlayed`; M-4b: one-to-one
conversations with at least 10 reply pairs; M-4c: groups with admin flags and with timed ChatActivity. Gate:
**build** read-and-latency if at least 5 phones have owner read times on at least 20 percent of incoming
messages; **build** group roles if at least 50 timed ChatActivity records exist in a case.

**Server result (stage A3, `measurements/a3/P*.json` `s05_m4a`, `s05_m4c`; read by `cb-approaches` 3 Nov).** M-4a:
owner read times on at least 20 percent of incoming messages on 2 phones (P03 457 of 867, P04 2,471 of 4,797);
next P07 872 of 4,619 (18.9 percent); 0 to 2.2 percent elsewhere (P05, P06, P08, P09, P12 none). M-4c: timed
ChatActivity 277 on P14 (3-phone case) and 25 on P04 (10-report case). Live reference phones (m4.1, read-only): C3 0
of 1,702 and C9 0 of 2,013 incoming with an owner read time. Gate: read-and-latency **fail** (2 phones < 5);
group roles **pass** (277 >= 50 in the 3-phone case). Reverse if a case adds phones with read times on 20 percent of
incoming messages until 5 phones meet it. **Built (`cb-approaches`, 05-S7, `awareness` version 4.1-groups, screen "Group admins and
membership"):** step 5 only; steps 1 to 4 (read and play events, reply latency, read without reply, unread) are
**not built** on these numbers, and the screen says so.

### 7.7 Dependencies

02 (message view, owner identity, per-app mapping of which Party a read time belongs to), 04 (timestamp
meanings; `DateRead` as an interaction-strength event), approach 2 (server versus device stamps).

### 7.8 Acceptance tests

1. Incoming at 10:00, read 10:05, reply 10:20: latency 20 min, read-to-reply 15 min.
2. Three incoming then one reply: one latency, from the third.
3. Read, no reply for 3 days: counted in read without reply; with the window parameter at 96 h, not counted.
4. A ChatActivity with no timestamp appears in the group panel with "time not recorded".

---

## 8. Approach 5: who used which phone

### 8.1 Question it answers

Whether two phones in the case behave as one person's two devices (they are together and are used in turn),
whether one phone shows signs of more than one user, and whether a phone was used while its owner's other
phone was elsewhere.

### 8.2 Data it rests on

`Location` 63,784 on 13 phones with `Coordinate` and accuracy fields (`GpsHorizontalAccuracy` 28,656 on 5;
`Precision`, `Confidence`, `Origin`; `DeviceLocationAffiliation` Extracted/Synced/Unknown 33,877 on 8), very
unevenly spread (A-C2 42,607; B-C1 13,355; A-C9 7; A-C6 17); `WirelessNetwork.BSSId` 25,484 on 7;
`DeviceConnectivity` 193,070 on 8 (B-C1 187,649); `DeviceEvent` 135,183 on 10 (interaction classes from 04);
`InstantMessage`/`Call` outgoing; `UserAccount` 391 on 13; `Password.Account` 7,939 on 10 (account names, not
passwords); `SIMData` 87 on 9 (`Name`, `Value`, `Category`); report metadata `ICCID`, `IMSI`, `MSISDN`
(A-C3 only of the locals); `User` 12 on 3 (`UserType` Owner, `TimeLastLoggedIn`); owner identifiers (M14).

### 8.3 Method

1. **Shared identity markers** between phones X and Y (counts of equal normalised values, by kind): owner
   identifiers, account usernames, saved-login account names, SIM identifiers (ICCID or IMSI in metadata or
   SIMData), Bluetooth peer names and addresses, WiFi BSSIDs. Each kind is listed with its count; strength
   per kind: `strong` (same SIM ICCID or IMSI; same owner E.164), `medium` (same account username on a
   service), `weak` (same BSSID, same Bluetooth peer name).
2. **Co-location.** 15-minute bins. In a bin a phone is placed if it has a presence observation (04 section
   6.1; Synced points excluded unless the run includes them). Together and apart per bin come from 04
   section 8.4's verdict function, the one implementation: radius `2 × accuracy` (04 section 6.2), an
   unknown radius replaced by the run's stated assumed radius and the pair marked `assumed`; X and Y are
   `together` in a bin when the verdict is `compatible` (`d ≤ R`), `apart` only when it is `separated`
   (beyond the 40 m/s movement allowance, `d - R > v × dt`), else `indeterminate`. Statistic: `C = together / (together + apart)` over
   bins where both are placed, with n. A WiFi bin counts as together when both phones report the same BSSID
   within the bin (no position needed).
3. **Complementary use.** Per 15-minute bin, each phone's interaction indicator (04 class `interaction`).
   Over bins where both phones have data (availability bands), compute: `both`, `only_X`, `only_Y`, `neither`.
   Report the phi coefficient and the switching rate (transitions between only_X and only_Y within one hour,
   per day). One person with two devices predicts high co-location with low simultaneous interaction; the
   approach reports the numbers, not the inference.
4. **Use while apart.** Bins where X and Y are `apart` and X has an interaction event: listed with both
   phones' records.
5. **Multiple users on one phone.** Indicators listed, never scored as a conclusion: more than one owner-flagged
   phone number (distinct E.164 owners, M14 shows 5 to 10 owner identifiers per phone including app
   accounts, so only E.164 numbers count); more than one `User` record; distinct account usernames for the
   same service; SIM changes (SIMData or metadata history where present).

### 8.4 What the investigator gets

A pair view for two phones: shared markers by kind and strength, co-location statistic with the bins behind
it, complementary-use table and switching rate, periods where they were apart and one was used. A per-phone
"signs of more than one user" panel. All on the Map (03/04) and the day view.

### 8.5 Undercuts

Sparse location (most phones have few points; coverage stated); Synced points; family members sharing WiFi
and Bluetooth (BSSID and peer-name matches are weak for that reason); a shared SIM moved between phones;
interaction classes depend on 04's mapping; clock offset between phones (approach 2) at 15-minute bins is
mostly negligible but stated.

### 8.6 Measurement first

M-5a: per phone pair, bins where both are placed; M-5b: pairs with any strong marker; M-5c: pairs with at
least 7 days of overlapping interaction data. Gate: **build** co-location only if some pair has at least 200
co-placed bins; **build** complementary use if some pair has at least 14 days of overlapping interaction
data. Locally only A-C2 and B-C1 have location volume, and they are in different cases, so the local gate is
not met; server measurement on the 10-report case decides.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-5a: the most co-placed 15-minute bins for any pair is 43 (P03 and P04), and no pair shares a BSSID in a
bin; M-5b: one pair has a strong marker (P04 and P06: 2 owner E.164 numbers in common); M-5c: 43 pairs have at
least 14 days of overlapping interaction data (most: P08 and P10, 729). Gate: co-location **fail** (43 < 200);
complementary use **pass**. `cb-approaches` builds the complementary-use part (8.3 steps 1, 3 and 5: shared markers,
complementary use, signs of more than one user) and not the co-location statistic or "use while apart" (steps 2 and
4 rest on co-placed bins). Reverse if a case yields a pair with at least 200 co-placed bins. **Built (05-S8, `device_users`
version 5.2-use, screen "Who used which phone").** Tests 8.8.3 and 8.8.4 pass; 8.8.1 and 8.8.2 belong to the
co-location part, which is not built.

### 8.7 Dependencies

02 (identifier registry), 04 (uncertainty radii, attribution, activity strength, availability bands, places).

### 8.8 Acceptance tests

1. Two phones with GPS fixes 30 m apart, radii 20 m each, same bin: together; 2 km apart: apart.
2. A bin with only a Synced point: not placed by default.
3. Fixture with X used 09:00 to 12:00 and Y 12:00 to 15:00 daily, co-located: phi negative, switching rate 1 per
   day; numbers in `measures`.
4. Same ICCID in both phones' metadata: strong marker listed.

---

## 9. Approach 6: other devices and accounts in play

### 9.1 Question it answers

Which other devices (cars, headsets, computers, other phones), networks, accounts and services the phone shows
contact with, when each was first and last seen, and which of them more than one phone in the case shares.

### 9.2 Data it rests on

`DeviceConnectivity` (`DeviceName` 186,736, `DeviceType` Headset/Phone/Unknown, `ConnectivityMethod`
Bluetooth/WiFi, `ConnectivityNature` Connected/Detected/Disconnected/Paired, `StartTime`) on 8 phones;
`RecognizedDevice` 51 on 10 (`Name`, `DeviceModel`, `DeviceType`, `<multiModelField>DeviceIdentifiers`);
`WirelessNetwork` (`BSSId` 25,484 on 7, `SSId` 173 on 11, `LastConnection`, `LastAutoConnection`,
`SecurityMode`; `Password` sensitive); `RemoteServiceSession` 6 on B-C1 (`UserAgent`, `DeviceType`,
`DateStarted`, `Account`); `UserAccount` 391 on 13; `Cookie.Domain` 14,967 on 10; `Password.Service`
7,191 on 10; `FileUpload` 3,332 on 4 (`Account`, `DateUploaded`, `FileType`).

### 9.3 Method

1. Inventory per phone by kind (bluetooth peer, WiFi network, remote session, account, service): normalised key
   (Bluetooth: address if present else name casefolded; WiFi: BSSID lowercase colon form; SSID only if no
   BSSID; account: service + username normalised; service: registrable domain), first seen, last seen, count of
   events, event natures.
2. Cross-phone: same key on two or more phones; strength `strong` for BSSID and Bluetooth address, `weak`
   for names and SSIDs (common names).
3. Services without apps: a service present by cookie, saved login or account where no installed application
   for it exists (`InstalledApplication` is on 8 phones only; where the type is absent the comparison is not
   made and coverage says so).
4. Remote sessions: user agent parsed into device family and OS (a pinned parser library, offline), listed
   with account and time.

### 9.4 What the investigator gets

A devices-and-accounts panel per phone and a case-wide "shared across phones" list, each item opening to its
events; WiFi BSSIDs feed 04's places (offline reference only).

### 9.5 Undercuts

Detected is not connected (Bluetooth scans list nearby devices); device names are user-settable and not
unique; SSIDs repeat across places; accounts synced from another device.

### 9.6 Measurement first

M-6a: per phone, distinct keys by kind; M-6b: keys shared by at least two phones in a case, by kind and
strength. Gate: **build** the cross-phone list if any case has at least 5 strong shared keys; the per-phone
inventory is generic interpretation plus a view and is built with 03 regardless.

**Server result (stage A3, `measurements/a3/README.md` section 9):** keys on two or more phones: 10-report case 2 strong (owner E.164), 346 medium (account usernames 21,
saved-login accounts 325), 376 weak; 3-phone case 0 strong, 464 medium, 144 weak. Header ICCID, IMSI and
MSISDN are shared by no pair. Gate: cross-phone list **fail** (2 < 5).

**Do not build** the cross-phone list (`cb-approaches`, 2026-11-03): 2 strong shared keys against 5 needed; the
per-phone inventory stays generic interpretation. Approach 5's shared markers (05-S8) list the same strong keys per
phone pair. *Reverse if* a case reaches 5 strong keys shared by two or more phones (measure m6.1 on that case).

### 9.7 Dependencies

02, 04 (places from BSSID), 03 (views).

### 9.8 Acceptance tests

1. One BSSID on two phones: shared, strong. One SSID "Home" on two phones with different BSSIDs: listed under
   weak name matches only.
2. Detected-only Bluetooth peer is labelled "nearby, not connected".
3. Cookie for a domain with no installed app on a phone that has `InstalledApplication` data: "service without
   app"; on a phone without that type: comparison not made, stated.

---

## 10. Approach 7: what was typed, even if deleted

### 10.1 Question it answers

Which names, numbers, amounts, addresses and terms known to the investigation occur in the keyboard's learned
words or in autofill values on a phone, and which of those do not occur in any message, note or search the
extraction holds.

### 10.2 Data it rests on

`DictionaryWord` 14,260 on 4 phones (`Word`, `Frequency`, `UsagePattern` on A-C8; no time); `Autofill` 70 on 6
(`Key`, `Value`, `TimeStamp`, `LastUsedDate`). M13: words containing a digit A-C8 97, A-C9 3.

### 10.3 Method

1. Case vocabulary: names and aliases of case entities (02 identities, Loupe entities), counterparties and
   holders from the financial records, account and card endings, amounts in the ledger formatted in the
   phone's locale forms, addresses and place names from the case, and terms the investigator adds.
2. Compare each dictionary word and autofill value with the vocabulary after the 03 search fold; exact token
   match, and for numbers digit-sequence match of length ≥ 4.
3. For each hit, search the phone's own text (messages, emails, notes, searches, calendar) for the same token.
   No occurrence → `typed_not_in_extraction`. Occurrence → `typed_and_present` with links.
4. Autofill entries carry times; DictionaryWord does not, and the result says "no time recorded".

### 10.4 What the investigator gets

Per phone: hits grouped by vocabulary kind, frequency, whether the word appears elsewhere on the phone, and for
autofill the times. Values are shown masked until revealed (3.8).

### 10.5 Undercuts

Dictionaries learn from any typing on the device (other apps, other users); a word may come from a synced
dictionary; frequency is not a count of uses in a known period; absence from the extraction can be selection
rather than deletion (coverage).

### 10.6 Measurement first

M-7a: per phone, dictionary and autofill entries matching the case vocabulary, and how many have no occurrence
elsewhere. Gate: **build** if any case with these types has at least 10 vocabulary hits, or any
`typed_not_in_extraction` hit on a financial identifier ending or amount.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-7a needs the case vocabulary (02 identities and Loupe entities) and is measured by `cb-approaches`.

**Server result (`cb-approaches`, typed_words m7.3, read-only on the live reference cases, 2026-11-03).** Vocabulary
from 02 identities (names and numbers) and the case's financial records (account endings, holders, counterparties;
none in the three reference cases); Loupe case entities, ledger amounts, addresses and investigator terms are not
included, so the counts are a lower bound. The C9 phones: 639 learned words and autofill values, 37 vocabulary hits
(all on contact names), 12 of them found in no message, email, note, search or calendar entry. C3: 8 typed records, 3
hits, 0 not found elsewhere. Gate: **pass** (37, 10 needed). **Built (`cb-approaches`, 05-S10, `typed_words`
version 7.1, screen "Typed words").** 10.3 steps 1 to 4 with the vocabulary above (`vocabulary.py`); 10.8 tests 1 to 3
in `test_phone_analysis_typed_intent.py`. Results carry the kind of term matched and the masked value; the value is
seen through the record's Reveal, which is logged (3.8). Not built yet: the vocabulary parts listed as not included.

### 10.7 Dependencies

02, financial records of the case, 03 fold, 3.8.

### 10.8 Acceptance tests

1. A dictionary word equal to a counterparty name absent from messages: `typed_not_in_extraction`, masked in the
   response until a reveal is recorded.
2. A 4-digit dictionary token equal to an account ending: hit of kind `account_ending`.
3. No hit is sent to any model or the search index.

---

## 11. Approach 8: media spread across phones

### 11.1 Question it answers

Which images, videos and audio files occur on more than one phone, in what order each phone came to hold them,
which phone holds the camera original, and where and when it was taken.

### 11.2 Data it rests on

Tagged files with `MD5` (100 percent of tagged files in the local samples; SHA256 on 224, 80 and 3: plan 3.4)
and `Tags`; Attachment records (136,345 on 14) linked to files by `file_id`, `attachment_extracted_path` or
jump target (M15 resolution: A-C3 404 of 456, A-C9 759 of 874, A-C8 83 of 3,770 because its file index is
truncated and many attachments carry only a `URL`); the owning message's sender, recipients and time;
tagged-file metadata EXIF items (`EXIFCaptureTime`, `EXIFCameraMaker`, `EXIFCameraModel`, `ExifEnumGPSLatitude`,
`ExifEnumGPSLongitude`, `MetaDataLatitudeAndLongitude`; M16) and file-system times
(`CoreFileSystemFileSystemNodeModifyTime`, `...LastAccessTime`); the file's original `path` attribute.

### 11.3 Method

1. Population: files that are (a) attachment-linked, or (b) in a camera or screenshot path (original path
   matches a reviewed list of camera directories), or (c) have EXIF camera make or model. Everything else is
   excluded, because system files dominate whole-index overlap (X10 against X11).
2. Exact tier: group by MD5 (and SHA256 where both copies carry it; a SHA256 disagreement with equal MD5 is
   flagged). A group spanning two or more phones is a spread item.
3. Perceptual tier (images only): a 64-bit pHash and dHash computed locally in the engine on the file bytes;
   Hamming distance ≤ 6 on both is `visually_similar`. Reported separately and never as identical.
   Reasoning: messaging apps recompress, so exact hashes miss forwarded copies.
4. Ordering per group: for each phone, the earliest of (owning message time, file-system modify time, EXIF
   capture time) with the field named. Order across phones uses approach 2's offsets where device-stamped;
   otherwise times are shown unadjusted with `clock_offset_unknown`.
5. Camera original: a copy with camera EXIF, in a camera path, whose EXIF capture time precedes all message
   times in the group: `camera_original_candidate`. A copy arriving as an incoming attachment is `received`;
   outgoing is `sent`. Where the message is gone but the file remains (attachment-linked file whose message is
   deleted, or a file in a messaging app's media folder with no message), the item says so.
6. Place: EXIF GPS and 04's place model; shown with source "photo EXIF".

### 11.4 What the investigator gets

A spread view: each media item with a thumbnail (from Media, 03), the phones holding it, the order, sent and
received links with the participants, camera original candidate, place and time; opens to messages and files.

### 11.5 Undercuts

Recompression (exact tier misses); stickers, memes and forwarded viral images are common across unrelated
people (reported with a "common file" flag when the same hash appears on more than half the phones in the case);
EXIF can be edited or stripped; file-system times change on copy; perceptual false matches on simple images.

### 11.6 Measurement first

M-8a: attachment-linked, camera-path and EXIF-camera files per phone; M-8b: exact groups spanning phones in
that population; M-8c (engine): perceptual groups. Local result: 4 attachment-linked exact matches, one pair
(X11). Gate: **build** exact tier if the 10-report case yields at least 25 cross-phone exact groups in the
population; **build** perceptual tier only if a sample of 20 attachment pairs known to be the same message
(from approach 2's `both_sides` media messages) shows exact MD5 failing on at least a quarter of them.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-8a per phone: attachment-linked files with MD5 40 to 12,011, camera-path or EXIF-camera files with MD5 0
to 1,115; M-8b: 112 exact groups spanning phones in the 10-report case, 46 in the 3-phone case. Gate: exact tier
**pass** (112 >= 25); the perceptual tier needs approach 2's `both_sides` sample and is measured by `cb-crossev`.

**Perceptual-tier gate (cb-media, `measurements/m8-perceptual-gate.md`, scripts `scripts/p8_extract.py` and
`scripts/p8_cross.py`, 3 Nov):** **not met; the perceptual tier is not built.** Every phone pair of the 10-report
and 3-phone cases was matched by approach 2's rules (same family, opposite directions, within 120 s, ties left
unmatched; content not used). The corpus holds no 20 such media pairs: with 5.3.2's K3 rule, 58 pairs, of which 14
have an MD5 on both sides and 1 of 14 (7.1 percent) differs (44 lack the file on one side); with the loosest rule
tried (receiver side only), 3 of 17 (17.6 percent). Images alone: 1 of 3 and 3 of 6. Reverse if a case yields at
least 20 image pairs with an MD5 on both sides of which at least a quarter differ.

**Loupe result (`measurements` m8.1 on live, 2026-11-03; `measurements/g/`):** M-8a on the live reference phones:
C3 2,497 and C9 3,017 attachment-linked files with an MD5; M-8b 0 groups spanning phones (one phone per case).
Synthetic cases: 5 groups spanning phones in each. M-8c on the live cases adds nothing to the corpus result above:
no live case holds two real phones.

### 11.7 Dependencies

01 (file resolution and hash verification), 03 Media, 04 (places), approach 2 (offsets, media message pairs),
17.4 (engine for perceptual hashing).

### 11.8 Acceptance tests

1. Same MD5 on two phones, attached to an outgoing message on X and an incoming one on Y: spread item, sent and
   received, ordered.
2. Same MD5 for a system file on all phones: excluded from the population.
3. Copy with camera EXIF earlier than all messages: camera original candidate.
4. Recompressed copy (fixture JPEG re-encoded at quality 70): not in exact group; in `visually_similar`.

---

## 12. Approach 9: intent and research

### 12.1 Question it answers

What the phone shows was searched for and which pages were visited, how often, and how those that carry a
time sit against key dates.

### 12.2 Data it rests on

`SearchedItem` 13,067 on 12 (`Value` 12,352; `TimeStamp` 3,083; `Origin`; `SearchResults` 1,031; `Source`);
`VisitedPage` 100,801 on 12 (`Url`, `Title` 5,675, `LastVisited` 70,147, `VisitCount` 34,120, `UsagePattern`
13 on 3); `WebBookmark` 98 on 12.

### 12.3 Method

1. Terms: case vocabulary (as approach 7) plus investigator-added terms; fold and token match on search values,
   page titles and URL path tokens.
2. Each hit carries its time field and meaning from 04: `SearchedItem.TimeStamp` when present; for pages
   `LastVisited` is "most recent visit only", with `VisitCount` as the total.
3. Relative to anchors: a search with a time before an anchor is listed as "before"; a page whose last visit is
   after an anchor is listed as "last visited after; earlier visits not dated", never as "visited before".

### 12.4 What the investigator gets

Hits by term with times and counts; an all-searches list with time where recorded; anchors on the same timeline.

### 12.5 Undercuts

`LastVisited` semantics; 76 percent of searches undated (3,083 of 13,067); suggested searches and prefetching
create records without typing (`Origin` where present); synced browser history from another device.

### 12.6 Measurement first

M-9a: per phone, searches with and without time; pages with title, with visit count; M-9b: hits on the case
vocabulary. Gate: generic interpretation already lists these; the term-matching view is **built** if any case
has at least 10 vocabulary hits.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-9a: pages 0 to 55,590 per phone (P11), with title up to 2,621 (P02); searches with time up to 897,
without time up to 7,884 (P11). M-9b needs the case vocabulary and is measured by `cb-approaches`.

**Server result (`cb-approaches`, intent m9.3, read-only on the live reference cases, 2026-11-03).** Vocabulary as
approach 7 (10.6). C3: 399 hits (3 searches, 396 pages, 340 of the pages only through words in the page address), 29
distinct terms, 17 of them matching fewer than 3 records (specific terms, 20 hits). The C9 phones: 57 hits (1 search,
56 pages), 4 distinct terms, 1 specific. Page addresses are matched on their path words only: with any 4-digit run
counted as a phone-number hit, 5,866 C3 addresses matched 3,523 distinct numbers. Gate: **pass** (399 and 57, 10
needed; 20 on specific terms). **Built (`cb-approaches`, 05-S12, `intent` version 9.1, screen "Searches and
pages").** 12.3 steps 1 to 3 with the vocabulary of 10.3; 12.8 tests 1 and 2 in `test_phone_analysis_typed_intent.py`
(server) and `TypedIntentPages.test.tsx` (screen). Investigator-added terms are not built yet.

### 12.7 Dependencies

02, 03, 04.

### 12.8 Acceptance tests

1. A page with `LastVisited` after an anchor and `VisitCount` 5 is never shown as visited before the anchor.
2. An undated search appears in the list under "time not recorded" and never on the timeline.

---

## 13. Approach 10: plans and self-reported places

### 13.1 Question it answers

What the phone's calendar, social check-ins and notes say a person planned or reported doing, where those carry
a place, and how they compare with the phone's own location and activity at the same time.

### 13.2 Data it rests on

`CalendarEntry` 1,000 on 11 (`StartDate`, `EndDate`, `Subject` 993, `Details` 417, `RepeatRule` 255,
`RepeatDay`, `RepeatInterval`, `RepeatUntil`, `Location` 3 on 1, `Availability`); `SocialMediaActivity` 2,111 on
5 (`SocialActivityType` CheckIn, Comment, Post, Update; `TimeStamp`, `Body`, `Title`, `Url`, `Account`); `Note` 31
on 7 (`Title`, `Body`, `Creation`, `Modification`, `Folder`).

### 13.3 Method

1. Expand repeating entries over the case period (RFC 5545 semantics for the stored rule fields; occurrences
   generated only up to `RepeatUntil` or the extraction date).
2. Entries with a place (calendar `Location`, check-ins with a place in their nested record where one exists)
   are geocoded only from offline reference data or the case's own place list (standing decision 8); unresolved
   places stay text.
3. Compare each dated, placed item with 04's place model over its window: `consistent`, `inconsistent`
   (phone placed elsewhere with non-overlapping uncertainty), `no_data`.
4. Notes: amounts and names detected as in approach 7's vocabulary and approach 1's parser; money in notes is a
   p4 reading (approach 1 S9 path), never a ledger row.

### 13.4 What the investigator gets

Plans and check-ins on the day view and timeline; per item the comparison with location; notes with detected
amounts and names.

### 13.5 Undercuts

Calendar entries are plans, not attendance; shared and subscribed calendars (`Account`); check-ins can be made
from elsewhere; place text is ambiguous.

### 13.6 Measurement first

M-10a: per phone, calendar entries with location, check-ins (by type), notes; M-10b: check-ins with a place.
Gate: **build** the comparison if any case has at least 20 placed items on phones that also carry location;
otherwise these types remain generic interpretation only. Calendar location (3 values) alone will not meet it.

**Server result (stage A3, `measurements/a3/README.md` section 9):** calendar entries with a location: 3 (P06); check-ins: 9 on P02, P13 and P14, none with a nested place
record; notes 0 to 13. Gate **fail** (3 placed items < 20).

**Do not build** the comparison (`cb-approaches`, 2026-11-03): 3 placed items against 20 needed; calendar entries,
check-ins and notes stay generic interpretation. *Reverse if* a case holds 20 placed items on phones that also
carry location (measure m10.1 on that case).

### 13.7 Dependencies

04 (places, day view), approach 1 parser, approach 7 vocabulary.

### 13.8 Acceptance tests

1. A weekly entry with `RepeatUntil` expands to the right number of occurrences.
2. A check-in placed 50 km from a GPS fix of 20 m accuracy in the same hour: inconsistent.

---

## 14. Approach 11: relationships over time

### 14.1 Question it answers

For each person in the case and each phone: when the contact was saved and last modified, what each phone calls
them, when contact began and ended, how its volume changed, which calls fall immediately around key events, and
whether contact stops when a statement says it did.

### 14.2 Data it rests on

`Contact` 43,624 on 13 (`Name`, `TimeCreated` 4,996 on 8, `TimeModified` 979 on 6, `Notes` 4,569 on 9, `Type`,
`InteractionStatuses`, `Account`, nested `PhoneNumber` 29,788, `UserID` 41,251, `EmailAddress` 106); `Call`
30,205 on 14 (`Direction`, `Status`, `Duration` 26,415, `TimeStamp`, `VideoCall`, `Source`); messages (approach 2
data).

### 14.3 Method

1. Per (phone, identity): contact saved time (`TimeCreated`), last modified (`TimeModified`), the name the phone
   uses, the names other phones use (by 02 identity), first and last call and message, monthly counts by channel
   and direction.
2. Change detection on weekly counts: a PELT changepoint (Poisson cost, penalty BIC) with each changepoint's
   before and after rates. Last contact versus statement dates (04's statement check takes a claim "no contact
   with X after D" and this approach supplies the supporting and contradicting records and the data gaps).
3. Around an anchor: calls and messages with that identity within ±N hours (parameter, default 6), and the
   phone's calls with anyone in the same window, ranked by time distance.

### 14.4 What the investigator gets

A relationship card per person per phone; a cross-phone names table ("how each phone names this person"); a
volume chart over time with changepoints; anchor views. Every count opens to its records.

### 14.5 Undercuts

No rename history (only the current name and last modification); `TimeCreated` absent on 5 of 13 phones with
contacts; contact through apps not extracted; numbers shared by more than one person; deleted call logs (approach 3).

### 14.6 Measurement first

M-11a: per phone, contacts with created and modified times; M-11b: identities with at least 20 communications on
some phone; M-11c: identities named differently on two phones. Gate: **build** if at least 3 phones have created
times and at least 10 identities meet M-11b in a case.

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-11a: contacts with a created time on 6 phones of the 10-report case (P11 2,357, P10 1,530, P04 529, P03
182, P02 10, P07 7) and 2 of the 3-phone case (P13 280, P14 101). The first half of the gate is met; M-11b and M-11c need 02's
identities and are measured by `cb-approaches`.

**Loupe result (`measurements` m11.1 on the live reference phones, read-only, `measurements/g/`).** M-11b: 16
identities with at least 20 communications on C3 and 37 on C9, both phones of the 10-report case. With M-11a's six
phones with created times in that case, the gate **passes**: build. M-11c (identities named differently on two
phones) needs two phones of one case in Loupe; none of the live cases with a real phone holds two, so it is counted
on the synthetic cases when the approach runs and is not a gate input. **Built (`cb-approaches`, 05-S9, `relationships` version 11.2, screen
"Relationships over time").** Measure m11.2 adds M-11a's created times per phone and M-11c.

### 14.7 Dependencies

02 (identities, names per phone), 04 (statement check), approach 3 (deletion caveats).

### 14.8 Acceptance tests

1. Weekly counts 10, 10, 10, 0, 0, 0: one changepoint at week 4.
2. Two phones name one identity differently: both names shown with the phone.
3. Statement "no contact after D" with a call after D: contradicting record listed with its source.

---

## 15. Approach 12: extraction comparison

### 15.1 Question it answers

Whether two extractions are of the same device, and if so which records appear in one and not the other, which
changed state between them (for example intact then deleted), and how much of the difference the extractions'
own selections and decoder versions account for.

### 15.2 Data it rests on

Extraction metadata items (`IMEI`, `ICCID`, `IMSI`, `MSISDN`, `DeviceInfoAndroidID`, `Bluetooth MAC Address`,
`Mac Address`, `Factory number`, `Model`, `Vendor`, `DeviceInfoSelectedManufacturer`,
`DeviceInfoSelectedDeviceName`, `DeviceInfoExtractionStartDateTime`, `DeviceInfoExtractionEndDateTime`,
`ExtractionType`, `UFED_PA_Version`, `ProjectStateExtractionId`), `extractionInfo` attributes
(`IsSelectiveExtraction`, `IsPartialData`, `IsStoppedByUser`, `IsTriageExtraction`), root attributes
(`reportVersion`, `extractionType`), owner identifiers, account usernames, installed application identifiers,
WiFi BSSIDs; every captured record.

Corpus case: A-C1a and A-C1b. Also the two exports of A-C8 (local and server), which give a control: same
extraction, different export and producer (the local export carries `SelfDestructDuration` on all 2,829 messages,
the server export's catalogue does not list that field: `cat_c8.json` against `measurements/catalogue-14-phones.json`).

### 15.3 Method

1. **Device identity check.** Compare hardware identifiers present in both: any equal IMEI, serial or Android ID
   → `same_device_established`; any present in both and different → `different_device`. If none present in both
   (A-C9 and A-C8 carry none), compare content markers: owner E.164 numbers, account usernames, installed
   application identifiers (Jaccard), WiFi BSSIDs (Jaccard). `same_device_indicated` when the owner E.164 set is
   equal and non-empty and application Jaccard ≥ 0.6; else `undetermined`. Thresholds are parameters.
   *Reverse if* the measurement on A-C1a and A-C1b shows a different separation.
2. **Same extraction, different export** (equal `ProjectStateExtractionId`): compare type and field coverage
   (registry entries per export) and record counts; differences are attributed to the producer, not the device.
3. **Record keys.** Report record ids are not assumed stable across extractions (not established, section 20).
   Natural key per type from 02's reviewed mapping (for messages: source app, chat key, sender identity,
   instant, body hash; for calls: identity, instant, direction, duration; for contacts: source, account, name,
   sorted identifiers); types without a mapping use a generic key: type + sorted (field, value) pairs excluding
   fields marked volatile in the registry (counters, last-access times).
4. **Diff kinds.** `present_in_both`, `only_in_earlier`, `only_in_later`, `state_changed` (equal key,
   `deleted_state` differs), `field_changed` (equal key, a non-volatile field differs, both values shown).
5. **Attribution of differences.** For each `only_in_*` record: covered by the other extraction's selection?
   (selected types and ranges); type decoded by the other producer version? (registry); record time after the
   earlier extraction's end (`only_in_later` and newer than the earlier extraction: "created after the first
   extraction"). Remaining records are `unexplained` and listed first.

### 15.4 What the investigator gets

An extraction comparison page: identity check result with the identifiers compared, summary per type, records
that disappeared between extractions with attribution, state changes (intact then deleted), new records after
the first extraction.

Two other surfaces read this result:
- **Comparing phones for a person or a pair** (07 J-16): the per-pair counts "on both", "only on one (reason)"
  and "only on the other" equal this approach's `present_in_both`, `only_in_earlier` and `only_in_later`
  counts for the same pair and scope.
- **Links from a replaced copy** (01 section 10.7; 07 CO-9a and CO-9b): a Workspace link to a record of a
  replaced report shows "from a replaced copy" and offers the record with the equal natural key (15.3 step 3)
  in the newer report. When no record has an equal key it says so and offers none.

### 15.5 Undercuts

Different extraction methods (logical against file system) recover different data; different PA versions decode
differently; selective extractions; device reset between extractions.

### 15.6 Measurement first

Run on the server (Neil), read-only: M-12a identity identifiers present in each of A-C1a and A-C1b and whether
equal (report equal / different / absent, never values); M-12b content-marker overlaps (counts and Jaccard);
M-12c record-id overlap between the two reports (count of equal ids); M-12d the same three on the two A-C8
exports. Gate: **build** only if M-12a or M-12b classifies A-C1a and A-C1b as the same device, or another case
supplies two extractions of one device. M-12c decides whether natural keys are needed (they are, unless ids
overlap above 95 percent on the A-C8 control).

**Server result (stage A3, `measurements/a3/README.md` section 9):** M-12a: IMEI, IMSI and MSISDN are present in one of the two C1 reports and absent in the other; ICCID,
Android ID, Bluetooth and WiFi MAC and factory number are absent in both, so identifiers cannot classify the
pair. M-12b: 4 equal content markers over 23 record types, overall Jaccard 0.0002. M-12c: 0 equal record ids
(9,910 and 15,206). M-12d cannot be measured: the second C8 export exists only on the Mac. Gate **fail**: the
two C1 reports are not shown to be one device, and no other case supplies two extractions of one device.
Natural keys are needed (record ids do not overlap).

### 15.7 Dependencies

01 (metadata capture, extraction info), 02 (registry, natural-key mappings), 03 (Extraction profile).

### 15.8 Acceptance tests

1. Equal IMEI: `same_device_established`; equal IMEI with different serial: flagged contradiction, `undetermined`.
2. Message intact in earlier, deleted in later: `state_changed`.
3. Record newer than the earlier extraction's end: `only_in_later` with "created after the first extraction".
4. Type not selected in the earlier extraction: its later-only records attributed to selection.
5. J-16 equality: on a synthetic pair, the compare-phones counts equal this approach's diff-kind counts.
6. CO-9b: after Replace, a link to a record of the older report offers the record with the equal key in the
   newer one; a record with no equal key offers none and says so.

---

## 16. Approach 13: incident window

### 16.1 Question it answers

What every phone in the case recorded, by any signal, in a window around one anchor time, and where each phone
has no data in that window.

### 16.2 Data it rests on

All timestamped records (generic interpretation, plan 6.4), 04's activity strength and availability bands.

### 16.3 Method

**Entry points** (07 J-5): "Open the window around this" from a record, a key date (04 section 8.6) or the
Timeline Lanes; from a ledger payment (a date-only anchor opens the whole day and says "This payment has a
date but no time. Showing the whole day."); from a statement claim (its window, 04 section 9); and from this
approach's own screen with a typed anchor. Each entry opens the same view with the anchor and its zone named.

The 04 day view generalised, drawn with the shared Lanes component (04 section 8.6), to: all phones, a window `[anchor − before, anchor + after]` (defaults 2 h each,
up to 7 days), one lane group per phone, lanes per class (interaction, device state, communications, places,
money), approach 2's offsets shown beside times (not applied), availability bands drawn per phone so that no
data reads as no data. Counts per phone and class; filter by identity.

### 16.4 What the investigator gets

One screen around an anchor with every phone; export of the window (03 export) with sources.

### 16.5 Undercuts

Clock offsets; synced records; selective extractions; time zone of each phone (04).

### 16.6 Measurement first

M-13a: for three anchors chosen by the investigator in the 10-report case, records per phone in ±2 h. Gate: built
as part of 04's day view work; the measurement only sets the default window.

**Server result (cb-pol, `measurements/m13a-window.json`, script `scripts/pol_m13a_window.py`).** No investigator
has chosen anchors yet, so the three were chosen by a stated rule and are labelled `rule` in the file: the UTC hours
when the most phones of the case hold a record within 2 hours either side, ties to more records then the earlier
hour, at least 7 days apart. Items are time values with an offset inside the window (one per record and time field,
as the lanes draw them); records whose first-to-last range overlaps the window are kept beside them and are inflated
by long-running records such as conversations. Across the 10 reports:

| Window | Phones with items (of 10), per anchor | Items, median phone | Items, busiest phone |
|---|---|---|---|
| ±1 h | 8, 9, 7 | 132, 98, 16 | 563, 629, 358 |
| ±2 h | 9, 9, 9 | 209, 174, 36 | 945, 1,057, 428 |
| ±6 h | 9, 9, 9 | 441, 624, 153 | 2,346, 3,248, 999 |
| ±24 h | 9, 9, 9 | 1,390, 1,875, 376 | 8,218, 8,205, 3,185 |

**Default window: ±1 h.** It already shows items on 7 to 9 of the 10 phones and keeps the busiest lane under 650
items; ±24 h passes the 5,000-item lane limit on the busiest phone, so that lane would show hourly counts instead
of items. ±2 h, ±6 h and ±24 h stay one click away. *Reverse if* the same measure on three anchors an investigator
chooses shows phones with nothing at ±1 h that ±2 h would show; the script takes the anchors as arguments
(`measure <scratch> <out> <epoch seconds> ...`).

**Built (`cb-approaches`, 05-S16, screen "Incident window").** The 04 window view (shared Lanes, availability per
phone, the money lane) on its own screen with a typed moment, opened from a statement (its own start, end and zone),
a selected message or call in Conversations, and, as before, a key date and the Timeline. With no moment chosen it
opens around the latest moment on the case's phones and says so. Default ±1 h (16.6). Approach 2's offsets are not
drawn beside the times yet.

### 16.7 Dependencies

04 (day view), approach 2 (offsets).

### 16.8 Acceptance tests

1. A phone with no data in the window shows a "no data" band, not an empty lane.
2. Window of 7 days loads every record under the filter (plan 10.2: complete results when filtered), with the
   total stated.
3. J-5c: the incident window opens from a statement claim with the claim's window and zone, and from a key
   date, record and Timeline Lanes with the same anchor; each entry shows the same counts per phone and class.

---

## 16a. Approach 14: common contacts

### 16a.1 Question it answers

Who links person A and person B: the identities that both are in contact with, on any phone in the case, with
the volume and the first and last contact on each side (contact chaining, one step).

### 16a.2 Data it rests on

`Call` 30,205 on 14 phones (`TimeStamp`, `Direction`, `Duration`, parties); `InstantMessage` 377,648 on 14
(`<modelField>From` and `To` parties, `TimeStamp`); `Email` 25,727 on 12; `Contact` 43,624 on 13 (saved
entries, not contact events); 02's identities, reviewed identity-to-dossier links and owner of each
extraction.

### 16a.3 Method

1. Resolve A and B to their identities (dossier links, 02 section 8) and the extractions they own.
2. For each identity X other than A and B: communications between A and X and between B and X, from both
   sides of every phone in the case (a message present only on X's phone counts, marked "seen on the other
   phone"), by channel and direction, with first and last instant.
3. X is a common contact when both sides have at least one communication in the window (parameter, default
   the whole span). A saved contact entry with no communication is listed separately as "saved, no contact
   seen".
4. Rank by the smaller of the two sides' counts, then by recency; every count opens to its records.

### 16a.4 What the investigator gets

A table: common contact, counts with A and with B by channel, first and last on each side, the phones the
records come from; an "Add to…" on any row. The agent's "who links A and B" tool reads the same result
(07 section 7.1, XF-3).

### 16a.5 Undercuts

`identity_unreviewed` when X's identifiers are joined only by normalised identifier; apps not extracted;
selective extractions; numbers shared by more than one person; deleted call logs (approach 3).

### 16a.6 Measurement first

M-14a: per case, per pair of owner identities, the number of identities with at least one communication on
both sides; M-14b: the share of those that rest on an unreviewed identity join. Gate: **build** if at least
one case has a pair of owners with 3 or more common contacts.

**Corpus result (`cb-approaches`, `measurements/scripts/m14_16.py` over the a2 extracts of the 10-report case,
2026-11-03, `measurements/a2/m14-16-10-report.json`).** Messages only (the extracts hold no calls or emails), so
counts are a lower bound. 10 phones, 8 owners (phones sharing an owner identity are one owner), 28 owner pairs: 21
have 3 or more common contacts, the most 36. M-14b: 1.0, by construction: the corpus joins identities by equal
normalised identifier only, never by a reviewed decision. Gate: **pass** (21 pairs with 3 or more). **Built
(`cb-approaches`, 05-S16a, `common_contacts` version 14.1, screen "Common contacts").** Every pair of the case's
owners (19.S16a-a), whole span (19.S16a-b); 16a.8 tests 1 to 3 in `test_phone_analysis_common_contacts.py`. A message
held on both phones is counted on each phone and the result says so; counting it once needs approach 2's matches,
which approach 15 uses. The agent's "who links A and B" tool does not read this result yet.

### 16a.7 Dependencies

02 (identities, dossier links, owners), approach 3 (deletion caveats).

### 16a.8 Acceptance tests

1. A calls X and B messages X: X listed with both counts; Y called only by A is not listed.
2. A message from B to X present only on X's phone counts and is marked "seen on the other phone".
3. A saved contact X on A's phone with no communication is listed as "saved, no contact seen", not as a
   common contact.

---

## 16b. Approach 15: directional from/to frequency matrix

### 16b.1 Question it answers

Who contacts whom, and how often in each direction: a square association matrix over the case's identities,
rows "from" and columns "to" (research note 09 section 5, telephone analysis and the frequency matrix).

### 16b.2 Data it rests on

As 16a.2: calls, messages and emails with their parties and direction, and 02's identities.

### 16b.3 Method

1. Population: the owners of the case's extractions and every identity with at least N communications
   (parameter, default 1) in the window.
2. Cell (X, Y) = count of communications sent or placed by X to Y, by channel, with the call total duration
   for calls. A message counted from both phones is counted once (approach 2's matches); unmatched copies
   count once each.
3. Calls by status (answered, missed, rejected) are separate counts in the cell, never summed into
   "contact".
4. Row and column totals; the asymmetry per pair (X to Y against Y to X) is stated as two counts, never as
   a ratio alone.

### 16b.4 What the investigator gets

The matrix with sortable rows and columns, the "Sent by" and "Sent to" counts on each person (07 J-2, J-3),
and every cell opening to its records.

### 16b.5 Undercuts

`clock_offset_unknown` does not apply (counts only); approach 2's matching decides double counting, so
unmatched copies of one message on two phones count twice and the result says how many such copies exist;
`identity_unreviewed`; apps not extracted; selective extractions.

### 16b.6 Measurement first

M-15a: per case, the number of identities in the population at N = 1 and N = 5; M-15b: the share of
message pairs counted on two phones that approach 2 matches. Gate: **build** if a case has at least 3 owners
with communications between them; M-15a sets the default N.

**Corpus result (`cb-approaches`, `m14_16.py`, 10-report case, messages only).** M-15a: 8,502 identities at N = 1
and 5,519 at N = 5 (owners included); 8 owners in contact with another owner over 9 owner pairs. M-15b: 3,193 message
copies between owners on the phones; approach 2 matched 814 pairs of them as strong (1,628 copies, about half; the
rest count once each and the result says how many). Gate: **pass** (8 owners with communications between them, 3
needed). **Built (`cb-approaches`, 05-S16b, `contact_matrix` version 15.1,
screen "Who contacts whom").** One result per non-empty cell, in each direction; calls by recorded status with the
connected minutes; approach 2's matched messages counted once and unmatched copies between owners stated; 16b.8 tests
1 to 3 in `test_phone_analysis_contact_matrix.py`. The square grid view is not drawn: each cell is a row that sorts
and opens to its records.

### 16b.7 Dependencies

02 (identities), approach 2 (cross-phone matching).

### 16b.8 Acceptance tests

1. X sends Y 3 messages and Y calls X twice, one missed: cell (X, Y) messages 3; cell (Y, X) calls 2 with
   missed 1.
2. One message present on both phones and matched by approach 2 counts once.
3. Cell totals equal the record query under the same scope.

---

## 16c. Approach 16: number switching

### 16c.1 Question it answers

Whether one person appears to move from one number or account to another: an identity whose contact stops
while another identity, with a similar set of counterparts, starts near the same time.

### 16c.2 Data it rests on

As 16a.2, with first and last communication per identity and per (identity, counterpart); 02's identities;
`Contact` saved entries that hold two numbers under one entry.

### 16c.3 Method

1. For each identity X with a last communication before the end of the data, and each identity Y whose first
   communication falls within a gap parameter (default 14 days) after X's last: the counterpart sets of X
   before its end and of Y after its start, each over a window (default 90 days).
2. Jaccard similarity of the two sets and the count of shared counterparts. A pair is listed when the
   similarity is at least a threshold (default 0.5) and shared counterparts are at least 5 (parameters).
3. Supporting markers listed beside the pair: a saved contact entry holding both identifiers; the same
   display name on one phone for both; X and Y never active on the same day.
4. Nothing is merged. A listed pair is a lead; joining the identities is a 02 identity decision made by a
   person.

### 16c.4 What the investigator gets

Candidate pairs with the gap, the similarity, the shared counterparts and the markers, each opening to the
records; "Add to…" and the identity-link action of 03 section 10.

### 16c.5 Undercuts

Counterparts who changed phone together; a group chat that makes many counterparts shared; short data
spans; a phone whose data starts or stops (availability bands, 04 section 5) creating artificial starts and
stops; `identity_unreviewed`.

### 16c.6 Measurement first

M-16a: per case, identities whose last communication falls before the case's last data by more than the
gap; M-16b: for those, the distribution of Jaccard similarity with identities starting within the gap;
M-16c: the same on shuffled start times, as a base rate. Gate: **build** only if M-16b has pairs above the
threshold at a rate clearly above M-16c; M-16b and M-16c set the defaults. *Reverse if* the base rate equals
the observed rate.

**Corpus result (`cb-approaches`, `m14_16.py`, 10-report case, messages only, defaults gap 14 days, window 90
days, threshold 0.5, at least 5 shared).** M-16a: 8,428 identities stop more than 14 days before the case's last
message. M-16b: 1,118,315 candidate pairs; 3 at or above the threshold with 5 or more shared counterparts. M-16c (start
times shuffled 20 times, fixed seed): 0 such pairs in every shuffle (mean 0.0, most 0). Gate: **pass** (3 against a
base rate of 0); the defaults stand. Most candidate pairs share only the phone's owner (Jaccard 0.9 to 1.0 on
single-counterpart sets: 267,536), which the 5-shared minimum removes. **Built (`cb-approaches`, 05-S16c,
`number_switching` version 16.1, screen "Possible number changes").** 16c.3 steps 1 to 4 with these defaults; a stop
or start within the gap of the end or start of a phone's data is not counted (16c.8 test 2); nothing is joined; 16c.8
tests 1 to 3 in `test_phone_analysis_number_switching.py`. The identity-link action of 03 section 10 is not offered
from the row yet.

### 16c.7 Dependencies

02 (identities, identity decisions), 04 (availability bands).

### 16c.8 Acceptance tests

1. Fixture: X talks to 8 counterparts until day 30; Y talks to 7 of them from day 35: pair listed with
   similarity and shared count.
2. An identity that stops because the phone's data stops is not paired (availability band boundary).
3. Listing a pair changes no identity; a link made from it is a recorded 02 decision.

---

## 17. Section 13: closing the gaps

### 17.1 Raw record view

Every approach result, message, event and point opens to its captured record (01 owns the endpoint). This file
requires the view to show: all fields in report order with every value and its data type (all values of
multi-value fields); model attributes (`id`, `deleted_state`, `decoding_confidence`, `extractionId`,
`source_index`, `file_id`, `labels`, `isrelated`, `originalId`); the parent chain for nested records; jump
targets resolved to tagged files with the file's original `path`, local path, MD5 and SHA256, and
verification state (match, mismatch, missing on disk); the extraction's report version and producer; and a
"source" panel (17.2). Nothing captured is unreachable (plan 6.4).

Acceptance: a nested Party opens with its parent message and chat; a file whose bytes are absent shows "listed in
the report, not present in the production".

Built (05-S2). The record panel (`services/phone/records.record_detail`, `RecordPanel`) shows every field in report
order with every value and its type, all model attributes under "Everything the report says about this record", the
records it sits inside nearest first ("Inside", each opening its own record), the report file with its SHA-256, the
producer, report version and extraction type, and for each linked file the production path, the path on the phone
(the report's `path`), MD5 and SHA-256 as stated and as computed, and its check result. An absent file reads "The
report refers to a file that is not in the production.", the sentence Media and the record panel already share; it
says the same as the acceptance wording, and one sentence across screens keeps them consistent. Tests:
`test_phone_media.py` (nested record, producer, original path, hashes) and `RecordPanel.test.tsx`.

### 17.2 Source database view

**Measured on the local samples:**

| | A-C3 | A-C9 | A-C8 |
|---|---|---|---|
| Tagged files tagged `Database` | 0 | 0 | 1,081 (682 `.db`, 243 no extension, 57 `.workdb`, 45 `.events`, ...) |
| Well-known app databases by original file name (e.g. `msgstore.db`, `mmssms.db`, `contacts2.db`, `History`, `Cookies`) | 0 | 0 | 81 |
| Database files present on disk | n/a | n/a | **0**: `files/Database/` exists and is empty; only `files/Application` (1,734 files), `files/Image` (32), `files/Video` (2) are populated |
| Record-to-source sections | `extraInfos` empty | `extraInfos` empty | `.xmlExtra`, `.xmlModelSource`, `.xmlNodeSource` are zero bytes |
| Top-level records with a file jump target | | | 163 of 37,013; none resolves to a Database file (`measurements/scripts/s05/fileid.py`) |

The plan's statement that "C8 has a database folder" is true of the folder and not of its contents. No local
sample allows opening the source row of any record.

Specification (conditional on data that the corpus does not yet contain):

1. A record links to a source database when (a) a jump target with `ismodel="false"` resolves to a tagged file
   tagged `Database`, or (b) an `extraInfo` for the record names a source node (PA writes source information
   there in some exports; the element and attribute names are not established from the corpus, section 20).
2. The file must be present and its MD5 must verify (01). Otherwise the panel says which of those failed.
3. The database is opened read-only from a copy in the job's scratch area: SQLite URI
   `file:<copy>?mode=ro&immutable=1`, `PRAGMA query_only = ON`, extension loading disabled, a 5-second
   statement timeout, result rows capped at 500 per page with the total stated. WAL and journal files present
   beside it are copied with it and listed; no checkpoint is run.
4. Shown: tables, row counts, schema, and, where the report names table and row (or offset), that row with all
   columns, values shown raw (integers as integers, blobs as length plus hex preview of 64 bytes, never decoded).
   Where the report names only the file, the panel shows the file and its tables and says "the report does not
   say which row this record came from".
5. No hex editor, no carving (plan 13: not pursued).

Measurement gate: **build** when a production arrives whose records resolve to present, verified database files
for at least 1,000 records. Until then the panel states the reason per record.

**Server result (stage A3, `measurements/a3/README.md` section 10):** `extraInfos` is populated on 9 of the 14
server reports. Each `extraInfo` (`id`, `type`) holds `sourceInfo` with `nodeInfo` entries (`id`, `name`,
`path`, `tableName`, `offset`, `size`); a `nodeInfo` `id`, where present, is mostly a tagged file id (P08:
952,331 of 992,010), and `tableName` and `offset` name the source table and position. Top-level records reaching a tagged file tagged `Database`, present on disk and
MD5-verified, through their `extraInfo`: P11 77,446; P13 42,604; P08 37,052; P02 8,028; P03 6,733; P07 3,785;
P12 1,306 (15 to 55 verified database files per report). Gate **pass** on 7 reports; the start of stage J is
the coordinator's decision. These counts resolve by `nodeInfo` id only (no `path` matches a tagged file's
`path` on any report) and are a lower bound.

### 17.3 Independent re-parse (ALEAPP, iLEAPP)

Facts (project pages, read 2026-10-29): ALEAPP (Android) and iLEAPP (iOS) are MIT-licensed; command line
`python aleapp.py -t <zip|tar|fs|gz|raw> -i <input> -o <output>` and for iLEAPP `-t <fs|tar|zip|gz|itunes|file>`;
the output folder must exist; ALEAPP requires Python 3.11 or above and iLEAPP Python 3.11 to 3.15; outputs are
HTML, TSV, timeline, KML and LAVA. The backend runs Python 3.10 and cannot host them; the engine runs 3.12.

**Measured:** no local production contains the database files these tools read (17.2). Nothing can be re-parsed
on the corpus today.

Specification:

1. Runner in the engine: `evidence-engine/app/pipeline/reparse/leapp_runner.py`, invoking a pinned release of
   ALEAPP or iLEAPP (chosen by the extraction's OS from 01's metadata) as a subprocess from its own virtual
   environment (`/opt/leapp/<tool>-<version>/`), with no network (subprocess run in a network namespace or with
   proxy variables pointing nowhere and the tools' geolocation features off), a wall-clock limit, and `-t fs`
   over a reconstructed tree: each tagged file placed at its original `path` (from the file element's `path`
   attribute, present on 100 percent of files in all three samples), only files whose MD5 verified.
2. Read the LAVA output (or TSV where LAVA is absent in the pinned version; the parser is chosen per pinned
   version and tested against it). Record the tool, version, git commit, command line and output hashes on the
   run.
3. Map tool artefacts to captured types through a reviewed mapping (data, as plan 6.5), starting with SMS, call
   log, contacts, WhatsApp messages, Chrome history.
4. Compare per artefact: counts; record-level by natural key (approach 12 keys). Disagreement kinds:
   `count_differs`, `only_in_reparse` (could be a record PA did not decode or a deleted row the tool read),
   `only_in_report`, `time_differs` (both instants and both original strings shown, with the difference in hours
   to expose zone conversion), `value_differs`.
5. Results are `reparse_comparison` runs in 3.3 tables. Re-parsed records are shown as "read by [tool]
   [version]" beside the report's record; they are never merged into the captured record and never become the
   report's record.

Gate: **build** when a production with database files is received (same trigger as 17.2).

### 17.4 Local media pipeline

What exists in the engine (read for this file):

| Function | Code | Provider |
|---|---|---|
| Image text | `extract_text.py:1154-1155` → `_extract_image`; `config.py:85` `image_provider = "tesseract"` default | local Tesseract by default; `openai` option sends the image to `openai_vision_model` (`config.py:99`, `gpt-4o`) through `_describe_image_vision` (`extract_text.py:865-900`) |
| Audio | `_extract_audio` → `transcribe_audio` (`openai_client.py:778-853`), model `openai_transcription_model` (`config.py:100`, `gpt-4o-transcribe-diarize`) | OpenAI only; `get_openai_client` requires an OpenAI key (`openai_client.py:74-87`) |
| Video | audio track transcribed as above; key frames **always** described by `_describe_image_vision` (`extract_text.py:1047-1065`) regardless of `image_provider` | OpenAI |
| Chat models | `ai_model_policy.py:49` accepts providers openai, anthropic, gemini, deepseek | all third-party |
| Dispatch | by file extension (`extract_text.py:35-39`, `1154-1159`): audio `.mp3 .m4a .wav .mpeg .mpga .ogg .flac`; no `.opus`, `.amr`, `.3gp`, `.aac` | |

Consequences for phone media under standing decision 8 (local by default): audio and video would leave the
building today; phone audio in C8 includes `.ogg` 379, `.mp3` 60, `.wav` 17, `.m4a` 6, `.amr` 1 (`c8.json`
`file_ext`), and C3 and C9 file elements carry no `name` extension at all (`file_ext` "(none)"), so dispatch by
extension is unreliable for phone files. `backend/requirements.txt:126` lists `openai-whisper`, but no backend
module imports it.

Specification:

1. Content-type sniffing (magic bytes) for phone media, ahead of the extension table, in a phone-media entry
   point `evidence-engine/app/pipeline/phone_media.py`.
2. Local providers, selected per workload by a new provider value `local` in the engine's policy:

| Workload | Local default | Notes |
|---|---|---|
| OCR of screenshots and photographed documents | Tesseract (existing), language packs per case | first in order (plan 13): ties to the ledger through approach 1's parser and correlation as p4 |
| Voice-note and call transcription | a Whisper-family model run locally (implementation and weights pinned at build; model id, version and weights hash recorded on every transcript) | second |
| Translation | 17.5 | third |
| Image description and search | 17.6 | fourth |
| Face grouping | not built; only on a case that needs it, by Neil's decision | |

3. Third-party providers remain selectable per case only by an explicit case setting that records who decided and
   when; the setting is shown on every machine output produced under it.
4. Every output is a machine-generated text row beside its source (standing decision 9) with model, version,
   parameters and input hash, written to the shared text store with source locations so search and chat cite the
   source file and, for transcripts, the time offset.
5. The video frame path must honour the provider setting (fix of the defect above), in the same unit.

Gate: **build** OCR and transcription when 03 Media exists; measurement M-17.4: per phone, audio files by sniffed
type and total duration, images in screenshot paths; build transcription first if total voice-note duration in a
case exceeds one hour.

**Server result (cb-media, `measurements/m17_4-media.json`, script `scripts/m17_4_media.py`).** Audio files on disk
are typed by their first bytes and timed by ffprobe. Voice-note audio (files in a voice-note path) totals 31.57 hours
in the 1-phone case (1,629 files), 32.51 hours in the 10-report case (12,742 files on 10 phones) and 22.26 hours in
the 3-phone case (7,579 files). All audio totals 44.45, 49.44 and 33.78 hours. Ogg is the largest type on most phones;
AMR holds 29.73 hours on the 1-phone case's phone, and CAF and MP4 are common on the phones that have them. 1,065
audio files on the 10-report case have no duration ffprobe can read (812 of them on P06, all with bytes that name no
type) and 494 are not on disk (424 on P10). Images in screenshot paths: 2,783, 701 and 198. Gate: transcription
first (every case exceeds one hour).

**Speed (cb-media item B, measured 3 Nov on this server):** Whisper `base` (openai-whisper 20250625, MIT; torch 2.11,
BSD-3) through the production child (`derive._transcribe`, 2 threads, nice 15, load average 6.3) transcribed 10
corpus voice notes (4 Ogg, 4 AMR, 2 MP4; 5.6 to 179 s each, 481.6 s in all) in 163.8 s: a real-time factor of
0.34, with about 5 to 6 s of model loading per file. At that rate one worker would take about 11 hours for the
10-report case's voice notes (computed from the measured rate, **estimate, not measured** end to end).

### 17.5 Translation

Per message or transcript segment: local language identification, then local machine translation, stored as a
machine-generated row beside the original (never replacing it), with model and version; the original is always
shown first. Search covers both, labelled. Model choice is made at build after a licence check (several
well-known translation model families carry non-commercial licences; Loupe is used commercially, so a
non-commercial licence excludes a model). Acceptance: original and translation shown together; export carries
both with the label; no text leaves the server under the default setting.

### 17.6 Image search by description

Local image-text embedding model (licence-checked at build) over images in the Media population (approach 8's
population plus camera files), embeddings stored per file hash (so duplicates are embedded once), queried by text;
results show the image, its phones and messages. Labelled machine-ranked; a result is a pointer to an image, not a
statement about it. Gate: build after OCR and transcription, when a case has more than 1,000 user images
(M-17.6).

**Server result (M-17.6):** attachment-linked images whose bytes are in the production: 2,165, 2,165 and 2,109 per
case, each above 1,000. Gate: **pass**. Built as section 19 records (17.6 rows).

### 17.7 Identity consolidation as the approaches use it

02 owns the identifier registry and merges. Approaches use identities at two levels and always say which:

| Level | Definition | Used by |
|---|---|---|
| `exact` | equal normalised identifier (E.164, app id, email, username) | default for approaches 2, 5, 6, 11 |
| `reviewed` | joined by a reviewed merge in 02's decision log | shown where it changes a result: the result lists the merge it relied on and the result is recomputed if the merge is undone (input revision includes the merge log head) |

Merge suggestions are not used by any approach. Phone identities link to financial counterparties only through
the reviewed path (plan 6.6; `account_identity.py`, `identity_graph.py:77-128`).

### 17.8 Combined communication and money edges

1. Edge between two identities (02, at `reviewed` level, plus each identity's exact identifiers) per time slice:
   calls by direction and status with total duration; messages by direction and platform; payments from the ledger
   where the payment's counterparty resolves to one identity and the account holder to the other.
2. Payment linking uses the existing reviewed payment-to-identity link (`identity_graph.py:115-125`,
   `payment_counterparty_link.resolved_link`, `payment_counterparty_link.py:81`), admitted non-superseded rows only.
3. Sums: by default over `DEFAULT_TOTAL_CLASSES` (p0 to p2, `proof_class.py:136`), with p3 shown as a separate
   stated figure; currencies never summed together; approach 1's p4 readings shown as a count "money mentioned on
   phones: n" and never added to any sum.
4. Label example (UI copy, no em dashes): "14 calls, 230 messages, 6 payments totalling USD 8,400.00 (p0 to p2);
   2 more payments USD 1,100.00 (p3)".
5. Computed in Postgres by the one module `backend/services/phone/link_edges.py` (02 section 11.1, built in
   02-U16; 05-S10 only wires the approach screen to it) per case and time slice, cached by input revision; projected to Neo4j as
   rebuildable edges per plan decision 6; every edge opens to its calls, messages and ledger rows (`ref_id`).
6. Chart export carries for every edge the record locators and ledger `ref_id`s.

Acceptance: an edge with 2 payments in USD and 1 in MXN shows two totals; a p4 reading never changes a total; a
merge undone removes its contribution on recompute.

---

## 18. Build order, dependencies and measurement gates

Order follows plan 12.2, with section 13 units placed where their dependencies land. Each unit: measurement
recorded first (3.3 `phone_analysis_measurements` and in this file), then build, test, commit.

| Step | Unit | Depends on | Gate (from its section) |
|---|---|---|---|
| 0 | Framework (3): tables, jobs, endpoints, coverage, directions, decisions, sensitive reveals, shared results layout (3.9, AP-1) | 01, 02 registry, cb-ux shared kit | none |
| 1 | Measurement module with M-1 to M-16 implemented as read-only functions | 01, 02 | none; produces the gates |
| 2 | 17.1 raw record view requirements met in 01 and 03 | 01, 03 | none |
| 3 | Approach 1a: institution directory, parser, readings, binding, corroboration (no contradiction), leads | step 0, financial modules | 4.7 |
| 4 | Approach 1b: coverage join `read_account_continuity` → `coverage_from_continuity` with reconciliation status; contradictions enabled | step 3 | 4.7 plus at least one bound account with a continuous reconciled run over a reading's window |
| 5 | Approach 2 | 02 identities, 04 availability | 5.6 |
| 6 | Approach 3 | 01 deleted state, 04 | 6.6 |
| 7 | Approach 4 | 02, 04 | 7.6 |
| 8 | Approach 5 | 02, 04 places and strength | 8.6 |
| 9 | Approach 11 | 02, 04 statement check | 14.6 |
| 10 | 17.8 link edges | 02 reviewed identities, step 5 counts | any case with at least one reviewed phone-to-counterparty link |
| 11 | Approaches 6, 7, 9, 10 (each separate) | 02, 03, 04 | 9.6, 10.6, 12.6, 13.6 |
| 12 | 17.4 OCR and transcription local, video frame provider fix | 03 Media | 17.4 |
| 13 | Approach 8 exact tier, then perceptual tier | 01 files, step 12 engine | 11.6 |
| 14 | 17.5 translation, 17.6 image search | step 12 | 17.5, 17.6 |
| 15 | Approach 12 | 01 metadata, 02 natural keys | 15.6 |
| 16 | Approach 13, with its entry points (J-5c) | 04 day view and shared Lanes, step 5 offsets | 16.6 |
| 16a | Approach 14 | 02 identities | 16a.6 |
| 16b | Approach 15 | 02 identities, step 5 matches | 16b.6 |
| 16c | Approach 16 | 02 identities, 04 availability | 16c.6 |
| 17 | 17.2 source database view, 17.3 re-parse | a production with database files | 17.2, 17.3 |

---

## 19. Decisions made in this file (not settled by the plan)

| Decision | Reasoning | Reverse if |
|---|---|---|
| Bank short codes are identified from the sender Party identifier; `SMSC` is never used | M5: SMSC never equals the sender; few distinct values per phone | never; it is a fact of the data |
| `InstantMessage.Identifier` and `Chat.Id` are never cross-phone keys | X8, X9 collisions in local-id sources | a reviewed mapping shows a source app whose ids are global and measurement confirms |
| Phase 1b is the default: a reading is `contradicted` only when every account it could be on has a complete statement run with every period reconciled over the claim window and no such payment; phase 1a (never contradicts) stays a run parameter | 05-S4 built the join `read_account_continuity` to `coverage_from_continuity`, with unreconciled periods passed as unverified (tests in `test_phone_analysis_money_signals.py`) | a contradicted reading is shown wrong on real data |
| An account merged with others (account consolidation) gives no coverage, so an absence there is unresolved, never contradicted | its run spans every merged account while the rows weighed are its own; weighing the group together is on the follow-up list | the group's rows and periods are weighed together |
| Several payments that could each answer one reading link none of them: outcome `several_candidates`, each stored as a candidate | 4.3.4: tested against each, merged into none; a link names one payment | a tie-break rule is reviewed |
| Readings with no anchor (no institution, no account) are not correlated | nothing to bind them to an account; correlating against every account would invent a binding | a reviewed rule binds by holder or app |
| The results' `strength` column holds the reading strength (4.3.6), and the correlation outcome is in `measures.outcome` | 4.3.6 makes strength the filter on screen | the screen filters by outcome |
| A case alias may name a drafted directory entry; a drafted entry's templates are still not used | the person's decision in the case is the review for that channel value in that case | |
| Alert claim window `[d−1, d+7]` | authorisation versus posting, zone edge | M-1d lag distribution |
| Zero materiality first, default materiality second pass reported as `near_amount` | alerts are exact; FX and fees need tolerance | near-amount results mostly wrong |
| Institution directory is committed reviewed data plus case-scoped aliases | not evidence; review per plan 6.5 | 02 defines a reference-data store |
| Account-discovery leads reuse `account_references` statuses | same question already answered for payment descriptions | none expected |
| Results keyed by deterministic `result_key`; decisions through `decisions.record` with a new subject | one audit chain; decisions survive reruns | 02 defines a phone decision log |
| App-message matches split into server-stamped and device-stamped for clock offsets | X7: 18 of 18 exactly zero | measurement shows app times are device times for a source |
| Distinct-body rule (≥ 10 chars, ≤ 3 occurrences) unless all keys agree | X3 ratio of common to distinct bodies | precision review of matches |
| Selective clearing excludes explained deletions and uses per-app baselines | disappearing messages and decoder differences | |
| 19.S5-a A phone's owner identities for K2 and K3 are 02's owner (a recorded decision, else the computed owner) plus the owner accounts 02 lists, each read through reviewed persons | 5.3.2 K2 says "02's owner identity, not the raw flag alone"; app messages name the owner by account, not by number | 02 merges owner accounts into the owner itself |
| 19.S5-b A match whose copies differ Intact against Deleted or Trash is one result, kind `deleted_one_side`, naming the phone it is read from; the intact copy has the role `recovered_copy` | 5.3.6's `deleted_one_side` and `recovered_from_other_side` are the same condition seen from each side; two results would rest on the same two records | |
| 19.S5-c Drift: Theil-Sen slope with Sen's distribution-free 95 percent interval, not 1,000 bootstrap resamples; above 2,000 readings a fixed-seed sample of 2,000 | the bootstrap costs 1,000 x n squared slopes, about 250 million at the measured 496 pairs, inside one run | a run time budget that allows it |
| 19.S5-d "No data for that app in that period" is read from the other phone's own messages of that family (before its first or after its last) | 04 has no per-app band (as 19.S6-b) | 04 gains a per-app band |
| 19.S5-e `one_side_only` is computed only for messages between the two phones' owners | a message to a third person is not expected on the other phone | |
| 19.S5-f Copies of one message on one phone (02's duplicate group) count once | two copies of one message would tie for every match | |
| 19.S5-h Two extractions of one device (an equal IMEI, serial or Android ID in the two report headers) are not compared, and a text-and-time match needs one sent and one received copy | 5.3.1 leaves them to approach 12; two copies of one device's own message would otherwise show as "on both phones" and as deleted on one | approach 12 classifies devices |
| 19.S5-i The clock offset is read from distinctive bodies only (at least 10 characters, at most 3 times on each phone), one reading per message on each side; tau is at most the parameter's maximum (3,600 s) | repeated short bodies pair unrelated messages and pull the offset toward 0 | |
| 19.S5-j The gate counts `deleted_one_side` of the strong tier only | a text-and-time match carries `identity_unreviewed` | |
| 19.S5-g Not computed yet: the other phone's gap in that conversation (approach 3 holes) and leaving a group before the time | ChatActivity names a participant, not who left (19.S7-b) | a reviewed reading of who left |
| 19.S6-a Hole threshold: a gap is compared with the 99th percentile of the conversation's other gaps (leave one out) | with fewer than 100 gaps the nearest-rank 99th percentile is the largest gap itself, so no gap could exceed it | a corpus run shows leave-one-out marking more than 5 percent of conversations with 20 or more messages |
| 19.S6-b "Inside the availability band for app A" (6.3 step 4): a gap is a hole only when the phone holds messages of the same app in other conversations inside the gap | 04's observed bands come from observing streams only (device events, connectivity, places), never from messages, so there is no band per app; a gap in which the app recorded nothing on the phone is that app's no-data period, not a hole | 04 gains a per-app band |
| 19.S6-c `hole_confirmed_by_counterpart` is not emitted | it needs approach 2's matches, and approach 2 is not built (5.6) | approach 2 ships |
| 19.S6-d Named-set, TimeSpan and Boolean fields are read from the captured record body (`phone_analysis/fields.py`), never from the text table | the text table holds String fields only (measured on C3: no `Label`, `DeletionReason`, `EventType` or `Categories` rows) | 02 adds those values to a read view |
| 19.S6-e Key dates are placed beside results by the screen at display time, not stored in results | a key date added later must show without a rerun, and a result's key stays equal across runs | |
| 19.S6-f When the app's other conversations hold no unexplained deletion, the selective-clearing baseline is 3 divided by their message count (the 95 percent upper bound for zero events), never 0. Context results (concealment app, wipe, power off) rest on the field that makes them | a baseline of 0 makes any one deletion score p = 0; the upper bound keeps a fully cleared conversation significant while one deletion in 20 is not | a reviewed per-app deletion rate replaces the phone baseline |
| 19.S9-a A relationship result rests on the phone's contact cards for the person and its first and last communication, not on every message; its counts open Conversations filtered to the person | one result record per message would write a row per message (186,787 on P08) for a list Conversations already gives by filter | a result must be exported with every record behind it in one step |
| 19.S9-b Weekly counts run from the person's first communication on the phone to the phone's last communication of any kind; a changepoint needs at least 2 weeks either side (parameter) | contact that stops while the phone carries on shows as weeks of zero; a single quiet week is not a change | a corpus run shows changepoints that only mark the phone's own data starting or stopping |
| 19.S9-c PELT with a Poisson cost and a BIC penalty of 2 x ln(weeks) per changepoint | 14.3 step 2; a changepoint adds a location and a new rate | |
| 19.S9-d "No contact after D" (14.3 step 2) is 04's statement check; the screen links to it | 04 already gathers the supporting and contradicting records and the data gaps for a claim | 04's check cannot take a person and a date |
| 19.S9-e A person is a reviewed person (02) when one exists, else one identity; identities joined only by equal value carry `identity_unreviewed` | 17.7 | |
| 19.S9-f A relationship with no timed communication carries its own locator on its first contact card (or its first communication) | one contact card can list several numbers or accounts, each its own relationship; resting on the card alone gave two results on the same records and the run failed (measured 2026-11-03: 592 contact cards on 8 live phones list more than one number or account) | |
| 19.S7-a A chat is a group when its ChatType is Group, or, where the report gives none, when it lists more than two participants | ChatType exists on 4 of 14 reports (A3 section 9) | a reviewed mapping gives the chat type per app |
| 19.S7-b The party on a ChatActivity is shown as "participant named", never as who made the change | actor or subject is not established (section 20) | a reviewed mapping establishes it per app |
| 19.S7-c A group chat with no admin flag and no recorded change gives no result; the run counts every group | nothing to show for it; its existence is in the count | |
| 19.S8-a "Bins where both phones have data" (8.3 step 3) are the bins of days on which both phones hold at least one owner interaction event | 04's availability bands come from observing streams only and the live reference phones hold none, so a band test would drop every bin; this is the day rule M-5c measured | 04's bands cover the phones of a case |
| 19.S8-b A pair is listed for complementary use when it shares at least `min_days` such days (default 14, the gate's own figure) | fewer days give rates that move with a single day | |
| 19.S8-c Marker strength: same owner number, ICCID or IMSI strong; same account username or saved-login account on one service medium; same WiFi BSSID weak. Values are compared as SHA-256 digests inside the backend and never returned; the result gives counts by kind and the records on each side | 8.3 step 1; identifiers stay in the records, where the record panel shows them | |
| 19.S8-d Every shared-markers result carries its own pair locator on each phone | a phone's one SIM record can be the only record behind two pairs (its other sides hold the value in the report header only), and two results on the same records cannot be stored | |
| 19.S8-e Owner numbers are read from the current-generation owner candidates. The indicator "owner phone numbers" counts header (tier 1) numbers; the shared-number marker uses the numbers 02 computes the owner from (tier 1, else tier 2's top) | tier 2 numbers are inferred from account fields and owner parties, so several are expected on one phone used by one person | 02 changes how it computes the owner |
| 19.S10-a Typed and searched text matches the vocabulary by word tokens of 4 or more characters (not all digits) for names, a digit run equal to or ending with an account ending, and a run of 7 or more digits for phone numbers | 10.3 step 2 allows 4-digit runs for every number; on C3 any 4 digits in a web address matched some phone number (3,523 distinct matches in 5,866 addresses) | a measured sample shows 4 to 6 digit typed numbers that are real hits |
| 19.S10-b A typed hit is `typed_not_in_extraction` when no matched term occurs in the phone's messages, emails, notes, searches or calendar (10.3 step 3), else `typed_and_present` with up to 20 of those records linked and the full count stated | the elsewhere search counts every record; 20 links keep a result readable, and the count says how many there are | |
| 19.S12-a A search or page whose every matched term matches 3 or more records of the case has strength `common_term` (a business or site name), the others `specific_term`; nothing is dropped | on C3, 29 terms gave 399 hits, 20 of them on terms matching fewer than 3 records | reviews show common-term hits confirmed as often as specific ones |
| 19.S12-b Page addresses are matched on their path words only, and a hit only in the address says so | the host is a site name and the query repeats the search; 340 of C3's 396 page hits are address-only | address hits are rejected on review far more than title hits |
| 19.S16a-a Owners for common contacts are each phone's owner identities as 02 computes them (with account candidates), read through reviewed persons; phones whose owners share a person or identity are one owner | the 10-report case has 10 phones and 8 owners | 02 records owners per phone in another way |
| 19.S16a-b Common contacts cover the whole span; a narrower window is the Conversations filter the counts open | 16a.3 step 3 default; key dates never need a rerun | |
| 19.S16a-c A common-contact result rests on the first and last communication of each side and the saved entries, with a pair anchor of its own | one record can be the first contact of two owner pairs | |
| 19.S14b-a A phone analysis result, a kept result, a statement check and an incident window are exported by freezing their records as one selection, as a finding is; records that are not a message or call are counted in the dialog as not in the export, and a source with none is refused with that reason | the export draws communications; a silent drop would present a partial export as whole | the export draws other record kinds |
| 19.S16b-a The from/to matrix population defaults to N = 1 | M-15a: 8,502 people at N = 1, 5,519 at N = 5; every cell opens to its records, so the smaller population only hides people | the screen cannot list a case's cells |
| 19.S16b-b A record's sender is its sender or caller party (or the owner for an outgoing record naming none); every other party is a recipient; a record with neither is counted as "direction not recorded"; duplicate copies on one phone count once | 16b.3 step 2 | a reviewed mapping gives sender and recipients per app |
| 19.S16c-a A stop within the gap of the end of a phone's data, or a start within the gap of its start, is not a stop or start | 16c.8 test 2; availability is read as the phone's first and last communication | 04's availability bands give finer starts and ends |
| 19.S-ix The analyses are reached from one Phones sidebar entry, "Analyses", which also lists the approaches whose gate failed with the measured reason | one entry per approach would put ten links in the group; an absent analysis is stated, not silent | |
| Deletion time is an interval to extraction start unless `DateDeleted` exists | `DateDeleted` 1 in corpus | a source of deletion times is found |
| Media spread population restricted to attachment, camera-path and EXIF-camera files | X10 against X11 | |
| Approach code in `backend/services/phone_analysis/`; media and re-parse in the engine | backend 3.10 versus tool requirements 3.11+ | 01/02 fix another root |
| Sensitive values never in search, AI or exports by default; reveals logged | plan 12.1 rule 4 | Neil per case |
| Local providers for OCR, transcription, translation, image search; third party only by recorded case setting; video frames to honour the setting | standing decision 8; engine today sends audio and video frames out | Neil per case |
| `MobileCard` excluded from money signals until mapped | Type only `Unknown`; meaning not shown | a reviewed mapping |
| One sensitive list shared with 02 section 5.5: `Password.GenericAttribute` and `KeyValueModel.Value` included | the two lists must agree, or a field sensitive in one spec would be searchable or exportable through the other; `KeyValueModel.Value` contents are unknown per key | a reviewed mapping shows a key's values hold no credential |
| Every approach uses one results layout and labels its results "Lead for enquiry" (3.9) | an approach result points to records to examine and does not state probative value | a result kind is shown to be evaluative, then it carries the evaluative label with its propositions |
| Approaches 14 to 16 measured first like the others (16a.6, 16b.6, 16c.6) | the same gate discipline as approaches 1 to 13 | |
| Analysis runs have their own queue (C16), a table `phone_analysis_runs` claimed by its own thread in the phone worker, one run at a time | the backend image has no arq worker for phones (03 D-43); a run left `running` by a worker that died is queued again at start, and a run whose phones or records changed after it was asked for is queued again on the current material | measured host memory cannot hold both, or an analysis waits longer than a phone pass |
| 05-S12: the local models run from the backend in an isolated child process (`backend/services/phone/derive.py`); the entry point `evidence-engine/app/pipeline/phone_media.py` holds sniffing, the provider policy and model identity, standard library only, loaded by both the backend and the engine | the engine image has no Whisper or torch and the phone worker is capped at 1 GB; the backend venv already holds openai-whisper 20250625 (MIT) and torch 2.11 (BSD-3); Whisper `base` measured at 0.34 times real time on 2 threads (item B) | the engine gets a media worker with its own memory budget and the model |
| A phone file's kind is taken from its first bytes; the name's extension is used only when the bytes name nothing; in the engine only media and unknown extensions are sniffed, never document or text extensions | C3 and C9 file elements have no extension; `.opus`, `.amr`, `.caf` were unsupported; a text file starting `ID3` must stay text | a sniffed kind is shown wrong on corpus files |
| Every machine text records model id, version, weights SHA-256 (Tesseract: one hash over the language data used), parameters, input SHA-256, provider, sniffed container, language and duration; texts made before this keep NULL and say "not recorded" | 17.4 point 4; nothing is invented for older rows | |
| A person corrects machine text with a typed reason, or confirms it; the machine text is never overwritten and stays shown beside the correction; search, the PDF export and dossier assessments use the corrected text; each save is one decision in the case ledger (subject `phone_derived_text`, digests and lengths only) and one manual-change record; confirming text that already stands confirmed is a review | 07 4.6 and 5 Media (M-6); the ledger never holds evidence text | |
| Machine text is confirmed on use: the phone PDF export lists each unconfirmed text on the attachments in scope (first 50, the rest as a count) with its audio or image inline, to confirm or keep marked; the PDF prints each text under its attachment with its mark and the cover counts them. Using a text in a dossier assessment shows the same prompt first | 07 5 Media (M-7); collection, finding and dossier exports are not built yet, so the stream export is the export there is | |
| A transcript accepted into a dossier assessment is stored `ai_assisted`, names the text (`dossier_assessments.derived_text_id`), links the original file, and shows "Read by <model>, accepted by <name>"; accepting is not confirming, so the text keeps its own mark | CO-18 (transcript) | |
| The reading in use for a file and kind (search, the PDF, the prompt, the Media grid) is the latest a person corrected or confirmed, else the latest finished; a later machine reading never displaces a person's reading, and the Media panel says which reading is used | 07 4.6; review of the first M-6 build | |
| Batch reading (M-5): the Media scope shown is the batch scope; the batch reads every Audio and Video file (transcript) or Image (text) in it except those already read or waiting, not in the production, or empty placeholders, each left-out group counted; readings a person asks for one at a time are drawn first; cancelling removes readings not started and keeps every finished one. Progress is the true count of the batch's readings by state, polled every second while it runs; time left is this batch's own measured pace (no speed is assumed: measured base model 0.34 times real time on 2 threads plus about 5 to 6 s model load per file, 10 corpus voice notes, 3 Nov) | 07 5 Media and 4.7; there is no global header in the app yet, so the job tray sits on the Media toolbar for this case's batches; move it when a header is built | |
| 05-S13 media spread, exact tier: `backend/services/phone/media_spread.py`, routes `GET /api/phones/media-spread/index` and `/window` (view permission), and a Media spread screen reached from a phone's Media screen. A group is the population copies (11.3 step 1) with one MD5 on two or more of the case's phones, computed on request from the read views with no new table; groups are paged (at most 100 a page) with the total stated, and one phone's copies in one group are listed up to 20 with the full count stated | the measured gate passed (11.6: 112 groups in the 10-report case); views already give hashes, paths, links and times, so no migration. The request cost on the 10-report case is not measured | a measured request time on the largest case is too slow for the screen, then the groups are stored at interpretation time |
| Media spread population: attachment-linked means a resolved, unambiguous attachment reference (the same links Media counts); camera or screenshot folder is a whole path component `dcim`, `camera` or `screenshots` (reviewed list in code) matched on the file's original `path` attribute or its `Local Path`; EXIF camera means a non-empty `EXIFCameraMaker` or `EXIFCameraModel` item in any metadata section of the file. Files with no MD5, empty placeholders and the MD5 of zero bytes are never grouped. A copy outside the population on another phone does not join a group | 11.3 step 1; the A3 measurement counted `dcim` and `camera` on `Local Path`, so both paths are matched; system files dominate whole-index overlap | a reviewed sample shows camera files in folders the list misses, or spread copies left out because one phone's copy sits outside the population |
| Media spread captured fields: MD5 and SHA-256 (declared, or the disk hash where read), the original `path` attribute, `Local Path`, `EXIFCameraMaker`, `EXIFCameraModel`, `ExifEnumGPSLatitude`, `ExifEnumGPSLongitude` and `MetaDataLatitudeAndLongitude` (all kept in the captured file body), `EXIFCaptureTime` and the file-system modify time (`CoreFileSystemFileSystemNodeModifyTime` item or `ModifyTime` access timestamp, in the stored file timestamps) and the carrying message's time and direction. Not used: approach 2's clock offsets (not built), so every group says the order is by each phone's own clock; 04's place model (not joined), so place is the EXIF GPS text as written, source "photo EXIF"; the perceptual tier (step 3), which waits on its own gate. The synthetic report builder writes no EXIF items, so the EXIF paths are tested on invented file bodies only | 11.2, 11.3; nothing is invented where a field is absent | approach 2 offsets land (order across phones uses them); 04's place model gains a photo source; the perceptual gate passes |
| Media spread order and camera original: per copy and per phone the earliest of message time, file modified time and EXIF capture time that has an instant, with the field named. A time the report wrote without an offset is shown as written and never placed in a zone, so it takes no part in the order; for the camera original test it is compared by its widest bounds (every real offset lies between UTC-12 and UTC+14): earlier than the first message in any zone is a candidate, not earlier in any zone is not, otherwise "cannot tell" in words. With no timed message in the group a camera copy in a camera folder is a candidate and says no message carries a time | 01 decision D17 (no zone is guessed); 11.3 steps 4 and 5 | measurement shows EXIF capture times on a source are reliably in the device's zone, then that zone may be used with the basis named |
| Media spread flags: "common file" when the hash is on more than half the case's active phones, counting every copy of the hash (not only the population); equal MD5 with different SHA-256 on two copies keeps the group and flags it; a copy whose every carrying message is marked deleted, or a copy in a WhatsApp, Telegram, Signal or Viber folder that no message carries, says so | 11.5 and 11.3 steps 2 and 5 | a reviewed sample shows the common-file count should be limited to the population |
| 17.5 translation models: MarianMT models from OPUS-MT at pinned revisions, `Helsinki-NLP/opus-mt-es-en` at `c96e2c5399ebfae4fc43d9669556b9afa74bb69d` and `Helsinki-NLP/opus-mt-yo-en` at `f3d791bfa5ccd8d0ff7171f177f3e55c5bb3971c`, each with its weights SHA-256 pinned and checked at install; run by `transformers` 5.3.0 and `sentencepiece` 0.2.1 on the backend's torch, in the isolated child process with outbound connections refused and the Hugging Face offline switches set; language identification by `lingua-language-detector` 2.1.1 over all its languages. Target language is English. Weights are installed once by an operator (`python -m services.phone.translate_models`) into `LOUPE_TRANSLATION_MODEL_DIR` (default `~/.cache/loupe-mt`) and never fetched while evidence is translated; a missing model is refused in words and nothing is sent anywhere | live message mix (4,117 bodies of 25 characters or more, lingua 2.1.1): English 57.7%, Spanish 17.5%, Yoruba 7.1%, unsure 5.2%, Portuguese 1.0%, so the pairs are Spanish to English and Yoruba to English. `transformers` 5.3.0 is the release that accepts the pinned `tokenizers` 0.22.1 and `huggingface_hub` 1.3 (`huggingface_hub` moves from 1.2.3 to 1.3.1, the lowest 1.x that `transformers` 5 accepts; 5.4 and later need 1.5) | a language reaches the share of Yoruba in a case; a later model is measured better on the case's own text |
| 17.5 licence check: both model cards state `license: apache-2.0`; the upstream OPUS-MT weights are released under CC-BY 4.0; `transformers`, `sentencepiece`, `safetensors` and `lingua-language-detector` are Apache-2.0. All allow commercial use. Model families published under a non-commercial licence (NLLB-200 and M2M-100 variants under CC-BY-NC) are excluded, because Loupe is used commercially | 17.5 | the upstream licence of a pinned model is found to differ from its card |
| 17.5 English and unidentified text is not translated: text identified as English is stored as "Already in English"; text in which no language is identified is stored as "Language not recognised with confidence; not translated"; neither carries a translation. Text whose top language has an installed pair is translated whatever lingua's relative confidence, and the translation states the language and that confidence. A language with no installed pair is refused with its name ("No Portuguese to English translation model is installed on this server") | lingua's relative confidence is shared among close languages: on 3,956 live bodies of 25 characters or more, Spanish was the top language of 999 and reached 0.5 on only 384, the runner-up being Portuguese (208), Catalan (80) or Italian (49), so a 0.5 threshold refused most Spanish. The setting is recorded on every row, and an "unsure" row made under another setting is identified again when asked | a review of translations on case text shows a measured false-translation rate that a threshold would cut |
| 17.5 stale source: every translation records the SHA-256 of the exact text translated (a message's text in effect, with a person's correction applied; a machine text's corrected text, else its text). When the text in effect no longer matches, the translation is shown and printed as "Made from an earlier text" and is not searched; translating again makes a new row and both are kept | 02 section 10: only the corrected value is searched; a translation of superseded text is never presented as current | |
| 17.5 how text is translated: one sentence at a time (a long sentence cut at spaces under 400 characters), line breaks kept; a transcript per segment, keeping each segment's start and end, its language identified over the whole transcript; up to 20 waiting messages are drawn into one child process, a transcript alone, and a draw that fails is drawn again one text at a time so the failure is stated against its own text. Translation takes turns with OCR and transcription on the one media worker thread | measured on this server under load (3 Nov): loading the identifier and the libraries about 30 s, translating a sentence under 1 s; 20 two-sentence messages in one draw 142 s against 54 s for one message alone; given two sentences at once the Spanish model was seen to leave the first one out | a model is found to keep multi-sentence input whole |
| 17.5 labels: a translation is always shown under its original as "Machine translation (local, <model> <revision>, transformers <version>), not checked by a person", with the language identified and its confidence; search lists translations in the machine-generated group as machine translations citing the start of their original; the PDF prints each under its message or transcript and the cover counts them. A person does not correct or confirm a translation in this build | 17.5 acceptance | a reviewed-translation workflow is asked for |
| 17.6 model: Google SigLIP 2 base, `google/siglip2-base-patch16-224` at revision `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`, weights `model.safetensors` SHA-256 `612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b`, checked at install; run by `transformers` 5.3.0 on the backend's torch with the model's own processor (`SiglipImageProcessor`, Pillow; no `torchvision` needed) in the isolated child process with outbound connections refused and the Hugging Face offline switches set. Images go through the vision half, descriptions through the text half (lower-cased, padded to 64 tokens); vectors are unit length (768 values). Weights are installed once by an operator (`python -m services.phone.image_search_models`) into `LOUPE_IMAGE_MODEL_DIR` (default `~/.cache/loupe-image`); a missing model is refused with "The image search model is not installed on this server. Nothing was sent anywhere." | licence check at build: the model card says `license: apache-2.0`, which allows commercial use; the LAION OpenCLIP weights were not used because their model cards put deployed use of the model out of scope, and Loupe is deployed commercially. Loading the halves separately gives the same vectors as the full model (checked at build) | the upstream licence is found to differ from the card; a later model is measured better on case images |
| 17.6 population: Image files that are attachment-linked (resolved, unambiguous), in a camera or screenshot folder (`dcim`, `camera`, `screenshots` as a whole path component of the original path or the local path), or whose metadata names a camera make or model; the camera-folder and camera-EXIF parts are approach 8's own statements (`media_spread.CAMERA_PATH_SQL`, `EXIF_CAMERA_SQL`, 11.3 step 1), so the two populations cannot drift apart. Videos are not indexed (no frame is taken). "Index this case's images for search" shows the true counts first: images to index, and left out by reason (not in the population, not in the production, empty placeholder, could not be opened by an earlier run, already indexed, already waiting) | 17.6 and 11.3; a file the report gives no category is counted and not considered, as in batch reading | approach 8 lands on this branch: the two predicates become one call |
| 17.6 storage: one vector per distinct content per case (SHA-256 of the bytes: the verified `disk_sha256` when present, else computed while reading) and per model weights, stored as little-endian float32 bytes with the model id, revision and weights hash; a file is linked to its content by its finished indexing row, so a duplicate on several phones is embedded once and every copy is found. Case-scoped, so a deleted case leaves no vector. No vector extension is used (none is installed on the live database); scoring is done in the backend over the case's vectors, 2,000 at a time from a server-side cursor with a running top list, at most two searches scoring at once per server process; a search waits at most 45 s for its turn and is otherwise told "Another search is running; try again in a moment." A search ranks the files counted as indexed (in the population and the production) and says how many distinct pictures and how many files it scored | 35,000 synthetic vectors: peak memory 25.5 MB, 3.3 to 4.2 s, against 228.6 MB and 1.5 to 1.9 s loading all at once (measured 3 Nov, analysed tables) | a case grows past what is scored in a few seconds |
| 17.6 work and speed: indexing runs on the media worker thread in turn with readings and translations, 32 images per child process; HEIC (which the image library here does not open), bytes naming another kind, damaged files and empty files are refused with words and counted by reason; a draw that fails is drawn again one file at a time. Measured on this server under load (3 Nov, 32 synthetic 1600 x 1200 photos): the child starts and loads in 16 to 27 s, then 0.4 to 2.5 s per photo; 32 photos in 40 to 94 s. A description is embedded by the text half kept loaded in its own child between searches (first search about 31 s, then 1.3 to 2.0 s each), stopped after 10 idle minutes (`LOUPE_IMAGE_QUERY_IDLE_SECONDS`; 0 runs a child per description) | a child per description measured 43 s under load, which makes each new description a long wait | the warm child's memory (about 1.1 GB per server process while loaded) is needed elsewhere |
| 17.6 labels: results are ranked images, each shown with its thumbnail, every phone and file holding the same content and the messages that carried each copy; the score is shown only as a rank; the list says how many indexed images were scored and how many are shown, and how many images are not indexed and why. Every list is labelled "Machine-ranked by <model> <revision>; a result points to an image, it does not describe it." The description typed is not stored | 17.6: a result is a pointer to an image, not a statement about it | |
| 17.2 opener, write-ahead log: a copy with a non-empty `-wal` file beside it is opened `mode=ro` without `immutable=1`; every other copy `mode=ro&immutable=1`. The open mode is stated with every view | measured on SQLite 3.46 (3 Nov): with `immutable=1` a database whose last rows sit only in its log shows 0 of 2 such rows; `mode=ro` shows both, cannot checkpoint, and leaves the copy's database and log bytes unchanged (it adds a shared-memory file in the scratch folder only). The evidence file is never opened in either mode | a SQLite version is found to checkpoint or write the log under `mode=ro` |
| 17.2 opener, refusals: besides `query_only`, an authorizer allows only reads (SELECT, READ, functions, recursive queries and the table-info pragmas); ATTACH, VACUUM, writes, schema changes and every other PRAGMA are refused with "this view only reads". The opener and the copy run in the evidence engine (`app/phone/source_db.py`, route `GET /cases/{case}/phone/extractions/{ext}/files/{doc}/{ordinal}/database`); the backend resolves the record's sources and proxies (`GET /api/phones/records/{record_uid}/source-database`). A copy is made once per content into `<storage>/_scratch/source-db/` and reused; one not used for an hour is removed. Its SHA-256 must equal the capture's verified hash or it is not opened | `query_only` alone leaves ATTACH able to create a file (an ATTACH with `mode=rwc` is a write elsewhere) | |
| 17.2 named row: the report's `offset` is read as the table's rowid; a table without rowids, an offset that is not an integer, or no row with that rowid each says so in words | the measured meaning of `offset` on the loaded productions is recorded in `CB-STAGEJ-STATUS.md` | the measurement shows `offset` is not a rowid |

---

## 20. Not yet established

- M-1a against the reviewed directory and M-1c to M-1e (need the ledger and the Loupe case): `cb-crossev`.
- Which Loupe case the phones are loaded into (CB-INDEX question 3). None of the three phone cases exists in
  Loupe: their ids are v1 case ids and no Loupe case has a matching name. Approach 1's first run waits for
  that answer.
- Whether per-section card endings are persisted on admitted transaction rows (row-level binding in 4.3.4).
- Meaning of `ScrambledMessageData`, `MobileCard`, `ApplicationUsage.LastScreenshot`, and of the Party on
  `ChatActivity` (actor or subject).
- Whether report record ids are stable across two exports of one extraction: the corpus holds one C8 export on the
  server (the second is only on the Mac), so M-12d cannot be measured here.
- Common contacts per owner pair, matrix population size and number-switching base rates (M-14a to M-16c).
- What the `.xmlModelSource` / `.xmlNodeSource` split sections hold when non-empty (zero bytes in the local C8);
  `extraInfos` is measured (17.2).
- Pinned versions of ALEAPP or iLEAPP, the exact LAVA output schema of that version, and how to disable all network
  features in it.
- Whether SMS receive times on recipient phones are device-stamped or service-centre-stamped (affects clock offset
  from SMS pairs, M-2c).
- Gates that need 02's identities, the ledger or the case vocabulary: M-2b to M-2d (`cb-crossev`); M-7a, M-9b, M-11b,
  M-11c, M-14a to M-16c (`cb-approaches`); M-13a (`cb-pol`, with 04's day view). Every other gate is marked with its
  server result in its section.
