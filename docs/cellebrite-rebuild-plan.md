# Cellebrite in Loupe: rebuild plan

Status: planning. Nothing in this document is built yet. Written 2026-10-29 from a read-only
assessment of v1 (`origin/main`), Loupe (`integration/evidence-main-reunion`), the three sample
extractions on the development Mac, the 14 phone reports v1 ingested on the server, and published
material on the Cellebrite formats and the tools that read them.

This file holds the standing decisions, the evidence behind them and the summary of each area. The
detail lives in six specifications in `docs/cellebrite/`. **Where this file and a specification differ in
detail, the specification governs**; where they differ on a standing decision, this file governs and the
specification is corrected.

| Specification | Covers | Plan sections it details |
|---|---|---|
| [01 Intake, capture and storage](cellebrite/01-intake-capture-storage.md) | Input forms and detection, hashing, upload path, single-pass capture, the ten capture tables, file verification, exact reconciliation, time storage, the phone job, removal of the old ingestion | 2, 3, 6.1 to 6.3, 6.7 |
| [02 Interpretation, identity and projections](cellebrite/02-interpretation-identity-projections.md) | Schema registry, generic interpretation, reviewed mappings as data, coverage map, identity and Unicode folding, decisions, Neo4j projection, text store and citations, corrections, combined edges | 3.3, 6.4 to 6.6 |
| [03 Screens](cellebrite/03-screens.md) | Conversations, Extraction profile, Media; phone data in Timeline, People, Search, Export, Map, Graph; rules for completeness, time, names, duplicates; tests for every testing-hub item | 10 |
| [04 Pattern of life](cellebrite/04-pattern-of-life.md) | Signal inventory, timestamp meanings, activity strength, attribution, availability, places, day and pattern views, routine, together and apart, statement check | 11 |
| [05 Investigative approaches](cellebrite/05-investigative-approaches.md) | All thirteen approaches with method, measurement gate and tests; closing the gaps with other tools | 12, 13 |
| [06 Build order](cellebrite/06-build-order.md) | Every unit in one sequence with dependencies, gates, the server measurement batch, cross-cutting fixes, removal of old code, risks | 7 |

Settled while the specifications were written (2026-10-29): the device zone comes only from the
device's own setting in the report or a recorded decision, and the examiner's selected zone is shown as
the examiner's setting (01 section 9.3, 02 section 4.2); "between two people" means one-to-one threads
and direct calls by default, with shared group chats counted separately and one click to include them
(03 section 4.3, 02 section 9).

---

## 1. Standing decisions

Each decision carries what would reverse it.

