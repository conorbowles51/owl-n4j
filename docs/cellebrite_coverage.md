# Cellebrite Ingestion Coverage Audit

Generated: 2026-05-23T13:18:21
Reports scanned: 3
Total top-level models seen: 45,200
Total tagged files seen: 165,340

## Reports

- `220049582_06306946_C5_2022-12-15_Report_2025-03-19_Report.xml` — 25,596 models in 18 types, 92,761 tagged files
- `220049582_06306208_C3_2022-12-12_Report_2025-03-19_Report.xml` — 16,663 models in 20 types, 43,043 tagged files
- `220029502_06310028_C9_2023-03-02_Report_2025-03-20_Report.xml` — 2,941 models in 14 types, 29,536 tagged files

## Coverage gap headlines

**Types in our reports without a handler (0):**  
_none_

**Types in our reports NOT in UFEDLib's 56-class reference (probably Cellebrite-newer or app-specific) (1):**  
`Email`

**Types UFEDLib supports but neither in our reports nor our SUPPORTED set (31):**  
`ActivitySensorData`, `ActivitySensorDataMeasurement`, `ActivitySensorDataSample`, `AppsUsageLog`, `ChatActivity`, `ContactEntry`, `Cookie`, `Coordinate`, `CreditCard`, `DeviceConnectivity`, `DeviceInfoEntry`, `EMail`, `FileUpload`, `FinancialAccount`, `FinancialAsset`, `Journey`, `LogEntry`, `MailMessage`, `Map`, `MobileCard`, `Note`, `Notification`, `Organization`, `Price`, `PublicTransportationTicket`, `Recording`, `SharedFile`, `SocialMediaActivity`, `StreetAddress`, `TransferOfFunds`, `VoiceMail`

## Per-type coverage

