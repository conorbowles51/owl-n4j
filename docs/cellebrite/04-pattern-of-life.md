# 04. Pattern of life: activity, places and time

Status: specification. Nothing here is built. Written 2026-10-29. Details section 11 of
`docs/cellebrite-rebuild-plan.md` (the plan) and the pattern-of-life parts of build phases 5 and 7.

**Purpose.** A phone holds many timestamped records that were never meant as a diary but behave like one:
device events, app use, network use, web visits, searches, locations, WiFi and Bluetooth sightings,
sensor samples, message read times, power cycles. This specification turns them into signals that can
corroborate or contradict what a person said, without overstating what any one record shows. It fixes:
what every timestamp in the corpus means; how strongly each kind of record indicates that a person was
using the phone; who a record can be attributed to; when a phone was recording at all, so that silence is
never mistaken for inactivity; how places are represented as areas with an uncertainty, from offline
reference data only; the five views (day, pattern, places over time, together and apart, money as place
and time); the statement check that tests a claim against all of it and attaches the result to Workspace;
the API, the performance targets, the acceptance tests, and the read-only corpus measurements that must
run before each unit is built.

Plan standing decisions (section 1) hold throughout, in particular 5 (interpretation level computed, never
set), 6 (Postgres is the record), 7 (flag, don't refuse) and 8 (evidence stays in house).

## Contents

1. Conventions and sources
2. Signal inventory (timestamped types, counts, phones, fields, meanings)
3. Activity-strength mapping
4. Attribution
5. Data availability bands
6. Places
7. Storage (tables)
8. Views
   8.1 Day view · 8.2 Pattern view · 8.3 Places over time · 8.4 Together and apart · 8.5 Money as place and time
9. Statement check
10. API
11. Performance targets
12. Units, build order and acceptance tests
13. Corpus measurements to run before building
14. Decisions made here that the plan did not settle
15. Not yet established

---

## 1. Conventions and sources

### 1.1 Phone labels

The 14 server phone reports are in `measurements/catalogue-14-phones.json` order. The C labels are the exhibit labels in
the report names; they repeat across cases, so this file uses P01 to P14.

| Id | Case | Exhibit label | Local copy | Model elements (all levels) |
|---|---|---|---|---|
| P01 | 1-phone case | (single report) | | 32,332 |
| P02 | 10-report case | C8 | C8 (same per-type counts as the local split export) | 73,608 |
| P03 | 10-report case | C1, extraction 2023-01-20 | | 44,949 |
| P04 | 10-report case | C2 | | 251,466 |
| P05 | 10-report case | C5 | | 70,487 |
| P06 | 10-report case | C3 | C3 | 71,045 |
| P07 | 10-report case | C7 | | 55,361 |
| P08 | 10-report case | C6 | | 694,406 |
| P09 | 10-report case | C9 | C9 | 14,005 |
| P10 | 10-report case | C1, extraction 2022-11-15 | | 140,608 |
| P11 | 10-report case | C4 | | 290,509 |
| P12 | 3-phone case | C3 | | 17,496 |
| P13 | 3-phone case | C2 | | 523,024 |
| P14 | 3-phone case | C1 | | 967,543 |

The catalogue holds 10 reports from the case the plan calls the 10-report case (plan 12 notes two C1
reports, P03 and P10). The local-copy matches are by identical per-type counts (C3 vs P06: Location 31,
DeviceEvent 2, NetworkUsage 5,181; C8 vs P02: Location 206, NetworkUsage 20,961; C9 vs P09: Location 7,
SearchedItem 13).

### 1.2 Measurements used in this file

All counts come from these, run read-only and structure-only (no content printed):

| Name | What | Where |
|---|---|---|
| CAT | `measurements/catalogue-14-phones.json`: per phone, model counts, (type, field, kind, value type) counts, named-set values up to 50 | `measurements/` |
| POL-S | `pol_samples.py` over the three local samples: distinct short values of selected fields (guarded by a pattern; free text reported as `<other>`), timestamp shape (digits replaced by 9), `deleted_state` and `decoding_confidence` per type, (EventType, Value) and (Direction, Status) pairs | `measurements/scripts/pol_samples.py`; its outputs are not committed because they list short field values |
| POL-P | `pol_party.py`: Party models carrying DateRead / DateDelivered / DatePlayed, by parent type, Role, IsPhoneOwner | `measurements/` |
| POL-N | `pol_nest.py`: (parent type, container field, child type) for nested models | `measurements/` |
| HDR | header `item` names in C3 and C9 (`DeviceInfoExtractionStartDateTime`, `DeviceInfoExtractionEndDateTime`, `Time zone settings (ID)` and others) | grep over the first 60 kB |

CAT records only value-bearing field kinds (`field`, `multiField`); nesting is therefore not in CAT and
comes from POL-N. CAT does not list `DecodingSourceOptions` values (excluded by `catalog.py`), so
UserMapping values come from POL-S only.

### 1.3 Code read for this file

| Claim | Citation |
|---|---|
| v1 co-location loads at most 20,000 events | `origin/main:backend/services/cellebrite_intersection_service.py:89` |
| v1 spatial defaults 250 m and 600 s; distance test ignores accuracy | same file `:105-106`, `:153` |
| v1 cell-tower window 900 s; WiFi window 1800 s | `:206`, `:311` |
| v1 WiFi groups by BSSID, falling back to SSID | `:338` |
| v1 parses times with `fromisoformat`, so an offset-less value becomes a naive datetime | `:44-50` |
| v1 date filters compare stored strings | `:215`, `:320`, `:414` |
| v1 convoy evidence truncated to 50 | `:648`, `:664` |
| Loupe carries a copy with the same cap, radius and SSID fallback (to be removed) | `backend/services/cellebrite_intersection_service.py:89`, `:105`, `:338` |
| Workspace link relationships `unclassified, supports, contradicts, context` | `backend/postgres/models/workspace_entry.py:42`, `:265-267` |
| Workspace link target types (no phone record type today) | `backend/postgres/models/workspace_entry.py:43-53`, `:269-272` |
| Link carries `source_anchor` and `metadata` documents | `backend/postgres/models/workspace_entry.py:309-315` |
| Links are added through `add_entry_links(..., expected_version, links, ignore_existing, commit)` | `backend/services/workspace_entry_service.py:1352-1362` |
| Workspace AI output types and cited-JSON pattern | `backend/services/workspace_ai_service.py:31`, `:552-579` |
| Interview sources come from linked evidence transcripts and text, anchored by seconds or characters | `backend/services/workspace_ai_service.py:186-239`, `:311-356` |
| Accepting an output adds links with `supports`/`contradicts` per cited source | `backend/services/workspace_ai_service.py:700-754`, `:934-1013` |
| Workspace AI uses the `workspace_analysis` workload; providers are openai, anthropic, gemini, deepseek; no local provider exists | `backend/services/ai_model_policy.py:17-58`, `:64`, `:77`, `:87`, `:97`; `backend/services/workspace_ai_service.py:582-596` |
| Transcripts are `transcription` and `transcription_segments` on the evidence file | `backend/postgres/models/evidence.py:154-155` |
| Ledger dates are four DATE columns plus `ordering_date` and its source; no time of day, no place | `backend/postgres/models/financial.py:819-824` |
| Ordering precedence posted, transaction, value, effective | `backend/services/financial/transactions.py:293-298` |
| Ledger read defaults to `admitted` rows | `backend/services/financial/transaction_query.py:84-89` |
| Corrections append a superseding row and keep the original | `backend/services/financial/corrections.py:1-6`; `superseded_by_id` at `backend/postgres/models/financial.py:838-842` |
| Ledger timeline labels the date basis and says same-day position is not sequence | `backend/services/financial/ledger_timeline.py:24-39` |
| Reverse geocoder is pluggable: Nominatim at a configured URL, or offline GeoNames; off by default | `backend/services/geocoder.py:1-31`, `:313-345`, `:354-363` |
| Router conventions: `APIRouter(prefix=...)`, `require_case_view` / `require_case_edit` | `backend/routers/workspace_entries.py:16`, `:41`, `:286`; `backend/routers/case_access.py:102`, `:112` |
| Evidence engine runs Python 3.12; backend 3.10 | `evidence-engine/Dockerfile:1`, `evidence-engine/pyproject.toml:5`; `CLAUDE.md` |

### 1.4 Sibling specifications referred to abstractly

- **Capture** (plan 6.2): every record, nested record, field and value with a locator `(extraction_id,
  record_id, field path, value index)`. This file reads captured values through that locator and never
  re-parses XML.
- **Mapping format** (spec 02): versioned, reviewed mapping data. The activity-strength mapping, the
  timestamp-meaning mapping and the attribution mapping in this file are three mapping kinds in that
  format. This file defines their content and match semantics, not their storage.
- **Time** (plan 6.7): each timestamp as exact instant, original offset and original string. This file
  uses `instant_utc`, `offset_status` in {`explicit`, `absent`} and `original` from it.
- **Identity**: phone identities, the owner identity of each extraction, and reviewed links from
  identities to persons (Loupe entities). This file uses `owner_identity_id` per extraction and
  `person -> [extraction]` resolution, and never merges identities itself.

---

## 2. Signal inventory

### 2.1 Every type that carries a TimeStamp or TimeSpan value (CAT, 14 server phones)

"Records" counts models of that type at any nesting level. "Values" counts records carrying a value in
that field. Phones are P numbers.

| Type | Records | Phones | Phones carrying it | Time fields: values (phones) |
|---|---|---|---|---|
| Party | 634,942 | 14 | all | DateDelivered 20,672 (8); DateRead 19,716 (11); DatePlayed 2,347 (3) |
| ActivitySensorDataSample | 424,657 | 3 | P11, P13, P14 | DateSampled 424,657 (3); DateEnded 287,141 (2) |
| InstantMessage | 377,648 | 14 | all | TimeStamp 370,754 (14); SelfDestructDuration [TimeSpan] 68,258 (2); DateDelivered 20,801 (5); DateDeleted 1 (1) |
| DeviceConnectivity | 193,070 | 8 | P02 P03 P04 P07 P08 P11 P13 P14 | StartTime 187,155 (8) |
| DeviceEvent | 135,183 | 10 | P02 P03 P04 P05 P06 P07 P08 P11 P13 P14 | StartTime 134,342 (10); EndTime 68,441 (5) |
| VisitedPage | 100,801 | 12 | all but P01, P10 | LastVisited 70,147 (12) |
| AppsUsageLog | 67,723 | 3 | P11, P13, P14 | StartTime 67,723 (3); EndTime 45,283 (3) |
| Location | 63,784 | 13 | all but P10 | TimeStamp 59,659 (12); EndTime 16,815 (5) |
| NetworkUsage | 53,031 | 4 | P02 P06 P07 P08 | DateStarted 53,031 (4); DateEnded 53,031 (4) |
| ActivitySensorData | 45,518 | 3 | P11, P13, P14 | From 45,518 (3); To 45,518 (3) |
| Contact | 43,624 | 13 | all but P01 | TimeCreated 4,996 (8); TimeModified 979 (6) |
| Call | 30,205 | 14 | all | TimeStamp 30,203 (14); Duration [TimeSpan] 26,415 (14) |
| LogEntry | 25,942 | 4 | P04 P11 P13 P14 | TimeStamp 24,176 (4); EndTime 13,881 (4) |
| Email | 25,727 | 12 | | TimeStamp 25,727 (12) |
| WirelessNetwork | 25,569 | 12 | | TimeStamp 25,356 (10); LastAutoConnection 207 (5); LastConnection 73 (7); EndTime 1 (1) |
| Cookie | 14,967 | 10 | | LastAccessTime 13,426; CreationTime 10,405; Expiry 9,410 (10 each) |
| SearchedItem | 13,067 | 12 | | TimeStamp 3,083 (12) |
| Chat | 9,789 | 14 | | StartTime 9,315; LastActivity 9,171 (14) |
| Password | 8,595 | 10 | | DateCreated 6,334; DateModified 6,327 (5) |
| Notification | 7,881 | 2 | P13, P14 | TimeStamp 7,881 (2) |
| InstalledApplication | 3,507 | 8 | | PurchaseDate 618 (8); InstallDate 6 (1); DeletedDate 5 (1) |
| FileUpload | 3,332 | 4 | | DateUploaded 3,332; DateLastModified 3,332 (4) |
| ApplicationUsage | 2,608 | 3 | P11 P13 P14 | ActiveTime [TimeSpan] 2,565 (3); EndTime 2,537 (2); StartTime 2,521 (2); BackgroundTime [TimeSpan] 2,302 (3); LastUsageDuration [TimeSpan] 2,246 (1); LastLaunch 71 (2) |
| SocialMediaActivity | 2,111 | 5 | | TimeStamp 1,773 (5) |
| ForwardedMessageData | 2,065 | 11 | | TimeCreated 1,130 (3) |
| ChatActivity | 1,052 | 5 | | SystemMessageTimeStamp 302 (2) |
| CalendarEntry | 1,000 | 11 | | StartDate 1,000; EndDate 995 (11); Reminders [multi] 7 (2); RepeatUntil 3 (2) |
| CellTower | 902 | 5 | P03 P04 P11 P13 P14 | TimeStamp 851 (1) |
| UserAccount | 391 | 13 | | TimeCreated 97 (11) |
| PoweringEvent | 128 | 5 | P02 P05 P06 P08 P13 | TimeStamp 128 (5) |
| Journey | 122 | 6 | | StartTime 109 (6); EndTime 8 (3) |
| WebBookmark | 98 | 12 | | TimeStamp 18 (2); LastVisited 12 (1) |
| Voicemail | 76 | 1 | P13 | Timestamp 76; Duration [TimeSpan] 76; LastModified 38 |
| Autofill | 70 | 6 | | TimeStamp 70; LastUsedDate 70 (6) |
| DeviceInfoEntry | 45 | 1 | P14 | TimeStamp 1 |
| Note | 31 | 7 | | Creation 31; Modification 31 (7) |
| User | 12 | 3 | P05 P06 P08 | TimeLastLoggedIn 12 |
| FileDownload | 11 | 4 | | StartTime 11; EndTime 11; LastAccessed 6 (3) |
| Recording | 7 | 1 | P13 | TimeStamp 5; Duration [TimeSpan] 5 |
| RemoteServiceSession | 6 | 1 | P14 | DateStarted 6 |
| MobileCard | 4 | 4 | | PurchaseTime 4; ModifyTime 4 |
| CreditCard | 1 | 1 | P12 | ExpirationDate 1; DateLastUsed 1 |

Note the field name `Voicemail.Timestamp` (lower-case s) differs from every other type's `TimeStamp`;
the registry treats them as distinct fields.

Per-phone distribution of the pattern-relevant types (CAT):

| | DeviceEvent | PoweringEvent | AppsUsageLog | NetworkUsage | SearchedItem | VisitedPage | Location | WirelessNetwork | CellTower | DeviceConnectivity | ActivitySensorDataSample | Notification | LogEntry |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P01 | | | | | 71 | | 1,220 | | | | | | |
| P02 | 2 | 1 | | 20,961 | 752 | 4,129 | 206 | 284 | | 5 | | | |
| P03 | 208 | | | | 777 | 838 | 617 | 4 | 8 | 1,215 | | | |
| P04 | 21,718 | | | | 560 | 1,703 | 42,607 | 24,390 | 860 | 1,630 | | | 11,809 |
| P05 | 1 | 1 | | | | 9,658 | 110 | 667 | | | | | |
| P06 | 2 | 2 | | 5,181 | 19 | 6,936 | 31 | 8 | | | | | |
| P07 | 1 | | | 9,357 | 32 | 4,255 | 477 | 1 | | 4 | | | |
| P08 | 2 | 2 | | 17,532 | 71 | 4,282 | 17 | 14 | | 1 | | | |
| P09 | | | | | 13 | 213 | 7 | 2 | | | | | |
| P10 | | | | | | | | | | | | | |
| P11 | 8,928 | | 8,960 | | 8,781 | 55,590 | 1,482 | 26 | 10 | 1,228 | 113,290 | | 4,502 |
| P12 | | | | | 371 | 1,789 | 104 | 6 | | | | | |
| P13 | 53,322 | 122 | 17,486 | | 101 | 2,139 | 3,551 | 56 | 7 | 1,338 | 173,851 | 4,792 | 6,162 |
| P14 | 50,999 | | 41,277 | | 1,519 | 9,269 | 13,355 | 111 | 17 | 187,649 | 137,516 | 3,089 | 3,469 |

Consequence: pattern of life is rich on P04, P11, P13 and P14, thin on most others, and on P10 rests on
messages and calls only. Every view states which signal families a phone carries (section 5).

### 2.2 Named sets relevant to pattern of life (CAT, union over 14 phones; phones in brackets)

| Set | Values |
|---|---|
| DeviceEventTypes | AirplaneMode (4), AudioInputRoute (2), AudioOutputRoute (4), CameraState (5), DeviceLockStatus (5), DevicePluginStatus (5), DisplayOnOff (5), DoNotDisturbState (2), FlashlightState (5), MotionState (1), NotificationAction (2), OrientationChange (5), PowerEvent (6), TextInput (2), WifiState (5), Wipe (3) |
| PowerEventType / PowerElementType | On (5), Off (1) / Device (5) |
| NetworkUsageMode | Background (4), Foreground (4) |
| NWConnectionType | Cellular (4), Wireless (5), Unknown (1) |
| AppAction | Launch (1), Close (1) |
| ApplicationOperationMode | Foreground (8), Background (5), Unknown (3) |
| ModelDirections | Incoming (14), Outgoing (14), Unknown (3) |
| TelephonyCallStatus | Established (14), Missed (14), NotEstablishedUnknownReason (14), Rejected (13), Canceled (8), Unknown (6), BusyLine (2), Voicemail (1) |
| CallType | Incoming, Outgoing, Missed, Cancelled (3 each) |
| MessageStatus | Read (14), Sent (14), Unread (14), Delivered (11), Unsent (10), Default (9), Opened (2) |
| PartyRole | From (14), To (14), General (7) |
| Platform | Mobile (13), Web (7), Unknown (2) |
| InstantMessageType | AppMessage (14), Sms (14), Mms (11), IMessage (6) |
| ConnectivityMethod / ConnectivityNature | Bluetooth (8), WiFi (1) / Paired (8), Detected (5), Connected (4), Disconnected (4) |
| DeviceType (connectivity) | Headset (5), Phone (3), Unknown (1) |
| DeviceLocationAffiliation | Extracted (5), Synced (3), Unknown (7) |
| AccountLocationAffiliation | Extracted (4), Unknown (8) |
| LocationOrigin | Device (1), Unknown (2) |
| SearchItemOrigin | Default (2), Device (1), Unknown (10) |
| SocialMediaActivityType | Post (5), CheckIn (3), Comment (3), Update (3) |
| MeasuredVariableType / MeasurementUnits | Steps, DistanceTraveled, FlightsClimbed, Speed (3 each), EnergyBurned (2), HeartRate, Height, Mass (1 each) / Steps, Meters, Floors, MeterPerSecond (3), KiloCalories (2), BPM, Centimeters, Kilograms (1) |
| SampleSourceType | Unknown (1) |
| CellTowerType | GSM (1) |
| JourneyType | Route (2) |
| UserType | Owner (3) |

`DeviceEvent.Value` is a String, not a named set (CAT: `Value [field] String 126,295, 10 phones`), so its
values are not in CAT. In the three local samples it has exactly two distinct values: `Power on` with
EventType PowerEvent (C3: 2, C8: 2) and `Factory Reset` with EventType Wipe (C8: 1) (POL-S). The values of
the other fourteen EventTypes exist only on the server phones and are measured by M1 (section 13) before
the mapping rows that depend on them are written.

`UserMapping` (`DecodingSourceOptions`) has exactly one value in the three samples: `Decoding`, on every
type that carries it (POL-S). Its full value set across the 14 phones is measured by M2.

### 2.3 What each timestamp means

Each (type, field) gets a **time semantics** value from a fixed vocabulary. The vocabulary is part of the
timestamp-meaning mapping kind (spec 02 format) and is shown beside every event in the product.

| Semantics | Meaning | Usable as |
|---|---|---|
| `event_instant` | the moment the recorded thing happened | point event |
| `interval_start` / `interval_end` | bounds of something that lasted | interval |
| `aggregate_bucket` | bounds of a counting period; the activity happened somewhere inside it | interval of low time resolution |
| `latest_of_many` | the most recent of possibly several occurrences; earlier ones are lost | point event that proves one occurrence, never absence before it |
| `first_record` | creation of a record (contact, cookie, account) | point event, often account-level |
| `last_modified` | latest modification | as `latest_of_many` |
| `service_observed` | last time a service saw a place or item (carved or cached locations) | point event of presence, weak |
| `counterpart_action` | an action by another person, recorded on this phone (a recipient read the owner's message) | event of the counterpart, not the owner |
| `scheduled` | a planned time (calendar, reminder) | plan, not activity |
| `expiry` | an end of validity (cookie, card) | never an activity |
| `duration` | a TimeSpan, not an instant | length of an interval |
| `unknown` | not established | shown, never used to contradict or support a claim |

Established-by vocabulary: `field_name` (the meaning is read from the field's own name and is
unambiguous, e.g. `Expiry`), `corpus_measured` (a measurement in section 13 settles it), `vendor_doc`
(Cellebrite documentation located and cited), `not_established`. A row whose basis is
`not_established` has semantics `unknown`.

Initial content of the timestamp-meaning mapping (draft for review; nothing is applied until reviewed,
per plan 6.5):

| Type.Field | Semantics | Basis now | How it is established |
|---|---|---|---|
| InstantMessage.TimeStamp | event_instant (sent or received time per direction) | field_name | M2 cross-tab of Folder, Status, Platform and owner party |
| InstantMessage.DateDelivered | event_instant (delivered to the recipient's device) | field_name | |
| InstantMessage.DateDeleted | event_instant | field_name | 1 value in corpus |
| InstantMessage.SelfDestructDuration | duration | field_name | |
| Party.DateRead | event_instant if the party is the owner; `counterpart_action` otherwise | corpus_measured: POL-P shows DateRead only on `To` parties of InstantMessage, 27 with IsPhoneOwner True and 31 with False (C8) | M6 on all phones |
| Party.DatePlayed | as DateRead | not_established | M6 |
| Party.DateDelivered | event_instant, delivery to that party's device; `counterpart_action` for non-owners | POL-P: on `To` parties, IsPhoneOwner False (C8: 18) | M6 |
| Call.TimeStamp | event_instant (start of the call attempt) | field_name | |
| Call.Duration | duration | field_name | |
| DeviceEvent.StartTime / EndTime | interval_start / interval_end; event_instant where EndTime is absent | field_name | M1 (EndTime present on 68,441 of 134,342 starts, 5 phones) |
| PoweringEvent.TimeStamp | event_instant | field_name | |
| AppsUsageLog.StartTime / EndTime | interval_start / interval_end | field_name | M4 duration distribution |
| ApplicationUsage.StartTime / EndTime | aggregate_bucket | not_established | M4: if EndTime minus StartTime is a constant period, the record is a usage summary |
| ApplicationUsage.LastLaunch | latest_of_many | field_name | |
| ApplicationUsage.ActiveTime / BackgroundTime / LastUsageDuration | duration | field_name | |
| NetworkUsage.DateStarted / DateEnded | aggregate_bucket | not_established | M4 bucket-width histogram |
| ActivitySensorData.From / To | aggregate_bucket | field_name | M4, M9 |
| ActivitySensorDataSample.DateSampled / DateEnded | interval_start / interval_end (event_instant when DateEnded absent) | field_name | M9 |
| VisitedPage.LastVisited | latest_of_many | plan 11.2 item 2; corroborated by VisitCount (Int32, 34,120 values) | M7: share with VisitCount > 1 is the share whose earlier visits are lost |
| WebBookmark.TimeStamp / LastVisited | first_record / latest_of_many | field_name | |
| Cookie.CreationTime / LastAccessTime / Expiry | first_record / latest_of_many / expiry | field_name; plan 11.2 item 2 says LastAccessTime is not a page view | |
| SearchedItem.TimeStamp | event_instant | field_name; present on 3,083 of 13,067 records | M2 by Source |
| Location.TimeStamp / EndTime | event_instant or interval; `service_observed` for carved or cached sources | not_established per source | M5 by Source, Type, Category |
| Coordinate (no time of its own) | inherits the parent's time | POL-N: Coordinate nested under Location.Position and WirelessNetwork.Position | |
| WirelessNetwork.TimeStamp | not_established | 25,356 values on 10 phones; P04 alone has 24,390 records | M5 by Source (`Wifi Log Data`, `Native Wifi`, `WiFi` seen in POL-S) |
| WirelessNetwork.LastConnection / LastAutoConnection | latest_of_many | field_name | |
| CellTower.TimeStamp | not_established | 851 values, 1 phone | M5 |
| DeviceConnectivity.StartTime | event_instant of the connectivity change named by ConnectivityNature | not_established for `Paired` (pairing time or last seen) | M4 per ConnectivityNature |
| Notification.TimeStamp | event_instant (posted) | field_name | |
| LogEntry.TimeStamp / EndTime | event_instant / interval_end | field_name | |
| Email.TimeStamp | event_instant (sent or received per folder) | field_name | M2 Folder values |
| Chat.StartTime / LastActivity | first_record / latest_of_many | field_name | derived from messages; not used as activity |
| Contact.TimeCreated / TimeModified | first_record / last_modified | field_name | |
| Password.DateCreated / DateModified | first_record / last_modified | field_name | |
| InstalledApplication.InstallDate / DeletedDate | event_instant | field_name | 6 and 5 values on 1 phone |
| InstalledApplication.PurchaseDate | first_record (account-level purchase) | field_name | |
| FileUpload.DateUploaded / DateLastModified | event_instant / last_modified | field_name | |
| FileDownload.StartTime / EndTime / LastAccessed | interval_start / interval_end / latest_of_many | field_name | |
| SocialMediaActivity.TimeStamp | event_instant (post, comment, check-in) | field_name | |
| ForwardedMessageData.TimeCreated | time of the original message, not of forwarding | field_name | |
| ChatActivity.SystemMessageTimeStamp | event_instant | field_name | |
| CalendarEntry.StartDate / EndDate / Reminders / RepeatUntil | scheduled | field_name | |
| UserAccount.TimeCreated | first_record (account) | field_name | |
| User.TimeLastLoggedIn | latest_of_many | field_name | |
| Autofill.TimeStamp / LastUsedDate | first_record / latest_of_many | field_name | |
| Note.Creation / Modification | first_record / last_modified | field_name | |
| Voicemail.Timestamp / LastModified / Duration | event_instant / last_modified / duration | field_name | |
| Recording.TimeStamp / Duration | event_instant / duration | field_name | |
| RemoteServiceSession.DateStarted | event_instant (a session on another device) | field_name | |
| Journey.StartTime / EndTime | interval_start / interval_end | field_name | |
| MobileCard.PurchaseTime / ModifyTime | first_record / last_modified | field_name | |
| CreditCard.ExpirationDate / DateLastUsed | expiry / latest_of_many | field_name | |
| DeviceInfoEntry.TimeStamp | unknown | not_established | 1 value |
| Tagged file system times (CoreFileSystemFileSystemNode CreationTime, ModifyTime, LastAccessTime, ChangeTime, DeletedTime) | first_record / last_modified / latest_of_many / last_modified / event_instant | HDR shows these item names on tagged files | used for media place observations (6.2), not as activity |

**Offset.** In the three samples every TimeStamp value in the pattern types has an explicit offset, with
two exceptions: `Location.TimeStamp` (C3: 21 values, C8: 6 values) and `CalendarEntry.RepeatUntil` (C3: 1)
have none (POL-S, shape `9999-99-99T99:99:99.999`). C3's 21 offset-less Location times equal its 21
Location records with Category `Media Locations`. An offset-less value has `offset_status = absent`
(time spec); it is placed on the timeline only after a zone is resolved by the time spec, and every
derived event from it carries the flag `offset_absent`. It never contradicts a claim by itself (9.4).

---

## 3. Activity-strength mapping

### 3.1 Classes and strength

Class is computed from (type, field, value, context) by the reviewed activity-strength mapping. Default
when no reviewed row matches: `unknown`. The class basis is recorded on every event: `reviewed_mapping`
(with mapping version id) or `default_unknown`. Nobody sets a class on an event by hand (plan 11.2 item 1;
standing decision 5).

| Class | Definition (plan 11.2) |
|---|---|
| `interaction` | needs a person at the device |
| `device_state` | a change of device state that can happen without a person |
| `passive` | recorded without any action by the owner: incoming items, background activity, scans, sync |
| `unknown` | not established |

Two qualifiers sit beside the class. They are part of the same mapping rows:

- `actor`: `owner`, `counterpart`, `other_device`, `account`, `unknown`. An interaction by a counterpart
  (a recipient reading the owner's message) is evidence about the counterpart, not the owner, and is
  filed under the counterpart's identity where the identity spec resolves it.
- `physical`: true when the record shows the device (or a paired wearable) physically moved or was
  carried (motion state, orientation change, step counts). A physical signal is not an interaction, but a
  claim of being asleep in bed is weakened by the phone walking (9.4).

**Strength** is computed per event from class, actor, attribution flags and time quality, in this order:

| Strength | Rule |
|---|---|
| `strong` | class `interaction`, actor `owner`, no attribution flag from 4.3 group A, `offset_status = explicit`, semantics `event_instant` or `interval_*`, `deleted_state = Intact` |
| `moderate` | class `interaction` with exactly one group-B flag, or semantics `latest_of_many`; or class `device_state`, actor `owner`, no group-A flag |
| `weak` | class `interaction` with a group-A flag; or `device_state` with any flag; or `aggregate_bucket` semantics; or `physical` true with class `passive` |
| `none` | class `passive` without `physical`, or class `unknown` |

Strength is a display and ordering aid and an input to the statement check (9.4). It is never stored as an
editable column; it is recomputed from its inputs whenever a mapping version changes.

### 3.2 Initial mapping rows (draft for review)

Match columns: type, field (the time field the event is built from), value predicate on named fields,
context predicate. "M1 pending" means the row's value list is completed only after measurement M1; until
then only the rows whose values are known from POL-S or from a named set apply, and every other value of
that EventType falls to `unknown`.

#### DeviceEvent (EventType is a named set; Value is free String)

| EventType | Value predicate | Class | Actor | Physical | Reasoning | Would change the class |
|---|---|---|---|---|---|---|
| DeviceLockStatus | value denotes unlock (M1 pending) | interaction | owner | | unlocking needs a passcode, biometric or a deliberate gesture | M1 shows unlock values emitted by trusted-device or on-body auto-unlock without a person (Android Smart Lock); then split by Source |
| DeviceLockStatus | value denotes lock (M1 pending) | device_state | owner | | auto-lock on timeout needs no person | |
| DisplayOnOff | any | device_state | owner | | a notification lights the screen (plan 11.2) | M1 shows a value that distinguishes user wake from notification wake |
| TextInput | any (Value never displayed; see 12.1 rule 4 of the plan) | interaction | owner | | typing needs a person | M1 shows TextInput emitted by dictation or automation sources |
| CameraState | value denotes camera on (M1 pending) | interaction | owner | | foreground camera use needs a person | a source shows background camera access |
| CameraState | value denotes off | device_state | owner | | closing follows use but can be a timeout | |
| FlashlightState | on | interaction | owner | | switched by a person | apps that drive the torch (alarms) seen in Source |
| FlashlightState | off | device_state | owner | | | |
| OrientationChange | any | device_state | owner | true | rotation needs movement, which a vehicle or bag can cause | |
| MotionState | any (M1 pending; P14 only) | passive | owner | true when value is not stationary | motion coprocessor classification needs no interaction | |
| AirplaneMode | any | device_state | owner | | plan 11.2 lists it as device state; toggling is normally manual, so the event is shown with moderate strength | M1 or a source showing scheduled or MDM toggles; or Neil ruling it interaction |
| DoNotDisturbState | any | device_state | owner | | schedules and focus modes switch it | |
| AudioInputRoute / AudioOutputRoute | any | device_state | owner | | route changes on headset or car connection | |
| DevicePluginStatus | any | device_state | owner | | plugging in usually needs a person, but wireless pads and docks do not | M1 values separate cable from wireless |
| PowerEvent | `Power on` (POL-S) and other values (M1 pending) | device_state | owner | | power cycles occur on low battery and updates | |
| WifiState | any | device_state | owner | | radios toggle by automation and location rules | |
| NotificationAction | value denotes user action (opened, dismissed, replied) (M1 pending) | interaction | owner | | acting on a notification needs a person | |
| NotificationAction | value denotes posted or received (M1 pending) | passive | owner | | | |
| Wipe | `Factory Reset` (POL-S) and others | device_state | unknown | | a reset can be local or remote; plan 12 approach 3 uses it | Source shows a local, user-initiated reset |

#### Power, network and app use

| Type | Predicate | Class | Actor | Reasoning | Would change |
|---|---|---|---|---|---|
| PoweringEvent | Event On / Off | device_state | owner | power events are not proof of a person | |
| NetworkUsage | UsageMode Foreground | interaction | owner | plan 11.2: foreground app use; strength is `weak` because the semantics are `aggregate_bucket` | M4 shows buckets narrow enough (under 15 minutes) to move to `moderate` |
| NetworkUsage | UsageMode Background | passive | owner | background traffic needs no person | |
| AppsUsageLog | Action Launch | interaction | owner | launching an app is a user action in the common case | M2 shows Launch emitted for system-started apps (Source and Identifier patterns) |
| AppsUsageLog | Action Close | device_state | owner | apps close on timeout or system kill | |
| AppsUsageLog | Action absent (26,446 of 67,723 records, 2 phones) | unknown | owner | the record kind depends on Source | M2 by Source; reviewer adds rows per Source |
| ApplicationUsage | ActiveTime > 0 | interaction | owner | an app was in use in the period; `aggregate_bucket`, so `weak` | |
| InstalledApplication.InstallDate / DeletedDate | any | interaction | owner | install and removal are normally user actions | restore from backup or management (Source evidence) |
| InstalledApplication.PurchaseDate | any | passive | account | account purchase, possibly on another device | |

#### Communications

Direction for InstantMessage: there is no Direction field on InstantMessage (CAT lists none). Outgoing is
determined in this order: the From party has `IsPhoneOwner = True`; else Folder `Sent` (POL-S: Folder
values Inbox, Sent, Draft); else Status `Sent` or `Unsent`. The rule used is recorded on the event.

| Type and field | Predicate | Class | Actor | Reasoning | Would change |
|---|---|---|---|---|---|
| InstantMessage.TimeStamp | outgoing, Platform Mobile or Unknown | interaction | owner | composing and sending needs a person | scheduled send or auto-reply evidence |
| InstantMessage.TimeStamp | outgoing, Platform Web | interaction | other_device | sent from a web client on the same account, not from this phone (Platform enum: Mobile, Web, Unknown) | |
| InstantMessage.TimeStamp | incoming | passive | owner | arrives without action | |
| InstantMessage.TimeStamp | Folder Draft | interaction | owner | `unknown` time semantics until M2 settles whether it is creation or last edit | |
| InstantMessage.DateDelivered | any | passive | owner | network delivery | |
| Party.DateRead / DatePlayed | party IsPhoneOwner True | interaction | owner | reading or playing by the owner; read receipts can sync from the owner's other devices, so flag `account_level_sync` (group B) applies on apps known to sync read state | M6 |
| Party.DateRead / DatePlayed | party IsPhoneOwner False | interaction | counterpart | the recipient read the owner's message on their own device | |
| Party.DateDelivered | any | passive | counterpart when non-owner | | |
| Call.TimeStamp | Direction Outgoing, any Status | interaction | owner | dialling needs a person, including Canceled, BusyLine, NotEstablishedUnknownReason | automated redial or app call-backs identified by Source |
| Call.TimeStamp | Incoming, Established | interaction | owner | answering needs a person; auto-answer exists but is rare | Source shows auto-answer |
| Call.TimeStamp | Incoming, Rejected | interaction | owner | declining is usually manual, but focus modes reject automatically; shown `moderate` | |
| Call.TimeStamp | Incoming, Missed, Voicemail, Unknown, NotEstablishedUnknownReason | passive | owner | no action needed | |
| Email.TimeStamp | sent folder (M2 pending) | interaction | owner | | |
| Email.TimeStamp | other folders | passive | owner | | |
| Notification.TimeStamp | any | passive | owner | posting needs no person | |
| SocialMediaActivity.TimeStamp | Post, Comment, Update, CheckIn | interaction | account | could be posted from any device on the account | IsFromActivityLog values (Boolean, 993 values) or Platform show the device |
| ChatActivity.SystemMessageTimeStamp | any | unknown | unknown | whether the owner performed the action is not established | |

Call direction and status pairs present locally (POL-S): Incoming with Established, Missed, Rejected,
NotEstablishedUnknownReason, Unknown; Outgoing with Established, Canceled, BusyLine,
NotEstablishedUnknownReason, Missed, Rejected, Unknown; both with no Status (C8: 5, C9: 15).
Outgoing Missed and Outgoing Rejected exist (C3: 16 and 27; C8: 5; C9: 19), so status names describe the
other party's side for outgoing calls; the class rule above keys on direction first for that reason.

#### Web, search, typing and accounts

| Type and field | Class | Actor | Reasoning |
|---|---|---|---|
| SearchedItem.TimeStamp | interaction | owner; `account` when Source is a synced account history (M2) | typing a search needs a person |
| VisitedPage.LastVisited | interaction | owner | strength `moderate` because `latest_of_many`; a restored tab can reload a page, flagged by M7 if Source shows it |
| WebBookmark, Autofill.LastUsedDate, Note.Creation/Modification, Contact.TimeCreated/TimeModified, Password.DateCreated/DateModified | interaction | account | browser and account sync can create these from another device |
| Cookie.CreationTime / LastAccessTime | passive | owner | pages and apps set and read cookies without a person (plan 11.2) |
| FileDownload.StartTime | interaction | owner | |
| FileUpload.DateUploaded | unknown | unknown | apps upload in the background (backups) |
| Recording.TimeStamp | interaction | owner | |
| Voicemail.Timestamp | passive | owner | |
| User.TimeLastLoggedIn | interaction | owner | `latest_of_many` |
| RemoteServiceSession.DateStarted | interaction | other_device | a session on another device |
| LogEntry.TimeStamp | unknown | unknown | system log lines; content-dependent; reviewer adds rows per Source and Application |

#### Connectivity, places and sensors

| Type | Predicate | Class | Actor | Physical | Reasoning |
|---|---|---|---|---|---|
| DeviceConnectivity | Connected, Disconnected | device_state | owner | | headsets and cars connect automatically |
| DeviceConnectivity | Detected | passive | owner | | scan result |
| DeviceConnectivity | Paired | unknown | owner | | whether StartTime is the pairing moment is not established (M4) |
| WirelessNetwork.TimeStamp | any | passive | owner | | scan or log entry |
| WirelessNetwork.LastConnection | any | device_state | owner | | `latest_of_many` |
| WirelessNetwork.LastAutoConnection | any | passive | owner | | automatic |
| CellTower.TimeStamp | any | passive | owner | | registration |
| Location.TimeStamp | Type Searched (POL-S: C3 7, C8 4, C9 6) | interaction | owner | | a searched place, which is not a presence (6.1) |
| Location.TimeStamp | other | passive | owner or per 4.2 | | presence evidence, handled in section 6 |
| ActivitySensorData | any | passive | owner, or `other_device` when the source is a wearable (M9) | true when steps or distance > 0 | |
| ActivitySensorDataSample | any | passive | as above | true when the measured variable is steps, distance, flights or speed and Quantity > 0 | |
| Journey | any | unknown | unknown | | 122 records; meaning per Source not established |

### 3.3 Types never in the activity lanes

`scheduled` and `expiry` timestamps (CalendarEntry dates, Reminders, RepeatUntil, Cookie.Expiry,
CreditCard.ExpirationDate), ForwardedMessageData.TimeCreated, Chat.StartTime/LastActivity,
UserAccount.TimeCreated, MobileCard times and DeviceInfoEntry.TimeStamp stay on the generic timeline
(plan 6.4) and never enter the activity tables. Calendar entries with a location become planned place
observations (6.2).

### 3.4 Match semantics

1. Rows match on (type, time field) exactly, then on value predicates (equality on named-set values;
   equality or an explicit list for String values; numeric comparisons for Int and Double).
2. More specific rows win: a row with more predicates beats one with fewer. Two equally specific rows
   that both match is a mapping validation error, rejected at review time, never resolved at run time.
3. An event matched by no row is `unknown` with basis `default_unknown`.
4. Every mapping version is applied to all captured data without re-ingest (plan 6.5). Applying it
   rewrites the class columns of the derived activity table (7.2) for the affected (type, field) keys and
   bumps `pol_projection_state.activity_mapping_version`.

---

## 4. Attribution

### 4.1 Inputs

| Input | Values measured | Source |
|---|---|---|
| `UserMapping` (DecodingSourceOptions) | `Decoding` only, in C3, C8, C9 | POL-S |
| `DeviceLocationAffiliation` | Extracted (5 phones), Synced (3), Unknown (7); present on 33,877 Location records on 8 phones | CAT |
| `AccountLocationAffiliation` | Extracted (4), Unknown (8) | CAT |
| `LocationOrigin` | Device (1), Unknown (2); 14,576 values on 3 phones | CAT |
| `InstantMessage.Platform` | Mobile, Web, Unknown | CAT |
| `Source` (app or database name) | present on most types; e.g. Location Sources `Google Maps`, `Facebook`, `WhatsApp` (POL-S) | |
| `Account` | String on Location (721), SearchedItem (106), Journey, SocialMediaActivity | CAT |
| `deleted_state` | Intact, Deleted, Unknown (POL-S) | |
| `decoding_confidence` | `High` on every pattern record in the samples | POL-S |
| ActivitySensorData `DeviceName`, `SourceDeviceType` | DeviceName String on 1 phone; SourceDeviceType Unknown | CAT |

The meaning of `UserMapping` values other than `Decoding`, and of `Synced` versus `Extracted`, is not
documented in anything read for this file. v1 treated UserMapping as a multi-user profile marker in a
comment only (`ingestion/scripts/cellebrite/neo4j_writer.py:451-458` on `origin/main`). M2 measures the full value set and
cross-tabulates it with Source.

### 4.2 Rules

Each derived event and place observation gets `attribution_flags text[]`. Flags are computed by the
attribution mapping kind (spec 02 format), initial content:

| Flag | Group | Condition | Displayed as (UI copy) |
|---|---|---|---|
| `synced_from_account` | A | DeviceLocationAffiliation = Synced | "Synced from the account. May come from another device." |
| `affiliation_unknown` | B | DeviceLocationAffiliation = Unknown, or absent on a Location from a source known to sync (Google Maps timeline, M5) | "Not known whether this device recorded it." |
| `other_device_platform` | A | InstantMessage Platform = Web | "Sent from a web or desktop session." |
| `account_level` | B | actor `account` in the activity mapping | "Recorded on the account. The device that did it is not shown." |
| `user_mapping_other` | A | UserMapping present and not `Decoding` (pending M2 meaning) | "Linked to a different device user or source." |
| `wearable` | A | sensor record from a non-phone device (M9) | "Recorded by a paired wearable." |
| `deleted_record` | B | deleted_state = Deleted | "Recovered deleted record." |
| `deleted_state_unknown` | none (shown only) | deleted_state = Unknown | |
| `low_decoding_confidence` | B | decoding_confidence not High | "Decoded with lower confidence." |
| `offset_absent` | A for statement checks | time offset absent | "Time zone not stated in the source." |
| `latest_only` | B | semantics `latest_of_many` | "Latest occurrence only. Earlier ones are not kept." |
| `bucketed` | B | semantics `aggregate_bucket` | "Happened somewhere in this period." |
| `counterpart` | none | actor `counterpart` | "Action by the other person." |

Group A flags demote an `interaction` event to `weak`; one group-B flag demotes it to `moderate`; two or
more group-B flags demote it to `weak` (3.1).

**Owner.** "Owner" means the owner identity of the extraction as resolved by the identity spec. For a
person-level view, an event counts for the person only if its extraction is linked to the person by a
reviewed identity link. Two extractions of one device (P03 and P10 may be one) are both included and
their events deduplicated by (record source identity, instant, type, value) with the duplicate shown,
never dropped (plan 10.4 item 1).

---

## 5. Data availability bands

### 5.1 Purpose

Plan 11.2 item 4: an empty period must read as "no data" or as "data present, no interaction", never
ambiguously. This section defines how that is decided.

### 5.2 Streams and families

- A **stream** is (extraction, type, Source value). For DeviceEvent the stream is (extraction,
  DeviceEvent, Source, EventType), because one database records several event kinds at different rates.
- A **family** groups streams for display: `device_events`, `power`, `app_usage`, `network_usage`,
  `messages`, `calls`, `web`, `search`, `locations`, `wifi`, `cell`, `connectivity`, `sensors`,
  `notifications`, `logs`, `email`, `social`.
- A stream is **interaction-capable** on an extraction if it contains at least one event of class
  `interaction` with actor `owner` anywhere in the extraction. Computed, per mapping version.

### 5.3 Algorithm (per extraction, recomputed when captures or mappings change)

Inputs: the derived activity events of the extraction (7.2), the report header
(`DeviceInfoExtractionStartDateTime`, `DeviceInfoExtractionEndDateTime` from HDR), the production's own
statement of selection where present (`IsSelectiveExtraction`, `IsPartialData`, chosen types and ranges,
plan 6.5), and the stream gap thresholds.

1. **Extraction edge.** `extraction_start` = DeviceInfoExtractionStartDateTime. Every instant after it is
   band `after_extraction`. Events stamped after it are kept and flagged `after_extraction_time`
   (clock or zone anomaly), and counted in the Extraction profile.
2. **Selection.** If the production states selected date ranges, instants outside them are
   `outside_selection` for the selected types. If it states types were not selected, those families are
   `not_selected` for the whole span. If the production says nothing, no such band exists and the
   profile says "The production does not state a selection."
3. **Per stream, first and last.** `first`, `last` over events with semantics `event_instant`,
   `interval_*` or `aggregate_bucket`. `latest_of_many`, `first_record`, `last_modified`,
   `scheduled`, `expiry` do not extend coverage, because a latest-only time says nothing about the
   period before it.
4. **Per stream, observed segments.** Sort instants (intervals contribute both ends and are covered
   throughout). Merge consecutive instants whose gap is at most `max_gap(stream)`. Each merged run is an
   observed segment. `max_gap(stream)` comes from the stream-gap table in the attribution/meaning
   mapping (reviewed data), with provisional defaults: device events 2 h; connectivity 2 h; sensors 1 h;
   network usage the bucket width plus 10 percent; messages, calls, web, search, email, social and
   notifications are **never** used to establish observation (their absence is the very thing being
   asked about, and their rate follows the person), so they have no observed segments. The defaults are
   replaced from measurement M4 before unit U4 lands (13).
5. **Power.** From PoweringEvent (Event Off then On) and DeviceEvent PowerEvent values that denote off and
   on (M1): `powered_off` from an off event to the next on event. An on event with no preceding off event
   inside the 24 h before it produces `powered_off_inferred` from the end of the last observed segment of
   any stream before it to the on event, flagged as inferred. P02, P05, P06, P08 carry only `On`
   (CAT: PowerEventType On on 5 phones, Off on 1), so on those phones every off period is inferred.
6. **Hour cells.** For each local hour H (zone per 8.0) and each extraction:
   - `after_extraction`, `outside_selection` or `powered_off` if the hour is wholly inside such a band;
   - `interaction` if any owner interaction event (any strength other than `none`) has an instant in H;
   - `data_no_interaction` if at least one interaction-capable stream has an observed segment covering
     at least 50 minutes of H, or any non-interaction-capable stream with observation covers at least
     50 minutes of H and the hour has no interaction (labelled with which streams);
   - `no_data` otherwise.
   The 50-minute threshold avoids calling an hour observed on the strength of one stray event at its
   edge. Reverse if M4 shows observed segments are typically shorter than an hour on the rich phones.
7. **Window state** (for statement checks and the day view): the window is split at band boundaries;
   each piece carries its band and the list of streams observing it.

Display rule (UI copy): "No data" when nothing on the phone was recording; "Phone recording, no use
seen" when recording streams exist and nothing needed a person; "Switched off"; "Switched off
(inferred)"; "After the extraction"; "Outside what the production selected". Each label opens a list of
the streams behind it with their first and last times.

### 5.4 Stored result

`pol_availability_band` (7.4) holds bands per extraction and family; hour cells are not stored but
derived from bands and the hourly rollup (7.5).

---

## 6. Places

### 6.1 Place observation model

Every place-bearing record becomes one or more rows in `pol_place_observation` (7.3), each an area in
time:

- `lat`, `lon` (WGS84), `radius_m` (the uncertainty radius used in comparisons, or null when unknown),
  `radius_basis` (where the radius came from), `radius_reported` (the source's own figure);
- `start_utc`, `end_utc` (equal for instants), `time_semantics`, `offset_status`;
- `kind`: `presence` (the device or account was there), `searched` (looked up, not visited), `planned`
  (calendar), `declared` (a check-in or post claiming a place), `media` (a photo or video taken there),
  `transaction` (a card payment place, 8.5);
- `presence_basis`: which rule decided `presence`;
- `source_kind`: `gps`, `device_location`, `app_location`, `account_location`, `wifi_position`,
  `wifi_case_anchor`, `cell_reference`, `media_exif`, `calendar`, `checkin`, `journey`, `manual`;
- attribution flags (4.2).

Only `presence` and `media` observations with attribution allowing it enter routine detection and
together-and-apart. `searched`, `planned` and `declared` are shown as such and can support or contradict
a claim about intent or plans, never about presence.

### 6.2 Sources and their radius

| Source | Records (CAT / POL-N) | Radius rule | Basis | Notes |
|---|---|---|---|---|
| Location with Coordinate and GpsHorizontalAccuracy | Coordinate.GpsHorizontalAccuracy 28,656 values on 5 phones; Location.GpsHorizontalAccuracy 12,728 on 1 phone | `radius_m = 2 × accuracy` for comparisons; `radius_reported = accuracy` shown | Android documents horizontal accuracy as a 68 percent radius; doubling gives roughly 95 percent under a normal error model | Reverse if M5 shows accuracy values cluster in a way that indicates a different convention for a Source |
| Location with Precision | Precision String on 52,653 records, 5 phones | per value, reviewed rows (M5 lists the values) | not established | |
| Location with Confidence | Int32 on 24,054 records, 5 phones | not used for radius until M5 shows its scale | not established | shown beside the point |
| Location, no accuracy | the rest | null | | shown as a point with "accuracy not stated"; compared only under an assumed radius chosen in the analysis and printed with every result (8.4) |
| Location Type `Searched` | C3 7, C8 4, C9 6 (POL-S) | as above | | kind `searched` |
| Location Category `Media Locations` | C3 21, C8 30 (POL-S) | null unless the media carries a positioning error | | kind `media`; presence only if the media was taken on this device (camera make and model match the extraction device, or the file is in the device camera folder); else `declared`-like `received_media` and excluded from presence |
| WirelessNetwork with Position Coordinate | C8 3 (POL-N); P04 likely most of its 24,390 (M5) | 2 × accuracy if present; else 100 m | a WiFi position fix | `wifi_position` |
| WiFi BSSID without position | BSSId on 25,484 values, 7 phones | case-derived anchor (6.3) | | never SSID |
| CellTower | 902 records, 5 phones; MCC on 851 (1 phone); MNC, LAC, CID on all 902 | offline reference range (6.4) | | without MCC, a tower key is incomplete and is resolved only if the extraction's home network MCC is known from SIM data, flagged `mcc_inferred` |
| CalendarEntry.Location | 3 values, 1 phone | null; text place resolved only by a person or the offline gazetteer (6.5) | | `planned` |
| SocialMediaActivity CheckIn | CheckIn type on 3 phones | if a Coordinate is nested, as Location; else text only | | `declared` |
| Journey | 122 records | per nested coordinates (M5) | | |
| Card transaction | ledger | a place attached by a person only (8.5) | | `transaction` |

### 6.3 WiFi: case-derived anchors, never a third-party lookup

No offline BSSID position dataset with terms that permit this use was identified. WiGLE and the
commercial providers are lookup services or restricted licences, and a lookup sends the identifier out,
which standing decision 8 forbids. So BSSID positions come from the case itself:

1. For each phone, collect BSSID connection evidence with a time: WirelessNetwork records with BSSId and
   a TimeStamp, LastConnection, or a Position (which gives the position directly), and NetworkUsage
   records on `Wireless` with an SSId (SSID only; used to propose, never to anchor).
2. For each BSSID evidence time t, find GPS observations from the same phone with
   `|t_gps - t| ≤ 5 min` and `radius_m ≤ 100`.
3. Anchor = coordinate-wise median of matched GPS points; `radius_m = max(75, P90 distance of matched
   points from the median + 50)`; `support = number of distinct days`. An anchor needs support ≥ 2
   days, else it is `tentative` and shown but not used for co-location.
4. Anchors are case-scoped and recomputed when captures change. They are the only WiFi positions used.
   A BSSID seen on two phones is co-location evidence by itself (8.4) even without an anchor.

Reverse if Neil adopts a licensed offline BSSID dataset for a case.

### 6.4 Cell towers: offline reference data

- Dataset: OpenCelliD bulk export (`cell_towers.csv.gz`, worldwide or per-country). Download needs an
  API token; exports include only cells observed in the last 18 months and are offered daily (OpenCelliD
  downloads page, read 2026-10-29). Licence: CC BY-SA 4.0 per third-party descriptions (Wikipedia
  infobox; Source Cooperative mirror); the downloads page itself states only that products using the data
  must visibly credit OpenCelliD. Columns as published in third-party schemas: radio, mcc, net, area,
  cell, unit, lon, lat, range, samples, changeable, created, updated, averageSignal. No sector azimuth.
- **The 18-month window matters**: the case extractions date from 2022-11 to 2023-03 (report names).
  Cells decommissioned since are missing from a current export. Each import is retained as a dated
  version and never overwritten, so a case can use the version nearest its period. Coverage of the case's
  towers is reported per import (count of tower keys resolved / total).
- Licence check (Neil): whether holding a CC BY-SA database and deriving case observations from it
  creates a share-alike obligation for anything Loupe outputs. Until that ruling, the dataset is imported
  on the server only, attribution text is shown on every map that uses it, and exports of derived cell
  positions carry the attribution.
- Update cadence: manual import per case need, plus quarterly refresh; each import is a new
  `pol_reference_dataset` row with sha256 and row count. Nothing fetches at query time.
- Lookup key: (radio, mcc, mnc, lac, cid). Radius = `max(range, 300 m)` when `samples ≥ 3`; else
  `max(range, 2,000 m)` and flag `reference_sparse`. A tower not found has no position; it is listed as
  "tower not in reference data" with its key.
- No identifier is sent anywhere. Import is a file the operator places on the server; the importer reads
  it from disk.

### 6.5 Text places and reverse geocoding

Calendar locations, check-in names and transaction places that are text are resolved to coordinates only
by a person (choosing a point and radius on the map, recorded as a decision with an Actor), or by the
offline GeoNames backend of `backend/services/geocoder.py` producing a suggestion a person confirms.
Reverse geocoding for display uses `geocoder.reverse_geocode` only when the configured backend is
in-house: GeoNames (offline) or Nominatim at a host on the deployment's own network. The pattern service
checks this at startup and disables reverse geocoding otherwise, logging why.

---

## 7. Storage

All tables are projections (standing decision 6): rebuildable from captures, mappings, reference datasets
and recorded decisions. Models in `backend/postgres/models/pattern_of_life.py`; migration in the
backend Alembic tree `backend/postgres/alembic/versions/` (where Workspace and dossier migrations
live), unless the capture spec places phone tables in the evidence-engine tree, in which case these
follow it. Every table carries `case_id uuid not null references cases(id) on delete cascade`
(plan 5 lesson 7).

### 7.1 `pol_projection_state`

| Column | Type | Notes |
|---|---|---|
| extraction_id | uuid PK | the capture spec's extraction id |
| case_id | uuid not null | |
| activity_mapping_version | uuid | version applied |
| meaning_mapping_version | uuid | |
| attribution_mapping_version | uuid | |
| cell_dataset_id | uuid null | |
| built_at | timestamptz | |
| event_count | bigint | |
| status | varchar(16) | `building`, `ready`, `stale`, `failed` |
| error | text null | |

### 7.2 `pol_activity_event`

One row per (record, time field) with an activity-relevant semantics (all of 2.3 except section 3.3).

| Column | Type | Notes |
|---|---|---|
| id | bigint identity PK | |
| case_id | uuid not null | |
| extraction_id | uuid not null | |
| record_locator | text not null | capture locator of the record |
| record_type | varchar(64) not null | |
| time_field | varchar(64) not null | |
| instant_utc | timestamptz not null | start for intervals |
| end_utc | timestamptz null | |
| offset_status | varchar(8) not null | `explicit`, `absent` |
| original | text not null | original string |
| time_semantics | varchar(24) not null | 2.3 vocabulary |
| stream_key | varchar(160) not null | type, Source, and EventType for DeviceEvent |
| family | varchar(24) not null | 5.2 |
| value_key | varchar(160) null | the matched predicate values, e.g. `EventType=DisplayOnOff` |
| activity_class | varchar(16) not null | `interaction`, `device_state`, `passive`, `unknown` |
| class_basis | varchar(16) not null | `reviewed_mapping`, `default_unknown` |
| activity_mapping_row | varchar(64) null | the matched row id |
| actor | varchar(16) not null | `owner`, `counterpart`, `other_device`, `account`, `unknown` |
| counterpart_identity_id | uuid null | for counterpart events and communications |
| physical | boolean not null default false | |
| attribution_flags | text[] not null default '{}' | 4.2 |
| deleted_state | varchar(16) null | |
| decoding_confidence | varchar(16) null | |
| source_app | varchar(128) null | the record's Source |

Strength is not a column; it is computed in SQL from the columns above by a view
`pol_activity_event_v` so that a mapping change cannot leave a stale strength behind.

Indexes: `(extraction_id, instant_utc)`; `(case_id, instant_utc)`; partial
`(extraction_id, instant_utc) WHERE activity_class = 'interaction'`; `(case_id, counterpart_identity_id,
instant_utc)`; unique `(extraction_id, record_locator, time_field)` (idempotent rebuild).

### 7.3 `pol_place_observation`

| Column | Type | Notes |
|---|---|---|
| id | bigint identity PK | |
| case_id, extraction_id | uuid not null | extraction null for manual and transaction places |
| record_locator | text null | |
| kind | varchar(16) not null | 6.1 |
| source_kind | varchar(24) not null | 6.1 |
| lat, lon | double precision not null | |
| radius_m | double precision null | |
| radius_reported | double precision null | |
| radius_basis | varchar(32) not null | `gps_accuracy_x2`, `precision_value`, `wifi_anchor`, `cell_reference`, `default_wifi_position`, `manual`, `unknown` |
| start_utc, end_utc | timestamptz not null | |
| offset_status | varchar(8) not null | |
| time_semantics | varchar(24) not null | |
| presence_basis | varchar(32) null | |
| attribution_flags | text[] not null | |
| reference_dataset_id | uuid null | |
| wifi_anchor_id | bigint null | |
| decision_id | uuid null | manual placement |

Indexes: `(extraction_id, start_utc)`, `(case_id, start_utc)`, GiST on
`tstzrange(start_utc, end_utc, '[]')` for window queries. No PostGIS dependency: distances are
haversine in SQL or Python; spatial pre-filtering uses a lat/lon bounding box from radius (adequate at
these volumes, 13,355 Locations on P14). Reverse if a case's place volume makes bounding-box scans slow
(performance test 11).

### 7.4 `pol_availability_band`

`(id, case_id, extraction_id, family, stream_key null, band varchar(24), start_utc, end_utc,
event_count int, inferred boolean, computed_from jsonb)`; band in `observed`, `powered_off`,
`powered_off_inferred`, `after_extraction`, `outside_selection`, `not_selected`. Index
`(extraction_id, start_utc)`.

### 7.5 `pol_hourly_rollup`

`(extraction_id, hour_utc timestamptz, interaction_strong int, interaction_moderate int,
interaction_weak int, device_state int, passive int, physical int, observed_minutes smallint,
band varchar(24) null)`, PK `(extraction_id, hour_utc)`. Stored in UTC hours; a local-zone grid is
assembled by the API from UTC hours (zones with 30 or 45 minute offsets are assembled from the event
table directly; flagged in the response).

### 7.6 Reference data

- `pol_reference_dataset (id uuid PK, kind varchar(8) 'cell', name, licence text, attribution text,
  source_note text, file_sha256 char(64), retrieved_on date, imported_at, row_count bigint,
  imported_by_name, imported_by_email)`.
- `pol_cell_reference (dataset_id, radio varchar(8), mcc int, mnc int, lac bigint, cid bigint, lat, lon,
  range_m int, samples int, updated_at timestamptz)`, PK `(dataset_id, radio, mcc, mnc, lac, cid)`.
- `pol_wifi_anchor (id, case_id, bssid_norm varchar(17), lat, lon, radius_m, support_days int,
  support_points int, status varchar(12) 'anchored'|'tentative', computed_at)`, unique
  `(case_id, bssid_norm)`. BSSIDs are normalised to lower-case colon form.

### 7.7 Routine and co-location results

- `pol_place_cluster (id, case_id, subject_key varchar(80), lat, lon, radius_m, stay_count, day_count,
  profile jsonb /* 7x24 dwell minutes */, label text null, label_decision_id uuid null, computed_with jsonb)`.
- `pol_stay (id, case_id, extraction_id, cluster_id null, lat, lon, radius_m, start_utc, end_utc,
  observation_count)`.
- `pol_colocation_run (id uuid, case_id, subjects jsonb, window, params jsonb, status, started_at,
  finished_at, counts jsonb, requested_by)` and `pol_colocation_item (run_id, a_observation_id,
  b_observation_id, verdict varchar(12), distance_m, radii_sum_m, dt_s, basis varchar(16))`.

### 7.8 Claims (section 9)

- `pol_claim`: `id uuid PK, case_id, version int, status varchar(12) 'draft'|'confirmed'|'withdrawn',
  kind varchar(24), subject jsonb, window_start timestamptz, window_end timestamptz, window_zone
  varchar(64), window_text text, place jsonb null, activity jsonb null, counterpart jsonb null, origin
  varchar(12) 'manual'|'ai_draft', source_anchor jsonb null /* evidence_file_id + anchor, or message
  locator */, ai_output_id uuid null, created_by_user_id, confirmed_by_user_id null, confirmed_at null,
  created_at, updated_at`. Check: `status = 'confirmed'` requires `confirmed_by_user_id` and non-null
  window.
- `pol_claim_revision`: immutable copy per version (same shape as Workspace revisions).
- `pol_claim_evaluation`: `id uuid, claim_id, claim_version, evaluated_at, inputs jsonb /* extraction ids,
  mapping versions, dataset ids, params */, inputs_fingerprint char(64), outcome varchar(24), summary
  jsonb, counts jsonb`.
- `pol_claim_evaluation_item`: `evaluation_id, ordinal, role varchar(16) 'contradicting'|'supporting'|
  'context'|'gap', ref_kind varchar(16) 'activity_event'|'place_observation'|'band'|'colocation'|
  'transaction', ref_id text, strength varchar(8), reason_code varchar(48), explanation text`.

---

## 8. Views

### 8.0 Time zone in every view

Default display zone: the device zone from the report's time zone configuration (C9:
`_America/New_York`; C3: `_Africa/Abidjan` with convert-to-UTC on, per `c3.json`/`c9.json` tz entries),
resolved by the time spec. UTC one click away. 12-hour time with date always shown (plan 10.2). Every
item opens to its original string, offset status, field name and time semantics. Days are local-zone
days; a day containing a DST change has 23 or 25 hours and the grid shows that.

### 8.1 Day view

- Subject: one extraction, or one person (all extractions linked to the person, 4.2), one local date.
- Lanes, top to bottom: **availability** strip (5.3 hour states, per extraction); **interaction**;
  **device state**; **communications** (messages and calls, with name and number, plan 10.4 item 1);
  **places** (observations with radius, kind and source); **money** (8.5); **passive** (collapsed by
  default with a count).
- Each item: time, field name, meaning, class, strength, actor, flags, source app, phone, and the raw
  record one click away.
- Every item for the day is returned; no limit. If more than 5,000 items, the passive lane is returned
  as hourly counts with an explicit "show all" that pages through every item, and the response says so.
- Counterpart events (actor `counterpart`) appear under the counterpart's person when viewing that
  person, and in a separate "others' actions" row otherwise.

### 8.2 Pattern view

- Grid: rows = local dates in range, columns = 24 local hours. Cell = hour state (5.3) and, for
  `interaction`, the count by strength. Default filter: interaction only, owner only, strength at least
  `moderate`. Toggles: include weak; include device state; include physical.
- **Usual quiet hours** (per subject, computed over days that have at least 12 observed hours):
  for each local hour h, `f(h)` = share of qualifying days with any interaction in h. Quiet hours = the
  longest circular run of hours with `f(h) ≤ 0.10`, at least 3 hours long. If none, the view says
  "No regular quiet period found". Threshold reasoning: a 10 percent tolerance lets an occasional late
  night exist without dissolving the routine; reverse if M12 shows rich phones have no run at 0.10.
- **Nights that break it**: days with at least one `strong` or `moderate` interaction inside the quiet
  hours, listed with the items, and days whose quiet hours are `no_data`, listed separately as
  "not observed".
- Per person across phones: a cell is `interaction` if any linked phone has interaction; the cell lists
  which phones. Availability is the best state across phones and states that.
- Large ranges: the API returns at most one response for the full extraction span of the largest phone
  (11) using the hourly rollup; no paging needed at that size.

### 8.3 Places over time

**Stays.** Per extraction, presence observations with `radius_m ≤ 250` (a stay needs a place more precise
than a neighbourhood), in time order:
1. Start a candidate at observation i. Extend to j while every observation in i..j is within
   `D = max(100 m, radius_i + radius_j)` of the running median position.
2. If `t_j - t_i ≥ 10 min` and at least 2 observations, emit a stay (median position, radius = max of
   P90 distance to median and the median observation radius, start, end).
3. Continue from j+1.

**Places (clusters).** DBSCAN over stays of the subject (all linked phones), haversine distance,
`eps = 150 m`, `min_samples = 3` stays. Cluster radius = P90 stay distance to centroid plus median stay
radius. A **routine place** is a cluster with stays on at least 4 distinct days, or on at least 25 percent
of days with any presence data. Clusters are unnamed until a person labels them (a decision).

**Profiles.** For each routine place, a 7 × 24 matrix of dwell minutes by local day of week and hour,
normalised by the number of observed weeks for that cell.

**Deviation.** For each day with at least 3 hours carrying stays:
1. For each hour h with a stay, `p = P(observed cluster | dow, h)` estimated from all other weeks
   (leave-one-week-out), Laplace-smoothed with α = 1 over clusters plus "elsewhere".
2. `surprise(h) = -log2 p`. Day score = mean surprise over hours with stays.
3. Flag the day if its score exceeds the subject's own 95th percentile and the day has at least one hour
   with surprise ≥ 3 bits (less than one-in-eight).
4. Report the deviating hours with the stays and observations behind them, and the routine expectation
   they broke ("usually at place B on Tuesdays 21:00 to 07:00").

Parameter reasoning: 10 minutes and 100 m match common stay-point defaults and the GPS radius floor in
6.2; 150 m eps merges the stays of one building without merging neighbours; 4 days keeps a one-off visit
out of routine. All are recorded with every result and are reviewable per case. Reverse after M5 and M12
if presence observations are too sparse for stays on the rich phones (then routine falls back to hourly
cluster membership of single observations, and says so).

**Trajectories and playback.** Ordered observations with their radii drawn as areas; segments between
observations longer than 2 hours are drawn as gaps, not lines. Uses the existing Map panels
(`frontend_v2/src/features/map/components/MovementTrails.tsx`, `RouteAnalysisPanel.tsx`,
`HotspotPanel.tsx`), fed by the observation API.

### 8.4 Together and apart

For two or more subjects (phones or persons) and a time window.

**Observation pairs.** For subjects A and B, presence observations a, b with
`dt = max(0, gap between [a.start, a.end] and [b.start, b.end])`, considered when `dt ≤ W`, where
`W = 5 min` by default (parameter).

**Verdict per pair**, with `d` = haversine distance, `R = r_a + r_b` (radii; unknown radius replaced by
the run's `assumed_radius_m`, default 1,000 m, and the pair marked `assumed`), `v = 40 m/s` (maximum
plausible ground speed, about 144 km/h):
- `compatible` if `d ≤ R` (the areas overlap; they may have been together);
- `separated` if `d - R > v × dt` (they could not have been in one place at either time);
- `undetermined` otherwise.
`compatible` is tight when `R ≤ 150 m`, broad otherwise; the UI never calls a broad overlap "together".

**Non-coordinate evidence.**
- Same BSSID observed by both within W: `compatible`, basis `shared_bssid`, radius from the anchor or
  150 m when unanchored (typical indoor WiFi reach). SSID alone is never used.
- Same full cell key (radio, mcc, mnc, lac, cid) within 15 min: `compatible`, basis `shared_cell`,
  broad, radius from reference or unknown.
- Bluetooth: one phone detecting a device whose name or address matches the other phone's own Bluetooth
  identity (identity spec): `compatible`, basis `bluetooth`, radius 30 m. Feasibility measured in M10.

**Episodes.** Consecutive `compatible` pairs for the same subject pair, separated by less than 30 min,
merge into an episode (start, end, tight or broad, observation counts). Consecutive `separated` pairs merge
into "apart" episodes the same way.

**Algorithm and limits.** Sort each subject's observations by start; sweep with two pointers over
`[start - W, end + W]`; compare only overlapping pairs; bounding-box reject before haversine.
Complexity O(n_a + n_b + pairs). **No cap.** If the estimated pair count (from hourly counts) exceeds
2,000,000 the request runs as a background job (`pol_colocation_run`) and the UI shows progress; results
are paged with total counts always returned. Nothing is dropped.

**Contrast with v1** (all citations `origin/main:backend/services/cellebrite_intersection_service.py`):

| v1 | Here |
|---|---|
| Fixed 250 m radius, accuracy ignored (`:105`, `:153`) | Sum of per-observation uncertainty radii; unknown radius uses a stated assumed radius |
| Fixed 600 s window (`:106`), 900 s for cells (`:206`), 1800 s for WiFi (`:311`) | 5 min default for points; intervals compared by overlap; movement allowance decides `separated` |
| At most 20,000 events loaded, silently (`:89`) | No cap; background job above a size; totals always returned |
| WiFi keyed by BSSID, falling back to SSID (`:338`) | BSSID only |
| `fromisoformat` on stored strings; offset-less becomes naive (`:44-50`) | Instants with offset status; offset-less observations excluded from `separated` verdicts and flagged in `compatible` |
| String comparison of dates in queries (`:215`, `:320`, `:414`) | timestamptz ranges |
| Convoy evidence cut to 50 (`:648`, `:664`) | All evidence, paged |
| Only "together" | Together, apart and undetermined, each with basis |

The Loupe copy of that service (`backend/services/cellebrite_intersection_service.py`) is removed with
the rest of the replaced Cellebrite code.

### 8.5 Money as place and time

- Source: `financial_transactions` rows with `ledger_status = 'admitted'` only, the default population of
  `list_transactions` (`backend/services/financial/transaction_query.py:84-89`). A corrected row is
  superseded by a new admitted row (`corrections.py:1-6`; `superseded_by_id`), so only the corrected
  value appears, and the original stays one click away in the financial views.
- Time: the ledger holds dates only (`transaction_date`, `posted_date`, `value_date`, `effective_date`,
  all DATE, `financial.py:819-822`). In the day view a transaction is an all-day item on the money lane,
  placed on the day of its `transaction_date` where present, labelled "transaction date"; a row with only
  a posted date is placed on that day labelled "posted date, the purchase may be earlier". Both dates are
  shown where both exist. It is never placed at a time of day. This follows the ledger's own rule that
  dates do not imply sequence (`ledger_timeline.py:39`).
- Place: the ledger has no place column. A person may attach a place to a transaction (map point and
  radius, recorded through the decision log with an Actor, `decisions.record`,
  `backend/services/financial/decisions.py:252-263`); it then becomes a `transaction` place observation
  covering the whole local day. A suggestion from the offline gazetteer over `counterparty_raw` or
  `description` may be offered; it is never applied without a person.
- Money items never contradict a time-window claim inside one day (they have no time); they appear as
  context, and can contradict a claim spanning whole days ("away all week") when the place is attached.
- Money stays p4 when read from a phone (plan 12.1 rule 5); this section only reads the ledger.

---

## 9. Statement check

### 9.1 Claim kinds and schema

`subject` = `{"kind": "person", "entity_id": ...}` or `{"kind": "extraction", "extraction_id": ...}`.
Window = `[window_start, window_end)` instants, with `window_zone` and `window_text` (the words of the
statement, e.g. "from about eleven until seven").

| Kind | Extra fields | Example |
|---|---|---|
| `inactive` | `activity: {"tolerance_minutes": 0}` | asleep 23:00 to 07:00 |
| `active` | `activity: {"what": "phone_use"}` | was on the phone all evening |
| `at_place` | `place: {"lat","lon","radius_m"}` or `{"cluster_id"}` or `{"text"}` (text must be resolved before confirming) | at home all evening |
| `not_at_place` | `place` | never went to the address |
| `with_subject` | `counterpart: subject` | was with B that night |
| `apart_from_subject` | `counterpart: subject` | had not seen B since Monday |
| `no_contact` | `counterpart: {"identity_ids": [...]} or person` | no contact with B after a date |
| `contact` | `counterpart` | spoke to B that morning |

An approximate time in the statement is entered as a window that covers it ("about eleven" becomes a
window edge the person chooses), and the evaluation reports items within 30 minutes outside the window as
`context` so an approximation never hides a near miss.

### 9.2 Creating claims

**Manually**, in the statement check panel, linked optionally to a source: an interview transcript
segment (`source_anchor` = `{"evidence_file_id", "start_seconds", "end_seconds"}` as in
`workspace_ai_service.py:209-214`) or a document character range, or a message locator.

**AI-drafted**, then confirmed by a person:
1. Input: selected dossier interviews (sources assembled exactly as `_interview_sources`,
   `workspace_ai_service.py:311-356`) or a conversation's text rows (plan 6.6), with the target subject.
2. A new Workspace AI output type `statement_claims` is added beside the three in
   `workspace_ai_service.py:31`, using the same durable, cited, reviewed pattern (`create_output`,
   `run_output`, `accept_output`). Prompt schema:
   `{"claims": [{"kind": "...", "subject_text": "...", "window_text": "...", "place_text": null,
   "counterpart_text": null, "quote": "...", "citation_ids": ["S1"]}], "limitations": ["..."]}`.
   Every claim must cite; the validator rejects uncited claims (as `validate_generated_content` does).
3. The model never produces instants. On review the person resolves subject, window, place and
   counterpart (date pickers seeded by a deterministic parser of `window_text` against the interview
   date), then confirms. Accepting creates `pol_claim` rows with `origin = 'ai_draft'`, `status =
   'draft'`; each becomes `confirmed` only by an explicit confirm with the confirming user recorded.
4. **Model location**: the drafting runs under a new workload `statement_claim_drafting` which must
   resolve to a local model provider (standing decision 8). Loupe has no local provider today
   (`ai_model_policy.py:17-58`, `:64-97`), so AI drafting is unavailable until one exists, and the panel
   says "AI drafting needs a local model on this server" rather than falling back to a hosted provider.
   Reverse per case by Neil's decision, recorded with the case.

### 9.3 Evaluation inputs

For a confirmed claim: the subject's extractions (4.2); activity events, place observations, bands and
co-location in `[window_start - 30 min, window_end + 30 min)`; current mapping versions; dataset ids.
The `inputs_fingerprint` (sha256 of the canonical JSON of inputs) makes an evaluation reproducible; a
mapping or capture change marks earlier evaluations `stale` (shown, never deleted).

### 9.4 Evaluation per kind

Common: items outside the window but within 30 minutes are `context`. Bands give `gap` items for every
window piece in `no_data`, `powered_off*`, `after_extraction`, `outside_selection` or `not_selected`.

**`inactive`**
1. Contradicting: owner `interaction` events in the window, strength `strong` or `moderate` (role
   `contradicting`, strength kept); `weak` ones also listed as contradicting with strength `weak`.
2. Contradicting, weak: `physical` events in the window (the phone moved).
3. Context: `device_state` events (screen on can be a notification), counterpart events, passive events.
4. Supporting: each window piece in `data_no_interaction`, with its observing streams, role
   `supporting`, strength `moderate` if at least one interaction-capable stream observed it, else `weak`.
5. Outcome (computed): `contradicted` if any strong contradicting item; `contradicted_weakly` if only
   moderate or weak; `consistent` if no contradicting item and supporting pieces cover at least 80
   percent of the window; `insufficient_data` otherwise. The UI copy for `consistent`: "Nothing on the
   phone needed a person during this time, and the phone was recording for most of it." It never says
   the person was asleep.

**`active`**: mirror image. Supporting = owner interactions; contradicting = `data_no_interaction`
pieces; outcome `supported`, `contradicted` (no interaction while observed for at least 80 percent),
`insufficient_data`.

**`at_place`**
1. Presence observations of the subject in the window. Each: `supporting` if inside (distance ≤ place
   radius + observation radius), `contradicting` if `separated` from the place by the 8.4 rule with
   `dt = 0`, `context` if neither.
2. Strength: `strong` when tight (radii sum ≤ 150 m) and no group-A flag; `moderate` when broad or one
   flag; `weak` for cell-only or assumed radius.
3. Gaps: window pieces with no presence observation are `gap` items ("no location recorded").
4. Outcome: `contradicted` if any strong contradicting item; `supported` if supporting items exist and
   none contradict; `mixed` if both; `insufficient_data` if no presence observations.

**`not_at_place`**: same computation, roles swapped.

**`with_subject` / `apart_from_subject`**: run 8.4 for the pair over the window; episodes become items:
compatible episodes support `with_subject`, separated episodes contradict it, and the reverse for
`apart_from_subject`. Outcome as `at_place`.

**`no_contact`**
1. Communications between the subject's extractions and the counterpart's identities in the window:
   messages, calls (all statuses), emails, from both sides of every phone in the case (a message present
   only on the counterpart's phone still counts, marked "seen on the other phone").
2. Each is `contradicting`; strength `strong` for owner-sent or owner-answered items, `moderate` for
   received and read by the owner, `weak` for received and unread or missed.
3. Gaps: the communication families of each extraction with no observed coverage, and deleted-message
   indicators in the window (plan 12 approach 3), listed as `gap` ("messages may have been deleted").
4. Outcome: `contradicted` if any strong item; `contradicted_weakly` if only moderate or weak;
   `consistent` if none and the extractions' message and call records span the window; else
   `insufficient_data`.

**`contact`**: mirror image.

### 9.5 Output

```json
{
  "evaluation_id": "uuid", "claim_id": "uuid", "claim_version": 3,
  "outcome": "contradicted",
  "outcome_basis": "2 strong contradicting items",
  "stale": false,
  "window": {"start": "2022-12-02T04:00:00Z", "end": "2022-12-02T12:00:00Z", "zone": "America/New_York"},
  "coverage": [{"extraction_id": "...", "start": "...", "end": "...", "state": "data_no_interaction",
                "streams": ["DeviceEvent/<Source>/DisplayOnOff"]}],
  "items": [{"role": "contradicting", "strength": "strong", "reason_code": "owner_interaction",
             "ref_kind": "activity_event", "ref_id": "123",
             "display": {"time_local": "2:14 AM, Fri 2 Dec 2022", "field": "TimeStamp",
                         "meaning": "sent time", "type": "InstantMessage", "source_app": "...",
                         "phone": "P14", "flags": []},
             "record_locator": "..."}],
  "counts": {"contradicting": {"strong": 2, "moderate": 0, "weak": 1}, "supporting": {}, "gap": 1, "context": 7},
  "inputs": {"activity_mapping_version": "...", "meaning_mapping_version": "...",
             "attribution_mapping_version": "...", "cell_dataset_id": null, "params": {}}
}
```

Every item is returned; no limit. The example dates are illustrative.

### 9.6 Attaching to Workspace

1. Migration adds `phone_record` and `statement_check` to `ENTRY_LINK_TARGET_TYPES`
   (`workspace_entry.py:43-53`) and to `ck_workspace_entry_links_target_type` (`:269-272`).
2. From an evaluation, the person chooses a finding or theory and selects items. The service calls
   `add_entry_links` (`workspace_entry_service.py:1352`) with, per selected item,
   `target_type = "phone_record"`, `target_id = record_locator`, `relationship` = `contradicts` for
   contradicting items and `supports` for supporting items, `context` for context and gap items,
   `source_anchor = {"time_field": ..., "instant_utc": ...}`, and `metadata = {"evaluation_id",
   "claim_id", "strength", "class_basis", "activity_mapping_version"}`; plus one link
   `target_type = "statement_check"`, `target_id = evaluation_id`, `relationship` = `contradicts` when the
   outcome is `contradicted`/`contradicted_weakly`, `supports` when `supported`/`consistent`, else
   `context`.
3. Links are never added automatically. A later evaluation that differs marks the linked evaluation
   `stale` in the Workspace link list ("A newer check of this statement gives a different result").
4. The claim's source anchor (the interview segment) is shown on the finding beside the phone items, so
   the statement and the records that test it sit together.

---

## 10. API

Router `backend/routers/pattern_of_life.py`, `APIRouter(prefix="/api/pattern", tags=["pattern-of-life"])`;
service package `backend/services/pattern_of_life/` (`activity.py`, `availability.py`, `places.py`,
`routine.py`, `colocation.py`, `money.py`, `claims.py`, `evaluation.py`, `drafting.py`). Reads use
`require_case_view`; writes `require_case_edit` (`routers/case_access.py:102`, `:112`). Times in and out
are ISO 8601 with offset; `zone` is an IANA name or `device` or `UTC`. Errors: 400 invalid range or
subject, 404 unknown subject, 409 projection `building` (body states progress), 422 claim not
confirmable (field list).

| Method and path | Request | Response |
|---|---|---|
| GET `/{case_id}/subjects` | | extractions with owner identity, families present, first and last, projection status; persons with linked extractions |
| GET `/{case_id}/availability` | `subject`, `start`, `end` | bands per extraction and family; streams with first, last, max_gap |
| GET `/{case_id}/day` | `subject`, `date` (local), `zone`, `include_passive` (bool) | `{lanes: {...}, availability: [...], totals: {...}, truncated: false}`; lane items as 9.5 `display` plus ids |
| GET `/{case_id}/grid` | `subject`, `start_date`, `end_date`, `zone`, `min_strength`, `classes` | `{days: [{date, hours: [{state, counts, phones}]}], quiet_hours: {...} | null, breaks: [...]}` |
| GET `/{case_id}/events` | `subject`, `start`, `end`, filters, `cursor` | every event, cursor-paged, `total` always returned |
| GET `/{case_id}/places` | `subject`, `start`, `end`, `kinds`, `cursor` | observations with radius, basis, flags; `total` |
| GET `/{case_id}/routine` | `subject` | clusters, profiles, parameters |
| GET `/{case_id}/routine/deviations` | `subject`, `start_date`, `end_date` | flagged days with hours, stays, expectations |
| POST `/{case_id}/together` | `{subjects: [...], start, end, params: {window_s, assumed_radius_m, max_speed_mps}}` | 200 with result, or 202 `{run_id}` |
| GET `/{case_id}/together/{run_id}` | `cursor` | status, counts, episodes, pairs page |
| GET `/{case_id}/money` | `subject`, `start_date`, `end_date` | admitted transactions with date basis and any attached place |
| POST `/{case_id}/places/manual` | `{target: {kind: "transaction"|"claim_text"}, lat, lon, radius_m, reason}` | observation id; recorded as a decision |
| POST `/{case_id}/claims` | 9.1 fields | claim (`draft`) |
| PATCH `/{case_id}/claims/{id}` | fields, `expected_version` | claim; 409 on version mismatch |
| POST `/{case_id}/claims/{id}/confirm` | `expected_version` | claim (`confirmed`) |
| POST `/{case_id}/claims/{id}/withdraw` | `reason` | claim |
| POST `/{case_id}/claims/{id}/evaluate` | | evaluation (9.5) |
| GET `/{case_id}/claims/{id}/evaluations` | | list with outcome and stale flag |
| POST `/{case_id}/claims/{id}/evaluations/{eid}/attach` | `{entry_id, expected_version, item_ordinals: [...], include_check_link: true}` | added link ids |
| POST `/{case_id}/claim-drafts` | `{dossier_id, interview_ids}` or `{conversation_locator}`, `subject` | Workspace AI output id (`statement_claims`); 409 when no local model |
| POST `/{case_id}/reference/cell` (admin) | `{file_path_on_server, name, licence, attribution, retrieved_on}` | dataset id, row count, sha256 |

Frontend: `frontend_v2/src/features/pattern/` (`api.ts`, `types.ts`, `components/DayView.tsx`,
`PatternGrid.tsx`, `StatementCheckPanel.tsx`, `ClaimForm.tsx`, `EvaluationResult.tsx`), a "Pattern of
life" screen with subject picker; Places over time and Together as Case Map panels in
`frontend_v2/src/features/map/components/`. Tests use `fireEvent` (CLAUDE.md).

---

## 11. Performance targets (largest phone P14; 3-phone case for multi-subject)

P14 carries 595,975 TimeStamp values in total (CAT sum over its catalogue) and the 3-phone case
1,176,038 across P12 to P14; derived activity events are bounded by these.

| Operation | Target (server, warm cache) |
|---|---|
| Full projection build for P14 (activity events, places, bands, rollup) | ≤ 5 min, streaming from capture, memory ≤ 1 GB |
| Re-applying a new activity mapping version to P14 | ≤ 60 s |
| Day view, P14, busiest day, passive collapsed | p95 ≤ 500 ms |
| Day view with all passive items | p95 ≤ 2 s |
| Pattern grid, P14, full extraction span | p95 ≤ 1.5 s |
| Pattern grid, person with 2 phones, full span | p95 ≤ 2.5 s |
| Statement check, 24 h window, person with 2 phones, any kind except together | p95 ≤ 2 s |
| Together, 2 phones of the 3-phone case, full span | ≤ 60 s (background job allowed) |
| Routine for P14 | ≤ 30 s |
| Cell reference import, worldwide file | ≤ 15 min, streaming |

Measured by `backend/tests/test_pattern_performance.py`, which runs only when the corpus environment
variable is set and records results in the build state, never failing the normal suite on timing alone.

---

## 12. Units, build order and acceptance tests

Phase 5 holds U1 (plan 11.4: the activity-strength mapping is the first reviewed mapping). The rest is
phase 7, in this order. Each unit is finished, tested and committed before the next. Tests live in
`backend/tests/test_pattern_<unit>.py` and use synthetic captured records built in the test, never case
evidence; corpus checks are separate and gated.

| Unit | Content | Acceptance tests |
|---|---|---|
| U0 | Run M1 to M12 (section 13); record results in `docs/cellebrite/measurements/` | Each measurement output exists, contains counts only, and the values feed the mapping drafts |
| U1 | Timestamp-meaning, activity-strength and attribution mapping content (sections 2.3, 3, 4) as reviewed data | Every (type, time field) in CAT has a meaning row or an explicit `unknown`; an unmatched value yields `unknown` / `default_unknown`; two equally specific matching rows fail validation; mapping change alters no captured row |
| U2 | `pol_activity_event` projection and strength view | Synthetic outgoing message (From owner) → `interaction`, `owner`, `strong`; same with Platform Web → actor `other_device`, `weak`; Party DateRead on non-owner To party → `counterpart`; offset-less time → flag `offset_absent` and not `strong`; rebuild twice → identical rows; new mapping version reclassifies without re-ingest |
| U3 | Attribution flags | Synced Location → `synced_from_account`; two group-B flags demote to `weak`; UserMapping `Decoding` produces no flag |
| U4 | Availability bands and hourly rollup | Power On without Off → `powered_off_inferred`; an 8-hour night with DisplayOnOff every 20 minutes and no unlock, on an extraction with unlocks elsewhere → `data_no_interaction`; same night with no events → `no_data`; events after extraction start flagged; messages never create observed segments |
| U5 | Place observations, cell reference import, WiFi anchors | Accuracy 20 → radius 40; Searched Location → kind `searched`, excluded from routine; unknown tower → listed as not in reference data; anchor needs 2 days; SSID never anchors; reverse geocoder disabled when backend is not in-house |
| U6 | Day view API and screen | Every item returned for a 6,000-item synthetic day with the passive lane summarised and `show all` paging to the full count; times shown with date in 12-hour form in device zone; original string reachable |
| U7 | Pattern grid, quiet hours, breaks | Synthetic 30 days with interaction 08:00 to 23:00 → quiet hours 23:00 to 08:00; one night with a strong event at 03:00 listed; a night of `no_data` listed as not observed, not as a break |
| U8 | Stays, clusters, routine, deviations | Synthetic home and work routine over 6 weeks → 2 routine places; a Tuesday night elsewhere flagged with its hours; parameters echoed in the result |
| U9 | Together and apart | Two phones 120 m apart with radii 50 and 100 → compatible; 5 km apart, dt 0, radii 100 → separated; 25,000 pairs → all returned with totals (no cap); SSID-only match → no item; v1 contrast cases encoded as tests |
| U10 | Money lane and manual places | Superseded row absent, corrected row present; posted-only row labelled; transaction never placed at a time of day; manual place recorded as a decision with Actor |
| U11 | Claims and evaluation | Each kind's outcome rules in 9.4 on synthetic data; evaluation reproducible from fingerprint; mapping change marks evaluation stale; confirm requires a user |
| U12 | AI claim drafting | Uncited claim rejected; model output never sets instants; with no local provider the endpoint returns 409 with the stated message and makes no network call |
| U13 | Workspace attachment | Migration accepts `phone_record` and `statement_check`; attach adds links with the right relationships through `add_entry_links`; version conflict returns 409; stale evaluation shown on the link |
| Gate | Phase 7 done-when (plan 7): a statement window shows supporting, contradicting and missing data with sources | End-to-end test on synthetic two-phone case through the HTTP API, plus a corpus run on P14 recorded in the build state |

---

## 13. Corpus measurements to run before building

Scripts live in `scripts/cellebrite_corpus/` (repo root `scripts/` already holds audit scripts). Each is
standard-library Python, compatible with 3.10, streams with `xml.etree.ElementTree.iterparse` and clears
top-level models, runs with `python3 -I`, takes the report path (or zip and inner path) and an output
path, and writes JSON of counts only. Common guards:

- A String value is printed only if it matches `^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$` **and** occurs at
  least 3 times in the report; otherwise it is counted as `<other>`. Free-text fields (Body, Subject,
  Name, Value of TextInput, DeviceName, Account, SSId, BSSId, Url, Title) are never printed; for them only
  presence counts, length histograms or character-class shapes are written.
- Times are reduced to shape (digits to 9), to UTC hour-of-day histograms, or to durations; no absolute
  time is written except the extraction start in M11 (structural metadata).
- Coordinates are never written; only distances, counts and radius histograms.
- Runs read-only on the server copies under `/mnt/owl-data/ingestion-data/` (plan 8) by Neil or with his
  agreement, and on the three local samples.

| Id | Script | Logic | Feeds |
|---|---|---|---|
| M1 | `pol_m1_device_events.py` | For DeviceEvent: count by (Source, EventType, Value) with the guard; TextInput Value replaced by its length bucket; per EventType the share with EndTime and a histogram of EndTime minus StartTime (seconds, log buckets); per (Source, EventType) count by UTC hour | 3.2 DeviceEvent rows; power values for 5.3 |
| M2 | `pol_m2_enums.py` | Distinct guarded values for: UserMapping per type; Location Type, Category, Precision, Source; AppsUsageLog Source × Action; SearchedItem Source × Origin × has TimeStamp; Email Folder (guarded) × Status; InstantMessage Folder × Status × Platform × (From party IsPhoneOwner) × Type; Notification Status × Type; DeviceConnectivity Nature × Method × DeviceType | 3.2 communications and app rows; 4.2 |
| M3 | `pol_m3_time_shapes.py` | Per (type, time field): shape histogram (offset present or absent, fractional digits), and count of values whose text differs from the `formattedTimestamp` attribute where present | 2.3 offset rule; time spec |
| M4 | `pol_m4_stream_gaps.py` | Per stream (type, Source, and EventType for DeviceEvent): sorted instants; inter-event gap quantiles P50, P90, P95, P99, max; same split by UTC hour of gap start; NetworkUsage bucket width histogram (DateEnded minus DateStarted); ActivitySensorData To minus From; AppsUsageLog EndTime minus StartTime; ApplicationUsage EndTime minus StartTime; DeviceConnectivity Paired StartTime gap to the next Connected event | 5.3 `max_gap`; 2.3 bucket semantics |
| M5 | `pol_m5_places.py` | Per Location (Source, Type, Category): count; with nested Coordinate; with GpsHorizontalAccuracy (quantiles); Precision values; Confidence histogram; with TimeStamp, EndTime; offset-absent share; DeviceLocationAffiliation × AccountLocationAffiliation × Origin cross-tab; WirelessNetwork per Source: with BSSId, with Position, with accuracy, with TimeStamp, LastConnection; CellTower: with MCC, digit counts of MNC, LAC, CID, Type; Journey nesting; per phone the number of BSSIDs with at least one GPS observation (radius ≤ 100 m) within 5 minutes on 2 or more days | 6.2 radius rows; 6.3 feasibility |
| M6 | `pol_m6_party_dates.py` | Generalises POL-P: Party with any of DateRead, DateDelivered, DatePlayed by (parent type, parent Source, Role, IsPhoneOwner, which dates), plus the parent message's outgoing rule result | 2.3 Party rows; 3.2 |
| M7 | `pol_m7_web.py` | VisitedPage: VisitCount histogram; share with VisitCount > 1; LastVisited present; Source counts; UsagePattern values; SearchedItem TimeStamp presence by Source | latest_of_many caveat sizing |
| M8 | `pol_m8_power.py` | Sequences of PoweringEvent and DeviceEvent PowerEvent values in time order: count of On after On, Off after Off, On after Off; gap before each On to the previous event of any stream (needs M4's stream index) | 5.3 step 5 |
| M9 | `pol_m9_sensors.py` | Nesting chain of ActivitySensorData, Measurement, Sample (from POL-N style traversal); MeasuredVariableType per Sample; whether DeviceName contains the tokens `Watch`, `iPhone`, `Phone` (boolean counts only); SourceDeviceType values; sample interval histogram | 3.2 sensor rows; `wearable` flag |
| M10 | `pol_m10_colocation.py` | Per case, per phone pair: number of presence observation pairs within 5 minutes by radius-sum band (≤150 m, ≤1 km, >1 km, unknown) and by distance band; shared BSSID within 5 minutes; shared full cell key within 15 minutes; Bluetooth detections naming the other phone's device (needs identity spec output; else skipped) | 8.4 feasibility and defaults |
| M11 | `pol_m11_extraction_edges.py` | DeviceInfoExtractionStartDateTime and EndDateTime; per family first and last as offsets in days from extraction start; count of events after extraction start; selection metadata items present | 5.3 steps 1 and 2 |
| M12 | `pol_m12_daily_coverage.py` | Per phone: days with at least one candidate interaction event (by the U1 draft rows), days with 12 or more observed hours (by M4 thresholds), quiet-hour run at thresholds 0.05, 0.10, 0.20 | 8.2 thresholds; 8.3 deviation minimums |

Results are written to `docs/cellebrite/measurements/pol-mNN-<phone>.json` (counts only) and summarised
in this file when each unit starts, per plan 12.1 rule 1.

---

## 14. Decisions made here that the plan did not settle

Each is a decision with its reasoning and what would reverse it.

1. **Strength is a computed view, not a stored column.** Prevents a stale strength after a mapping
   change. Reverse if the view is too slow at P14 scale (then a column refreshed in the same transaction
   as the mapping application).
2. **Two qualifiers beside the four classes: `actor` and `physical`.** The plan's classes do not express
   "the other person read it" or "the phone was carried"; both matter to a sleep claim. Reverse if Neil
   prefers counterpart reads as their own class.
3. **Communications never establish that a phone was recording.** Their rate follows the person, so
   using them for coverage would make silence prove itself. Reverse if M4 shows a messaging database that
   logs continuous system events.
4. **Hour observed at 50 minutes of stream coverage.** Reverse if M4 shows segments typically under an
   hour on rich phones.
5. **GPS radius doubled for comparisons.** Android documents a 68 percent radius. Reverse per Source if
   M5 shows a different convention.
6. **No external WiFi dataset; BSSID positions from the case.** No suitably licensed offline set was
   identified and lookups leak identifiers. Reverse by Neil adopting a licensed set.
7. **OpenCelliD imports kept as dated versions**, chosen per case, attribution shown, licence question
   put to Neil. Reverse on his licence ruling.
8. **Co-location verdicts include `separated` with a 40 m/s movement allowance.** "Apart" claims need
   a positive test, not absence of overlap. Reverse if a case involves air travel (then the allowance is
   a parameter raised for that run, and stated).
9. **SSID never used for co-location.** Common names produce false matches. Not reversible without new
   evidence that an SSID is unique (a decision per network, recorded).
10. **Money items are all-day, never timed, and get places only from a person.** The ledger has dates
    only and no place. Reverse if a production carries authorisation times (then a new ledger field, in
    the financial subsystem first).
11. **Claim outcome is computed from fixed rules**, like proof class; a person can withdraw a claim or
    add links but never set an outcome. Follows standing decision 5.
12. **AI claim drafting only on a local model; otherwise unavailable.** Standing decision 8. Reverse per
    case by Neil.
13. **New Workspace link target types `phone_record` and `statement_check`** rather than overloading
    `evidence` or `timeline_event`. A phone record is not an evidence file and must open to its locator.
14. **Pattern-of-life tables live in the backend Alembic tree** with models in
    `backend/postgres/models/pattern_of_life.py`. Reverse if the capture spec puts phone tables in the
    evidence-engine tree.
15. **A "Pattern of life" screen** for Day view, Pattern view and Statement check; Places over time and
    Together as Case Map panels. Day lanes differ from the Case Timeline's swim lanes. Reverse if Neil
    wants them as Timeline modes.
16. **Stay and routine parameters** (100 m, 10 min, eps 150 m, 3 stays, 4 days, 95th percentile and 3
    bits) as stated in 8.3, echoed with every result. Reverse after M5 and M12.
17. **Approximate times handled by a 30-minute context margin** rather than fuzzy windows. Keeps the
    window exact and the near misses visible.

## 15. Not yet established

- The values of `DeviceEvent.Value` for 14 of 16 EventTypes (only `Power on` and `Factory Reset` are in
  the samples). M1.
- The full `UserMapping` value set and what non-`Decoding` values mean. M2.
- What `DeviceLocationAffiliation = Synced` and `Extracted` mean precisely, and the meaning of
  `Location.Precision` and `Location.Confidence`. M5; Cellebrite documentation not located.
- What `WirelessNetwork.TimeStamp` (25,356 values) and `CellTower.TimeStamp` record. M5.
- NetworkUsage and ApplicationUsage bucket widths. M4.
- Whether `DeviceConnectivity` `Paired` times are pairing moments. M4.
- Sensor nesting and whether any sensor records come from a wearable. M9.
- Whether P03 and P10 are the same device (plan 12).
- Why the catalogue holds 10 reports for the case the plan calls the 10-report case.
- OpenCelliD licence obligations for Loupe outputs; whether the current export covers the case's
  2022-2023 towers.
- Whether any production states selected date ranges (`IsSelectiveExtraction`, `IsPartialData` were not
  among the header items seen in C3 and C9). M11.
- Whether a local model provider will exist for claim drafting, and which.