1. **Rebuild the core; use v1 as the specification.** v1 holds the domain knowledge (47 type handlers,
   field-name aliasing across PA versions, owner inference, E.164 identity keys, per-type
   reconciliation, the investigator UI). Its storage and write layer is not ported: it can destroy
   evidence across phones and cannot prove provenance (section 4). Loupe's existing Cellebrite code
   (copied from v1 around 2026-05-15, before about 130 of v1's 220 Cellebrite commits) is replaced.
   *Reverse if* a phone case needs support within weeks: then patch v1's three destructive defects
   (4.1 to 4.3) as a stopgap first.
2. **`.ufdr` is a first-class input**, alongside a PA XML report folder, a zip of one, and the split
   section export (`.xmlModel`, `.xmlTagged` and siblings). A protected UFDR is detected and explained,
   never decoded. *Reverse if* reading the Reader EULA or legal advice says otherwise.
3. **Complete coverage is the priority.** Every element, attribute and value in the report is captured,
   whether or not any code understands it. *Not reversible without Neil.*
4. **Types are discovered, not listed.** A schema registry is learned from the data on every ingest.
   New types reach production with generic interpretation and no code change. *Reverse if* the
   self-description in section 3.3 stops holding for a new PA version (the registry would flag it).
5. **Interpretation level is computed, never set.** Every interpreted fact says whether it came from
   generic rules or a reviewed mapping, by the same principle as proof class.
6. **Postgres is the record; Neo4j is a projection.** Captured records, decisions and corrections live
   in Postgres with provenance. The graph is rebuilt from them. Nothing is written to the graph that
   cannot be rebuilt. *Reverse if* measured write or query volume makes the projection unworkable.
7. **Flag, don't refuse**, as everywhere in Loupe: hash mismatches, truncated exports, deleted or carved
   records, missing timestamps, unknown types are all kept and flagged.
8. **Evidence stays in house.** AI runs on local models by default, and cell tower and WiFi positions
   come from offline reference data. No evidence or identifier goes to a third-party service unless Neil
   decides so for a case. *Reverse* per case, by decision.
9. **Machine output never replaces the original.** Transcripts, OCR, translations and AI summaries are
   labelled machine-generated with model and version, and sit beside the source.
10. **Pattern of life is a priority alongside conversations** (section 11), and all thirteen approaches
    in section 12 are in scope.

---

## 2. What arrives

| Sample | Form | Report version | Producer | Notes |
|---|---|---|---|---|
| C3 | Zip and extracted folder, 805 MB, 43,144 files | 7.48 | PA 7.59 | `extractionType` Legacy; time zone config converts to UTC |
| C9 | Zip, 1.2 GB, half of entries `__MACOSX` | 7.48 | PA | `extractionType` FileSystem; convert-to-UTC **off** |
| C8 | Folder of split sections, 3.2 GB | 8.5 | PA 10.4 | `.xmlModel` (records) parses completely; `.xmlTagged` (file index) is cut off mid-element; six zero-byte siblings; no joined `.xml` |

None is a `.ufdr`. Published sources: a UFDR is a zip with `report.xml` at its root and files grouped by
category; there is no public schema; protected UFDRs are refused by IPED and Relativity with advice to
re-export unprotected or decrypt in Reader.

Consequence for intake: recognise UFDR, folder, zip (ignoring `__MACOSX` and `.DS_Store`) and split
sections; read what is readable from a truncated export and flag it as incomplete; state plainly what
is needed for a protected UFDR.

---

## 3. Measured coverage

### 3.1 v1 drops data below the level its check measures

v1 keeps a record only if its type is on `SUPPORTED_MODEL_TYPES` (`ingestion/scripts/cellebrite/parser.py:96`),
and reads only `field`, `modelField`, `multiModelField` and `jumptargets` inside a record
(`parser.py:779-811`). Field kinds never read, per sample:

| | C3 | C9 | C8 |
|---|---|---|---|
| `multiField` | 6,270 | 224 | 15,607 |
| `nodeField` | 278 | 92 | 34 |
| `dataField` | 456 | 874 | 3,155 |

Also discarded by v1: report sections `images`, `HashSetsInfo` (the extraction's own hashes), `carvedFiles`,
`infectedFiles`, `MalwareScanner`, `extraInfos`, `projectConfigurations`. In all three local samples
`images`, `HashSetsInfo`, `carvedFiles`, `infectedFiles` and `extraInfos` are present but empty, so no data
was lost from them there; other productions may fill them, and capture keeps them either way. Only the first `<value>` of a
field is kept. Per-type handlers save only the fields they name (v1's own coverage notes: 75 to 90 percent
for the main types).

v1's reconciliation counts top-level records per type only, so none of this was visible to it. Its
count files on the server show every one of the 14 phones under-counted at least one type.

### 3.2 Catalogue across 17 report files (14 phones on the server plus the 3 local samples)

| Measure | Result |
|---|---|
| Distinct record types | 62 (v1 lists 47) |
| Distinct (type, field name, field kind) | 470 |
| Named value sets | 57 |
| Types present in every report | 6 |
| Types present in one report only | 5 |
| New types contributed by each report in turn | 16, 25, 7, 1, 1, 0, 0, 0, 0, 0, 5, 1, 4, 2, 0, 0, 0 |

Types seen but not on v1's list: ten nested helpers (Coordinate, EmailAddress, ForwardedMessageData,
MessageLabel, PhoneNumber, QuotedMessageData, ReplyMessageData, StreetAddress, UserID, WebAddress) and
ten others (ActivitySensorDataMeasurement, ActivitySensorDataSample, ContactEntry, CreditCard,
DeviceInfoEntry, MobileCard, Organization, Recording, RemoteServiceSession, ScrambledMessageData). Some
of the second group may occur only nested; not yet established.

### 3.3 The report describes itself

- Every `<value>` carries a data type. Basic: String, TimeStamp, Boolean, Int64, Int32, Double, TimeSpan,
  Guid. Named sets, e.g. `ModelDirections` {Incoming, Outgoing}, `PartyRole` {From, To, General},
  `TelephonyCallStatus` (7 values), `MessageStatus` (6 values).
- Nested records name their type (Party, Coordinate, PhoneNumber, UserID, ...).
- Records carry `id`, `deleted_state`, `decoding_confidence`, `extractionId`, `source_index`, `file_id`,
  `labels`, `isrelated` (and `originalId` in 8.5).
- Across 17 reports: **zero untyped values**; **one** field whose data type differs between reports
  (`ChatActivity.SystemMessageId`: String and Guid).

### 3.4 Files and attachments

Three independent reference mechanisms: `taggedFiles/file` with `Local Path`; `jumptargets/targetid`
with `ismodel="false"`; the Attachment record's `file_id` attribute and `attachment_extracted_path`
field. v1 links only through `jumptargets` (`file_linker.py:373-404`). Chat and contact media under
`chats/`, `contacts/`, `photos/` are referenced only by the third mechanism and are present on disk at
100 percent in C3 (419) and C9 (852), so v1 never links them to their messages.

Per-file MD5 is present on 100 percent of tagged files; SHA256 on very few (224, 80, 3).

---

## 4. v1 defects (checked in source at `origin/main`)

1. **Deleting or replacing one phone deletes contacts other phones depend on.** A shared Person is
   merged per case and keeps the `cellebrite_report_key` of the phone that created it first
   (`neo4j_writer.py:571-600`); `delete_phone_report` detach-deletes every node with that key
   (`backend/services/neo4j_service.py`). **Live in v1.**
2. **Replace deletes before it writes** (`backend/services/cellebrite_service.py:303-316`). A failed
   re-ingest leaves the phone with no data.
3. **Writes are not idempotent.** Nodes use `CREATE` (`neo4j_writer.py:633-636`); 37 record keys are
   the record id cut to 12 characters and not scoped to the report.
4. **No integrity chain.** The uploaded zip is deleted without its hash kept; report MD5 never compared
   with the file; `images` and `HashSetsInfo` discarded; `extractionId` and `source_index` parsed but
   not stored.
5. **Silent truncation of content.** Email bodies cut to 2,000 characters (`neo4j_writer.py:1681`);
   multi-party `To` dropped; first value only; section 3.1.
6. **Time.** UI "Device" zone hard-coded to America/New_York (`frontend/src/components/cellebrite/shared/cellebriteTime.js:22`);
   offset-less times read as server local in intersections and as UTC in the backfill; date filters
   compare strings.
7. **Co-location quality.** Silent 20,000-event cap; location accuracy ignored (cell tower compared with
   GPS at 250 m); WiFi falls back to SSID name.
8. **Security.** Account passwords stored (flagged `is_sensitive`); media analysis sends images to OpenAI
   by default.
9. **Scale.** All records held in memory; one transaction per node and per edge; v1 ingest times on the
   server up to 292 minutes, and 200 minutes for a 25,600-record phone.

## 5. Lessons from v1's history (220 commits, April to July 2026)

1. Every major loss was silent and found weeks later (62k app events, 25k WiFi points, 122 photo GPS
   points, 2,079 audio files, half of searches). Measure completeness from day one.
2. Do not judge data "noise" without reading it (DictionaryWord was skipped, then found to hold typed
   amounts, emails and a date of birth).
3. Identity first: one normaliser, a deterministic report key, a guaranteed owner identity, aliases.
   Changing keys later forced full re-ingests.
4. Durable job state in a transactional store, not shared JSON files.
5. Jobs need staged progress, heartbeat, watchdog and an honest end state.
6. Never cap silently.
7. Scope every query by case; deleting a case must remove its graph.
8. Large uploads are infrastructure: resumable transfer, real staging disk, clear capacity errors.
9. Media needs its own track: classify from Cellebrite's category folder, transcode for playback.

---

## 6. Architecture

```
intake ─▶ capture (lossless) ─▶ registry + generic interpretation ─▶ reviewed mappings + curated views
                │                          │                                   │
                └──── element-level reconciliation (must match exactly) ───────┘
                                           │
              projections: Neo4j graph · shared text store (search, AI) · map · timeline · identities
```

### 6.1 Intake
- Forms: UFDR, folder, zip, split sections. Protected UFDR detected by magic bytes and explained.
- Hash the container as received and the report XML; keep both before anything is unpacked or deleted.
- Dedicated arq queue and worker, on the `PdfReviewWorkerSettings` pattern (`evidence-engine/app/worker.py:91-102`).
  Cooperative pause and resume through `services/ingestion_control.py`; checkpoints through
  `services/ingestion_checkpoints.py`. Structured progress, not log scraping.

### 6.2 Capture
- One streaming pass. Every model, top-level and nested, with all attributes; all seven field kinds;
  every value with its data type; every jump target; every tagged and carved file; every section
  (extraction info, case information, metadata, images, hash sets, time zone configuration).
- Stored in Postgres per extraction, each element with a locator (extraction, record id, field path,
  value index). Loading the same extraction twice is a no-op.
- Files: verify MD5 (and SHA256 where present) against the bytes on disk; record match, mismatch or
  missing per file. Resolve all three attachment mechanisms.

### 6.3 Reconciliation (the completeness proof)
- Count every element, attribute and value in the source and in the capture. They must be equal. A
  difference fails the ingest and names the path.
- Runs on every ingest and as a test over the reference corpus (section 8).

### 6.4 Registry and generic interpretation
- Registry: every (type, field, kind, data type) and every named-set value seen, with first-seen
  extraction and producer version. Flags: new type, new field, new set value, data-type drift.
- Generic interpretation by value role:

  | Record has | Becomes |
  |---|---|
  | TimeStamp field | timeline entry per field, labelled with the field name |
  | nested Coordinate | map point |
  | Party / PhoneNumber / UserID / EmailAddress | identity links across phones |
  | `PartyRole` or direction | who acted on whom |
  | file reference | attachments |
  | String values | searchable text with locator |
  | `deleted_state`, `decoding_confidence` | flags |

- Every type gets a generic list and detail view and a raw source view. Nothing captured is unreachable.

### 6.5 Reviewed mappings and curated views
- Mappings are versioned data, not code: e.g. "type X: field Y is the event time; role From is the
  sender". Applied to everything already captured, no re-ingest. AI may draft a mapping; a person
  reviews it; it is never applied automatically.
- Curated views (conversations, calls, co-location and so on) are built on mapped types.
- The coverage map (per type and field: interpreted, captured only) is the backlog and is shown in the
  product beside the report's own statement of what was selected (`IsSelectiveExtraction`,
  `IsPartialData`, chosen types and ranges).