| Type | Reports | Instances | UFEDLib | Supported | Handler | Fields seen | Fields captured | Coverage |
|---|---:|---:|:---:|:---:|:---:|---:|---:|---:|
| ActivitySensorData | 0 | 0 | yes | no | no | 0 | 0 | — |
| ActivitySensorDataMeasurement | 0 | 0 | yes | no | no | 0 | 0 | — |
| ActivitySensorDataSample | 0 | 0 | yes | no | no | 0 | 0 | — |
| AppUsage | 0 | 0 | — | yes | yes | 0 | 0 | — |
| ApplicationUsage | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| AppsUsageLog | 0 | 0 | yes | no | no | 0 | 0 | — |
| Attachment | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| Autofill | 1 | 8 | yes | yes | yes | 6 | 5 | 83% |
| CalendarEntry | 3 | 84 | yes | yes | yes | 10 | 9 | 90% |
| Call | 3 | 7,896 | yes | yes | yes | 9 | 8 | 89% |
| Cell | 0 | 0 | — | yes | yes | 0 | 0 | — |
| CellLocation | 0 | 0 | — | yes | yes | 0 | 0 | — |
| CellTower | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| Chat | 3 | 995 | yes | yes | yes | 8 | 7 | 88% |
| ChatActivity | 0 | 0 | yes | no | no | 0 | 0 | — |
| Contact | 3 | 3,364 | yes | yes | yes | 6 | 5 | 83% |
| ContactEntry | 0 | 0 | yes | no | no | 0 | 0 | — |
| ContactPhoto | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| Cookie | 0 | 0 | yes | no | no | 0 | 0 | — |
| Coordinate | 0 | 0 | yes | no | no | 0 | 0 | — |
| CreditCard | 0 | 0 | yes | no | no | 0 | 0 | — |
| DeviceConnectivity | 0 | 0 | yes | no | no | 0 | 0 | — |
| DeviceEvent | 2 | 3 | yes | yes | yes | 4 | 3 | 75% |
| DeviceInfoEntry | 0 | 0 | yes | no | no | 0 | 0 | — |
| DictionaryWord | 2 | 7,180 | yes | skipped | no | 4 | 0 | 0% |
| EMail | 0 | 0 | yes | no | no | 0 | 0 | — |
| Email | 3 | 704 | — | yes | yes | 8 | 7 | 88% |
| FileDownload | 1 | 1 | yes | yes | yes | 10 | 9 | 90% |
| FileUpload | 0 | 0 | yes | no | no | 0 | 0 | — |
| FinancialAccount | 0 | 0 | yes | no | no | 0 | 0 | — |
| FinancialAsset | 0 | 0 | yes | no | no | 0 | 0 | — |
| InstalledApplication | 1 | 588 | yes | yes | yes | 8 | 7 | 88% |
| InstantMessage | 3 | 839 | yes | yes | yes | 10 | 9 | 90% |
| Journey | 0 | 0 | yes | no | no | 0 | 0 | — |
| KeyValueModel | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| Location | 3 | 148 | yes | yes | yes | 8 | 6 | 75% |
| LogEntry | 0 | 0 | yes | no | no | 0 | 0 | — |
| MailMessage | 0 | 0 | yes | no | no | 0 | 0 | — |
| Map | 0 | 0 | yes | no | no | 0 | 0 | — |
| MobileCard | 0 | 0 | yes | no | no | 0 | 0 | — |
| NetworkUsage | 1 | 5,181 | yes | skipped | no | 10 | 0 | 0% |
| Note | 0 | 0 | yes | no | no | 0 | 0 | — |
| Notification | 0 | 0 | yes | no | no | 0 | 0 | — |
| Organization | 0 | 0 | yes | no | no | 0 | 0 | — |
| Party | 0 | 0 | yes | yes | yes | 0 | 0 | — |
| Password | 2 | 561 | yes | yes | yes | 9 | 7 | 78% |
| PoweringEvent | 2 | 3 | yes | yes | yes | 4 | 4 | 100% |
| Price | 0 | 0 | yes | no | no | 0 | 0 | — |
| ProfilePicture | 0 | 0 | — | yes | yes | 0 | 0 | — |
| PublicTransportationTicket | 0 | 0 | yes | no | no | 0 | 0 | — |
| RecognizedDevice | 2 | 6 | yes | yes | yes | 4 | 3 | 75% |
| Recording | 0 | 0 | yes | no | no | 0 | 0 | — |
| SIMData | 1 | 9 | yes | yes | yes | 4 | 3 | 75% |
| ScreenEvent | 0 | 0 | — | yes | yes | 0 | 0 | — |
| SearchedItem | 2 | 32 | yes | yes | yes | 5 | 3 | 60% |
| SharedFile | 0 | 0 | yes | no | no | 0 | 0 | — |
| SocialMediaActivity | 0 | 0 | yes | no | no | 0 | 0 | — |
| StreetAddress | 0 | 0 | yes | no | no | 0 | 0 | — |
| TransferOfFunds | 0 | 0 | yes | no | no | 0 | 0 | — |
| User | 2 | 2 | yes | yes | yes | 6 | 5 | 83% |
| UserAccount | 3 | 87 | yes | yes | yes | 8 | 7 | 88% |
| UserEvent | 0 | 0 | — | yes | yes | 0 | 0 | — |
| VisitedPage | 3 | 16,807 | yes | yes | yes | 8 | 6 | 75% |
| VoiceMail | 0 | 0 | yes | no | no | 0 | 0 | — |
| WebBookmark | 3 | 25 | yes | yes | yes | 6 | 4 | 67% |
| WirelessNetwork | 3 | 677 | yes | yes | yes | 7 | 6 | 86% |

## Field coverage per type

_Sorted by instance count, top 25 types. "Captured" = field is read by the handler dispatched to this type, OR by a helper (`_attachment_props`, `_message_provenance_props`, etc) — best effort static match, may underreport when helpers fan out._

### VisitedPage (16,807 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Source | 16,807 | 16,807 | yes |
| Url | 16,807 | 16,807 | yes |
| LastVisited | 16,807 | 15,995 | yes |
| UserMapping | 16,807 | 1,450 | yes |
| UrlCacheFile | 16,807 | 725 | yes |
| CanRebuildCacheFile | 725 | 725 | **no** |
| Title | 16,807 | 606 | yes |
| VisitCount | 84 | 84 | yes |

### Call (7,896 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Direction | 7,896 | 7,896 | yes |
| TimeStamp | 7,896 | 7,896 | yes |
| Status | 7,896 | 7,881 | yes |
| UserMapping | 7,896 | 7,766 | yes |
| Duration | 6,310 | 6,310 | yes |
| Source | 7,896 | 4,665 | yes |
| VideoCall | 4,626 | 4,626 | yes |
| Account | 7,896 | 4,535 | yes |
| Type | 88 | 88 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Parties | Party | 12,620 | yes |

