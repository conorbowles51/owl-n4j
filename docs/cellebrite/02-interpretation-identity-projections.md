# Cellebrite rebuild, spec 02: registry, interpretation, identity and projections

Status: specification. Nothing here is built. Written 2026-10-29 against `integration/evidence-main-reunion`,
v1 at `origin/main`, the structural catalogue of 17 report files (14 server phones and the 3 local samples),
and streamed structural measurements of C3, C9 and C8 taken for this file. Plan sections detailed here: 3.3,
6.4, 6.5, 6.6, 6.7 (display), and the identity and link-analysis rows of 13.

**Purpose.** Spec 01 captures every element of a report into Postgres losslessly. This file turns that
capture into things an investigation can use without losing the link back to the capture: a registry that
learns every record type, field and value set from the data and flags what is new; generic interpretation
that gives every record type a timeline, a map, participants, files and searchable text from the report's
own value types, with no code per type; reviewed mappings, held as versioned data, that refine
interpretation for the core types and are applied retroactively; a coverage map that says per type and
field how far Loupe understands it; an identity model that keeps each phone's own view of who is who and
links identities to people only by recorded decisions; corrections that keep the machine reading beside
the correction; and projections into Neo4j, the shared text store and AI citations that are rebuilt from
Postgres and never become the record. It also provides the read contract that spec 03 (screens) and spec 04
(pattern of life) are written against.

## Contents

1. Scope, interfaces and conventions
2. Measurements this file rests on
3. Schema registry
4. Value parsing: times, durations, coordinates
5. Generic interpretation by value role
6. Reviewed mappings as versioned data
7. Coverage map
8. Identity model
9. Projections: Neo4j, text store, embeddings, citations
10. Corrections on phone data
11. Combined communication and money edges
12. Read contract for specs 03, 04 and 05
13. Build units and acceptance tests
14. Decisions made in this file
15. Not yet established

---

## 1. Scope, interfaces and conventions

### 1.1 In and out

In: everything between the capture (spec 01) and the screens (spec 03): registry, interpretation, mapping
format and the initial type mappings, coverage, identities, owner identity, corrections, Neo4j projection,
thread text documents, embeddings policy, citation anchors, combined edges.

Out: intake, capture, file verification, reconciliation (spec 01); screen behaviour, endpoints that only
read (spec 03); the content of the activity-strength, timestamp-meaning and attribution mappings (spec 04
writes their rows; this file defines the format they live in, section 6); investigative approaches
(spec 05).

### 1.2 What this file reads from spec 01 (capture)

Spec 01 (`01-intake-capture-storage.md` section 6.2) defines the capture tables. This file builds on these
exact names and reads nothing from the XML again.

| 01 table | What this file uses |
|---|---|
| `phone_extractions` | `id`, `case_id`, `capture_state` (this file starts only on `captured` or `captured_incomplete`), `standing` (`pending`, `active`, `superseded`), `supersedes_id`, `report_version`, `producer_version`, `extraction_type`, `device_zone`, `device_zone_source`, `flags` |
| `phone_extraction_documents` | `skeleton` (every non-record section: metadata items, `extractionInfo`, `timeZoneConfigurations`, case information), `role`, `parse_state` |
| `phone_records` | key `(extraction_id, document_index, ordinal)`; `parent_ordinal`, `top_ordinal`, `depth`, `model_type`, `source_model_id` (Cellebrite `id`; **not unique**, 01 section 1.3), `deleted_state`, `is_partial`, `body` (the element as `[tag, attrs, text, children]`, nested records as `["@", ordinal]`, 01 section 5.3) |
| `phone_timestamps` | every TimeStamp value already parsed: `owner_kind`, `owner_ordinal`, `body_path`, `model_type`, `field_name`, `original_text`, `formatted_text`, `instant`, `local_wall_time`, `original_offset_minutes`, `offset_state` (`explicit`, `absent`, `unparsed`), `parse_rule` (01 section 9) |
| `phone_files`, `phone_file_references`, `phone_container_entries` | files, their verification `outcome`, and the three reference mechanisms (`jumptarget`, `file_id_attribute`, `extracted_path_value`) with `resolution` |
| `phone_reconciliations` | only to refuse interpretation of a document whose result is `differs` (flagged, shown, not interpreted until a person accepts it; plan decision 7) |

Identifiers this file adds on top of 01's keys:

- **`record_uid`** = `uuid5(PHONE_NS, f"{extraction_id}/{document_index}/r{ordinal}")`, where `PHONE_NS` is
  a fixed namespace uuid in `backend/services/phone/ids.py`. Stable across re-runs because 01's ordinals are
  a function of the bytes (01 section 6.3). Spec 03's contract uses `record_uid`.
- **`file_uid`** the same with `/f{ordinal}`.
- **Locator**: 01's positional locator (01 section 6.4) is carried on every derived row as `locator text`,
  with `body_path` for the value.

Decisions need a subject row with `id` and `case_id` (`decisions.record` checks both,
`backend/services/financial/decisions.py:296-306`), and `phone_records` has neither. So decisions about a
record go through `phone_record_subjects` (`id uuid PK` = `record_uid`, `case_id`, `extraction_id`,
`document_index`, `ordinal`, `created_at`), a row created in the same transaction as the first decision
about that record (section 8.8).

Body access: `backend/services/phone/body.py` walks a body and yields `FieldView(name, kind, position,
values=[ValueView(index, type, text, attrs, is_empty, body_path)], children=[ordinal])` for all six field
kinds. Every interpretation step uses it, so no code depends on field order or on a field name being unique
inside a record (C8 has 38 records with a repeated field name, 01 section 1.3).

### 1.3 Code placement and runtime

| What | Where |
|---|---|
| Models | `backend/postgres/models/phone_interpretation.py` (registry, derived tables), `backend/postgres/models/phone_identity.py` |
| Migrations | `backend/postgres/alembic/versions/` (the backend owns the shared schema: `evidence_document_texts` was created there, `20260721_add_evidence_document_texts.py`; the engine mirrors tables it writes, `evidence-engine/app/models/job.py:82-100`) |
| Services | `backend/services/phone/`: `registry.py`, `values.py`, `generic.py`, `mappings/loader.py`, `mappings/apply.py`, `mappings/data/*.json`, `coverage.py`, `fold.py`, `identifiers.py`, `names.py`, `owner.py`, `suggestions.py`, `identity_decisions.py`, `corrections.py`, `thread_text.py`, `graph_projection.py`, `link_analysis.py`, `sweep.py`, `time_display.py` (03 section 3.2) |
| Router | `backend/routers/phones.py`, prefix `/api/phones` (placement fixed by spec 03 section 4.1) |
| Tests | `backend/tests/test_phone_*.py`; corpus tests read the local samples from `LOUPE_PHONE_CORPUS` and skip with a stated reason when it is unset; evidence is never committed (CLAUDE.md) |