### 6.6 Projections into Loupe
- Neo4j rebuilt from Postgres. A contact belongs to every phone it appears on (membership edges), so
  removing one phone removes only what no other phone references.
- Conversation threads and voice-note transcripts written as `evidence_document_texts` rows with
  per-message `source_locations`, so global search, AI chat and workspace citations work unchanged.
- Corrections and identity merges through `decisions.record` with a named Actor; both values kept,
  only the effective one used.
- Phone contacts link to financial counterparties only through the reviewed identity path
  (`financial/account_identity.py`, `identity_graph.py`). Money mentioned in messages is
  `unstructured_narrative`, therefore p4, never a ledger row.
- Graph and timeline need an explicit policy so phone volume does not swamp case views (they query
  without label filters today: `services/neo4j/timeline_service.py:24-43`).

### 6.7 Time
- Store each timestamp as an exact instant plus its original offset and the original string.
- The device zone comes from the report's `timeZoneConfigurations` and extraction metadata, never a
  constant. Offset-less values are flagged, not guessed.

---

## 7. Build order

Summary. The full sequence of about 75 units, with dependencies, gates and the server measurement batch, is in [06 Build order](cellebrite/06-build-order.md).

Each unit is finished, tested and committed before the next.

| Phase | Units | Done when |
|---|---|---|
| 0 | Reference corpus manifest; element-level counter over source XML | Counts for C3, C9, C8 recorded and stable |
| 1 | Intake for all four forms; container and report hashing; capture into Postgres; file verification; all attachment mechanisms | Reconciliation exact on C3, C9 and readable C8; second load is a no-op |
| 2 | Dedicated queue and worker; progress, pause, resume, cancel; staged replace | Kill mid-ingest and resume to the same result |
| 3 | Registry and generic interpretation; coverage map; raw source view | A type absent from the code appears with timeline, map and identity links |
| 4 | Projections: graph with membership, text store, identities, corrections | Deleting one of two phones sharing a contact leaves the other intact |
| 5 | Curated views and reviewed mappings (section 10.4): Conversations, Extraction profile, People, search, export; the activity-strength mapping (11.4) | Alex's testing-hub items each have a passing test |
| 6 | Cross-evidence (section 13): phone to financial identity links; combined communication and money edges; co-location with accuracy; RSMF export | |
| 7 | Pattern of life (section 11): day view, pattern view, places over time, statement check | A statement window shows supporting, contradicting and missing data with sources |
| 8 | Investigative approaches (section 12) in the order of 12.2, each preceded by its corpus measurement | Measurement recorded before each build |
| 9 | Media track (section 13): OCR and transcription on local models, translation, image search | |