### DictionaryWord (7,180 instances)

_No handler — all 4 fields and 0 nested children silently dropped._

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Frequency | 7,180 | 7,180 | **no** |
| Word | 7,178 | 7,178 | **no** |
| Source | 7,180 | 2 | **no** |
| UserMapping | 7,180 | 0 | yes |

### NetworkUsage (5,181 instances)

_No handler — all 10 fields and 1 nested children silently dropped._

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 5,181 | 5,181 | yes |
| Source | 5,181 | 5,181 | **no** |
| SSId | 5,181 | 5,181 | **no** |
| DateStarted | 5,181 | 5,181 | **no** |
| DateEnded | 5,181 | 5,181 | **no** |
| NumberOfBytesReceived | 5,181 | 5,181 | **no** |
| NumberOfBytesSent | 5,181 | 5,181 | **no** |
| IsRoaming | 5,181 | 5,181 | **no** |
| UsageMode | 5,181 | 5,181 | **no** |
| NetworkConnectionType | 5,181 | 5,181 | **no** |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | AdditionalInfo | KeyValueModel | 39,303 | **no** |

### Contact (3,364 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 3,364 | 3,274 | yes |
| Name | 3,364 | 2,469 | yes |
| Source | 3,364 | 2,365 | yes |
| Account | 3,364 | 2,361 | yes |
| Type | 1,546 | 1,546 | yes |
| Group | 3,364 | 0 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Entries | PhoneNumber | 2,913 | yes |
| multiModelField | Entries | UserID | 2,307 | yes |
| multiModelField | AdditionalInfo | KeyValueModel | 1,340 | **no** |
| multiModelField | Photos | ContactPhoto | 822 | yes |
| multiModelField | Entries | ProfilePicture | 519 | yes |
| multiModelField | Addresses | StreetAddress | 67 | yes |
| multiModelField | Entries | EmailAddress | 21 | yes |
| multiModelField | Entries | WebAddress | 13 | yes |
| multiModelField | Organizations | Organization | 2 | yes |

### Chat (995 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Source | 995 | 995 | yes |
| Id | 984 | 984 | yes |
| LastActivity | 995 | 967 | yes |
| StartTime | 995 | 929 | yes |
| UserMapping | 995 | 380 | yes |
| Account | 995 | 367 | yes |
| Name | 29 | 29 | yes |
| Description | 2 | 2 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Messages | InstantMessage | 18,531 | yes |
| multiModelField | Participants | Party | 2,466 | yes |
| multiModelField | Photos | ContactPhoto | 125 | **no** |
| multiModelField | ActivityLog | ChatActivity | 34 | **no** |

### InstantMessage (839 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Source | 839 | 839 | yes |
| Type | 839 | 839 | yes |
| SourceApplication | 839 | 839 | yes |
| Body | 826 | 826 | yes |
| TimeStamp | 839 | 817 | yes |
| UserMapping | 839 | 673 | yes |
| Identifier | 702 | 673 | yes |
| Status | 839 | 531 | yes |
| Folder | 839 | 144 | yes |
| DateDelivered | 107 | 107 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| modelField | Attachment | ? | 839 | **no** |
| modelField | From | Party | 817 | yes |
| modelField | From | ? | 22 | yes |
| multiModelField | To | Party | 817 | **no** |
| multiModelField | Attachments | Attachment | 13 | **no** |

### Email (704 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 704 | 704 | yes |
| Source | 704 | 704 | yes |
| TimeStamp | 704 | 704 | yes |
| Folder | 704 | 703 | yes |
| Body | 703 | 703 | yes |
| Account | 704 | 703 | yes |
| Subject | 701 | 701 | yes |
| Status | 652 | 652 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| modelField | From | Party | 704 | **no** |
| multiModelField | To | Party | 704 | **no** |
| multiModelField | Attachments | Attachment | 30 | **no** |
| multiModelField | Cc | Party | 11 | **no** |

### WirelessNetwork (677 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Source | 677 | 677 | yes |
| TimeStamp | 672 | 672 | yes |
| BSSId | 667 | 667 | yes |
| SSId | 10 | 10 | yes |
| LastConnection | 677 | 5 | yes |
| SecurityMode | 5 | 5 | yes |
| UserMapping | 677 | 0 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| modelField | Position | Coordinate | 2 | **no** |

