# Cellebrite ingestion coverage audit

_Generated from 14 per-report reconciliation files across all ingested phones._

Aggregates the `owl_ingest_report.json` reconciliation each ingest already writes.
`not_supported` = no writer (100% dropped). `under` = writer dropped a subset (parser/writer bug).
`nested InstantMessage` negative 'loss' is EXPECTED (messages persist via Chat parsing).

## `not_supported` — entire artifact types with NO writer (100% dropped)

| Type | # phones | total instances dropped |
|---|---|---|
| ActivitySensorData | 1 | 17,082 |
| LogEntry | 2 | 16,311 |
| Cookie | 6 | 10,115 |
| AppsUsageLog | 1 | 8,960 |
| Notification | 2 | 7,040 |
| DeviceConnectivity | 6 | 4,083 |
| FileUpload | 4 | 3,332 |
| SocialMediaActivity | 3 | 1,006 |
| Voicemail | 1 | 76 |
| Journey | 4 | 75 |
| DeviceInfoEntry | 1 | 45 |
| Note | 5 | 13 |
| Recording | 1 | 7 |
| RemoteServiceSession | 1 | 6 |
| MobileCard | 4 | 4 |
| CreditCard | 1 | 1 |

## `under` — writer exists but dropped a subset (writer bug)

| Type | # phones | total lost |
|---|---|---|
| Contact | 12 | 2,025 |
| Location | 6 | 1,463 |
| SearchedItem | 8 | 715 |
| DictionaryWord | 4 | 91 |
| SIMData | 7 | 14 |
| CalendarEntry | 6 | 7 |
| RecognizedDevice | 2 | 2 |

## Per-phone detail

### EVD-25-255083-Inseyets Extraction_2026-01-20_Report  (case `34fbbb06`)
- **under** `SearchedItem` — xml 71 / persisted 37 (lost 34)

### 220049582_06306369_C4_2022-12-12_Report  (case `43f1afb1`)
- **not_supported** `ActivitySensorData` — xml 17082 / persisted 0 (lost 17082)
- **not_supported** `AppsUsageLog` — xml 8960 / persisted 0 (lost 8960)
- **not_supported** `LogEntry` — xml 4502 / persisted 0 (lost 4502)
- **under** `Location` — xml 1352 / persisted 111 (lost 1241)
- **not_supported** `DeviceConnectivity` — xml 1228 / persisted 0 (lost 1228)
- **under** `Contact` — xml 2552 / persisted 1397 (lost 1155)
- **not_supported** `Cookie` — xml 643 / persisted 0 (lost 643)
- **not_supported** `Journey` — xml 36 / persisted 0 (lost 36)
- **under** `SearchedItem` — xml 8781 / persisted 8768 (lost 13)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)

### 220029502_06310028_C9_2023-03-02_Report  (case `43f1afb1`)
- **under** `DictionaryWord` — xml 640 / persisted 635 (lost 5)
- **under** `Contact` — xml 235 / persisted 231 (lost 4)
- **under** `CalendarEntry` — xml 1 / persisted 0 (lost 1)

### 220049582_06305320_C1_2023-01-20_Report  (case `43f1afb1`)
- **not_supported** `DeviceConnectivity` — xml 1215 / persisted 0 (lost 1215)
- **not_supported** `Cookie` — xml 720 / persisted 0 (lost 720)
- **under** `SearchedItem` — xml 777 / persisted 436 (lost 341)
- **not_supported** `Journey` — xml 22 / persisted 0 (lost 22)
- **under** `Location` — xml 508 / persisted 488 (lost 20)
- **under** `Contact` — xml 3983 / persisted 3971 (lost 12)
- **not_supported** `FileUpload` — xml 9 / persisted 0 (lost 9)
- **not_supported** `MobileCard` — xml 1 / persisted 0 (lost 1)
- **not_supported** `Note` — xml 1 / persisted 0 (lost 1)