## 8. Reference corpus

- Local: C3, C9, C8 (the readable sections). Never committed.
- Server: the 14 phones v1 ingested, under `/mnt/owl-data/ingestion-data/` (read-only use). Each has
  v1's `owl_ingest_report.json` with per-type counts and ingest duration, which serve as a baseline.

## 9. Not yet established

- Where real UFDRs differ from XML report folders: no `.ufdr` sample yet.
- Whether the second group of types in 3.2 occurs top-level or only nested.
- Whether v1's identity merge records an audit trail.
- Memory profile of a single-pass capture on the largest report (338,715 records).
- Reader EULA terms (text not located).

---

## 10. User-facing features

Summary. Full specification: [03 Screens](cellebrite/03-screens.md).

### 10.1 Evidence used

- **Alex's own words:** the v1 testing hub (`/home/conorbowles51/app_v2/data/testing-feedback.json` on the
  server): 12 items she filed on 2026-06-09 and 10, 2 comments, 14 checklist verdicts (8 pass, 5 fail,
  1 partial). All concern the Comms Center and the Timeline.
- **Work directed with Alex:** per Neil, all committed v1 work. Iteration per screen: Comms Center 37
  commits, Cross-Phone Graph 32, Timeline 27, Locations 19, Location & Events 17, Overview 7,
  Communications 6, Files 5, Report 3, Unified Contacts 3, Search & Discovery 1.