### InstalledApplication (588 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Identifier | 588 | 588 | yes |
| OperationMode | 585 | 585 | yes |
| Version | 570 | 570 | yes |
| IsEmulatable | 555 | 555 | yes |
| DecodingStatus | 169 | 169 | yes |
| Name | 153 | 153 | yes |
| PurchaseDate | 588 | 134 | yes |
| UserMapping | 588 | 0 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Users | User | 3 | **no** |

### Password (561 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Type | 561 | 561 | yes |
| Account | 561 | 557 | yes |
| Label | 557 | 557 | yes |
| Source | 557 | 557 | yes |
| UserMapping | 561 | 556 | yes |
| Service | 552 | 552 | yes |
| AccessGroup | 548 | 548 | yes |
| Data | 457 | 457 | **no** |
| ServiceIdentifier | 286 | 286 | yes |

### Location (148 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Name | 120 | 120 | yes |
| Category | 120 | 120 | yes |
| TimeStamp | 148 | 102 | yes |
| UserMapping | 148 | 28 | yes |
| Source | 148 | 28 | yes |
| Type | 22 | 22 | yes |
| Description | 22 | 5 | yes |
| Account | 148 | 0 | **no** |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| modelField | Position | Coordinate | 148 | yes |
| modelField | Address | StreetAddress | 6 | **no** |

### UserAccount (87 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Username | 69 | 69 | yes |
| UserMapping | 87 | 68 | yes |
| Source | 64 | 64 | yes |
| ServiceType | 51 | 51 | yes |
| Name | 87 | 32 | yes |
| Password | 9 | 9 | yes |
| ServiceIdentifier | 8 | 8 | yes |
| TimeCreated | 5 | 5 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Entries | ProfilePicture | 27 | yes |
| multiModelField | Entries | UserID | 21 | yes |
| multiModelField | Entries | PhoneNumber | 16 | yes |
| multiModelField | AdditionalInfo | KeyValueModel | 4 | **no** |
| multiModelField | Entries | EmailAddress | 3 | yes |
| multiModelField | Photos | ContactPhoto | 3 | **no** |

### CalendarEntry (84 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 84 | 84 | yes |
| Source | 84 | 84 | yes |
| Category | 84 | 84 | yes |
| StartDate | 84 | 84 | yes |
| EndDate | 83 | 83 | yes |
| Subject | 80 | 80 | yes |
| Details | 79 | 79 | yes |
| Location | 3 | 3 | yes |
| RepeatRule | 1 | 1 | yes |
| RepeatUntil | 1 | 1 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Attendees | Party | 3 | **no** |

### SearchedItem (32 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Source | 32 | 32 | yes |
| Value | 32 | 32 | yes |
| UserMapping | 32 | 18 | yes |
| TimeStamp | 32 | 15 | yes |
| Origin | 4 | 3 | **no** |

### WebBookmark (25 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 25 | 25 | yes |
| Source | 25 | 25 | yes |
| Title | 25 | 25 | yes |
| Url | 19 | 19 | yes |
| TimeStamp | 10 | 10 | yes |
| Path | 25 | 0 | **no** |

### SIMData (9 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Name | 9 | 9 | yes |
| Value | 9 | 9 | yes |
| Category | 9 | 9 | yes |
| UserMapping | 9 | 0 | yes |

### Autofill (8 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 8 | 8 | yes |
| Source | 8 | 8 | yes |
| Key | 8 | 8 | yes |
| Value | 8 | 8 | yes |
| TimeStamp | 8 | 8 | yes |
| LastUsedDate | 8 | 8 | yes |

### RecognizedDevice (6 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 6 | 6 | yes |
| Source | 6 | 6 | yes |
| Name | 5 | 5 | yes |
| SerialNumber | 5 | 0 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | DeviceIdentifiers | KeyValueModel | 6 | **no** |
| multiModelField | AdditionalInfo | KeyValueModel | 5 | **no** |

### DeviceEvent (3 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| StartTime | 3 | 3 | yes |
| EventType | 3 | 3 | yes |
| Value | 3 | 3 | yes |
| UserMapping | 3 | 0 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | Additional_Info | KeyValueModel | 3 | **no** |

### PoweringEvent (3 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Element | 3 | 3 | yes |
| TimeStamp | 3 | 3 | yes |
| Event | 3 | 3 | yes |
| Description | 3 | 3 | yes |

