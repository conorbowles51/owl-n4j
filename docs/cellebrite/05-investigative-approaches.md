# 05. Investigative approaches and closing the gaps

Purpose. This file specifies, to build level, the thirteen investigative approaches accepted in plan
section 12 and the gap-closing work of plan section 13 (validation against the raw data, media AI and
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
3. Shared framework for every approach (tables, jobs, endpoints, results, decisions, coverage, sensitivity)
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
| Record locator | 01 | `(extraction_id, record_id, field_path, value_index)` addressing any captured value, top-level or nested. |
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
| `link_edges.py` | 17.8 |
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
`extraction_comparison`, `incident_window`, `link_edges`, `reparse_comparison`.

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
| `record_id` | varchar(128) null | report record id |
| `field_path` | varchar(512) null | e.g. `From/Party/Identifier` |
| `ledger_transaction_id` | uuid null | `financial_transactions.id` |
| `role` | varchar(40) not null | e.g. `sender_copy`, `recipient_copy`, `alert`, `ledger_row`, `evidence` |

Primary key `(result_id, coalesce(extraction_id,…), record_id, field_path, ledger_transaction_id, role)` as a
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

Runs execute on the phone queue's worker (plan 6.1) as job kind `analysis`, with checkpoints per
extraction and cooperative cancel. A run never writes to captured records, interpreted records, the ledger
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
| `UserAccount.Password` | 25, 8 phones |
| `WirelessNetwork.Password` | 26, 2 phones |
| `Cookie.Value` | 13,593, 10 phones |
| `CreditCard.CreditCardNumber` | 1, B-C3 |
| `Autofill.Value` | 70, 6 phones |
| `DictionaryWord.Word` | 14,256, 4 phones |
| `KeyValueModel.Value` | 395,831, 13 phones (contents unknown per key; sensitive until a reviewed mapping says otherwise) |

Rules: values render masked (`••••` plus, for card and account numbers, the last four characters) until a
person presses Reveal; each reveal is logged (actor, time, locator, field) in an append-only
`phone_sensitive_reveals` table; sensitive values are never placed in the shared text store or search index
by default, never sent to any model, never included in exports unless the export dialog's explicit option
is chosen (and the export manifest then lists every revealed field). Approaches that need to compare a
sensitive value (approach 1 card endings, approach 7 typed words) compare inside the backend and return only
the match and the masked display.

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
is still built if M-1e has any `account` or `transactional` lead. The first case to run it on is the
3-phone case (notifications) if it has financial records; whether it does is not established.

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
none deleted on one side. Gate: **build** if the 10-report case (55 pairs, measured on the server) yields at
least 100 `matched_strong` pairs in total or at least 10 `deleted_one_side`/`recovered_from_other_side`
results; the local three-phone figure (18) alone is **inconclusive**.

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
2. **Co-location.** 15-minute bins. In a bin a phone is placed if it has a location with uncertainty radius r
   (04: GPS accuracy, else source default; Synced points excluded unless the run includes them). X and Y are
   `together` in a bin when their uncertainty discs overlap (`distance ≤ r_X + r_Y`), `apart` when
   `distance > r_X + r_Y + 500 m`, else `indeterminate`. Statistic: `C = together / (together + apart)` over
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

### 15.7 Dependencies

01 (metadata capture, extraction info), 02 (registry, natural-key mappings), 03 (Extraction profile).

### 15.8 Acceptance tests

1. Equal IMEI: `same_device_established`; equal IMEI with different serial: flagged contradiction, `undetermined`.
2. Message intact in earlier, deleted in later: `state_changed`.
3. Record newer than the earlier extraction's end: `only_in_later` with "created after the first extraction".
4. Type not selected in the earlier extraction: its later-only records attributed to selection.

---

## 16. Approach 13: incident window

### 16.1 Question it answers

What every phone in the case recorded, by any signal, in a window around one anchor time, and where each phone
has no data in that window.

### 16.2 Data it rests on

All timestamped records (generic interpretation, plan 6.4), 04's activity strength and availability bands.

### 16.3 Method

The 04 day view generalised to: all phones, a window `[anchor − before, anchor + after]` (defaults 2 h each,
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

### 16.7 Dependencies

04 (day view), approach 2 (offsets).

### 16.8 Acceptance tests

1. A phone with no data in the window shows a "no data" band, not an empty lane.
2. Window of 7 days loads every record under the filter (plan 10.2: complete results when filtered), with the
   total stated.

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
5. Computed in Postgres (`link_edges.py`) per case and time slice, cached by input revision; projected to Neo4j as
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
| 0 | Framework (3): tables, jobs, endpoints, coverage, directions, decisions, sensitive reveals | 01, 02 registry | none |
| 1 | Measurement module with M-1 to M-13 implemented as read-only functions | 01, 02 | none; produces the gates |
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
| 16 | Approach 13 | 04 day view, step 5 offsets | 16.6 |
| 17 | 17.2 source database view, 17.3 re-parse | a production with database files | 17.2, 17.3 |

---

## 19. Decisions made in this file (not settled by the plan)

| Decision | Reasoning | Reverse if |
|---|---|---|
| Bank short codes are identified from the sender Party identifier; `SMSC` is never used | M5: SMSC never equals the sender; few distinct values per phone | never; it is a fact of the data |
| `InstantMessage.Identifier` and `Chat.Id` are never cross-phone keys | X8, X9 collisions in local-id sources | a reviewed mapping shows a source app whose ids are global and measurement confirms |
| Phone money readings never contradict a ledger in the first build | `claim_comparison.py:55-59` precedent; the coverage join has no production caller | step 4 lands with tests |
| Alert claim window `[d−1, d+7]` | authorisation versus posting, zone edge | M-1d lag distribution |
| Zero materiality first, default materiality second pass reported as `near_amount` | alerts are exact; FX and fees need tolerance | near-amount results mostly wrong |
| Institution directory is committed reviewed data plus case-scoped aliases | not evidence; review per plan 6.5 | 02 defines a reference-data store |
| Account-discovery leads reuse `account_references` statuses | same question already answered for payment descriptions | none expected |
| Results keyed by deterministic `result_key`; decisions through `decisions.record` with a new subject | one audit chain; decisions survive reruns | 02 defines a phone decision log |
| App-message matches split into server-stamped and device-stamped for clock offsets | X7: 18 of 18 exactly zero | measurement shows app times are device times for a source |
| Distinct-body rule (≥ 10 chars, ≤ 3 occurrences) unless all keys agree | X3 ratio of common to distinct bodies | precision review of matches |
| Selective clearing excludes explained deletions and uses per-app baselines | disappearing messages and decoder differences | |
| Deletion time is an interval to extraction start unless `DateDeleted` exists | `DateDeleted` 1 in corpus | a source of deletion times is found |
| Media spread population restricted to attachment, camera-path and EXIF-camera files | X10 against X11 | |
| Approach code in `backend/services/phone_analysis/`; media and re-parse in the engine | backend 3.10 versus tool requirements 3.11+ | 01/02 fix another root |
| Sensitive values never in search, AI or exports by default; reveals logged | plan 12.1 rule 4 | Neil per case |
| Local providers for OCR, transcription, translation, image search; third party only by recorded case setting; video frames to honour the setting | standing decision 8; engine today sends audio and video frames out | Neil per case |
| `MobileCard` excluded from money signals until mapped | Type only `Unknown`; meaning not shown | a reviewed mapping |

---

## 20. Not yet established

- Notification amount and institution counts (M-1a, M-1b): no local sample carries Notification; server run needed.
- Whether the 3-phone case has financial records in Loupe (decides where approach 1 is first measured).
- Whether per-section card endings are persisted on admitted transaction rows (row-level binding in 4.3.4).
- Meaning of `ScrambledMessageData`, `MobileCard`, `ApplicationUsage.LastScreenshot`, and of the Party on
  `ChatActivity` (actor or subject).
- Count of `DeviceEvent` Wipe events and of `Label` values SelfDestruct, Recalled, Scrambled on the server phones.
- Whether `SocialMediaActivity` check-ins carry a nested place record.
- Whether report record ids are stable across exports or extractions (M-12c on the A-C8 pair).
- Whether A-C1a and A-C1b are one device (M-12a, M-12b).
- PA's element and attribute names for record-to-source information in `extraInfos` and the `.xmlModelSource` /
  `.xmlNodeSource` sections: empty in every local sample.
- Pinned versions of ALEAPP or iLEAPP, the exact LAVA output schema of that version, and how to disable all network
  features in it.
- Choice and licences of the local transcription, translation, language-identification and image-embedding models.
- Whether SMS receive times on recipient phones are device-stamped or service-centre-stamped (affects clock offset
  from SMS pairs, M-2c).
- Every gate above that depends on server measurements (10-report and 3-phone cases).