- **Notes from the time:** `.claude/plans/alex-call-roadmap.md` (handwritten-note items),
  `cellebrite-comms-geo-deep-dive.md` (a verbatim customer ask), the v1 Claude memory notes.
- **Market:** documented features of Cellebrite Reader, PA, Pathfinder, Guardian, Magnet AXIOM and
  Review, Oxygen, XAMN, Belkasoft, Relativity, Everlaw, Nuix, IPED and i2. Mostly vendor documentation;
  little independent testing is published.
- **Loupe:** its case-wide Timeline, Map, Graph and Table already show any node with a date or
  coordinates, so phone nodes appear there today with no phone-specific code.

### 10.2 What Alex's feedback asks for, in her words

| Theme | Her words (testing hub) |
|---|---|
| The phone's own view of the world | "if I'm looking through a phone's lens, then I want to see how that phone views the world" |
| Who to whom, always with name and number | "I know that #1 texted but I don't know to who. it should show as: [name] (#####) -> [name] (####)" |
| Complete results when filtered | "having to click load more constantly is pretty annoying ... when filters are at play, the timeline should load in full"; Comms Center showing one call where the Timeline shows many; scroll that stops loading |
| Readable dates | "only shows time. not the day ... military time which is confusing. can we do 12h?" |
| Search that matches what a person types | a display name in decorative Unicode letters cannot be found by typing it in plain letters |
| Faithful export | "Export Data to PDF" of a filtered conversation or timeline between two people and dates; the PDF cut message text, shifted a date by a day, and printed decorative letters as boxes |
| Basics | copy and paste in timelines; duplicate messages |

None of her filed items concern the graph, locations, co-location, files, discovery or the report. That
is an absence of written feedback over two days of testing, not evidence those screens lack value: the
graph's 32 commits trace to the handwritten call notes.

### 10.3 Market, honestly

Better elsewhere:
- Validation against the raw data (source database, hex view, carving checks): Physical Analyzer.
- Media AI (classification, faces, OCR, transcription) and translation: Pathfinder, Magnet, Oxygen,
  Belkasoft, IPED.
- Cross-app conversation by participant: XAMN's Participant Mode; Relativity's participant filter.
- Identity consolidation: Pathfinder's Person Resolution.
- Link analysis: i2 Analyst's Notebook.

Weak across the market, where Loupe can be clearly better:
- **No reviewed tool puts phone data and bank records in one timeline, one set of people and one
  search.** i2 comes closest, with hand-built imports.
- No tool shows the stored and converted time side by side for each event; practitioners resort to hex.
- Free reviewer tools hide source, deleted state and production gaps; legal review tools reach phone data
  through conversion that slices chats by day and drops categories without saying so.
- AI answers that cannot be traced to artifacts are the main criticism of vendor AI.
- Cost: free viewers are limited; capable tools are quote-only, thousands of dollars a year.

### 10.4 Recommended feature set

Each item names the Loupe screen it lives in.

**Core**
1. **Conversations** (phone-specific screen). One reader across apps and phones, by participant. Name
   and number on every message. The phone's own names by default, with a case-wide view one click away.
   Every result when filtered, with any limit stated. Day and 12-hour time, the zone shown, the original
   value one click away. Copy and paste. Duplicates collapsed visibly, never silently. Deleted and
   source badges, and the raw record behind every message.
2. **Case Timeline** (existing Loupe screen) with a phone lens: phone events beside financial
   transactions and documents. One swim-lane mode, not two. Full load under filters.
3. **People** (Loupe entities and dossiers) with a per-phone lens: one identity surface replacing four
   v1 places; reviewed links from phone identities to financial counterparties.
4. **Search** (Loupe-wide; none exists today): exact by default, folds decorative Unicode to plain
   letters, covers messages, and feeds the AI chat with record-level citations.
5. **Export**: a filtered conversation or timeline to PDF with full text, correct dates and fonts that
   cover every character; RSMF for counsel's review platform.
6. **Extraction profile** (phone-specific screen): owner, devices, what the production says was
   selected, the coverage map, hash verification, deleted counts, incomplete-export flags.

**Second**
7. **Case Map** (existing) with a phone layer: source, accuracy radius and carved status on every point;
   trajectories and playback. Co-location ("together") as an analysis that respects accuracy and reports
   any limit. Loupe already has unused MovementTrails, RouteAnalysis and Hotspot panels.
8. **Case Graph** (existing) with communication edges across phones beside financial flows; v1's path
   and flow features carried over.
9. **Media** (phone-specific screen): gallery by phone and app; transcription and OCR through Loupe's
   pipeline on demand, so voice notes and screenshots become searchable.

**Later**: translation; media classification.

### 10.5 What happens to each v1 screen