### User (2 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Identifier | 2 | 2 | yes |
| SerialNumber | 2 | 2 | yes |
| TimeLastLoggedIn | 2 | 2 | yes |
| UserType | 2 | 2 | yes |
| Name | 1 | 1 | yes |
| UserMapping | 2 | 0 | yes |

### FileDownload (1 instances)

| Field | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| UserMapping | 1 | 1 | yes |
| Source | 1 | 1 | yes |
| Url | 1 | 1 | yes |
| TargetPath | 1 | 1 | yes |
| StartTime | 1 | 1 | yes |
| EndTime | 1 | 1 | yes |
| LastAccessed | 1 | 1 | yes |
| FileSize | 1 | 1 | yes |
| BytesReceived | 1 | 1 | yes |
| DownloadState | 1 | 1 | yes |

**Nested:**

| Kind | Field | Child type | Count | Captured |
|---|---|---|---:|:---:|
| multiModelField | AdditionalInfo | KeyValueModel | 2 | **no** |

## TaggedFile metadata coverage

_For each `<file>` inside `<taggedFiles>`, every `<metadata section="X">` block's `<item name="Y">` entries. "Captured" means parser.py's TaggedFile extractor matches this item_name._

### Section: `File`

| Item name | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| Local Path | 165,340 | 165,340 | **no** |
| MD5 | 165,340 | 165,340 | **no** |
| Tags | 165,340 | 165,340 | **no** |
| SHA256 | 165,340 | 1,579 | **no** |

### Section: `MetaData`