### 220049582_06306207_C2_2022-12-12_Report  (case `43f1afb1`)
- **not_supported** `LogEntry` — xml 11809 / persisted 0 (lost 11809)
- **not_supported** `FileUpload` — xml 3259 / persisted 0 (lost 3259)
- **not_supported** `DeviceConnectivity` — xml 1630 / persisted 0 (lost 1630)
- **not_supported** `Cookie` — xml 309 / persisted 0 (lost 309)
- **not_supported** `SocialMediaActivity` — xml 176 / persisted 0 (lost 176)
- **under** `SearchedItem` — xml 560 / persisted 452 (lost 108)
- **under** `Contact` — xml 2303 / persisted 2267 (lost 36)
- **not_supported** `Journey` — xml 16 / persisted 0 (lost 16)
- **not_supported** `Note` — xml 6 / persisted 0 (lost 6)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)
- **under** `CalendarEntry` — xml 249 / persisted 248 (lost 1)
- **not_supported** `MobileCard` — xml 1 / persisted 0 (lost 1)

### 220049582_06306208_C3_2022-12-12_Report  (case `43f1afb1`)
- **under** `Contact` — xml 1612 / persisted 1610 (lost 2)
- **under** `CalendarEntry` — xml 80 / persisted 79 (lost 1)

### 220049582_06306946_C5_2022-12-15_Report  (case `43f1afb1`)
- **under** `DictionaryWord` — xml 6540 / persisted 6512 (lost 28)
- **under** `CalendarEntry` — xml 3 / persisted 1 (lost 2)
- **under** `Contact` — xml 1517 / persisted 1516 (lost 1)
- **under** `RecognizedDevice` — xml 1 / persisted 0 (lost 1)

### 220049582_06306962_C6_2022-12-14_Report  (case `43f1afb1`)
- **not_supported** `Cookie` — xml 3984 / persisted 0 (lost 3984)
- **not_supported** `SocialMediaActivity` — xml 5 / persisted 0 (lost 5)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)
- **not_supported** `Note` — xml 2 / persisted 0 (lost 2)
- **under** `Contact` — xml 13005 / persisted 13004 (lost 1)
- **under** `CalendarEntry` — xml 40 / persisted 39 (lost 1)
- **under** `Location` — xml 17 / persisted 16 (lost 1)
- **not_supported** `DeviceConnectivity` — xml 1 / persisted 0 (lost 1)

### 220049582_06306964_C7_2022-12-17_Report  (case `43f1afb1`)
- **not_supported** `Cookie` — xml 1157 / persisted 0 (lost 1157)
- **not_supported** `FileUpload` — xml 46 / persisted 0 (lost 46)
- **under** `DictionaryWord` — xml 2432 / persisted 2411 (lost 21)
- **under** `SearchedItem` — xml 32 / persisted 24 (lost 8)
- **not_supported** `DeviceConnectivity` — xml 4 / persisted 0 (lost 4)
- **under** `Location` — xml 474 / persisted 471 (lost 3)
- **under** `Contact` — xml 464 / persisted 461 (lost 3)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)
- **not_supported** `Note` — xml 2 / persisted 0 (lost 2)
- **not_supported** `Journey` — xml 1 / persisted 0 (lost 1)

### C1-06304890_2022-11-15_Report  (case `43f1afb1`)
- **under** `Contact` — xml 2940 / persisted 2217 (lost 723)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)

### 220049582_06308586_C8_2023-01-18_Report (1)  (case `43f1afb1`)
- **not_supported** `Cookie` — xml 3302 / persisted 0 (lost 3302)
- **not_supported** `SocialMediaActivity` — xml 825 / persisted 0 (lost 825)
- **under** `Location` — xml 206 / persisted 35 (lost 171)
- **under** `DictionaryWord` — xml 4648 / persisted 4611 (lost 37)
- **not_supported** `FileUpload` — xml 18 / persisted 0 (lost 18)
- **not_supported** `DeviceConnectivity` — xml 5 / persisted 0 (lost 5)
- **under** `Contact` — xml 241 / persisted 239 (lost 2)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)
- **not_supported** `Note` — xml 2 / persisted 0 (lost 2)