Python: 3.10 syntax (CLAUDE.md; `backend/Dockerfile:1` runs 3.11 and the local venv 3.12, so nothing newer
than 3.10 may be used and the Unicode tables must not depend on characters added after Unicode 13.0, the
version in Python 3.10's `unicodedata`).

Runtime: interpretation, identity and projection run in the backend as a sweep loop
`run_phone_interpretation_forever()` started in `backend/main.py` beside the financial identity sweep
(`backend/main.py:131-132`), on the same pattern as `run_identity_graph_forever`
(`backend/services/financial/identity_graph.py:328-340`): a thread per pass, one extraction at a time, a
stop event, retry with backoff. **Decision** (14.1): interpretation is a pure function of the capture, the
registry and the mapping set, so it does not need the intake worker's pause and resume. *Reverse if* the
first run on the largest phone (C6 of the 10-report case: 186,787 messages) takes more than 15 minutes or
raises the backend's p95 API latency by more than half during the pass; then move the same functions to
the dedicated phone worker of plan 6.1.

### 1.4 Vocabulary

- **Extraction**: one ingested report, one phone. Labelled C1, C2 ... as in the plan.
- **Record**: one captured `model`, top level or nested.
- **Interpretation level** (plan decision 5): `captured_only`, `generic`, `reviewed`. Computed, never set.
- **Identity**: one identifier in the case (a phone number, an app account, an email address). Keyed by
  `identity_key` (section 8.2). Not a person.
- **Person**: a Loupe dossier (`case_profiles` row; `backend/postgres/models/dossier.py:22` points
  `dossier_id` at `case_profiles.id`). Identities are linked to persons only by decisions (spec 03 section
  10.2 places people on the Dossiers page; this file follows it).

---

## 2. Measurements this file rests on

All from structure only. "Catalogue" is the union of `server_catalog.jsonl` (14 phones) and `cat_c3.json`,
`cat_c9.json`, `cat_c8.json`, aggregated for this file. "Stream" is a streamed iterparse of the local
sample taken for this file.

| Measure | Value | Source |
|---|---|---|
| Report files, record types, total records | 17 files, 62 types, 3,405,526 records (nested included) | catalogue |
| Distinct (type, field, kind) | 470; as (type, field, kind, value type) 471, because one field has two value types | catalogue |
| Field kinds present in the catalogue | `field` 3,300 rows and `multiField` 122 rows across files; no `modelField`, `multiModelField`, `nodeField` or `dataField` rows, because the catalogue script records a combination only when a `<value>` is directly inside it (`catalog.py` in the scratchpad, lines 13-20) | catalogue script |
| Value types | 65: 9 basic (String, TimeStamp, TimeSpan, Guid, Boolean, Int32, Int64, Double, UInt32) and 56 named sets | catalogue |
| Named sets with values recorded | 55 sets, 210 values. The catalogue's 57 "enums" include `Guid` (61 identifiers) and `UInt32` (0, 1), which are basic types, and exclude `DecodingSourceOptions`, which `catalog.py` skips | catalogue, `catalog.py` line 17 |
| `DecodingSourceOptions` (field `UserMapping`) values | `Decoding` only: C3 11,737, C9 5,667, C8 39,865 | stream |
| Combinations by value type | String 229, named set 110, TimeStamp 78, Int32 15, Double 14, Boolean 9, TimeSpan 7, Int64 5, Guid 3, UInt32 1 | catalogue |
| Data-type drift | one field: `ChatActivity.SystemMessageId` String 25 values, Guid 277 values | catalogue |
| Nesting relations (parent type, field, kind, child type) | 47 distinct across C3, C9, C8 (list in 3.6) | stream |
| Types in every report / in one report only | Call, Party, Chat, InstantMessage, Attachment, ContactPhoto / CreditCard, ContactEntry, Recording, Voicemail, RemoteServiceSession | catalogue |
| TimeStamp values | C3 22,881; C9 5,218; C8 59,672 | stream |
| TimeStamp `format` attribute | C3: TimeStampKnown 22,859, DateTimeOnly 21, DateOnly 1. C8: TimeStampKnown 59,666, DateTimeOnly 6. C9: all 5,218 carry an offset in the text | stream |
| `formattedTimestamp` attribute | present on every TimeStamp value, always with an offset, including the DateTimeOnly and DateOnly values (C3: 22,881 of 22,881) | stream |
| TimeSpan text shapes | `HH:MM:SS` (C3 1,258; C8 2,960); `HH:MM:SS.fffffff` (C8 1) | stream |
| `<empty/>` children of fields | C3 31,540 elements (VisitedPage 20,515, InstantMessage 3,754, Contact 2,902, Call 1,854, Party 1,445 ...) | `c3.json` `tagcount`, stream |
| Plain `field` with more than one value | C8: `QuotedMessageData.Label` on 38 fields; none in C3, C9 | stream |
| Coordinates | C3: 31, all under `Location.Position`; C9: 7 under Location, 2 under `WirelessNetwork.Position`; C8: 35 of 206 Location records have a Position, 3 under WirelessNetwork | stream |
| Accuracy on those coordinates | zero in all three samples, on both `Coordinate.GpsHorizontalAccuracy` and `Location.GpsHorizontalAccuracy`; across the 14 server phones `Location.GpsHorizontalAccuracy` is present on 12,728 of 63,784 Location records (spec 03 section 2) | stream, catalogue |
| Party container, `Role`, `IsPhoneOwner` (C3) | InstantMessage.From: Role From, owner False 1,702 / True 857 / absent 284; InstantMessage.To: Role To absent-owner 157, True 141, False 40; InstantMessage party with no Role and owner True 216; Call.Parties: To/absent 559, To/False 496, From/True 462, To/True 333, From/absent 326, From/False 324; Chat.Participants: no Role 981, General 2; Email.From 294, Email.To 293 | stream |
| Party container, `Role` (C8) | InstantMessage.To parties with Role `General` and owner True: 478; SocialMediaActivity.Author Role General 931; Chat.Participants Role General 196 | stream |
| Call `Direction` x `Status` (C3) | Outgoing/Established 535, Outgoing/NotEstablishedUnknownReason 420, Incoming/Missed 362, Incoming/Established 227, ... | stream |
| Party `Identifier` shapes (C3) | WhatsApp user JID 3,360; phone-like 2,174; other 885; email-like 589; short digit strings 48 | stream |
| `UserID.Category` values (C3, C8) | WhatsApp User Id, User Id, User ID, Username, Facebook Id, Additional Name, UNIQUE ID, Signature | stream |
| `PhoneNumber.Category` values (C3, C8) | Mobile, General, Other, Main, Phone, Phone Number, Celular, Móvil, Casa, WhatsApp, and free labels | stream |
| Header MSISDN | metadata item `MSISDN` present in C3; absent in C9 and C8 | `c3.json`, `c9.json`, `c8.json` `meta_items` |
| Device zone in metadata | `Time zone settings (ID)` present in C9 only | `c9.json` `meta_items` |
| `timeZoneConfigurations` | C3: convert-to-UTC on, selected zone Africa/Abidjan; C9: off, America/New_York; C8: none | `c*.json` `tz` |
| Selection flags | `IsPartialData`, `IsSelectiveExtraction`, `IsStoppedByUser` on `extractionInfo` in all three; `IsTriageExtraction` added in 8.5 (C8) | `c*.json` `attrnames` |
| Model attributes | `decoding_confidence`, `deleted_state`, `extractionId`, `file_id`, `id`, `isrelated`, `labels`, `source_index`, `type`; `originalId` added in 8.5 | `c*.json` `attrnames` |
| `deleted_state` values | Intact 138,570; Unknown 18,520; Deleted 1,582; Trash 15 (three samples) | `c*.json` `mt_deleted` |
| `decoding_confidence` values | High only (C3 71,045; C9 14,005; C8 73,637) | stream |
| `file_id` model attribute | only on Attachment: C3 404, C9 759, C8 132 | stream |

---

## 3. Schema registry

### 3.1 What it is for

Plan decision 4: types are discovered, not listed. The registry is the list of everything the reports have
been seen to contain, learned on every ingest, with the first place each thing was seen and a flag for
anything new. It holds **structure only**: type names, field names, field kinds, value types, named-set
values (vocabulary such as `Incoming`), nesting and attribute names. It never holds a String, TimeStamp or
numeric value, an identifier or a GUID. It is therefore not case data, and is global to the deployment
(Loupe is single tenant: `evidence-engine/CLAUDE.md` line 9).

### 3.2 Tables

All in `backend/postgres/models/phone_interpretation.py`. Times are `timestamptz`.

`phone_schema_types`

| Column | Type | Notes |
|---|---|---|
| `type_name` | varchar(128) PK | model `type` attribute verbatim |
| `origin` | varchar(16) not null | `seed` or `observed` (which put it here first) |
| `first_seen_at` | timestamptz not null | |
| `first_seen_extraction_id` | uuid null, FK `phone_extractions.id` ON DELETE SET NULL | null for seed rows |
| `first_seen_report_version` | varchar(32) null | root `reportVersion` of that extraction |
| `first_seen_producer_version` | varchar(64) null | metadata `UFED_PA_Version` |
| `seed_report_count` | int not null default 0 | reports in the seed carrying it |
| `seed_record_count` | bigint not null default 0 | |
| `observed_extraction_count` | int not null default 0 | maintained by the per-extraction observation pass |
| `observed_record_count` | bigint not null default 0 | |
| `seen_top_level` | bool not null default false | answers plan 9 "occurs top-level or only nested" |
| `seen_nested` | bool not null default false | |

`phone_schema_fields` (one row per type, field name, field kind and value type)

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `type_name` | varchar(128) not null FK `phone_schema_types` | |
| `field_name` | varchar(256) not null | verbatim, case kept (`Voicemail.Timestamp` and `Call.TimeStamp` are different names) |
| `field_kind` | varchar(16) not null | check in (`field`, `multiField`, `nodeField`, `dataField`) |
| `value_type` | varchar(128) not null | the `type` attribute; `(empty)` for a field seen only with `<empty/>`; `(none)` for `nodeField` and `dataField` children with no typed value |
| `is_named_set` | bool not null | `value_type` not in the nine basic types and not a placeholder |
| origin, first-seen columns | as in `phone_schema_types` | |
| `seed_value_count`, `seed_report_count` | bigint, int | from the catalogue `{valueType: count}` |
| `observed_value_count`, `observed_empty_count`, `observed_extraction_count` | bigint, bigint, int | |
| `max_values_in_one_field` | int not null default 0 | 2 or more on a plain `field` is itself a flag (C8 `QuotedMessageData.Label`) |
| unique | (`type_name`, `field_name`, `field_kind`, `value_type`) | |

`phone_schema_nesting`: `id bigserial`, `parent_type`, `field_name`, `field_kind` (`modelField`,
`multiModelField`), `child_type`, origin and first-seen columns, `observed_child_count bigint`; unique
(`parent_type`, `field_name`, `field_kind`, `child_type`).

`phone_schema_set_values`: `id bigserial`, `set_name varchar(128)`, `value varchar(512)`, origin and
first-seen columns, `observed_count bigint`; unique (`set_name`, `value`). A set that would exceed 500
distinct values stops recording new values and raises `set_overflow` once (no set in the catalogue has more
than 23: `PermissionCategory`).

`phone_schema_attributes`: `element varchar(64)` (`model`, `extractionInfo`, `project`, `file`, `value` ...),
`attribute varchar(128)`, origin and first-seen columns; unique (`element`, `attribute`). This is how 8.5's
`originalId` and `IsTriageExtraction` would have been flagged.

`phone_schema_observations` (per extraction, so coverage and drift can be stated per phone):
`extraction_id uuid` FK ON DELETE CASCADE, `registry_table varchar(32)`, `registry_id bigint`,
`record_count bigint`, `value_count bigint`, `empty_count bigint`; PK (`extraction_id`, `registry_table`,
`registry_id`).

`phone_schema_flags` (the review queue)

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `flag_kind` | varchar(24) not null | `new_type`, `new_field`, `new_value_type`, `new_set_value`, `new_nesting`, `new_attribute`, `set_overflow`, `multi_value_field` |
| `registry_table`, `registry_id` | varchar(32), bigint | what was flagged |
| `raised_by_extraction_id` | uuid null FK ON DELETE SET NULL | |
| `severity` | varchar(16) not null | `blocks_mapping` when the flagged field or set is named by a reviewed mapping, else `info` |
| `state` | varchar(16) not null | `open`, `acknowledged`, `mapping_needed`, `mapped`, `dismissed` |
| `detail` | jsonb not null | e.g. for drift `{"previous": ["String"], "now": "Guid"}` |
| `raised_at` | timestamptz not null | |

`phone_schema_flag_events` (append only; the registry is global, so case `adjudications` rows, which need a
`case_id` (`backend/postgres/models/financial.py:960-963`), cannot hold these): `id`, `flag_id`,
`from_state`, `to_state`, `reason text not null`, `actor_name`, `actor_email`, `actor_user_id null`,
`created_at`. Actor columns copied in at the time, as in `AdjudicationEvent`
(`backend/postgres/models/financial.py:914-916`).

### 3.3 Observation pass (per extraction)

1. Wait for `capture_state` in (`captured`, `captured_incomplete`) (01 section 6.2).
2. Stream the extraction's `phone_records` ordered by key with a server-side cursor (batches of 5,000) and
   walk each body with `body.py`. Accumulate in memory, per (type, field, kind, value type): records,
   values, empties, the most values seen in one field; per nesting relation (parent type, field, kind, child
   type from the `["@", ordinal]` reference resolved to the child row's `model_type`); per named set its
   values; per element its attribute names (records' `attrs`, and the skeleton's `project`,
   `extractionInfo`, `file` attributes). The accumulators are bounded by the registry's size (hundreds of
   keys), not by the phone's. 01 chose body JSONB over a value table and left value-level indexing to this
   file (01 section 6.1); the registry does not need one.
3. Upsert registry rows. A row not present before gets `origin = observed`, first-seen columns from this
   extraction, and a flag of the matching kind with state `open`.
4. Drift: a new (`type`, `field`, `kind`) row whose first three columns already exist with another
   `value_type` raises `new_value_type` with `detail.previous`.
5. Write `phone_schema_observations` for this extraction (replace on re-run; idempotent).
6. Severity: computed against the current reviewed mapping set (section 6): a flag on a field or set value
   a reviewed mapping names is `blocks_mapping`, and that mapping is suspended for that field on this
   extraction (section 6.7) until the flag leaves `open`.

Concurrency: two extractions observed at once may both try to insert the same new row; inserts use
`ON CONFLICT DO NOTHING` and the flag is raised by whichever transaction inserted, so one flag is raised,
not two.

### 3.4 Review queue states

| From | To | Who | Effect |
|---|---|---|---|
| `open` | `acknowledged` | a person | understood; generic interpretation suffices |
| `open` | `mapping_needed` | a person | goes on the backlog shown in the coverage map |
| `mapping_needed` | `mapped` | automatic, when a reviewed mapping naming it is loaded | records the mapping version in the event |
| any | `dismissed` | a person | with reason |
| `acknowledged`, `dismissed` | `open` | a person | reopen |

Every transition writes a `phone_schema_flag_events` row before the state changes (the rule of
`decisions.py:22-23`). Endpoint: `GET /api/phones/registry/flags?state=open` and
`POST /api/phones/registry/flags/{id}/transition {"to", "reason"}`; admin role only, because the registry is
global (the role check reuses the existing admin dependency used by `routers/admin_ai_costs.py`).

### 3.5 Seeding from the catalogue

The seed is a derived, structure-only file committed to the repo:
`backend/services/phone/data/registry_seed_2026-10-29.json`. It is produced once by
`backend/scripts/phone_registry_seed_build.py` from `server_catalog.jsonl` and `cat_c3.json`, `cat_c9.json`,
`cat_c8.json`, and contains no path, no per-phone breakdown and no value of a basic type. Steps:

1. Read the 17 documents (14 lines of `server_catalog.jsonl`, 3 local files). The 3 local files are kept as
   separate reports, not deduplicated against their server copies, because they are different exports
   (local C8 is report version 8.5 with 250 combinations; its server counterpart has 221).
2. Types: for each `model_types` entry add `seed_record_count` and 1 to `seed_report_count`.
   Expected: 62 types, 3,405,526 records.
3. Fields: for each `catalog` entry `[type, field, kind, {valueType: count}]` and each value type in it, add
   `count` to `seed_value_count` and 1 to `seed_report_count`. Expected: 471 rows over 470 (type, field,
   kind).
4. Named-set values: for each `enums` entry whose set name is not one of the nine basic types, add each
   value. Expected: 55 sets, 210 values. `Guid` and `UInt32` value lists are dropped (they are basic types,
   and the GUIDs are record data). The catalogue capped each report's set at 50 values
   (`catalog.py` line 18); no named set reached that cap (largest 23).
5. `DecodingSourceOptions`: add the value `Decoding` with `origin = seed` and a note that it comes from the
   C3, C9, C8 stream measurement, since `catalog.py` excluded the type.
6. Nesting: the 47 relations measured on C3, C9, C8 (3.6), because the catalogue does not record them.
7. Attributes: the `attrnames` of `c3.json`, `c9.json`, `c8.json` for `model`, `extractionInfo`,
   `project`, `file`, `value`.
8. Pre-acknowledged flag: `ChatActivity.SystemMessageId` drift is written as a `new_value_type` flag in state
   `acknowledged` with reason "Seen in the catalogue: String 25 values, Guid 277 values, across 6 reports".
9. First-seen producer versions are null for seed rows: the catalogue did not record `reportVersion` or
   `UFED_PA_Version` per phone. They are never back-filled; a seed row says "known from the catalogue of
   2026-10-29", which is what is true.

The loader `backend/scripts/phone_registry_seed.py` applies the file idempotently (ON CONFLICT DO UPDATE of
seed columns only). Observation of a seeded combination never raises a flag.

### 3.6 Nesting relations in the seed (measured, C3, C9, C8)

| Parent | Field (kind) | Child types |
|---|---|---|
| Call | Parties (multiModelField) | Party |
| CalendarEntry | Attendees (multiModelField) | Party |
| Chat | Participants, Messages, ActivityLog, Photos (multiModelField) | Party, InstantMessage, ChatActivity, ContactPhoto |
| ChatActivity | Participant (modelField) | Party |
| Contact | Entries (multiModelField) | PhoneNumber, UserID, EmailAddress, ProfilePicture, WebAddress |
| Contact | Addresses, Photos, AdditionalInfo (multiModelField) | StreetAddress, ContactPhoto, KeyValueModel |
| DeviceEvent | Additional_Info (multiModelField) | KeyValueModel |
| Email | From (modelField); To, Cc, Attachments (multiModelField) | Party; Party, Party, Attachment |
| FileDownload, FileUpload | AdditionalInfo (multiModelField); FileUpload Owner (modelField) | KeyValueModel; Party |
| InstantMessage | From, Attachment (modelField); To, Attachments, MessageExtraData, SharedContacts (multiModelField) | Party, Attachment; Party, Attachment, {MessageLabel, ReplyMessageData, ForwardedMessageData, QuotedMessageData}, Contact |
| Location | Position, Address (modelField) | Coordinate, StreetAddress |
| WirelessNetwork | Position (modelField) | Coordinate |
| NetworkUsage | AdditionalInfo (multiModelField) | KeyValueModel |
| RecognizedDevice | AdditionalInfo, DeviceIdentifiers (multiModelField) | KeyValueModel |
| SocialMediaActivity | Author, ParentPost (modelField); Attachments (multiModelField) | Party, SocialMediaActivity; Attachment |
| UserAccount | Entries, Photos, AdditionalInfo (multiModelField) | PhoneNumber, UserID, EmailAddress, ProfilePicture; ContactPhoto; KeyValueModel |

The `Contact`, `ContactPhoto`, `DeviceEvent`, `Email`, `FileDownload`, `InstalledApplication`,
`NetworkUsage`, `SearchedItem`, `UserAccount` and `VisitedPage` records also carry `multiField` children
and `ContactPhoto`, `FileUpload` carry `nodeField`, `Attachment` carries `dataField` (`c*.json`
`fieldnames`). Field names for those kinds are recorded at observation.

---

## 4. Value parsing: times, durations, coordinates

`backend/services/phone/values.py`. Pure functions, no I/O, exhaustively unit tested.

### 4.1 TimeStamp

Spec 01 already parses every TimeStamp value into `phone_timestamps` (01 section 9): `instant`,
`local_wall_time`, `original_offset_minutes`, `offset_state` (`explicit`, `absent`, `unparsed`),
`parse_rule`, with `original_text` and the `formattedTimestamp` attribute as `formatted_text`. This file
does **not** parse times again. It adds, per value, in `phone_time_values` (5.6):

| Column | Rule |
|---|---|
| `producer_format` | the value's `format` attribute read from the body (`TimeStampKnown`, `DateTimeOnly`, `DateOnly` measured) |
| `format_mismatch` | true when `producer_format = TimeStampKnown` and `offset_state <> 'explicit'`, or `DateTimeOnly` with `explicit`; the text wins, the row is flagged |
| `offset_present` | `offset_state = 'explicit'` (spec 03's column) |
| `effective_instant` | `instant`, then corrections and clock offsets (section 10) |

Two rules are confirmed here because the interpretation layer is where they bite:

1. **`formatted_text` never fills an instant.** It carries an offset on every value measured, including the
   DateTimeOnly ones (C3: 22,881 of 22,881), so for offset-less values the offset is the producer's display
   setting, not the device's record (plan 6.7). 01 section 9.4 says the same.
2. **Offset-less values stay without an instant** (C3 22, C8 6; 01 section 9.4) unless a person records the
   decision `apply_phone_zone_to_offsetless` (section 8.8) on the extraction; the resulting instants are
   then labelled `instant from a decision` and the decision is cited on each. Unparsed values (`unparsed`)
   are timeline entries in the "no time" group (spec 03 section 3.1).

### 4.2 Device zone

Settled 2026-10-29: 01 section 9.3 now takes the device zone only from the device setting in the report
metadata or a decision, and records the examiner's selected zone as `flags.examiner_selected_zone`. This file
computes `pv_extraction.device_zone` from the same candidates:

| Candidate | Where | Used as the phone's zone |
|---|---|---|
| metadata item `Time zone settings (ID)` (C9 only) | skeleton metadata | yes, basis `device_setting_in_report` |
| `timeZoneConfigurations@selectedTimeZone` (C3 `Africa/Abidjan`, C9 `America/New_York`) | skeleton | no; shown as `examiner_zone`, basis `examiner_selection` |
| decision `set_phone_device_zone` | `adjudications` | yes, basis `decided`, the computed value kept in the decision's `before` |
| none | | `device_zone = null`, basis `not_in_report`; spec 03 disables the phone-zone option with its reason |

The selected zone is the examiner's report setting: C3 selects Africa/Abidjan with convert-to-UTC on, which
spec 03 section 3.2 records as an examiner setting rather than evidence of the device. 01 section 9.3 has been
aligned to this rule; `pv_extraction.device_zone` is the one every screen uses. *Reverse if* measurement across the 14 server phones shows `selectedTimeZone` equal to the
device's own `Time zone settings (ID)` wherever both exist; then 01's order stands and the basis label
changes.

### 4.3 Display (plan 6.7)

Formatting rules are spec 03's (section 3.2); `backend/services/phone/time_display.py` implements them for
exports and thread texts: `en-US`, 12-hour, weekday and date, zone abbreviation for the day, seconds in
full form, e.g. `Tue, Mar 14, 2023, 3:07:12 PM EDT`. A value with `offset_present = false` renders its
`local_wall_time` with the suffix `(no offset in report)` and never a zone abbreviation. Zone conversion uses
`zoneinfo`; never string slicing.

### 4.4 TimeSpan

`HH:MM:SS`, `HH:MM:SS.fffffff`, and the .NET form `d.HH:MM:SS[.f]` are accepted; result
`duration_seconds numeric(18,7)` plus the original text. Anything else: null with `problem = unparseable`.

### 4.5 Coordinate

A `Coordinate` record yields a point when `Latitude` and `Longitude` both parse as finite doubles within
[-90, 90] and [-180, 180]. Flags: `zero_zero` (both exactly 0), `out_of_range`, `unparseable`,
`missing_axis`. `Elevation` is kept in metres as captured. Accuracy:

1. `Coordinate.GpsHorizontalAccuracy` if present, basis `gps_horizontal`;
2. else the parent `Location.GpsHorizontalAccuracy`, basis `gps_horizontal`;
3. else `Location.Precision` is kept verbatim as text with basis `precision_field` (its unit is not
   established, 15);
4. else null, basis `none`. Spec 03 section 13 draws such points dashed.

### 4.6 Numbers and booleans

Int32, Int64, UInt32: Python `int`. Double: `decimal.Decimal` from the text, so no binary rounding enters a
stored value (the reason the financial subsystem forbids floats in snapshots: `decisions.py:162-168`);
coordinates are the one exception and are stored as `double precision` for spatial indexing, with the text
kept. Boolean: `True`/`False` verbatim (measured exactly these two strings).

---

## 5. Generic interpretation by value role

### 5.1 Principle

Every record of every type, known or not, is interpreted by the role its values play, read from the
report's own value types and nested type names (plan 3.3). No list of types appears in this code. A type
first seen tomorrow gets timeline entries, map points, participants, identities, files and text the moment
it is captured.

### 5.2 Rule table

| Record has | Derived object | Computed label and level | Edge cases |
|---|---|---|---|
| any field with value type `TimeStamp` (78 combinations, e.g. `Call.TimeStamp`, `VisitedPage.LastVisited`, `Party.DateRead`, `CalendarEntry.Reminders` multiField) | one `phone_time_values` row per value, and one timeline entry per value | label = field name verbatim (`LastVisited`), `field_meaning` null until a reviewed timestamp-meaning row supplies one (spec 04); level `generic` | multi-valued fields give one entry per value with `value_index`; a TimeStamp on a nested record (Party.DateRead) is an entry attributed to the nested record and its top-level ancestor; no-time and no-offset per 4.1 |
| field with value type `TimeSpan` (`Call.Duration`, `Voicemail.Duration`, `ApplicationUsage.ActiveTime`, `InstantMessage.SelfDestructDuration` ...) | `duration_seconds` on the record's derived row | `generic` | never added to a time to make an end instant except where a reviewed mapping says so (`Call`: section 6.9) because `SelfDestructDuration` is not an end time |
| nested `Coordinate` (under `Location.Position`, `WirelessNetwork.Position`; any parent) | one `phone_location_points` row | `source_kind` from the parent type through the generic table in 5.4; `affiliation` from `DeviceLocationAffiliation` on the parent; level `generic` | `instant` is the parent's first TimeStamp value in field order when no mapping names the event time, and the point carries `time_field`; a Location with no Position (C8: 171 of 206) is not a point and is counted as `not_positionable` with reason `no_coordinate` |
| nested `Party` (any container) | `phone_participations` row; identity sighting of its `Identifier` | role from 5.3; `is_phone_owner` verbatim; level `generic` | a Party with no `Identifier` and no `Name` still yields a participation with `identity_key = null` and role, so counts never drop it |
| nested `PhoneNumber`, `UserID`, `EmailAddress`, `WebAddress` (under Contact.Entries, UserAccount.Entries; any parent) | identity sighting with the `Value`, `Category`, `Domain` | kind from section 8.2, context `listed_on_card`; level `generic` | `WebAddress` is a URL, recorded as text, not an identity |
| nested `StreetAddress` (`Contact.Addresses`, `Location.Address`) | address text row: `Street1, Street2, HouseNumber, City, State, PostalCode, Country, Neighborhood` joined in that order | never geocoded (plan decision 8: no evidence to a third party); level `generic` | `Location.PositionAddress` (String) is kept as written text beside it |
| named-set value from `ModelDirections` (`Call.Direction`) | `direction` on the derived event: `incoming`, `outgoing`, `unknown` | `generic` | `Unknown` is a captured value, kept as `unknown`, not null |
| `PartyRole` value | role as in 5.3 | `generic` | |
| `IsPhoneOwner` on a Party | `is_phone_owner` on the participation; owner evidence for section 8.6 | `generic` | absent is not False |
| file reference: model attribute `file_id`; `jumptargets`; `*_extracted_path` fields (`attachment_extracted_path`, `contactphoto_extracted_path`, `voicemail_extracted_path`); `VisitedPage.UrlCacheFile` | link rows from spec 01's resolution (`pv_attachment_link`), joined to the record | `generic` | resolution and verification are 01's; this file only attaches; `ApplicationUsage.LastScreenshot` is a Guid whose referent is not established (15) |
| `String` value (229 combinations) | `phone_texts` row with `value` verbatim and `value_folded` (section 8.4) | searchable; level `generic` | sensitive fields (5.5) are marked `is_sensitive` and excluded from default search and export (plan 12.1 rule 4) |
| model attribute `deleted_state` | `deleted_state` on every derived row of the record | flag shown as captured: Intact, Deleted, Trash, Unknown | nested records inherit nothing: a Party's own `Unknown` is shown as the Party's; the message's state is the message's |
| model attribute `decoding_confidence` | `decoding_confidence` on every derived row | verbatim (`High` only, measured) | any other value is shown verbatim and raises `new_attribute`-style flag kind `new_set_value` on a pseudo-set `@decoding_confidence` |
| field `UserMapping` (`DecodingSourceOptions`) | `user_mapping` on derived rows | verbatim; the attribution meaning of values other than `Decoding` is spec 04's (its 4.3) | only `Decoding` measured |
| field `DeviceLocationAffiliation` / `AccountLocationAffiliation` | `affiliation` on the location point | verbatim (Extracted, Synced, Unknown) | `Synced` is flagged by spec 04's attribution mapping as possibly another device |
| Boolean, Int, Double, Guid fields | none generically | `captured_only` unless a mapping names them | they remain in the record view and raw source view |

### 5.3 Participant roles

Role is computed from the container field and `Role` together, because the measurements show `Role` absent
on many parties (C3: 216 InstantMessage parties with no Role) and `General` used inside a `To` container
(C8: 478).

| Container (parent.field) | `Role` value | Role | Basis |
|---|---|---|---|
| `*.From` (modelField) | From, absent | `sender` | `container` |
| `*.From` | To | `sender`, flag `role_conflict` | `container` |
| `*.To`, `*.Cc`, `*.Bcc` | To, General, absent | `recipient`, `cc`, `bcc` | `container` |
| `*.To` | From | `recipient`, flag `role_conflict` | `container` |
| `Call.Parties` | From | `caller` | `role` |
| `Call.Parties` | To | `callee` | `role` |
| `Call.Parties` | General, absent | from `Direction` and `IsPhoneOwner`: owner True and Outgoing, or owner False and Incoming, gives `caller`; owner True and Incoming, or owner False and Outgoing, gives `callee`; otherwise `unknown` | `direction_inferred` |
| `Chat.Participants` | any | `participant` | `container` |
| `ChatActivity.Participant` | any | `activity_subject` | `container` |
| `CalendarEntry.Attendees` | any | `attendee` | `container` |
| `SocialMediaActivity.Author` | any | `author` | `container` |
| `FileUpload.Owner` | any | `owner_of_item` | `container` |
| `ForwardedMessageData.OriginalSender` | any | `original_sender` | `container` |
| any other container | any | `party:<FieldName>` | `container` |

**Owner side.** A message, call or email with no participant whose `is_phone_owner` is True gets a
synthetic participation `role = owner_implicit` bound to the extraction's owner identity (section 8.6), or
to no identity when the owner is unidentified. Spec 03 requires this row so no screen joins two parties and
drops calls (03 section 1.2; v1 memory note `project_cellebrite_call_one_edge.md`).

**Direction of a message** (generic): sender `is_phone_owner` True gives `outgoing`; False gives
`incoming`; absent gives `unknown`. A call uses `Direction`; a disagreement between `Direction` and the
owner flag sets `direction_conflict` and keeps `Direction`.

### 5.4 Generic `source_kind` of a location point

| Parent type | `source_kind` |
|---|---|
| Location with `Origin = Device` or no Origin | `device_location` |
| WirelessNetwork | `wifi` |
| CellTower (no coordinates measured) | not a point; `not_positionable` with reason `cell_identity_only` |
| any other parent | `other:<ParentType>` |

Spec 04 refines kinds and radii through its reference data; the generic kind is never upgraded by code.

### 5.5 Sensitive fields (generic list, reviewed)

`Password.Data`, `Password.GenericAttribute`, `WirelessNetwork.Password`, `UserAccount.Password`,
`CreditCard.CreditCardNumber`, `Cookie.Value`, `Autofill.Value`, `DictionaryWord.Word` (plan 12.1 rule 4;
plan 11.1). Held in `mappings/data/sensitive_fields.json` (a mapping kind, section 6.3), so adding one is a
reviewed data change.

### 5.6 Derived tables (case-scoped; all rebuildable)

Every table carries `case_id uuid not null`, `extraction_id uuid not null`, `document_index smallint not null`,
`ordinal int not null` (01's record key), `record_uid uuid not null` (1.2), `root_record_uid uuid not null`
(from 01's `top_ordinal`), `locator text not null` (01 section 6.4), `interpretation_level varchar(16)`,
`mapping_version_id uuid null`, `deleted_state varchar(16) null`, `decoding_confidence varchar(16) null`,
`flags text[] not null default '{}'`, and `generation int not null` (section 5.7).

| Table | Key columns (beyond the common ones) |
|---|---|
| `phone_time_values` | `time_uid uuid PK` (uuid5 of `record_uid` and `body_path`), the 01 key of the `phone_timestamps` row (`document_index`, `owner_ordinal`, `body_path`), `model_type`, `field_name`, `field_path text` (readable, e.g. `Parties[2].DateRead`), `value_index`, copied from `phone_timestamps`: `instant`, `local_wall_time`, `original_text`, `formatted_text`, `original_offset_minutes`, `offset_state`; added: `producer_format`, `format_mismatch`, `offset_present`, `effective_instant` (section 10), `instant_basis` (`report`, `decision`), `field_meaning text null`, `semantics text null` (spec 04's timestamp-meaning row), `is_event_time bool` (a reviewed mapping names this field the event time) |
| `phone_location_points` | `point_uid` PK, `coordinate_record_uid`, `lat`, `lon` (double), `elevation_m numeric null`, `accuracy_m numeric null`, `accuracy_basis`, `precision_text`, `source_kind`, `affiliation`, `instant`, `end_instant`, `time_field` |
| `phone_participations` | `participation_uid` PK, `party_record_uid null`, `role`, `role_basis`, `is_phone_owner bool null`, `identifier_raw text null`, `name_in_record text null`, `identity_key text null`, `date_read`, `date_delivered`, `date_played` |
| `phone_comm_events` | as `pv_comm_event` in spec 03 section 1.2, produced only by reviewed mappings (section 6.9), plus `title text` |
| `phone_threads` | as `pv_thread`, produced by the Chat, InstantMessage, Call and Email mappings |
| `phone_texts` | `text_uid` PK, `field_path`, `value text`, `value_folded text`, `is_sensitive bool` |
| `phone_record_summaries` | `record_uid` PK, `title text` (generic: `<Type>` plus first String field value up to 120 characters for display only), `first_instant`, `has_time bool`, `has_point bool`, `participant_count int` |

Indexes are those spec 03 section 4.7 requires, plus `(case_id, extraction_id, model_type)` on each.

### 5.7 Generations and retroactive rebuild

Interpretation of one extraction is deterministic. Each pass writes its rows with
`generation = previous + 1` in one transaction and deletes the previous generation in the same transaction,
then updates `phone_interpretation_state`:

| Column | Notes |
|---|---|
| `extraction_id` PK | |
| `generation` | current |
| `mapping_set_id` | uuid of the reviewed mapping set used (6.6) |
| `registry_observed_at` | |
| `interpreted_at`, `identities_at`, `texts_at`, `projected_at` | per stage |
| `device_zone`, `device_zone_basis`, `examiner_zone` | section 4.2 |
| `decision_revision` | sha256 over the ids of the extraction's phone decisions (8.8), so a new decision re-derives |
| `status` | `pending`, `running`, `done`, `failed`, `held` (a document's reconciliation `differs`, 1.2) |
| `error` | text |

The sweep picks any extraction with `standing` in (`pending`, `active`) whose `mapping_set_id` differs from
the loaded set, whose capture was replaced, or whose `decision_revision` changed. A `superseded` extraction
(01 section 6.2) keeps its derived rows but is excluded from every `pv_*` view by `standing = 'active'`, so
replacing a phone never shows both copies and never deletes the earlier reading. This is how a newly reviewed mapping is applied to
everything already captured with no re-ingest (plan 6.5). Readers query the current generation only.

---

## 6. Reviewed mappings as versioned data

### 6.1 What a mapping is

A mapping is data that says what a type's fields mean: which TimeStamp is the event time, which party is
the sender, which fields are the text, where the place is. It is not code. Plan 6.5: applied to everything
already captured, AI may draft one, a person reviews it, it is never applied automatically.

### 6.2 Format and location

- JSON (not YAML: the backend test bootstrap in CLAUDE.md does not install PyYAML; JSON already serves as
  versioned data in `backend/services/financial/statement_engine_routes.json`).
- One file per mapping: `backend/services/phone/mappings/data/<kind>/<name>.json`.
- Validated by a pydantic model (`extra='forbid'`, as `account_identity.py:23`) in
  `backend/services/phone/mappings/loader.py`.
- History is git. The commit that changes a mapping is its review record (CLAUDE.md: commit messages are
  the durable record of reasoning).

### 6.3 Mapping kinds

| `kind` | Defines | Content written in |
|---|---|---|
| `type` | event time, participants, place, text, thread, title, flags for one record type | this file (6.9) |
| `activity_strength` | rows `(type, field, value, context) -> class, actor, physical` | spec 04 section 3 |
| `timestamp_meaning` | meaning sentence and semantics per (type, field) | spec 04 section 2 |
| `attribution` | flags such as `Synced` | spec 04 section 4.3 |
| `sensitive_fields` | list in 5.5 | this file |
| `dedup` | duplicate rule version | spec 03 section 3.4 (version 1) |
| `natural_key` | per type, the fields that identify "the same record" across two extractions | spec 05 approach 12 (its 15.x step 3); initial rows for messages, calls, contacts there |
| `platform_family` | normalisation of `Type`, `SourceApplication`, `Source` to a family (`sms`, `imessage`, app name) | spec 05 K1; rows written there |

Kinds other than `type` are **row tables** (6.5b): the same envelope, a `body.rows` array, and a match
discipline the loader enforces. Spec 04 asked that activity strength be computed in a view from reviewed
mapping data (04 section 3.4, 7.2); the loader therefore also writes every row of every loaded reviewed
version into `phone_mapping_rows` so the view can join in SQL.

### 6.4 Common envelope

```json
{
  "kind": "type",
  "name": "Call",
  "version": 1,
  "status": "reviewed",
  "origin": "human",
  "review": {
    "reviewed_by": "Neil Byrne",
    "reviewed_on": "2026-11-02",
    "basis": "Fields and value types checked against registry rows; see section 6.9 of spec 02.",
    "registry_requirements": [
      ["Call", "TimeStamp", "field", "TimeStamp"],
      ["Call", "Direction", "field", "ModelDirections"]
    ]
  },
  "body": {}
}
```

- `status`: `draft` or `reviewed`. The applier loads only `reviewed`.
- `origin`: `human` or `ai_draft`. An `ai_draft` file can only become `reviewed` in a commit that also sets
  `review.reviewed_by` to a person's name; the loader refuses a `reviewed` file whose `reviewed_by` is
  empty or names a model.
- `registry_requirements`: each listed (type, field, kind, value type) must exist in the registry; a
  requirement absent or under an open `new_value_type` flag suspends the mapping for the affected
  extraction (6.7).
- `version` increases by one on every change to `body`; the loader refuses two files with the same name and
  kind, and refuses a version lower than the highest already recorded in `phone_mapping_versions`.

### 6.5 `type` mapping body

```json
{
  "applies_to": "Call",
  "comm_kind": "call",
  "event_time": {"field": "TimeStamp"},
  "end_time": {"field": null, "duration_field": "Duration"},
  "other_times": [],
  "participants": {
    "containers": ["Parties"],
    "role_map": {"From": "caller", "To": "callee"},
    "owner_flag": "IsPhoneOwner",
    "direction_field": "Direction"
  },
  "thread": {"strategy": "counterpart_set", "group_field": null},
  "place": null,
  "text_fields": [],
  "status_fields": {"status": "Status", "call_type": "Type", "video": "VideoCall"},
  "app_field": "Source",
  "account_field": "Account",
  "title": "{direction} call, {status}",
  "activity_strength": {"$ref": "activity_strength/Call"}
}
```

Field rules: every field named must be a registry field of `applies_to` or of a child type reached through a
named container; `event_time.field` must have value type TimeStamp; `duration_field` TimeSpan; `place`
names a container whose child type is `Coordinate` or a String field holding written place text
(`{"text_field": "Location"}`); `thread.strategy` is one of `parent_chat` (the message is nested in a Chat's
`Messages`), `counterpart_set` (the sorted set of non-owner identity keys plus app), `field` (a named
field), `none`. `activity_strength.$ref` is the hook for spec 04: the referenced file's rows are evaluated
for this type's records and their result stored by 04; when absent, 04's default `unknown` applies.

### 6.5b Row-table kinds (activity strength, timestamp meaning, attribution, natural key, platform family)

```json
{
  "kind": "activity_strength", "name": "DeviceEvent", "version": 1, "status": "reviewed",
  "origin": "human", "review": {"reviewed_by": "Neil Byrne", "reviewed_on": "2026-11-05",
                                "basis": "...", "registry_requirements": [["DeviceEvent", "EventType", "field", "DeviceEventTypes"]]},
  "body": {
    "rows": [
      {
        "row_id": "devev-textinput",
        "type": "DeviceEvent",
        "field": "StartTime",
        "predicates": [{"field": "EventType", "op": "eq", "value": "TextInput"}],
        "context": [],
        "outputs": {"class": "interaction", "actor": "owner", "physical": false},
        "basis": "field_name",
        "reasoning": "typing needs a person",
        "would_change": "M1 shows TextInput emitted by dictation or automation sources"
      }
    ]
  }
}
```

| Element | Rules |
|---|---|
| `row_id` | unique within the name across versions; spec 04 stores it as `activity_mapping_row` (04 section 7.2) |
| `type`, `field` | exact registry type and field names; `field` is the time field the event is built from (04 section 3.2), or for `natural_key` and `platform_family` null |
| `predicates` | list of `{field, op, value}` on fields of the same record, read through `body.py`. `op` in `eq`, `in`, `lt`, `le`, `gt`, `ge`, `present`, `absent`. `eq`/`in` on a named-set field must use values present in `phone_schema_set_values` (load fails otherwise); numeric ops only on Int32, Int64, UInt32, Double fields |
| `context` | list of `{name, op, value}` over computed facts this file supplies on every derived event: `party_role` (5.3 roles of the party the time sits on), `party_is_owner` (true, false, null), `direction`, `container` (parent field name), `platform` (`InstantMessage.Platform`), `source` (the top-level record's `Source`), `user_mapping`, `affiliation`, `deleted_state`, `decoding_confidence`, `offset_state`, `semantics` (the timestamp-meaning row's result, available to activity and attribution rows) |
| `outputs` | per kind: `activity_strength` `{class, actor, physical}` with 04's vocabularies (class `interaction`, `device_state`, `passive`, `unknown`; actor `owner`, `counterpart`, `other_device`, `account`, `unknown`); `timestamp_meaning` `{semantics, meaning}` with 04 section 2's semantics list; `attribution` `{flag, group}`; `natural_key` `{fields: [...], volatile_fields: [...]}`; `platform_family` `{family}` |
| `basis` | `field_name`, `corpus_measured`, `vendor_doc`, `not_established` (04's vocabulary); `not_established` forces `unknown` outputs |
| `reasoning`, `would_change` | mandatory text; shown beside the result in the product (04 shows both) |

Match discipline (04 section 3.4, enforced at load, never at run time):

1. Rows of one kind match on (`type`, `field`) exactly, then all predicates and context items must hold.
2. Specificity = number of predicates plus context items. The most specific matching row wins.
3. Two rows of equal specificity that could both match one input are a load error. "Could both match" is
   decided statically: same (`type`, `field`), and for every field or context name the two rows both
   constrain, their value sets intersect (`eq`/`in` sets overlap; numeric ranges overlap; `present` with
   anything except `absent`). The loader names both `row_id`s and refuses to start.
4. No match: `unknown` with basis `default_unknown` (04) or, for attribution, no flag.

`phone_mapping_rows`: `mapping_version_id uuid`, `kind`, `name`, `row_id`, `type_name`, `field_name`,
`predicates jsonb`, `context jsonb`, `specificity int`, `outputs jsonb`, `basis`, `reasoning`,
`would_change`; PK (`mapping_version_id`, `row_id`); index (`kind`, `type_name`, `field_name`). The current
version of each kind is in `phone_mapping_current` (`kind`, `name`, `mapping_version_id`), which 04's
`pol_projection_state.*_mapping_version` columns record when they apply it. The Python evaluator
`mappings/rows.py:evaluate(kind, event_facts)` and the SQL used by 04's view implement the same rule and are
tested against one fixture (`backend/tests/fixtures/mapping_rows_cases.json`).

### 6.6 Versions and the mapping set

- `phone_mapping_versions`: `id uuid PK` (uuid5 of `kind`, `name`, `version`, sha256 of canonical JSON),
  `kind`, `name`, `version`, `content_sha256`, `content jsonb`, `status`, `origin`, `reviewed_by`,
  `reviewed_on`, `loaded_at`. Written by the loader at startup; append only. Spec 04's `*_mapping_version`
  columns hold these ids.
- The **mapping set** is the sorted list of loaded reviewed version ids; `mapping_set_id` = uuid5 of its
  joined text. A deploy that changes any reviewed file changes the set id, and the sweep (5.7) re-derives
  every extraction.
- `phone_mapping_applications`: `extraction_id`, `mapping_version_id`, `generation`, `records_matched`,
  `records_suspended`, `suspension_reasons jsonb`, `applied_at`. Answers "which mapping version produced
  this row".

### 6.7 Applying a mapping

For each extraction and each reviewed `type` mapping whose `applies_to` occurs in it:

1. Check `registry_requirements` against the extraction's observations. Any requirement with an open
   `blocks_mapping` flag: the mapping is suspended for this extraction; generic interpretation stands for
   that type; `records_suspended` and the reason are recorded; the coverage map shows `suspended`.
2. Otherwise produce, for each record of the type: the event time (`is_event_time` on the named
   `phone_time_values` row), the comm event and thread rows, the participants with mapped roles, the title.
   The record's derived rows carry `interpretation_level = reviewed` and `mapping_version_id`.
3. Generic rows are not discarded: every TimeStamp still has its own timeline entry; the mapping only marks
   which one is the event time and supplies meaning.

### 6.8 Review workflow and AI drafts

1. A draft is written as a file with `status: draft` (by hand, or by an AI draft job).
2. AI drafts: `POST /api/phones/registry/mapping-drafts {"type_name"}` (admin) runs a local model (plan
   decision 8) over the registry rows of that type only (names, kinds, value types, set values, counts; no
   case values), and stores the proposal in `phone_mapping_proposals` (`id`, `kind`, `name`, `content
   jsonb`, `model`, `model_version`, `created_at`, `state` in `draft`, `rejected`, `exported`). It is
   exported as a file for a person to edit and commit. Nothing reads `phone_mapping_proposals` at
   interpretation time; a test asserts that the applier never queries it.
3. Review means: a person checks each named field against the registry and the coverage counts on at least
   one extraction, writes the `review` block, sets `status: reviewed`, and commits. Neil is the reviewer of
   record (CLAUDE.md: only engineer). The loader records the version.
4. Removing a mapping is a reviewed change too (delete the file, commit); the next set id re-derives with
   generic interpretation.

### 6.9 Initial `type` mappings (to be reviewed; field names are the catalogue's)

| Type | Event time | End / duration | Participants (container: role) | Thread | Place | Text | Other fields carried |
|---|---|---|---|---|---|---|---|
| Call | `TimeStamp` | `Duration` (TimeSpan); end = start + duration, labelled computed | `Parties`: From caller, To callee; `IsPhoneOwner`; `Direction` | `counterpart_set` | none | none | `Status` (TelephonyCallStatus), `Type` (CallType), `VideoCall`, `DisconnectionCause`, `NetworkName`, `CountryCode`, `Account`, `Source`, `ServiceIdentifier` |
| InstantMessage | `TimeStamp` | none | `From`: sender; `To`: recipient | `parent_chat`, else `counterpart_set` for top-level messages (C3: 201 top-level, sources Android CallLog database and IMS Service) | `IsLocationSharing` flag only | `Body`, `Subject` | `Status` (MessageStatus), `Type` (InstantMessageType), `Folder`, `SourceApplication`, `Platform`, `Identifier`, `SMSC`, `DateDelivered`, `DateDeleted` with `DeletionReason`, `SelfDestructDuration`, `Label`, `MessageExtraData` children (MessageLabel.Label; ReplyMessageData.OriginalMessageID; QuotedMessageData.OriginalMessageID, ReferenceId; ForwardedMessageData.TimeCreated, OriginalSender), `Attachments`, `Attachment`, `SharedContacts`; per recipient `Party.DateRead`, `DateDelivered`, `DatePlayed` |
| Chat | `LastActivity` is not an event time; the Chat is a thread, not an event. `StartTime` and `LastActivity` become thread bounds as recorded | | `Participants`: participant | thread key = `chat:<extraction_id>:<record_uid>`; title `Name` | | `Name`, `Description` | `Id`, `ChatType`, `Account`, `Source`, `ServiceIdentifier`; `ActivityLog` children (ChatActivity: `Action`, `Participant`, `SystemMessageBody`, `SystemMessageTimeStamp`, `SystemMessageId`) as comm events of kind `chat_activity` |
| Email | `TimeStamp` | | `From`: sender; `To`: recipient; `Cc`: cc | `field`: `Folder` plus normalised `Subject` (leading `Re:`, `Fwd:` removed, case folded) | | `Subject`, `Body`, `Snippet` | `Labels`, `Status`, `Priority`, `Account`, `Attachments`. The full `Body` is kept (v1 cut it at 2,000 characters, plan 4.5) |
| Contact | none (a contact is not an event); `TimeCreated` and `TimeModified` keep their own timeline entries with meanings "Contact saved on this phone" and "Contact last changed on this phone" | | none; `Entries` identities are the contact's own identifiers (`listed_on_card`) | | | `Name`, `Notes` | `Type`, `InteractionStatuses`, `Account`, `Source`, `Addresses`, `Photos`, `AdditionalInfo`. `Name` is this phone's name for every identifier on the card (8.5) |
| Location | `TimeStamp` | `EndTime` | none | | `Position` (Coordinate), `Address`, `PositionAddress` | `Name`, `Description` | `Category`, `Type`, `Origin`, `Confidence`, `Precision`, `GpsHorizontalAccuracy`, `DeviceLocationAffiliation`, `AccountLocationAffiliation`, `AggregatedLocationsCount`, `Account` |
| CellTower | `TimeStamp` | | none | | cell identity `MCC`, `MNC`, `LAC`, `CID`, `Type`; position only through spec 04's offline reference data | | |
| WirelessNetwork | `TimeStamp` (meaning to be set by 04; `LastConnection`, `LastAutoConnection`, `EndTime` keep entries) | `EndTime` | none | | `Position` when present | `SSId` | `BSSId`, `NWConnectionType`, `SecurityMode`; `Password` sensitive |
| VisitedPage | `LastVisited` (latest visit only, plan 11.2 rule 2) | | none | | | `Title`, `Url` | `VisitCount`, `UsagePattern`, `UrlCacheFile`, `ServiceIdentifier` |
| SearchedItem | `TimeStamp` | | none | | | `Value`, `SearchResults` | `Origin`, `Account`, `OSUserId`, `Source` |
| DeviceEvent | `StartTime` | `EndTime` | none | | | `Value`, `AdditionalInfo` | `EventType` (DeviceEventTypes, 16 values), `Additional_Info` KeyValueModel children, `ServiceIdentifier` |
| PoweringEvent | `TimeStamp` | | none | | | `Description` | `Event` (On, Off), `Element` |
| UserAccount | none; `TimeCreated` keeps its entry ("Account created") | | none; `Entries` identities are the owner's accounts on this phone (owner evidence, 8.6) | | | `Name`, `Notes` | `Username`, `ServiceType`, `ServiceIdentifier`, `ServerAddress`, `Photos`; `Password` sensitive |
| CalendarEntry | `StartDate` | `EndDate` | `Attendees`: attendee | | written place `Location` (String; never geocoded) | `Subject`, `Details` | `Reminders` (multiField TimeStamp, each its own entry), `RepeatRule`, `RepeatInterval`, `RepeatDay`, `RepeatUntil`, `Availability`, `Category`, `Account` |
| Notification | `TimeStamp` | | none | | | `Subject`, `Body`, `Notes` | `ServiceIdentifier` (app), `Status`, `Type` |
| AppsUsageLog | `StartTime` | `EndTime` | none | | | `AdditionalInfo` | `Action` (Launch, Close), `Identifier`, `ServiceIdentifier`, `SubModule` |
| ApplicationUsage | `StartTime` | `EndTime` | none | | | `Name` | `LastLaunch`, `ActiveTime`, `BackgroundTime`, `LastUsageDuration`, `LaunchCount`, `ActivationCount`, `Identifier` |
| NetworkUsage | `DateStarted` | `DateEnded` | none | | | `SSId` | `UsageMode` (Foreground, Background), `NetworkConnectionType`, `IsRoaming`, `NumberOfBytesSent`, `NumberOfBytesReceived`, `ApplicationId` |
| DeviceConnectivity | `StartTime` | | none | | | `DeviceName` | `ConnectivityMethod`, `ConnectivityNature`, `DeviceType` |
| Voicemail | `Timestamp` (lower-case s, as captured) | `Duration` | none generic (the record has no Party) | `counterpart_set` empty, thread `voicemail` | | `Name` | `WasPlayed`, `LastModified`, `voicemail_extracted_path` |
| Note | `Modification`; `Creation` keeps its entry | | none | | | `Title`, `Body`, `Summary` | `Folder`, `Account`, `Attachments` |

Order of review: Call, InstantMessage, Chat, Email, Contact, UserAccount first (identities and Conversations
depend on them); then Location, WirelessNetwork, CellTower; then the activity types together with spec 04's
activity-strength rows (plan 11.4).

---

## 7. Coverage map

### 7.1 Computation

Per extraction, per (type, field path, kind, value type) from `phone_schema_observations`, the level is:

| Level | Rule |
|---|---|
| `reviewed` | a reviewed `type` mapping of this type names the field (any role), and it is not suspended |
| `suspended` | a reviewed mapping names it but is suspended on this extraction (6.7) |
| `generic_role` | the field's value type or child type has a role in 5.2 other than text: TimeStamp, TimeSpan, Coordinate, Party, PhoneNumber, UserID, EmailAddress, ModelDirections, PartyRole, IsPhoneOwner, file references, UserMapping, location affiliations |
| `generic_text` | a String field with no other role (searchable only) |
| `captured_only` | anything else (Boolean, Int, Double, Guid and named sets with no role) |

Record attributes are listed too (`deleted_state`, `decoding_confidence`: `generic_role`; `source_index`,
`extractionId`, `isrelated`, `labels`, `originalId`: `captured_only`).

Coverage is a view, `pv_coverage`, computed on read from observations and the loaded mapping set; nothing is
stored that could go stale.

### 7.2 API

`GET /api/phones/{extraction_id}/coverage?case_id=`

```json
{
  "extraction_id": "uuid",
  "selection": {
    "IsSelectiveExtraction": "False", "IsPartialData": "False", "IsStoppedByUser": "False",
    "IsTriageExtraction": null,
    "per_extraction_info": [{"index": "0", "name": "...", "type": "...", "IsPartialData": "False"}]
  },
  "summary": {"types": 35, "fields": 178, "reviewed": 0, "generic_role": 0, "generic_text": 0,
              "captured_only": 0, "suspended": 0, "records_by_level": {}},
  "types": [
    {"type": "Call", "records": 1657, "level": "reviewed", "mapping_version_id": "uuid",
     "fields": [{"field": "Duration", "kind": "field", "value_type": "TimeSpan",
                 "values": 1258, "empties": 0, "level": "reviewed"}]}
  ],
  "flags": [{"flag_kind": "new_field", "state": "open", "type": "...", "field": "..."}]
}
```

`selection` reproduces the production's own statement verbatim from every `extractionInfo` element (C3 has
three). Values are strings as captured, never converted to booleans, so `null` (absent) is distinguishable
from `"False"`. "Chosen types and ranges" is listed in plan 6.5; where the report states it is not
established (15).

### 7.3 Display (spec 03 section 7, Extraction profile)

Shown beside the production's selection, never instead of it, with the sentence pattern "The production
says it is a selective extraction. Loupe reads 31 of 35 record types in detail; 4 are kept and searchable
but not yet interpreted." Exact UI copy is spec 03's; no em dashes in it.

---

## 8. Identity model

### 8.1 Layers

| Layer | What | Changes by |
|---|---|---|
| Sighting | one identifier value seen in one record on one phone, with its context | capture only |
| Identity | one normalised identifier in the case (`identity_key`) | computation only |
| Phone's names | each phone's own name for an identity | computation only (evidence) |
| Owner | which identities belong to the phone's owner | computation, overridable by decision |
| Person | a dossier; identities linked to it | decisions only |

There is no automatic merge of two identities into one, except the one equivalence that is true by
construction: a WhatsApp user JID whose digits are a valid number is that number's identity (8.2 rule P2;
v1 did the same, `neo4j_writer.py:167-185` on `origin/main`, after a 72,000-message thread was split from
its number). Everything else is a suggestion a person decides (plan 13; spec 03 section 10.3).

### 8.2 Identifier normalisation

`backend/services/phone/identifiers.py`, function `classify(raw, *, context, region) -> Identifier |
None`, where `Identifier = (kind, subkind, value_normalised, value_display, identity_key, region_basis)`.
`kind` is spec 03's (`phone`, `app_user`, `email`, `other`).

Phone numbers use libphonenumber. Loupe does not have it today: `backend/services/phone_normalise.py`
is a regex normaliser accepting only E.164-shaped strings and US 10/11-digit numbers (lines 29-71); v1
replaced the same module with a libphonenumber implementation (`backend/services/phone_normalise.py` on
`origin/main`, `normalise()`, using `parse` then `is_valid_number` then E.164) pinned at
`phonenumbers==9.0.31` in v1's `backend/requirements.txt`. **Decision:** port v1's module and pin; add the
package to `backend/requirements.txt` and to the CLAUDE.md bootstrap line in the same commit (that edit is
the build unit's, not this file's).

Rules, in order (first match wins):

| # | Input shape | Result |
|---|---|---|
| P1 | `^\+?(\d{7,15})@(s\.whatsapp\.net|c\.us)$` (case-insensitive) | parse `+digits` with no region; valid: `kind phone`, `subkind whatsapp_jid`, key `phone:+E164`; invalid: `kind app_user`, key `app:whatsapp:jid:<lowercased jid>` |
| P2 | `...@g.us` | `kind other`, `subkind group`, key `other:whatsapp_group:<lowercased>`; never a person |
| E1 | after stripping `mailto:`, exactly one `@`, a dot in the domain, no whitespace | `kind email`, value lowercased whole, key `email:<value>` |
| P3 | no letters, only digits and `+ ( ) - . / space`, 7 to 17 digits | `phonenumbers.parse(s, None if s starts with + else region)`; `is_valid_number`: `kind phone`, key `phone:+E164`, `region_basis` = `explicit_plus` or the region source (8.3); not valid: `kind other`, `subkind digits_unverified`, key `other:digits:<digits only>` |
| P4 | 3 to 8 digits, no `+` | `kind other`, `subkind short_code`, key `other:short_code:<digits>` (bank and service SMS senders; plan 12 approach 1) |
| A1 | anything else, in an app context | `kind app_user`, key `app:<namespace>:<label>:<value>`; namespace = slug of the containing top-level record's `Source` (`WhatsApp`, `Instagram`, `Telegram`, `Facebook Messenger` measured in C3); label = slug of `UserID.Category` when present (`username`, `facebook-id`, `user-id`, `unique-id`), else `id`; value = stripped; for label `username` also casefolded and a leading `@` removed |
| N1 | a value that is only a display name (Party with Name and no Identifier) | no identity; the participation keeps `name_in_record` |

Slug: NFKC, casefold, runs of non-alphanumerics to `-`, trimmed. Raw values are never discarded: every
sighting keeps `identifier_raw`.

### 8.3 Default region for bare numbers

v1 used a per-case `default_region`, default `US` (`backend/services/case_storage.py:227-243` and
`ingestion/scripts/cellebrite/ingestion.py:406-409` on `origin/main`). Loupe's `cases` table has no such
column (`backend/postgres/models/case.py`). Order:

1. `set_phone_default_region` decision on the extraction (section 10), basis `decided`;
2. `cases.phone_default_region` (new column, `varchar(2) null`, ISO 3166-1 alpha-2, set from the case
   settings page), basis `case_setting`;
3. `US`, basis `assumed_default`.

Every identity parsed from a number without `+` records `region_basis` on its sighting; the Extraction
profile states how many numbers were read with an assumed region. Changing the region re-derives the
identities of that extraction (5.7). Owl works from Washington DC (CLAUDE.md), which is why `US` is the
fallback; *reverse if* a case's numbers are mostly foreign without a `+`.

### 8.4 Name folding

One function, `backend/services/phone/fold.py:fold(text, exact=False)`, shared with search (spec 03 section
11.3 defines it; this file adds step 3 and fixes the order). Steps:

1. `unicodedata.normalize("NFKC", text)`: maps mathematical alphanumerics, fullwidth, circled, superscript and
   modifier letters to plain letters.
2. Supplementary table `backend/services/phone/data/styled_letters.json` for styled letters NFKC leaves
   alone: negative circled Latin capitals U+1F150 to U+1F169 and negative squared U+1F170 to U+1F189 to A to
   Z; regional indicators U+1F1E6 to U+1F1FF to A to Z (spec 03 section 11.3); Latin small capitals
   (U+1D00 ᴀ, U+0299 ʙ, U+1D04 ᴄ, U+1D05 ᴅ, U+1D07 ᴇ, U+A730 ꜰ, U+0262 ɢ, U+029C ʜ, U+026A ɪ, U+1D0A ᴊ, U+1D0B ᴋ,
   U+029F ʟ, U+1D0D ᴍ, U+0274 ɴ, U+1D0F ᴏ, U+1D18 ᴘ, U+0280 ʀ, U+A731 ꜱ, U+1D1B ᴛ, U+1D1C ᴜ, U+1D20 ᴠ, U+1D21 ᴡ,
   U+028F ʏ, U+1D22 ᴢ). Every listed code point exists in Unicode 13.0.
3. Mixed-script confusables: within one whitespace-separated token that contains Latin letters **and**
   Cyrillic or Greek letters, map the Cyrillic and Greek letters that Unicode UTS #39 `confusables.txt`
   lists as confusable with a single ASCII letter to that letter. A token entirely in Cyrillic or Greek is
   left alone, so a name genuinely written in Cyrillic is not turned into Latin. The table is generated by
   `backend/scripts/phone_build_confusables.py` from a pinned `confusables.txt` (version recorded in the
   JSON header) and restricted to source characters in the Cyrillic and Greek blocks.
4. Remove format and control characters (categories Cf, Cc: zero-width spaces and joiners, variation
   selectors U+FE0E, U+FE0F).
5. Unless `exact`: NFD, drop combining marks (category Mn), NFC (spec 03: `Jose` finds `José`).
6. `casefold()`.
7. Characters that are not letters, digits or marks become spaces; collapse whitespace; trim.

`exact=True` applies steps 4 and 6 only (spec 03's `Exact characters` toggle).

Test vectors (synthetic names; `backend/tests/fixtures/fold_cases.json`, shared with the frontend per spec
03), verified with a prototype for this file:

| Input (code points described) | `fold()` |
|---|---|
| `𝓐𝓷𝓪` (MATHEMATICAL BOLD SCRIPT A, n, a) | `ana` |
| `ＡＮＡ` (FULLWIDTH) | `ana` |
| `ᴀɴᴀ` (small capitals) | `ana` |
| `🅰🅽🅰` (negative squared) | `ana` |
| `Ⓐⓝⓐ` (circled) | `ana` |
| `Аna` (CYRILLIC CAPITAL A, then Latin n, a) | `ana` |
| `Анна` (all Cyrillic) | `анна` |
| `José` (precomposed) and `Jose` + U+0301 | `jose` |
| `ANA` U+200B `MARIA` | `ana maria` |
| `𝐀𝐧𝐚 𝐌𝐚𝐫𝐢𝐚` (MATHEMATICAL BOLD) | `ana maria` |
| `Ana-María`, `ana.maria` | `ana maria` |
| `Αna` (GREEK CAPITAL ALPHA, then Latin) | `ana` |
| `Straße` | `strasse` |
| `𝟏𝟐𝟑` (MATHEMATICAL BOLD DIGITS) | `123` |
| `Ana 🇺🇸` (regional indicators) | `ana us` |

With `exact=True`: `José` stays `josé`; `𝓐𝓷𝓪` stays `𝓐𝓷𝓪` folded only in case.

Phone test vectors are equivalence classes, because whether libphonenumber 9.0.31 treats the reserved
fictional ranges as valid is not established (15): `"+1 (202) 555-0143"`, `"+12025550143"`,
`"1-202-555-0143"` and `"(202) 555-0143"` with region US must give one identical result (a `phone` key or
the same `other:digits` key); `"12025550143@s.whatsapp.net"` must give the same key as `"+12025550143"`;
`"120363000000000000@g.us"` gives `other:whatsapp_group:...`; `"72975"` gives `other:short_code:72975`;
`"Mailto:A.B@Example.COM"` gives `email:a.b@example.com`; `"@SomeUser"` under Instagram with category
`Username` gives `app:instagram:username:someuser`.

### 8.5 Sightings and each phone's names

`phone_identities`: `id uuid PK` (uuid5 of `case_id` and `identity_key`, so ids are stable across rebuilds),
`case_id`, `identity_key text`, `kind`, `subkind`, `value_normalised`, `value_display` (libphonenumber
INTERNATIONAL format for phones, as v1's `display_format`), `sighting_count`, `first_instant`,
`last_instant`; unique (`case_id`, `identity_key`). Rows are never deleted while any decision names them
(they become `sighting_count = 0`), because decisions outlive their subjects (`decisions.py:27-32`).

`phone_identity_sightings`: `id`, `case_id`, `identity_id`, `extraction_id`, `record_uid`, `field_path`,
`identifier_raw`, `context` (`party`, `listed_on_card`, `account_field`, `header`, `owner_party`),
`name_alongside text null` (the Party `Name`, or the card's `Contact.Name`), `region_basis`, `generation`.

`phone_identity_names` (= spec 03 `pv_identity_name`): for each (identity, extraction):

1. `basis = contact`: `Contact.Name` of every Contact record on that extraction whose `Entries` contain the
   identity (and `ContactEntry` records, `basis = contact_entry`; 2 records in one report); with the
   contact's `TimeCreated`, `TimeModified`.
2. `basis = name_in_record`: distinct Party `Name` values for the identity on that extraction with counts.
3. The **phone's name** for display is the most frequent `contact` name; ties broken by latest
   `TimeModified`, then lowest `record_uid`. Else the most frequent `name_in_record` with the same tie rule.
   Else none ("(no name on this phone)" in spec 03). This follows v1's per-device saved name
   (`device_contact_names`, `backend/services/neo4j_service.py:8388-8414` on `origin/main`, most common
   saved name per identity and report) and v1's recorded rule that per-device naming is the default
   (`feedback_cellebrite_perspective_primary.md`).
4. Names that are the identifier echoed back are not names (v1 `_is_real_name`,
   `neo4j_writer.py:204-228`): equal to the raw identifier, phone-shaped, JID-shaped.

All names on all phones are kept and shown; no name is ever chosen as the identity's "real" name.

### 8.6 Owner identity of each phone

Computed in `backend/services/phone/owner.py`, rebuilt from v1's three tiers (`ingestion/scripts/
cellebrite/ingestion.py:298-322`, `neo4j_writer.py:683-940` on `origin/main`):

| Tier | Evidence | v1 source | Basis (spec 03) |
|---|---|---|---|
| 1 | Header numbers: metadata item `MSISDN` (v1 `parser.py:325-327`); `SIMData` records with `Category = SIM/USIM MSISDN` (measured in C3) | parse_header | `extracted` |
| 2 | Inference: count the `Account` field of every record (any type; the field exists on Call, Chat, Contact, Email, Location, CalendarEntry, FileUpload, Journey, Note, Password, SearchedItem, SocialMediaActivity, RemoteServiceSession) plus 1 for each identifier on a Party with `IsPhoneOwner = True`; keep those that classify as `phone`; the highest count wins, ties by E.164 string (`infer_owner_msisdn`, `neo4j_writer.py:894-940`) | infer_owner_msisdn | `inferred` |
| 3 | A person's decision `set_phone_owner` | manual identifier at intake | `manual` |

Differences from v1, each a decision (14):

- **No refusal.** v1 refused an extraction with no owner identity (memory note
  `feedback_cellebrite_phone_number_required.md`). Here the ingest proceeds and the owner is `unidentified`
  (plan decision 7, flag don't refuse). The reason for v1's rule (views collapse without an owner) is met by
  the `owner_implicit` participation, which exists whether or not the owner is identified, and by spec 03's
  label `Owner of C3 (number not in the extraction)`.
- **All tiers kept.** Every candidate with its count and basis is stored in `phone_owner_candidates`
  (`extraction_id`, `identity_id`, `tier`, `count`, `basis_detail jsonb`). The computed owner is tier 1 if
  any, else tier 2's top, else none; a decision overrides and is shown as such.
- **Owner names** are candidates, not decisions: `Party.Name` where `IsPhoneOwner = True` and
  `UserAccount.Name` filtered by the 8.5 rule 4 (v1 `_scan_for_phone_owner`, `neo4j_writer.py:688-737`).
- **Owner's app identities** (identities in `Account` fields and on `IsPhoneOwner` parties of that phone)
  are listed as `owner_accounts` suggestions (8.7 reason R2), not merged. v1 flagged them without merging
  (`flag_owner_app_identities`); this keeps that separation.

`pv_extraction.owner_identity_key` and `owner_basis` come from here.

### 8.7 Persons, suggestions and scores

A person is a dossier. Suggestions propose linking identities to a dossier, or to each other under a new
dossier. **No suggestion is produced from names alone** (spec 03 U-3; v1 note
`feedback_cellebrite_number_alongside_name.md`: names collide).

| Reason | Fires when | Weight |
|---|---|---|
| R1 `same_card` | two identities are listed on one Contact or UserAccount record on a phone (8.5 `listed_on_card`) | 0.6 for one phone, 0.8 for two or more phones |
| R2 `owner_accounts` | an identity is an `Account` value or an `IsPhoneOwner` party identifier on a phone, and the phone's owner identity is linked to a dossier | 0.7 |
| R3 `dossier_contact` | an identity's normalised value equals a contact of kind `phone` or `email` on a dossier (`frontend_v2/src/features/dossiers/api.ts:75-117` per spec 03 section 10.2), compared after the 8.2 normalisation | 0.9 |
| R4 `financial_identifier` | an identity equals a reviewed financial account identifier of kind `phone_number` or `email` (8.9), whose account's holder party is linked to a dossier | 0.8 |
| R5 `name_support` | only together with another reason: `fold()` of a name on any phone equals `fold()` of the dossier name or of a name of the other identity | adds 0.1 |

Score = `1 - product(1 - w_i)` over distinct reasons (R5 counted once), rounded to two places. Suggestions
with score at least 0.5 are listed, highest first, ties by identity key. Each lists its reasons and the
records behind each reason. The weights are stated so they can be argued with; *reverse if* reviewing the
first 100 suggestions on the 10-report case shows a reason accepted under half the time, in which case its
weight drops below the threshold.

`phone_identity_suggestions`: `id`, `case_id`, `identity_ids uuid[]`, `dossier_id uuid null`, `reasons
jsonb` (`[{"reason": "same_card", "records": ["record_uid"], "phones": ["C3"]}]`), `score numeric(3,2)`,
`state` (`open`, `accepted`, `rejected`, `superseded`), `computed_generation`. Recomputed with identities;
a suggestion whose pair has a recorded rejection is not recreated.

### 8.8 Decisions

Through `services.financial.decisions.record` (the module is the case decision ledger for all evidence,
not only financial: `postgres/models/enums.py:112-124`). Changes:

- **The phone decision log is the existing `adjudications` ledger.** There is no separate phone log: one
  answer to "who decided what about this case" (decision 21).
- `AdjudicationSubject` gains `phone_identity` (model `phone_identities`), `phone_extraction` (01's
  `phone_extractions`, which has `id` and `case_id`), `phone_record` (model `phone_record_subjects`, 1.2),
  and spec 05's `phone_analysis_result` (model `phone_analysis_results`, 05 section 3.7). Each name is at most
  24 characters, the column width (`postgres/models/financial.py:974`); `phone_analysis_result` is 21. Each
  has its model in `_SUBJECT_MODELS` (`decisions.py:101-107`; the import-time guard at lines 114-123 makes a
  missing entry fail at start-up). 05's `confirm_phone_result` and `reject_phone_result` are added in the same
  migration, with 05's semantics unchanged; 05 section 3.7's "reverse if 02 defines a phone decision log" is
  thereby settled in favour of its own design.
- `AdjudicationDecision` gains the members in the table; the `ck_adjudications_subject_type` and
  `ck_adjudications_decision` constraints (`postgres/models/financial.py:100-103` and below) are widened by a
  migration, as `20260910_account_party_decisions.py` did.

| Decision | Subject | before / after | Reversal |
|---|---|---|---|
| `link_phone_identity` | `phone_identity` | `{"dossier_id": null}` / `{"dossier_id": "<id>"}` | `unlink_phone_identity` |
| `unlink_phone_identity` | `phone_identity` | reverse of the above | `link_phone_identity` |
| `reject_phone_identity_link` | `phone_identity` | `{"rejected:<dossier_id or identity_id>": false}` / `true` | `restore_phone_identity_link` |
| `restore_phone_identity_link` | `phone_identity` | reverse | `reject_phone_identity_link` |
| `set_phone_owner` | `phone_extraction` | `{"owner_identity_ids": [...computed...]}` / `{...decided...}` | another `set_phone_owner` |
| `set_phone_device_zone` | `phone_extraction` | `{"device_zone": ...}` | another of the same |
| `set_phone_default_region` | `phone_extraction` | `{"default_region": ...}` | another of the same |
| `set_phone_clock_offset` | `phone_extraction` | `{"clock_offset": null}` / `{"clock_offset": {"seconds": n, "from": iso, "to": iso}}` | another of the same |
| `correct_phone_value` | `phone_record` | `{"<field_path>#<value_index>": machine}` / `{...: corrected}` | another `correct_phone_value` back to the machine value |
| `set_phone_identity_label` | `phone_identity` | `{"label": null}` / `{"label": "..."}` | another of the same |
| `apply_phone_zone_to_offsetless` | `phone_extraction` | `{"offsetless_zone": null}` / `{"offsetless_zone": "<IANA>"}` | another with `null` |
| `allow_phone_external_processing` | `phone_extraction` | `{"external_processing": false}` / `true`, reason mandatory (9.8) | another with `false` |
| `accept_phone_reconciliation_difference` | `phone_extraction` | `{"accepted_documents": [...]}` | another of the same |
| `set_phone_label` | `phone_extraction` | `{"label": "<computed>"}` / `{"label": "<decided>"}` | another of the same |
| `confirm_phone_result`, `reject_phone_result` | `phone_analysis_result` | as spec 05 section 3.7 | each other |

`split` (spec 03's action) is a set of `unlink_phone_identity` decisions written in one transaction with
one reason. Linking to a new person creates the dossier through `create_dossier`
(`backend/services/dossier_service.py:318`) in the same transaction, then records the link. The current
link state of an identity is the replay of its decisions in `subject_sequence` order
(`decisions.py:341-365`), materialised in `phone_identity_links` (`identity_id`, `dossier_id`,
`decision_id`) for querying; that table is rebuilt from `adjudications` and is never the source.

**Identity levels for spec 05** (05 section 17.7): `exact` = equal `identity_key` (8.2); `reviewed` = two
identities linked to the same dossier by current decisions. A reviewed-level result cites the
`link_phone_identity` decision ids it relied on; `phone_identity_links` exposes a `links_revision` (sha256
of the current link rows of the case) that 05 includes in its input revision, so an unlink recomputes. 05's
"reviewed merge" is therefore "linked to one person"; there is no merge of identities themselves.

Endpoint (spec 03 section 10.4): `POST /api/phones/identity-decisions` with `{case_id, decision, identity_keys,
dossier_id, new_person_name, reason, expected_revision}`; `expected_revision` is a sha256 over the current
link rows of those identities, and a mismatch returns 409, as account identities do
(`account_identity.py:122-123`).

### 8.9 Link to financial counterparties

Today a financial party reaches a case entity only through an account's reviewed identity: `entity_links`
(`party_id`, `entity_key`) saved with an account (`account_identity.py:39-42`, `135-143`), drawn as
`REVIEWED_SAME_IDENTITY` from `FinancialParty` to the entity by the identity graph sweep
(`identity_graph.py:103-105`, `210-214`). Account identifiers are limited to `account_number`, `clabe`,
`iban`, `customer_number`, `contract_number`, `holder_tax_id` (`account_identity.py:24`).

Changes:

1. **Missing identifier types.** Add `phone_number` and `email` to `Identifier.kind`. Payment services that
   address accounts by a phone number or email (for example Zelle in the United States, enrolled with an
   email address or US mobile number) put those on statements as the account reference. Validation:
   `phone_number` must classify as `kind phone` under 8.2 with region `US` unless written with `+`;
   `email` must pass rule E1. `compact()` (`account_identity.py:75-76`) is wrong for both (it uppercases and
   keeps parentheses), so `matches_identifier` (lines 99-104) compares these kinds by their 8.2 normalised
   value instead.
2. **Path.** Phone identity -> dossier (8.8 decision) and FinancialParty -> the dossier's case entity
   (existing reviewed `entity_links`, by a person in Financial). No new link type between phone data and
   ledger rows; plan 6.6 requires exactly this path.
3. **Suggestions only.** Reason R4 (8.7) proposes; nothing links automatically. Shown on the dossier as
   `Suggested, not reviewed` (spec 03 section 10.3).
4. **Gap stated.** A counterparty party that exists only on payments (`set_counterparty_party`,
   `backend/services/financial/counterparty_parties.py:117`) has no account and therefore no `entity_links`;
   it cannot reach a dossier today. Fixing that is a financial change outside this file (15).

---

## 9. Projections

### 9.1 Rules

Plan decision 6: Postgres is the record, the graph is a projection. Every node and relationship written
here carries `phone_projection_managed = true`, `layer = 'phone'` and `case_id`, and can be deleted and
rebuilt at any time from Postgres without loss.

### 9.2 Why most phone data is not in Neo4j

The case Timeline, Map and Graph scan every node of the case with no label filter:
`MATCH (n)` with a computed sort date from `date`, `timestamp`, `start_time`, `capture_time`,
`creation_time`, `date_time`, `datetime` (`backend/services/neo4j/timeline_service.py:19-31`, query at line
247; type filter `labels(n)[0] IN $types`, line 127); every node with `latitude` and `longitude`
(`backend/services/neo4j/geo_service.py:73-77`); every active node (`graph_service.py:129-133`,
`active_node_predicate`, `services/neo4j/driver.py:20-28`). One phone case holds hundreds of thousands of
timestamped records (spec 03 section 2). So:

- Messages, calls, events, locations and texts are **not** graph nodes. The timeline and map lenses read
  them from Postgres (spec 03 sections 9 and 13).
- Phone nodes **must not** carry any property named `date`, `time`, `timestamp`, `start_time`,
  `capture_time`, `creation_time`, `date_time`, `datetime`, `latitude` or `longitude`, so the existing
  queries never pick them up as events or places. A unit test asserts this over every projected property
  name.

### 9.3 Labels, keys, properties

| Label | Key (`key` property; unique per `case_id`) | Properties |
|---|---|---|
| `PhoneExtraction` | `phone-extraction:<extraction_id>` | `name` (`C3 · <manufacturer> <model>`), `extraction_id`, `phone_label`, `report_version`, `producer_version`, `owner_identity_key`, `owner_basis`, `summary` |
| `PhoneIdentity` | `phone-identity:<identity_key>` (full key, never truncated; v1 cut ids to 12 characters, plan 4.3) | `name` (case view label: the decided label, else the dossier name, else the most frequent phone name, always followed by the identifier, e.g. `Ana Maria (+1 202-555-0143)`), `identity_key`, `kind`, `value_display`, `phone_names_json` (`[{"phone": "C3", "name": "...", "basis": "contact"}]`), `person_id` (dossier id or null), `owner_of` (list of phone labels) |
| `PhoneGroup` | `phone-group:<identity_key>` for a group JID, else `phone-group:<extraction_id>:<chat record_uid>` | `name` (Chat `Name`), `chat_type`, `phones` |

Only identities that took part in at least one communication event (any phone), owners, and identities
linked to a dossier are projected; address-book-only identities stay in Postgres and People (spec 03
section 14.2; up to 13,053 contacts on one phone).

| Relationship | From, to | Properties |
|---|---|---|
| `APPEARS_ON` (membership) | `PhoneIdentity` -> `PhoneExtraction` | `phone_name`, `name_basis`, `records`, `roles` (list), `first_instant`, `last_instant` |
| `OWNS_PHONE` | `PhoneIdentity` -> `PhoneExtraction` | `basis` (`extracted`, `inferred`, `manual`), `decision_id` |
| `COMMUNICATED` | between two `PhoneIdentity`, stored from the lower key to the higher | `messages_ab`, `messages_ba`, `calls_ab`, `calls_ba`, `emails_ab`, `emails_ba`, `first_instant`, `last_instant`, `phones` (spec 03 section 14.2) |
| `POSTED_IN` | `PhoneIdentity` -> `PhoneGroup` | `messages`, `first_instant`, `last_instant` |
| `MEMBER_OF_GROUP` | `PhoneIdentity` -> `PhoneGroup` | `phones` |
| `REVIEWED_SAME_IDENTITY` | `PhoneIdentity` -> dossier's canonical entity node | `decision_id`, `reviewed: true` |

`COMMUNICATED` counts only events with exactly two identities (sender and one recipient, or the two call
parties, the owner side included through `owner_implicit`). Group messages count on `POSTED_IN`, so a
group of 200 does not draw 19,900 pair edges. Spec 03 section 4.3 now defines `between` with `group_scope` defaulting to `direct`, matching
`COMMUNICATED`, and reports group totals separately, matching `POSTED_IN` (settled 2026-10-29).

### 9.4 Membership and deletion semantics

An identity belongs to every phone it has a sighting on (`APPEARS_ON` per phone). Deleting an extraction (an
explicit action, never automatic: 01 section 10.7) deletes its capture and its derived rows (every derived
table has `extraction_id` referencing `phone_extractions(id) ON DELETE CASCADE`); superseding it removes it
from the views (5.7) and therefore from the projection plan. Either way, identities recompute their
`sighting_count`; the projector then computes the desired graph from Postgres and removes managed nodes and
relationships not in it. An identity still seen on another phone keeps its node and that phone's edges and
loses only the deleted phone's (plan 7 phase 4 done-when; spec 03 R-2). Decisions are never deleted.

Re-ingest replaces derived rows by generation (5.7); a failed re-ingest leaves the previous generation in
place (plan 4.2 was v1's delete-before-write defect).

### 9.5 Projection procedure

`backend/services/phone/graph_projection.py`, modelled on `apply_identity_graph`
(`identity_graph.py:153-257`):

1. Build the plan from Postgres in one short read transaction: nodes and relationships as rows; `revision`
   = sha256 of the canonical JSON of the plan.
2. One Neo4j transaction per case with timeout: `MERGE (m:PhoneProjectionSync {case_id})` with
   `system_node = true` (hidden from case views by `active_node_predicate`), increment a lock counter; if
   `m.revision = revision`, roll back and stop.
3. `UNWIND` in batches of 500 (the engine's write convention, `evidence-engine/CLAUDE.md` line 38):
   `MERGE (n:<Label> {case_id, key})` then `SET` properties; relationships `MERGE` on a
   `phone_projection_key` property.
4. Delete managed nodes and relationships of the case whose keys are not in the plan.
5. Carry-over: when a node key disappears and the identity's decisions show it was relinked, copy `notes`
   and `summary` set by investigators on the old node to the new one before deleting (graph node notes are
   investigator content that must survive a projection).
6. Set `m.revision`, `m.completed_at`, `m.status = 'current'`; commit.

Constraint created once: `CREATE CONSTRAINT phone_projection_sync_case IF NOT EXISTS FOR
(m:PhoneProjectionSync) REQUIRE m.case_id IS UNIQUE`, as `identity_graph.py:158-160`.

Rebuild on demand: `POST /api/phones/projection/rebuild {"case_id"}` (case admin) and
`python backend/scripts/phone_projection_rebuild.py --case <uuid> [--drop-first]`; `--drop-first` deletes
every managed phone node of the case before projecting, to prove the rebuild needs nothing from the graph.

### 9.6 Lens policy in case views

| View | Default | Phone data |
|---|---|---|
| Case Timeline | phone lens off | spec 03 section 9 merges Postgres-sourced phone rows when the lens is on |
| Case Map | phone layer off | spec 03 section 13; phone points are never Neo4j locations (spec 03 G-4) |
| Case Graph | phone identities and edges shown | bounded to communicating identities (9.3); `layer` property lets the graph filter |

### 9.7 Text store: thread documents

Global search, AI chat and workspace citations read `evidence_document_texts`
(`backend/services/evidence_text_search_service.py:155-169`; `workspace_ai_service.py:132-183`). Its primary
key is `evidence_file_id` (`backend/postgres/models/evidence.py:205-212`), so each text needs an
`evidence_files` row.

**One derived evidence file per thread part** (`backend/services/phone/thread_text.py`):

| `evidence_files` column | Value |
|---|---|
| `source_type` | `phone_text` |
| `original_filename` | `C3 · WhatsApp · <thread title or participant labels> (part 1 of 1)` |
| `stored_path` | `phone-text://<extraction_id>/<thread_key>/<part>` (no file on disk) |
| `sha256`, `size` | of the UTF-8 content |
| `status` | `processed` |
| `folder_id` | the phone's evidence folder (spec 01) |
| `metadata` | `{"phone_extraction_id", "thread_key", "part", "parts", "first_event_uid", "last_event_uid", "message_count", "generator_version", "generation"}` |

Content: one line per comm event, in sort order, in spec 03's copy format (03 section 3.7, line 373 of that
file): `Tue, Mar 14, 2023, 3:07:12 PM EDT | C3 | WhatsApp | Name (number) -> Name (number) | <full body>`,
with the phone's own names (perspective of the phone the thread came from), the extraction's device zone or
UTC when unknown, attachments listed by filename, deleted state as `[Deleted]`, corrected values in effect
(section 10). A voice note whose audio has a transcript (spec 03 section 8) is followed by a line
`  Transcript (machine-generated, <model> <version>): <text>` (plan decision 9).

`source_locations`: one entry per line, the engine's shape (`kind`, `label`, `start_char`, `end_char`,
`evidence-engine/app/services/evidence_document_text.py:24-46`) plus phone keys:

```json
{"kind": "phone_record", "label": "C3 WhatsApp message, Tue, Mar 14, 2023, 3:07 PM EDT",
 "start_char": 0, "end_char": 182, "record_uid": "uuid", "event_uid": "uuid",
 "extraction_id": "uuid", "field_path": "Body", "instant": "2023-03-14T19:07:12Z"}
```

Transcript lines use `kind: "phone_transcript"` with `model`, `model_version`.

Parts: a thread is split only at message boundaries when it exceeds 5,000 messages or 2,000,000
characters; never by day (plan 10.3: review tools that slice chats by day are a recorded weakness). Part
titles state the message range and dates. *Reverse if* a single-row thread of the largest measured size
(v1 note: one thread of about 72,000 messages) searches and opens within spec 03's targets.

Hidden from evidence listings: `visible_evidence_condition()`
(`backend/services/financial/source_lineage.py:163-171`, used by `list_files` and `list_contents`,
`backend/services/evidence_db_storage.py:323-325`, `366-367`) gains `EvidenceFile.source_type IS DISTINCT
FROM 'phone_text'`. Search counts `case_documents` excluding them.

Search hit: `_hit` (`evidence_text_search_service.py:86-104`) returns `location_kind`, `record_uid`,
`extraction_id` from the matched location, so a hit opens the record (spec 03 section 11). Folded search
over this content is spec 03's `content_folded` (03 section 11.3).

Lifecycle: regenerated per thread when the extraction's generation, names, owner, zone or corrections
change; content hash compared first, unchanged threads untouched. Deleted with the extraction.

Other strings (Notes, searches, page titles, KeyValueModel values) are searched through `phone_texts`
(`pv_text`), not documents.

### 9.8 Embeddings

The engine embeds with OpenAI, fixed in code: `EMBEDDING_PROVIDER = "openai"`,
`EMBEDDING_MODEL = "text-embedding-3-small"`, overrides refused (`evidence-engine/app/config.py:6-23`); the
client is `AsyncOpenAI` (`app/services/openai_client.py:74-86`, `embed_texts` at 668). Plan decision 8: no
evidence goes to a third-party service unless Neil decides so for a case.

**Decision:** phone text is not embedded while the only provider is a third party. It is embedded when
either a local embedding provider exists, or a per-case decision `allow_external_processing` (recorded by
Neil through the decision log on each `phone_extraction`, reason mandatory) permits it. When embedded:
collection `chunks` (the one the chat searches, `backend/services/vector_db_service.py:55-58`), ids
`<evidence_file_id>:<content_sha256>:chunk:<n>` (engine format, `chunk_embed.py:235-238`), chunks built
from consecutive message lines up to 3,500 characters, metadata the engine's keys (`case_id`, `doc_id`,
`doc_name`, `evidence_file_id`, `revision_id`, `ingestion_state`, `start_char`, `end_char`;
`chunk_embed.py:241-262`) plus `source_kind: "phone_text"`, `extraction_id`, `first_record_uid`,
`last_record_uid`. Activation uses the engine's staged-then-active protocol (the search filters
`ingestion_state`, `vector_db_service.py:377-379`).

Until then, chat reaches phone text by lexical retrieval: `rag_service._retrieve_chunks` (vector only today,
`backend/services/rag_service.py:673-689`) gains a step that runs the folded search over `phone_text`
documents and `phone_texts` for the question's terms and adds up to 8 message windows as chunks with the
same metadata. *Reverse if* Neil records the per-case decision or a local model is installed.

### 9.9 Citation anchors

New anchor kind for phone records, used in workspace AI, chat and dossier links:

```json
{"kind": "phone_record", "record_uid": "uuid", "extraction_id": "uuid",
 "field_path": "Body", "start_char": 120, "end_char": 302}
```

`record_uid` is the anchor; character offsets are a convenience and may go stale when a thread document is
regenerated, the record id never does. Spec 03 uses `{"record_uid"}` anchors and `rec://` links (03 section
11.5); this shape is a superset.

Changes:

| Where | Today | Change |
|---|---|---|
| `workspace_ai_service._source_url` (`workspace_ai_service.py:115-127`) | builds `/cases/<id>/evidence?file=&page=&start_char=` | for `kind = phone_record` builds the record link spec 03 defines |
| `_document_chunks` (`workspace_ai_service.py:132-183`) | takes the first 6 locations (`return chunks[:6]`, line 183) | for `phone_text` files selects the locations matching the theory terms or the preferred anchor, then groups each with its neighbours up to 3,500 characters; still at most 6 |
| `_bounded_sources` identity (`workspace_ai_service.py:259-283`) | evidence file and anchor | unchanged; the anchor now includes `record_uid` |
| `ChatSource` (`backend/routers/chat.py:67-70`) | `filename`, `excerpt`, `page` | adds optional `evidence_file_id`, `record_uid`, `source_anchor`, `url` |
| `rag_service._build_sources` (`rag_service.py:2336-2356`) | deduplicates by filename, at most 5 | deduplicates by (filename, `record_uid`), so two messages from one thread are two sources |

---

## 10. Corrections on phone data

### 10.1 What can be corrected

| Correction | Decision | Effective value used in |
|---|---|---|
| One captured value (a timestamp read wrongly, a body, a number) | `correct_phone_value` on the `phone_record` | timelines, sorting, search, threads, exports, counts |
| A device clock offset for a period | `set_phone_clock_offset` on the `phone_extraction` | every instant of that extraction within the period |
| The case-wide label of an identity | `set_phone_identity_label` | case view labels; never the phone's names |
| Identity links | 8.8 | people, graph, suggestions |
| Owner, device zone, default region | 8.8 | owner labels, display zone, number parsing |

Each phone's saved names are evidence of that phone and are not corrected; a person who disagrees sets a
case label, and both stay visible.

### 10.2 Storage

`phone_value_corrections`: `id`, `case_id`, `record_uid`, `field_path`, `value_index`, `machine_text`,
`corrected_text`, `decision_id uuid` (the `adjudications` row), `superseded_by_id null`, `created_at`.
Written in the same transaction as the decision, after it (`decisions.py:22-23`). Undo is a new correction
whose `corrected_text` equals `machine_text`; the chain stays (as financial corrections:
`backend/services/financial/corrections.py:1-6`).

### 10.3 Effective values

Derived rows hold both: `phone_time_values.instant` (machine) and `effective_instant` (corrected, or machine
plus clock offset, or machine); texts hold `value` and `effective_value`. Every read in sections 9, 11 and
spec 03 uses the effective column; every display shows the machine value beside a corrected one with
`Corrected by <name> on <date>: <reason>` (CLAUDE.md design rule: both visible, obvious which is real, only
the corrected value used in sums and searches). Search matches the effective text; the record view shows
both. A correction re-derives only the affected extraction (5.7).

### 10.4 Endpoint

`POST /api/phones/records/{record_uid}/corrections {"case_id", "field_path", "value_index",
"corrected_text", "reason", "expected_revision"}`: validates the corrected text with the value parser for
the field's value type (4.1 to 4.6); refuses a correction to a sensitive field's export flag; 409 on a stale
revision.

---

## 11. Combined communication and money edges

### 11.1 Definition

An edge joins two persons (dossiers), or two identities when no dossier links them. It carries:

- communication counts from `phone_comm_events` and `phone_participations` of the identities linked to each
  side: messages, calls, emails each direction, first and last instant, phones;
- money from the ledger, resolved the way spec 05 section 17.8 specifies and the reviewed identity graph
  already does: admitted, current transactions (`ledger_status = 'admitted'`, `superseded_by_id IS NULL`,
  `identity_graph.py:114-119`) whose reviewed payment identity (`payment_counterparty_link.resolved_link`,
  `backend/services/financial/payment_counterparty_link.py:81`, as used at `identity_graph.py:120-125`)
  resolves to a financial party or account on one side, on an account whose reviewed holder relationship
  (`RELATIONSHIPS['holder']`, `identity_graph.py:22-23`) is to a financial party on the other side. A
  financial party or account belongs to a side when its reviewed `entity_links` name the side's dossier
  canonical entity (8.9). Direction: a debit on side A's account to side B is `paid_ab`.
- sums in integer minor units per currency, never across currencies, from effective amounts; totals over
  `DEFAULT_TOTAL_CLASSES` (`backend/services/financial/proof_class.py:136`), with p3 rows stated separately
  and p4 never summed (05 section 17.8 point 3; plan 6.6).

**One implementation.** Spec 05 names the computation `link_edges.py` (its 17.8 point 5). It is one
module, `backend/services/phone/link_edges.py`, owned here for the identity and money resolution and used by
05's approach screens, spec 03's graph edges and this endpoint. Identity sides use 05's levels (8.8):
`exact` by default, `reviewed` when a side is a dossier.

### 11.2 Endpoint

`POST /api/phones/link-analysis/edges` (spec 03's `/api/phones/graph/edges` calls the same service):

```json
{"case_id": "uuid", "from_instant": "2023-01-01T00:00:00Z", "to_instant": "2023-07-01T00:00:00Z",
 "subjects": [{"dossier_id": "uuid"}, {"identity_key": "phone:+1..."}], "slice": "month"}
```

Response:

```json
{"edges": [{
  "a": {"dossier_id": "uuid", "label": "Ana Maria"},
  "b": {"identity_key": "phone:+1...", "label": "(no name) (+1 202-555-0143)"},
  "communication": {"messages_ab": 120, "messages_ba": 110, "calls_ab": 9, "calls_ba": 5,
                    "emails_ab": 0, "emails_ba": 0, "first_instant": "...", "last_instant": "...",
                    "phones": ["C3", "C7"], "no_time_count": 2},
  "money": [{"currency": "USD", "classes": "p0-p2", "paid_ab_minor": 840000, "payments_ab": 6,
             "paid_ba_minor": 0, "payments_ba": 0,
             "p3": {"paid_ab_minor": 110000, "payments_ab": 2, "paid_ba_minor": 0, "payments_ba": 0}}],
  "money_mentioned_on_phones": 3,
  "slices": [{"from": "2023-01-01", "to": "2023-02-01", "messages": 40, "calls": 3,
              "money": [{"currency": "USD", "paid_ab_minor": 120000, "payments_ab": 1}]}],
  "label": "14 calls, 230 messages, 6 payments totalling USD 8,400.00 (p0 to p2); 2 more payments USD 1,100.00 (p3)"
}], "limits": []}
```

Time slicing: communication by `effective_instant` in the case display zone (spec 03 section 4.6); money by
the transaction's ordering date (`services/financial/transactions.py`, `choose_ordering_date`), with the
date basis stated. Events with no instant are counted in `no_time_count`, never dropped. `label` is
computed, never stored (spec 03 section 14.2).

`POST /api/phones/link-analysis/edge-records {"case_id", "a", "b", "from_instant", "to_instant", "kind":
"messages|calls|emails|payments", "cursor", "limit<=200"}` returns the records behind the counts; the totals
equal the edge counts exactly (spec 03 R-1, R-3).

### 11.3 Money from messages

Amounts mentioned in messages are never counted here. They are `unstructured_narrative`, proof class p4,
reaching the ledger only through claim comparison (plan 6.6, 12.1 rule 5).

---

## 12. Read contract for specs 03, 04 and 05

### 12.1 Rules

- Spec 03 section 1.2 names the objects every screen reads. **All names are kept**; no rename is needed.
  Each is a Postgres view in migration `backend/postgres/alembic/versions/<date>_phone_read_views.py`, over
  the current generation of the derived tables (5.7) and only extractions with `standing = 'active'`.
- Every view exposes `case_id` and, where a phone is involved, `extraction_id` and `phone_label`.
  `phone_label` is `pv_extraction.label`; it is a column, not a separate object.
- Effective values (section 10) are what the views return; machine values are alongside where 03 shows both.
- Spec 03 section 4.7's indexes are created on the underlying tables named below.

### 12.2 Views

| View | Key | Columns (03's names) and where each comes from |
|---|---|---|
| `pv_extraction` | `extraction_id` | `extraction_id`, `case_id` (01 `phone_extractions`); `label` (`phone_extraction_labels`, 12.3); `state` (`ingested` when captured and interpreted, `partial` when `captured_incomplete`, `failed`, `replaced` when superseded); `owner_identity_key`, `owner_basis` (8.6); `device` jsonb (skeleton metadata `DeviceInfoSelectedManufacturer`, `DeviceInfoSelectedDeviceName`, `DeviceInfoOSType`); `report_version`, `producer` (= `producer_version`), `extraction_type` (01); `selection` jsonb (7.2 `selection`); `time_zone` jsonb (skeleton `timeZoneConfigurations` verbatim); `device_zone`, `device_zone_basis` (4.2); `container_sha256` (01 `phone_extraction_containers.sha256` of `first_container_id`); `report_sha256` (01 `report_set_sha256`); `ingested_at` (01 `captured_at`); `reconciliation_state` (latest `phone_reconciliations.result` per document, `exact` only if all are) |
| `pv_record` | `record_uid` | `record_uid`, `extraction_id`, `cellebrite_id` (`source_model_id`), `model_type`, `parent_record_uid` (from `parent_ordinal`), `deleted_state` (01), `decoding_confidence`, `source_index`, `file_id` (from body attrs), `is_carved` (false until a marker is established, 15; the column comment says so), `locator` (01 6.4) |
| `pv_comm_event` | `event_uid` | from `phone_comm_events` (6.9 mappings): `event_uid` (= uuid5 of `record_uid`, `comm`), `record_uid`, `extraction_id`, `case_id`, `kind` (`message`, `call`, `email`, `voicemail`, `chat_activity`), `thread_key`, `app`, `direction` (5.3), `sort_instant` (effective instant of the event-time field), `time_field`, `body` (complete), `subject`, `status`, `call_duration_s`, `call_status`, `video`, `dup_group_uid`, `dup_rule_version` (03 section 3.4 rule, evaluated here), `interpretation_level` |
| `pv_comm_party` | (`event_uid`, `participation_uid`) | from `phone_participations`: `event_uid`, `identity_key`, `role` (5.3, including `owner_implicit`), `name_in_record`, `identifier_raw`, `is_phone_owner`, `date_read`, `date_delivered`, `date_played` (effective instants of the Party's own fields) |
| `pv_thread` | `thread_key` | from `phone_threads`: `thread_key`, `extraction_id`, `app`, `thread_kind` (`chat`, `sms_group`, `call_log`, `email_folder`), `chat_type`, `title_in_record`, `first_instant`, `last_instant`, `event_count`, `party_identity_keys` |
| `pv_identity` | (`case_id`, `identity_key`) | from `phone_identities` and `phone_identity_links`: `identity_key`, `case_id`, `kind`, `value_normalised`, `value_display`, `person_id` (current dossier link or null) |
| `pv_identity_name` | (`identity_key`, `extraction_id`, `name`, `basis`, `record_uid`) | from `phone_identity_names` (8.5): `identity_key`, `extraction_id`, `name`, `basis` (`contact_entry`, `contact`, `name_in_record`), `record_uid`, `time_created`, `time_modified` |
| `pv_time` | `time_uid` | from `phone_time_values`: `record_uid`, `field_path`, `instant` (effective), `original_text`, `original_offset_minutes`, `offset_present`; plus `machine_instant`, `instant_basis`, `producer_format` |
| `pv_timeline_entry` | `entry_uid` (= `time_uid`) | `entry_uid`, `record_uid`, `extraction_id`, `case_id`, `model_type`, `field_path`, `field_meaning` and `semantics` (timestamp-meaning rows, 6.5b), `instant`, `activity_class` (from 04's strength view over `phone_mapping_rows`; `unknown` where 04 has no row), `summary` (`phone_record_summaries.title`), `identity_keys` (participations of the record and its top-level ancestor) |
| `pv_location_point` | `point_uid` | from `phone_location_points`: `point_uid`, `record_uid`, `extraction_id`, `case_id`, `lat`, `lon`, `accuracy_m`, `accuracy_basis` (`gps_horizontal`, `precision_field`, `none`), `source_kind`, `affiliation`, `instant`, `end_instant` |
| `pv_file` | `file_uid` | from 01 `phone_files`: `file_uid`, `extraction_id`, `cellebrite_file_id` (`source_file_id`), `category` (`tags`), `local_path`, `size` (`disk_size`, else `declared_size`), `md5`, `sha256` (disk values, else declared, with which in `hash_basis`), `verification` (01 `outcome` mapped to `match`, `mismatch`, `missing`, `unverified`), `deleted_state` (file body attribute `deleted`), `is_carved` (true when the row was captured from the report's `carvedFiles` section; whether any production populates it is open, 01's last section), `taken_instant` (the file's EXIF or `accessInfo` timestamp from `phone_timestamps` with `owner_kind = 'file'`, chosen by the rule in spec 03 section 8), `exif` |
| `pv_attachment_link` | (`record_uid`, `mechanism`, `body_path`) | from 01 `phone_file_references`: `record_uid`, `file_uid` (resolved row or null), `mechanism` (01's `jumptarget`, `file_id_attribute`, `extracted_path_value` shown under 03's names `jump_target`, `attachment_field`, `tagged_file`), `extracted_path` (`reference_text` when a path), `resolved` (`resolution <> 'unresolved'`) |
| `pv_text` | `text_uid` | from `phone_texts`: `record_uid`, `extraction_id`, `case_id`, `field_path`, `value` (effective), `value_folded` (`fold()`), `is_sensitive` |
| `pv_coverage` | (`extraction_id`, `model_type`, `field_name`, `field_kind`) | section 7: `records`, `interpretation` (03's three values: `reviewed`, `generic` for `generic_role` and `generic_text`, `captured_only`; plus `suspended` and the finer level in `level_detail`) |

### 12.3 Phone labels

`phone_extraction_labels`: `extraction_id uuid PK`, `case_id`, `label varchar(32) not null`, `basis`
(`report_name`, `assigned`, `decided`). Computed: the token `C<digits>` delimited by `_` or a space in the
report document's file name (01 `phone_extraction_documents.path`; all server reports of the 10-report and
3-phone cases carry one), else `Phone <n>` in capture order. A decision `set_phone_label` on the
`phone_extraction` overrides it. Labels are not unique: the 10-report case has two reports labelled C1
(whether one device is not established), so every screen that lists phones shows a shared label with its
extraction date (`DeviceInfoExtractionStartDateTime` from the skeleton).

### 12.4 What 04 and 05 read

| Consumer | Reads |
|---|---|
| 04 (pattern of life) | `pv_timeline_entry`, `pv_location_point`, `pv_comm_event`, `pv_comm_party`, `phone_mapping_rows` and `phone_mapping_current` (6.5b), `pv_extraction.owner_identity_key`, `phone_owner_candidates` |
| 05 (approaches) | the same, plus `pv_identity`, `phone_identity_links.links_revision` (8.8), `natural_key` and `platform_family` rows (6.3), the registry (`phone_schema_*`) for coverage statements, and `link_edges.py` (11) |

Spec 04's `*_mapping_version` columns hold `phone_mapping_versions.id` values (6.6); 05's input revisions
include `mapping_set_id` (6.6) and `links_revision`.

---

## 13. Build units and acceptance tests

Each unit is finished, tested and committed before the next (CLAUDE.md). Corpus tests use C3, C9, C8 from
`LOUPE_PHONE_CORPUS` and skip with the reason when it is absent; the seed tests use the committed seed
file.

| # | Unit | Acceptance tests |
|---|---|---|
| U1 | Body walker, ids and value parsers (1.2, 4) | `body.py` yields every field of every C3, C9, C8 record and its value count equals 01's reconciled value count per document; `record_uid` is identical across two captures of the same bytes; `phone_time_values` rows equal `phone_timestamps` rows with `owner_kind = 'record'` (C3 22,881; C9 5,218; C8 59,672) and carry `producer_format` (C3: TimeStampKnown 22,859, DateTimeOnly 21, DateOnly 1; C8: 59,666 and 6); no offset-less value gets an instant without the 8.8 decision, even though its `formatted_text` has an offset; `HH:MM:SS.fffffff` parses; out-of-range and (0,0) coordinates flagged; Double kept as Decimal; the device zone is C9's metadata zone and null for C3 and C8, with C3's examiner zone shown |
| U2 | Registry tables and seed | After seed: 62 types, 471 field rows over 470 (type, field, kind), 55 named sets with 210 values plus `DecodingSourceOptions` = `Decoding`, 47 nesting rows, `ChatActivity.SystemMessageId` drift flag `acknowledged`; re-running the seed changes nothing; the seed file contains no path and no String/Guid value (test scans it) |
| U3 | Observation pass and review queue | Observing C3, C9, C8 after the seed raises no flag for anything in the seed; a synthetic extraction with one new type, field, set value, nesting, attribute and a drifted value type raises exactly six flags; two concurrent observations of the same new field raise one flag; flag transitions write events before state; `QuotedMessageData.Label` on C8 gives `max_values_in_one_field` 2 or more |
| U4 | Generic interpretation (5) | C3: 22,881 time rows, 31 location points; C9: 5,218 and 9 (7 Location, 2 WirelessNetwork); C8: 59,672 and 38, and 171 Locations counted `not_positionable` with reason `no_coordinate`; a type absent from all code (synthetic `ZzzUnknown` with a TimeStamp, a nested Coordinate and a Party) gets a timeline entry, a point and a participant (plan 7 phase 3 done-when); every C3 Party yields a participation (count equals Party records under parents, 7,504 in `c3.json` `mt_all`); roles follow 5.3 on the measured combinations; no derived row lacks `record_uid` |
| U5 | Mapping loader, versions, applier, suspension (6) | A `draft` file is ignored; a `reviewed` file with empty `reviewed_by` fails start-up; changing a file changes the set id and the sweep re-derives without re-capture (asserted: no capture table written); a registry requirement under an open drift flag suspends the mapping on that extraction only and coverage shows `suspended`; the applier never reads `phone_mapping_proposals` |
| U6 | Initial type mappings (6.9) reviewed and committed | On C3: 1,657 calls, every call has a `caller` and a `callee` participation (owner side `owner_implicit` when absent); 2,917 messages with threads (2,716 under Chats, 201 top-level by counterpart set); 294 emails with full bodies (longest body length equals the captured length); direction conflicts counted and listed |
| U7 | Coverage map and endpoint (7) | C3 response lists 35 types and 178 value combinations plus nested-only types; selection flags returned verbatim from all three `extractionInfo` elements; a field becomes `reviewed` when its mapping loads and back to generic when removed |
| U8 | Identifiers, fold, region (8.2 to 8.4) | All fold vectors in 8.4 on Python 3.10; phone equivalence classes in 8.4; JID and number give one identity; group JIDs never become persons; numbers parsed with assumed region carry `region_basis = assumed_default` and are counted on the profile |
| U9 | Sightings, phone names, owner (8.5, 8.6) | An identity on two phones with two saved names shows both, each with its phone (spec 03 U-1); C3 owner basis `extracted` from header MSISDN; C9 and C8 owner result recorded with tier and candidates (expected tier not yet established); an extraction with no evidence of owner still produces `owner_implicit` participations and the label for an unidentified owner |
| U10 | Suggestions and decisions (8.7, 8.8) | No suggestion from names alone (spec 03 U-3); link then unlink restores state and both decisions appear with actor in order (spec 03 U-2); a rejected pair is not suggested again; `split` writes one decision per identity in one transaction; stale `expected_revision` returns 409; enum and constraint migration round-trips |
| U11 | Financial identifier kinds (8.9) | `phone_number` and `email` identifiers validate and match by normalised value (`(202) 555-0143` matches `+1 202 555 0143` under US); existing kinds behave as before (existing account identity tests pass unchanged); R4 suggestion appears only when the account holder party is linked to a dossier |
| U12 | Graph projection (9.3 to 9.5) | No projected node has a property named in 9.2 (test over the plan); after projecting C3 and C9 into one case, deleting C9 leaves every identity also seen on C3 with its C3 edges and removes C9-only identities (plan phase 4 done-when, spec 03 R-2); `--drop-first` rebuild yields the same revision; existing Timeline, Map and Graph endpoint results for the case are unchanged except for the added identity nodes in Graph; `COMMUNICATED` counts equal the Postgres counts per pair |
| U13 | Thread documents and search hits (9.7) | Every C3 chat yields thread text whose line count equals its message count; every location's `record_uid` exists; text search for a word in a message returns a hit carrying that `record_uid`; thread files do not appear in evidence listings; a thread over the part limit splits only at message boundaries; deleting the extraction removes the files and texts |
| U14 | Embedding gate, chat and workspace anchors (9.8, 9.9) | With no decision and the OpenAI provider, no phone chunk is sent to `embed_texts` (test patches it and asserts not called); lexical retrieval returns phone message windows to chat; `ChatSource` round-trips `record_uid`; two messages from one thread are two sources; a workspace theory citing a message stores a `phone_record` anchor whose URL opens the record |
| U15 | Corrections (10) | A corrected timestamp moves the event in streams and thread text and both values are shown; search finds the corrected body text and not the machine text in default mode; undo restores ordering and keeps the chain; a clock offset applies only within its period |
| U16 | Combined edges (11) | Edge communication counts equal Conversations `between` totals (spec 03 R-1) and time-sliced counts equal windowed totals (R-3); money sums use only admitted, current transactions, per currency (2 USD and 1 MXN payments give two totals, 05 17.8); p3 stated separately and p4 never in a total; undoing a link removes its contribution on recompute; a superseded correction's original amount is never counted; `edge-records` totals equal edge counts |
| U17 | Sweep and runtime (1.3, 5.7) | Killing the backend mid-pass leaves the previous generation readable and the next start completes it; the C6-scale timing measurement is recorded before the reverse-if in 1.3 is judged |

Order: U1, U2, U3, U4, U5, U6, U7 (plan phase 3), U8, U9, U10, U12, U13, U15 (plan phase 4), U11, U14, U16
(phases 5 and 6), U17 alongside U4.

---

## 14. Decisions made in this file

Each with its reason and what would reverse it.

1. **Interpretation runs as a backend sweep, not on the intake worker.** It is a pure function of Postgres
   state, so pause and resume are unnecessary; the financial identity sweep is the existing pattern.
   *Reverse if* the timing in 1.3 is exceeded.
2. **The registry is global, structure only, and its review history lives in its own event table.**
   Types are learned across cases; `adjudications` requires a case. *Reverse if* Loupe becomes
   multi-tenant.
3. **Seed producer versions are left null.** The catalogue did not record them; a back-filled value would
   be invented.
4. **Offset-less TimeStamps get no instant, and `formattedTimestamp` is never used to fill one.** Its
   offset is the examiner's display setting. *Reverse if* Cellebrite documentation shows the offset in
   `formattedTimestamp` is the device's.
5. **The device zone comes only from the metadata item `Time zone settings (ID)` or a decision;** the
   examiner-selected zone is shown but not used. This disagrees with 01 section 9.3, which prefers the
   selected zone; 01's column stays as captured and `pv_extraction.device_zone` follows this rule.
   *Reverse if* the 14 server phones show the two equal wherever both exist.
6. **Doubles are Decimals; coordinates alone are doubles.** Same reason as the ledger's ban on floats.
7. **Participant role combines container field and `Role`,** with conflicts flagged, because `Role` is
   absent or `General` inside `To` in measured data.
8. **Owner side is a synthetic `owner_implicit` participation** on every comm event lacking an owner party,
   as spec 03 requires.
9. **Mappings are JSON files in the repo, one per kind and name; review is the commit.** JSON avoids a
   dependency the test bootstrap lacks. *Reverse if* mappings must be changed per case without a deploy.
10. **Mapping version ids are uuid5 of kind, name, version and content hash;** a changed file is a new id
    and triggers re-derivation everywhere.
11. **A mapping is suspended per extraction when a field it names is under an open drift flag;** generic
    interpretation stands meanwhile.
12. **Coverage levels are five** (`reviewed`, `suspended`, `generic_role`, `generic_text`, `captured_only`),
    computed on read.
13. **Identity = identifier; person = dossier.** Matches spec 03 section 10; no third "cluster" object that
    could drift from dossiers.
14. **The only automatic equivalence is a valid WhatsApp user JID to its number.** True by construction;
    v1 learnt it from a split thread.
15. **Short codes and unverified digit strings are kept as `other` identities,** not discarded as v1 did,
    because bank and service SMS come from short codes (plan 12 approach 1).
16. **libphonenumber is adopted (`phonenumbers==9.0.31`, v1's pin), replacing Loupe's regex normaliser.**
17. **Default region: extraction decision, then case setting, then US with the basis recorded.**
18. **`fold()` adds a mixed-script confusable step** to spec 03's rules, limited to tokens mixing Latin with
    Cyrillic or Greek, so names written wholly in Cyrillic are untouched.
19. **Suggestion weights and the 0.5 threshold** as in 8.7, with R5 (names) never sufficient alone.
    *Reverse* by the measured acceptance rate.
20. **Ingest is not refused for a missing owner** (plan decision 7 over the v1 rule), with the owner side
    still represented.
21. **New decision subjects and members in the existing `adjudications` ledger,** rather than a phone
    ledger: one answer to "who decided what about this case".
22. **`phone_number` and `email` account identifier kinds,** compared by normalised value.
23. **Neo4j receives extractions, communicating identities, groups and aggregate edges only;** phone nodes
    carry no property the timeline or map would read.
24. **Pair edges exclude group messages, which count on `POSTED_IN`.** *Reverse if* spec 03's `between`
    is defined to include group messages; then pair counts gain a `group_messages_*` property instead.
25. **One derived `evidence_files` row per thread part, hidden from listings, split above 5,000 messages or
    2,000,000 characters at message boundaries.** Forced by the text table's primary key.
26. **Phone text is not embedded with a third-party provider without a per-case decision;** chat uses
    lexical retrieval until then.
27. **Citation anchors key on `record_uid`;** character offsets are advisory.
28. **Saved names are not correctable; a case label is set instead.**
29. **Money edges count only admitted, current, reviewed-linked ledger rows, per currency, over p0 to p2 with p3 separate,** in one module shared with spec 05.

30. **`record_uid` and `file_uid` are uuid5 of 01's positional keys,** because Cellebrite ids repeat and
    03's contract needs one stable id.
31. **Decisions about records use a `phone_record_subjects` row created on first decision,** because
    `phone_records` has no `id` or `case_id` column for `decisions.record` to check.
32. **Times are not parsed twice:** `phone_time_values` copies 01's `phone_timestamps` and adds format,
    meaning and effective instant.
33. **Row-table mapping kinds with a static ambiguity check, mirrored into `phone_mapping_rows`,** so 04's
    strength view and 05's natural keys read reviewed data in SQL.
34. **05's `phone_analysis_result` subject and its two decisions join the same ledger.**
35. **Phone labels come from the report file name, are not unique, and can be set by decision.**
36. **Superseded extractions keep their derived rows but leave every view.**
37. **A document whose reconciliation differs is held from interpretation** until a person records
    `accept_phone_reconciliation_difference`; it is shown, not interpreted silently.

## 15. Not yet established

- Whether `phonenumbers` 9.0.31 classifies the reserved fictional ranges used in tests as valid (tests use
  equivalence classes until recorded).
- Where a report states "chosen types and ranges" for a selective extraction (plan 6.5); candidate sections
  `projectConfigurations`, `extraInfos` were not inspected for this file.
- A record-level carving marker: `pv_record.is_carved` is false until one is found; candidates
  `source_index`, `labels`, `deleted_state`.
- The unit of `Location.Precision`.
- What `ApplicationUsage.LastScreenshot` (Guid) refers to.
- What `nodeField` and `dataField` children contain beyond being present (C3: 278 and 456).
- Owner tier results for C9, C8 and the 14 server phones (v1's memory note records three phones of the
  10-report case ingested with no owner number, before tier 2 existed).
- Count of communicating identities per case (sizes the graph; spec 03 20.9).
- Whether spec 03's Conversations `between` filter includes group messages (decision 24).
- Interpretation time on the largest phone (decision 1).
- How a payment-only counterparty party can be linked to a case entity (8.9 point 4); a financial change.
- Whether a local embedding model is available on Owl's server (decision 26).