| Item name | Total | Non-empty | Captured |
|---|---:|---:|:---:|
| ReportTemplateFileSize | 163,762 | 163,762 | **no** |
| CoreFileSystemFileSystemNodeFileChunks | 163,762 | 163,762 | **no** |
| CoreFileSystemFileSystemNodeFileDataOffsetName | 163,761 | 163,761 | **no** |
| CoreFileSystemFileSystemNodeModifyTime | 165,340 | 91,380 | **no** |
| CoreFileSystemFileSystemNodeLastAccessTime | 165,340 | 21,417 | **no** |
| Uid | 20,821 | 20,821 | **no** |
| Gid | 20,821 | 20,821 | **no** |
| URL | 15,651 | 15,651 | **no** |
| ExifEnumOrientation | 1,382 | 1,382 | **no** |
| EXIFOrientation | 1,382 | 1,382 | **no** |
| EXIFCaptureTime | 1,307 | 1,307 | **no** |
| ExifEnumSoftware | 1,296 | 1,296 | **no** |
| ExifEnumDateTimeOriginal | 1,027 | 1,027 | **no** |
| ExifEnumColorSpace | 1,011 | 1,011 | **no** |
| ExifEnumDateTime | 936 | 936 | **no** |
| ExifEnumImageWidth | 845 | 845 | **no** |
| ExifEnumImageLength | 845 | 845 | **no** |
| ExifEnumPixelXDimension | 814 | 814 | **no** |
| ExifEnumPixelYDimension | 814 | 814 | **no** |
| MetaDataPixelResolution | 814 | 814 | **no** |
| ExifEnumSubsecTimeOriginal | 808 | 808 | **no** |
| ExifEnumMake | 730 | 730 | **no** |
| ExifEnumModel | 730 | 730 | **no** |
| EXIFCameraMaker | 730 | 730 | **no** |
| EXIFCameraModel | 730 | 730 | **no** |
| ExifEnumISOSpeedRatings | 713 | 713 | **no** |
| ExifEnumFlash | 713 | 713 | **no** |
| ExifEnumFocalLength | 713 | 713 | **no** |
| ExifEnumApertureValue | 710 | 710 | **no** |
| ExifEnumExposureTime | 707 | 707 | **no** |
| ExifEnumXResolution | 702 | 702 | **no** |
| ExifEnumYResolution | 702 | 702 | **no** |
| ExifEnumResolutionUnit | 702 | 702 | **no** |
| MetaDataResolution | 702 | 702 | **no** |
| ExifEnumWhiteBalance | 693 | 693 | **no** |
| ExifEnumDateTimeDigitized | 656 | 656 | **no** |
| ExifEnumExifVersion | 639 | 639 | **no** |
| ExifEnumFNumber | 633 | 633 | **no** |
| ExifEnumMeteringMode | 622 | 622 | **no** |
| ExifEnumYCbCrPositioning | 511 | 511 | **no** |
| ExifEnumShutterSpeedValue | 498 | 498 | **no** |
| ExifEnumFocalLengthIn35mmFilm | 497 | 497 | **no** |
| ExifEnumExposureProgram | 490 | 490 | **no** |
| ExifEnumSceneCaptureType | 489 | 489 | **no** |
| ExifEnumComponentsConfiguration | 474 | 474 | **no** |
| ExifEnumBrightnessValue | 473 | 473 | **no** |
| ExifEnumSubsecTimeDigitized | 450 | 450 | **no** |
| ExifEnumExposureBiasValue | 443 | 443 | **no** |
| ExifEnumMaxApertureValue | 443 | 443 | **no** |
| ExifEnumSubsecTime | 439 | 439 | **no** |
| ExifEnumLightSource | 431 | 431 | **no** |
| ExifEnumExposureMode | 422 | 422 | **no** |
| ExifEnumFlashpixVersion | 406 | 406 | **no** |
| ExifEnumImageUniqueID | 407 | 339 | **no** |
| ExifEnumSceneType | 320 | 320 | **no** |
| CoreFileSystemFileSystemNodeCreationTime | 165,340 | 284 | **no** |
| ExifEnumDigitalZoomRatio | 282 | 282 | **no** |
| ExifEnumContrast | 231 | 231 | **no** |
| ExifEnumSaturation | 231 | 231 | **no** |
| ExifEnumSharpness | 231 | 231 | **no** |
| ExifEnumGPSLatitudeRef | 122 | 122 | **no** |
| ExifEnumGPSLatitude | 122 | 122 | **no** |
| ExifEnumGPSLongitudeRef | 122 | 122 | **no** |
| ExifEnumGPSLongitude | 122 | 122 | **no** |
| MetaDataLatitudeAndLongitude | 122 | 122 | **no** |
| ExifEnumGPSAltitudeRef | 107 | 107 | **no** |
| ExifEnumGPSAltitude | 107 | 107 | **no** |
| ExifEnumGPSTimeStamp | 107 | 107 | **no** |
| ExifEnumGPSDateStamp | 107 | 107 | **no** |
| ExifEnumSensingMethod | 101 | 101 | **no** |
| ExifEnumGPSVersionID | 83 | 83 | **no** |
| ExifEnumPhotometricInterpretation | 81 | 81 | **no** |
| ExifEnumBitsPerSample | 79 | 79 | **no** |
| ExifEnumSamplesPerPixel | 79 | 79 | **no** |
| ExifEnumGPSProcessingMethod | 23 | 23 | **no** |
| ExifEnumArtist | 16 | 15 | **no** |
| ExifEnumYCbCrSubSampling | 14 | 14 | **no** |
| ExifEnumCopyright | 11 | 11 | **no** |
| ExifEnumReferenceBlackWhite | 8 | 8 | **no** |
| ExifEnumImageDescription | 23 | 7 | **no** |
| ExifEnumFocalPlaneXResolution | 5 | 5 | **no** |
| ExifEnumFocalPlaneYResolution | 5 | 5 | **no** |
| ExifEnumFocalPlaneResolutionUnit | 5 | 5 | **no** |
| ExifEnumCustomRendered | 5 | 5 | **no** |
| ExifEnumGPSDOP | 3 | 3 | **no** |
| ExifEnumSubjectArea | 2 | 2 | **no** |
| ExifEnumWhitePoint | 1 | 1 | **no** |
| ExifEnumPrimaryChromaticities | 1 | 1 | **no** |
| ExifEnumYCbCrCoefficients | 1 | 1 | **no** |
| Capture datetime | 1 | 1 | **no** |
| Width | 1 | 1 | **no** |
| Height | 1 | 1 | **no** |
| Duration | 1 | 1 | **no** |
| ExifEnumFileSource | 1 | 1 | **no** |
| ExifEnumGainControl | 1 | 1 | **no** |
| ExifEnumSubjectDistanceRange | 1 | 1 | **no** |
| CoreFileSystemFileSystemNodeDeletedTime | 165,340 | 0 | **no** |
| CoreFileSystemFileSystemNodeChangeTime | 165,340 | 0 | **no** |

## `<accessInfo>` timestamps on files

| Timestamp name | Count |
|---|---:|
| ModifyTime | 91,380 |
| AccessTime | 21,417 |
| CreationTime | 284 |