### C1_06352318_ffs (3)  (case `5e374d4f`)
- **not_supported** `Notification` — xml 3089 / persisted 0 (lost 3089)
- **under** `SearchedItem` — xml 1519 / persisted 1322 (lost 197)
- **not_supported** `DeviceInfoEntry` — xml 45 / persisted 0 (lost 45)
- **under** `Location` — xml 12848 / persisted 12821 (lost 27)
- **not_supported** `RemoteServiceSession` — xml 6 / persisted 0 (lost 6)
- **under** `Contact` — xml 4679 / persisted 4674 (lost 5)
- **under** `CalendarEntry` — xml 138 / persisted 137 (lost 1)
- **under** `RecognizedDevice` — xml 11 / persisted 10 (lost 1)
- **not_supported** `MobileCard` — xml 1 / persisted 0 (lost 1)

### C2_06352877  (case `5e374d4f`)
- **not_supported** `Notification` — xml 3951 / persisted 0 (lost 3951)
- **under** `Contact` — xml 8497 / persisted 8416 (lost 81)
- **not_supported** `Voicemail` — xml 76 / persisted 0 (lost 76)
- **under** `SearchedItem` — xml 94 / persisted 81 (lost 13)
- **not_supported** `Recording` — xml 7 / persisted 0 (lost 7)
- **not_supported** `MobileCard` — xml 1 / persisted 0 (lost 1)

### C3_06352898  (case `5e374d4f`)
- **under** `SIMData` — xml 9 / persisted 7 (lost 2)
- **under** `SearchedItem` — xml 223 / persisted 222 (lost 1)
- **not_supported** `CreditCard` — xml 1 / persisted 0 (lost 1)


---

## Remediation (categorized)

The losses fall into three buckets with different fixes:

### 1. Version drift → **RE-INGEST** recovers them (no new code)
These types ARE in the current `SUPPORTED_MODEL_TYPES`, but the older
`43f1afb1` / `5e374d4f` ingests predate those writers, so they show as
`not_supported` there. Re-ingesting those phones with current code recovers them:
`Cookie` (10,115), `LogEntry` (16,311), `DeviceConnectivity` (4,083),
`AppsUsageLog` (8,960), `ActivitySensorData` (17,082), `SocialMediaActivity` (1,006),
`FileUpload` (3,332), `Journey` (75), `Note` (13). **~60k artifacts recoverable by re-ingest.**

### 2. Writer under-count bugs → **FIX THE WRITER** (then re-ingest)
Writer exists but drops a subset:
- **`SearchedItem`** — FIXED 2026-06-30 (required a `Value` field location-searches
  lack, and never read the lat/lon). Recovers ~720 searches + their geo across phones on re-ingest.
- **`Location`** under in several (lost 171, 1241, 20…) — investigate next.
- **`Contact`** under (lost 723, 1155, 81…) — investigate.
- **`SIMData`** consistently loses 2 (9→7) on every phone — systematic, investigate.
- `CalendarEntry` / `DictionaryWord` / `RecognizedDevice` — minor.

### 3. Genuinely missing writers → **ADD A WRITER** (not in any version)
Not in `SUPPORTED_MODEL_TYPES` at all — need new handlers, by value:
- **`Notification`** (7,040) — app notifications (message previews, alerts). High value.
- **`Voicemail`** (76) — voicemails (with audio). High value.
- `Recording` (7), `DeviceInfoEntry` (45), `RemoteServiceSession` (6),
  `MobileCard` (4), `CreditCard` (1) — low volume.

## Future-proofing (done 2026-06-30)
- Ingestion already logs a LOUD warning for `not_supported` (unknown) types.
- **Added**: an equally loud warning for `under`-counted types (a supported writer
  silently dropping a subset — the SearchedItem failure mode). So both classes of
  coverage loss are now surfaced at ingest time, not buried in JSON.
- The reconciliation is also persisted on each PhoneReport node + the
  `owl_ingest_report.json`. This audit aggregates them; re-run the generator to refresh.