| v1 screen | Becomes |
|---|---|
| Comms Center, Communications, Overview drill tables | Conversations (1) |
| Timeline, both swim lanes, Location & Events list and table | Case Timeline phone lens (2) |
| Unified Contacts, shared-contacts panel, Overview contacts, graph people | People with per-phone lens (3) |
| Search & Discovery | Loupe-wide search (4) |
| Report (PDF), callouts | Export (5) |
| Overview, Report device profile | Extraction profile (6) |
| Locations, Location & Events map and playback | Case Map phone layer (7) |
| Intersections | Together analysis on the Map (7), rebuilt |
| Cross-Phone Graph | Case Graph (8) |
| Files | Media (9) |

Eleven phone tabs become three phone-specific screens (Conversations, Extraction profile, Media) plus
phone data inside five shared Loupe screens. Overlap in v1 had a measured cost: one date-filter fix had
to be applied to five timeline hosts, and one copy-paste fix to two swim lanes.

*Reverse* any merge if Alex's use shows a screen's separate form doing work the merged form cannot.

### 10.6 Loupe defects that bear on these features (found while reading; not fixed)

- The Reports page calls `/api/reports`, which no backend route serves.
- Map and Graph load the whole case with no cap.
- No global search exists; text search is a `LIKE` over document text and cannot see messages.
- Chat's prompt says to cite page 1 when no page is known (`llm_service.py:503`).
- Agent answers render without a document opener, so their links do nothing.
- The query panel posts to a route that does not exist; the fallback `/api/query` is not scoped to the
  case and runs in a write transaction.

---

## 11. Pattern of life: activity, places and time

Summary. Full specification: [04 Pattern of life](cellebrite/04-pattern-of-life.md).

Priority set by Neil 2026-10-29: locations and timelines in the widest sense (device events, app use,
logins, cell towers, searches, sensors) as signals of a person's pattern of life, to corroborate or
contradict conversations and interview statements.

### 11.1 What the 14 phones contain

Timestamped records across the 14 server phones (record count, phones carrying it):

| Signal | Records | Phones | Notes |
|---|---|---|---|
| ActivitySensorDataSample / ActivitySensorData | 424,657 / 45,518 | 3 | step and motion samples; distance, flights climbed, heart rate, speed |
| DeviceConnectivity | 193,070 | 8 | Bluetooth / WiFi connected, disconnected, detected, paired |
| DeviceEvent | 135,183 | 10 | types include DeviceLockStatus, DisplayOnOff, TextInput, MotionState, OrientationChange, CameraState, AirplaneMode, DoNotDisturbState, PowerEvent, Wipe |
| VisitedPage | 100,801 | 12 | `LastVisited` only |
| Location | 63,784 | 13 | `GpsHorizontalAccuracy`, `Confidence`, `Origin`, `Precision`, `DeviceLocationAffiliation` (Extracted / Synced / Unknown) |
| AppsUsageLog / ApplicationUsage | 67,723 / 2,608 | 3 | app actions with start and end |
| NetworkUsage | 53,031 | 4 | `NetworkUsageMode` Foreground / Background |
| Messages / Party | 377,648 / 634,942 | 14 | `DateRead`, `DatePlayed`, `DateDelivered` per party |
| Call | 30,205 | 14 | direction and status |
| WirelessNetwork | 25,569 | 12 | last connection, last auto-connection |
| LogEntry | 25,942 | 4 | system log lines |
| SearchedItem | 13,067 | 12 | |
| CellTower | 902 | 5 | MCC, MNC, LAC, CID only: no coordinates |
| PoweringEvent | 128 | 5 | device on and off |
| Journey, SocialMediaActivity (CheckIn), CalendarEntry, UserAccount, Cookie, Autofill, FileUpload | smaller | | |

v1 had no writer for ActivitySensorData, AppsUsageLog, LogEntry or Notification on several phones
(its own audit) and never used DeviceEvent types as activity.

### 11.2 Principles

1. **Activity strength is computed, never set.** Each event carries a class derived from its type,
   field and value through reviewed mapping data, with "unknown" as the default:
   - *Interaction*: needs a person at the device. Unlock, text input, outgoing message or call, search,
     camera use, foreground app use, a message marked read or a voice note played by the owner.
   - *Device state*: display on, power, charging, airplane mode, do-not-disturb. Can happen without a
     person (a notification lights the screen).
   - *Passive*: incoming messages and calls, notifications received, background network use, WiFi and
     Bluetooth scans, cell registrations, sync.
2. **Every timestamp says what it means.** `LastVisited` is the latest visit only, not every visit;
   a carved location's time is the last time the service saw it; `Cookie.LastAccessTime` is not a page
   view. The field name and its meaning are shown on every event.
3. **Attribution is explicit.** `DeviceLocationAffiliation = Synced` and `UserMapping` can mean the
   record came from another device on the same account. Flagged on every point and event.
4. **No data is not no activity.** Each signal type shows when data exists for it (first, last, gaps,
   power-off periods, the production's selected ranges), so an empty night reads as "no data" or
   "data present, no interaction", never ambiguously.
5. **Places are areas, not dots.** Every location carries its source and an uncertainty radius:
   GPS accuracy, WiFi, cell tower, app or account location, photo, calendar, card transaction.
   Cell tower and WiFi positions come only from offline reference data; no evidence identifier is sent
   to a third-party lookup service.
6. **Time as in section 6.7**: instant, original offset and original string; the device clock is a
   source with its own reliability.

### 11.3 Features

1. **Day view**: everything for a person or phone on one date, in lanes (interaction, device state,
   communications, places, money), with strength and source on each item.
2. **Pattern view**: hour-of-day by date, interaction-only by default, showing usual quiet hours and
   the nights that break them; per phone and per person across phones.
3. **Places over time**: routine places by time of day and day of week; deviations from routine;
   trajectories and playback with uncertainty shown.
4. **Statement check**: a claim with a time window, a place or an activity ("asleep from 23:00 to 07:00
   on a date", "at home all evening", "no contact with a person after a date") is tested against every
   signal. The result lists supporting and contradicting items with their strength and source, and the
   data gaps in that window. Claims can be drafted by AI from interview transcripts or messages; a person
   confirms them. Results attach to Workspace findings and theories as supports or contradicts, which
   the workspace already models.
5. **Together and apart**: co-location of phones and people with overlapping uncertainty areas and
   time windows, any limit stated.
6. **Money as place and time**: card transactions on the same timeline and map as phone signals, with
   the transaction-versus-posting date distinction the financial subsystem already records.

### 11.4 Where it sits in the build

Generic interpretation (section 6.4) already puts every TimeStamp field on the timeline and every
coordinate on the map. Pattern of life adds: the activity-strength mapping (data, reviewed), timestamp
meanings, attribution flags, data-availability bands, and the views above. The activity-strength
mapping for DeviceEvent, messages, calls, searches, app usage and network usage is the first reviewed
mapping to write, because every pattern feature depends on it.

---

## 12. Further investigative approaches the data supports

Summary. Each approach in full (method, measurement gate, tests): [05 Investigative approaches](cellebrite/05-investigative-approaches.md).

**All thirteen accepted by Neil, 2026-10-29.** Grounded in the fields present across the 14 server
phones (three cases holding 10, 3 and 1 reports; two of the 10 are labelled C1 with different
extraction dates; whether they are the same device is not yet established).

| # | Approach | Fields it rests on |
|---|---|---|
| 1 | **Phone signals of money.** Bank and payment push notifications, SMS from short codes, bank emails, finance apps, banking and exchange site cookies, saved service passwords, card records: matched to the ledger, or revealing accounts and institutions absent from the financial productions | Notification (7,881 on 2 phones), short-code senders from `Party.Identifier` (not `InstantMessage.SMSC`, which is the SMS service centre and never equals the sender: 0 of 129, 16 and 11), Email, InstalledApplication.Categories, Cookie.Domain, Password.Service, VisitedPage. `CreditCard` has 1 record in the corpus; `MobileCard` excluded until its meaning is reviewed |
| 2 | **Cross-phone message reconciliation.** The same message on sender and recipient phones: corroboration from both sides, deletion on one side only, clock offset between devices, gaps filled | InstantMessage, Party, deleted_state, TimeStamp |
| 3 | **Deletion and concealment timeline.** When messages, chats and apps were deleted, disappearing-message settings, wipes, unreadable messages, set against key dates; which conversations were selectively cleared, and which deletions an auto-delete setting explains | deleted_state on every record; DeletionReason, SelfDestructDuration; InstalledApplication.DeletedDate; DeviceEvent Wipe; ScrambledMessageData (7,958); ChatActivity. `InstantMessage.DateDeleted` has 1 value in the whole corpus, so a deletion time is normally an interval from the message time to the extraction |
| 4 | **Knowledge and awareness.** When the owner read or played a message, how fast they replied, who reads without replying, who runs a group (admin, adds, removes) | Party.DateRead, DatePlayed, DateDelivered, IsGroupAdmin; ChatActivity actions |
| 5 | **Who used which phone.** Two devices that always travel together with complementary use (one person, two phones); multiple people on one phone; activity on a phone while its owner's other phone is elsewhere | Location, DeviceEvent, accounts, SIMData, MobileCard |
| 6 | **Other devices and accounts in play.** Car and headset Bluetooth names, named WiFi networks, sessions from other devices, accounts and services that exist even where no app does | DeviceConnectivity, RecognizedDevice, WirelessNetwork.SSId, RemoteServiceSession.UserAgent, UserAccount, Cookie, Password |
| 7 | **What was typed, even if deleted.** Keyboard-learned words and autofill values hold names, amounts and addresses after the message is gone | DictionaryWord (14,260 on 4 phones), Autofill |
| 8 | **Media spread across phones.** The same image on several phones: who shared what with whom and in what order, even where the message is gone; taken versus received; photo time and place | file hashes restricted to message attachments, camera folders and camera EXIF (shared system files dominate raw hash overlap: 7,030 shared, 0 to 4 once restricted); EXIF sits in the file index, not record fields. `ApplicationUsage.LastScreenshot` is an id, not a time |
| 9 | **Intent and research.** Searches and page titles with visit counts, set against events; with the caveat that only the latest visit time is kept | SearchedItem, VisitedPage.Title, VisitCount, UsagePattern |
| 10 | **Plans and self-reported places.** Calendar entries with locations and repeats; social check-ins; notes that are lists of names or amounts | CalendarEntry, SocialMediaActivity (CheckIn), Note |
| 11 | **Relationships over time.** When a contact was saved, renamed, first and last contacted; how each phone names the same person; calls just before and after key events; contact that stops when a statement says it did, or does not | Contact.TimeCreated, TimeModified, Notes; Call; per-phone names |
| 12 | **Extraction comparison.** Two extractions of one phone: what appeared or disappeared between them | report header identifiers, record ids |
| 13 | **Incident window.** Every phone in the case, every signal, around one anchor time | all timestamped types |

### 12.1 Rules for every approach

1. **Measure before building.** Each approach starts with a read-only count on the reference corpus that
   shows whether it pays off and on which phones: for example how many messages appear on two phones in
   the 10-report case, or how many notifications and SMS carry amounts. The count is recorded here.
2. **Coverage is shown.** Every result states which phones and periods carry the data it rests on
   (sensor data is on 3 of 14 phones, notifications on 2).
3. **Both directions.** Each approach reports what supports and what undercuts a reading: an auto-delete
   setting that explains deletions; synced data that may come from another device; a clock offset.
4. **Sensitive fields** (saved passwords, keyboard dictionary, autofill, credentials, card numbers) are
   captured, shown with care, and excluded from exports by default.
5. **Money stays p4.** Anything financial read from a phone enters through claim comparison and
   correlation as unstructured narrative; it can corroborate a ledger row, never become one.

### 12.2 Order

| Order | Approaches | Why |
|---|---|---|
| First | 1 money signals | Only possible on a platform that holds the ledger; can reveal accounts absent from productions |
| Second | 2 cross-phone reconciliation, 3 deletion timeline | Direct corroboration and concealment; depend on identity and capture only |
| Third | 4 knowledge, 5 who used which phone, 11 relationships over time | Build on identities and pattern of life |
| Fourth | 6 other devices and accounts, 7 typed words, 8 media spread, 9 intent, 10 plans and check-ins | Mostly generic interpretation plus a view each |
| Fifth | 12 extraction comparison, 13 incident window | 13 is largely the day view (11.3) across all phones; 12 needs two extractions of one device |

---

## 13. Closing the gaps where other tools are better

Summary. Full specification: [05 Investigative approaches](cellebrite/05-investigative-approaches.md) section 17.

| Gap | Approach in Loupe |
|---|---|
| **Validation against raw data** (Physical Analyzer) | Not an examiner tool. Every item opens to its captured report record (all fields, flags, Cellebrite record id). Where the production includes the source database, open the source row; where it is absent, say so. No sample carries one: C8's file index lists 1,081 database files but none are on disk, and C3 and C9 list none, so this view and the re-parse below are conditional on a future production. Hash verification, deleted, carved and decoding-confidence state on screen. Where raw files are present, an independent re-parse with open-source parsers (ALEAPP, iLEAPP) and disagreements flagged. No hex view or carving. |
| **Media AI and translation** (Pathfinder, Magnet, Oxygen, Belkasoft) | Today the engine's audio transcription calls OpenAI only, and video frames go to OpenAI regardless of the image setting; both are fixed as part of this work. Local models by default; no evidence sent to a third party unless Neil decides otherwise for a case. Machine output is labelled, carries model and version, and never replaces the original. Order: OCR of screenshots and photographed documents tied to the ledger through claim comparison; voice-note transcription; translation with the original always shown; image search by description. Face grouping only on a case that needs it, by decision. |
| **Conversations by participant across apps** (XAMN, Relativity) | Section 10.4 item 1: one stream per person or pair across apps and phones, phone's own names by default, name and number on every line, complete under filters, the person's payments in the same stream, faithful PDF and RSMF export that does not slice by day. |
| **Identity consolidation** (Pathfinder) | An identifier registry (E.164 numbers, app ids, emails, usernames, display names folded to plain letters). Merge suggestions with stated reasons; a person decides through the decision log; merges can be undone and split. Extended to financial counterparties through the reviewed identity path. |
| **Link analysis** (i2) | Communication and money edges on one link with counts and sums ("14 calls, 230 messages, $8,400 in 6 payments"), sliceable by time; every edge opens to its records; charts export with source references. |

Not pursued: hex-level validation and carving (the examiner's job on the original extraction).
