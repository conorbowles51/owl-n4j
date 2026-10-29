# 3. Sample extraction structure

Read-only analysis on 2026-10-29 of the three local samples, structure only: element and attribute names,
counts, sizes, types, versions. No content. Zips read with `unzip -l` / `unzip -Z1`; inner XML streamed with
iterparse.

**Corrections since:** the three samples are from the case later called the 10-report case (local C3 =
A-C3, C9 = A-C9; local C8 is a different export of A-C8, see `../measurements/README.md`). Spec 01 found
the `images`, `HashSetsInfo`, `carvedFiles`, `infectedFiles` and `extraInfos` sections present but empty in
all three, and that C8's `.xmlModel` section parses completely (only `.xmlTagged`, the file index, is cut
off). Spec 05 found C8's file index lists 1,081 Database-tagged files, none of them on disk.

## 1. What each sample is

None is a UFDR or a Reader package. All three are **Physical Analyzer XML report exports**: one XML file
plus sibling media folders following the `files/<Category>/` convention. Nothing has a .ufdr, .ufd or .ufdx
extension.

- **C3** (zip 640 MB, 812 MB uncompressed; extracted folder 805 MB, 43,144 files, matching the zip's
  non-`__MACOSX` entries; the XML MD5 is identical inside and outside the zip):
  - one report XML of 177.7 MB
  - `files/`: Image 33,585, Text 7,369, Video 920, Audio 834, Archives 115, Uncategorized 2
  - `chats/` (330) in five app folders: WhatsApp, Facebook Messenger, Native Messages, Instagram, Telegram
  - `contacts/` (7)
- **C9.zip** (1.2 GB, 1.78 GB uncompressed): one report folder with 29,673 real files plus 29,784
  `__MACOSX` AppleDouble entries:
  - report XML of 80.3 MB
  - `files/`: Image 22,477, Text 5,568, Audio 825, Video 448, Archives 132 (Android .apex up to 115 MB),
    Document 8, Uncategorized 5
  - `contacts/` (130), `chats/` (122), `photos/` (60), `useraccounts/` (4); `.DS_Store` throughout
- **C8 folder** (3.2 GB, 2,549 files), no complete XML:
  - `.xmlModel` 94.5 MB and `.xmlTagged` 29.3 MB
  - six zero-byte siblings: `.xmlExtra`, `.xmlLast`, `.xmlMdfSource`, `.xmlModelSource`, `.xmlNodeSource`,
    `.xmlTranslation`
  - `files/` (1,768 files, 2.9 GB): Application, Archives, Audio, Configuration, Database, Document, Image,
    Video; mostly .so, .apk, .odex, .jar
  - `chats/` (220), `contacts/` (16), `thumbnails/` (518), `FileUploads/` (18), `SocialMedia/` (1)

Both zips were made on macOS (`__MACOSX/`, `.DS_Store`); about half of all zip entries are AppleDouble files.

## 2. XML header facts

| | C3 | C9 | C8 |
|---|---|---|---|
| Root | `project` | `project` | `.xmlTagged`: `project`; `.xmlModel`: bare `decodedData`, no XML declaration, no namespace |
| Namespace | `http://pa.cellebrite.com/report/2.0` | same | same (Tagged part only) |
| `reportVersion` | 7.48 | 7.48 | 8.5 |
| `UFED_PA_Version` | 7.59.x | present | 10.4.1.x |
| `extractionType` | Legacy | FileSystem | FileSystem |
| `extractionInfo` entries | 3 (a device full-file-system acquisition, plus 2 Logical "Cellebrite Reports") | 2 | 3 |
| NodeCount / ModelCount | 43,043 / 16,661 | 29,536 / 2,941 | 72,849 / 37,011 |
| Time zone configuration | present (DST on, convert-to-UTC on, a selected zone) | present (convert-to-UTC off) plus a "Time zone settings (ID)" metadata item | absent (in the missing tail) |

`project` also carries `id`, `name`, `containsGarbage`; C3 and C9 add `licenseID`; C8 adds `MediaResults`.
`caseInformation` has nine fields (Examiner name, Location, Case number, Case name, Evidence number,
Department, Organization, Investigator, Crime type), each with `fieldType`, `isSystem`, `isRequired`,
`multipleLines`.

`metadata section="Extraction Data"`, keyed by `sourceExtraction`:
- all three: DeviceInfoExtractionStart/EndDateTime, DeviceInfoSelectedManufacturer,
  DeviceInfoSelectedDeviceName, DeviceInfoUnitIdentifier, DeviceInfoUnitVersion, ExtractionType,
  GlobalMachineName, ProjectStateExtractionId, **UFDIntegrity**, DeviceInfoReportType,
  DeviceInfoConnectionType (always empty)
- C3 additionally: IMEI, IMSI, ICCID (6), MSISDN (4), Model, Vendor, Android ID, Bluetooth and MAC
  addresses, Advertising ID, Factory number, OS type, carrier name, activation time, location-services flags
- C8: the thinnest set, with no IMEI or MSISDN

"Additional Fields" holds DeviceInfoCreationTime (DD/MM/YYYY) and UFED_PA_Version. Per-file hashes: MD5 on
100% of tagged files; SHA256 on 224 (C3), 80 (C9), 3 (C8).

## 3. Model types and counts (top-level)

**C3** (top-level 16,663): VisitedPage 6,936; NetworkUsage 5,181; Call 1,657; Contact 1,612; Chat 303; Email
294; Password 273; InstantMessage 201 top-level; CalendarEntry 80; UserAccount 34; Location 31; small types.
Nested: InstantMessage 2,917 in total, Party 7,504, Attachment 456, KeyValueModel 40,178, UserID 1,627,
PhoneNumber 625, ContactPhoto 554, ProfilePicture 424, MessageLabel 158, ChatActivity 34, Reply 22,
Forwarded 11. Deleted state: almost all Intact (Chat 1 Deleted, ProfilePicture 3 Deleted, CalendarEntry 1
Trash; Party mostly "Unknown"). Sources: calls mostly WhatsApp then Facebook Messenger; chats WhatsApp,
Facebook Messenger, Native Messages, Instagram, Telegram; email Gmail.

**C9** (2,941): Call 1,391; DictionaryWord 640; Password 288; Contact 235; VisitedPage 213; Chat 114. Nested:
InstantMessage 3,421, Attachment 874, Party 6,143. Deleted: InstantMessage 7 Trash 1 Deleted; Attachment 7
Trash 1 Deleted; Chat 1 Deleted. Sources: Telegram and WhatsApp dominate.

**C8** (37,013): NetworkUsage 20,961; DictionaryWord 4,648; VisitedPage 4,129; Cookie 3,302;
SocialMediaActivity 825; SearchedItem 752; Password 517; InstalledApplication 440; WirelessNetwork 284;
Call 269; Contact 241; Location 206; Email 108; Chat 94; plus Note, FileUpload, FileDownload,
DeviceInfoEntry and others. Nested: InstantMessage 2,829, Attachment 3,770, KeyValueModel 24,041. **Much
heavier deletion**: InstantMessage 802 Deleted of 2,829; Call 62 of 269; Chat 23 of 94; Attachment 104
Deleted, 615 Unknown; Party 552 Deleted. Some Cookie source names are localised (Spanish).

`decoding_confidence` is "High" on every model in all three. Element kinds inside a model: `field`,
`modelField`, `multiModelField`, `multiField`, `nodeField`, `dataField` (containing `source length=` or
`empty`), and `jumptargets/targetid[@ismodel]`. Model attributes include `file_id`, `source_index`,
`labels`, `isrelated`, `extractionId`; C8 also `originalId`.

## 4. How records reference files

Three independent mechanisms:

1. **`taggedFiles/file`** with an `id` and a "Local Path" metadata item (backslash form), plus MD5, Tags and
   file-system times. In 7.48 `file` has no `name` attribute; in 8.5 it has `name`, `imageFormat`,
   `decodedApplication`, `labels`. Local Path present on disk: C3 42,814 / 43,043 (99.5%); C9 29,456 / 29,536
   (99.7%); C8 1,734 / 11,663 parsed (14.9%, file index cut off).
2. **`jumptargets/targetid` with `ismodel="false"`** pointing at file ids: C3 709 resolved (16,370 point at
   models); C9 877 resolved, 2 not; C8 216 resolved, 275 not.
3. **The Attachment record's `file_id` attribute** (C3 404/404, C9 759/759, C8 83/132 resolved) and its
   **`attachment_extracted_path`** field (C3 417, C9 760, C8 127 attachments) pointing into `chats/`,
   `contacts/`, `photos/`, `useraccounts/`, `SocialMedia/`, which are **not in `taggedFiles`**. Every such
   path exists on disk: C3 419/419, C9 852/852, C8 143/143.

## 5. The split C8 files (inference)

These look like Physical Analyzer's intermediate section files during XML report generation, joined into the
final `.xml` at the end. C8 fits a generation that was interrupted: the Tagged part stops mid-element at line
260,037; the trailing parts are zero bytes; no joined `.xml`; "(1)" in the name suggests a repeat attempt. Not
a macOS unzip artifact (no `__MACOSX`, systematic pattern).

## 6. Would the parsers recognise each sample?

**v1:** `detect_cellebrite_xml` (`ingestion/scripts/cellebrite/ingestion.py:134-180`) searches `*.xml` to
depth 6 with the namespace in the first 4 KB. Parsing makes three iterparse passes (`parser.py:223`, `:468`,
`:658`); file linking resolves Local Path (`file_linker.py:115-150`) and links models to files only through
`jumptargets ismodel=false` (`:373-404`). C3 folder recognised; zips not (no zip handling; once extracted the
search finds it); C8 not recognised (no `*.xml`).

**Loupe's old code:** `detection.py:18` calls `ingestion.py:104-122`, which globs `*.xml` at the top level only.
C3 recognised if the report folder itself is passed; extracted C9 only if the inner folder is passed; C8 not;
zips not.

**Both:** model children handled are `field`, `modelField`, `multiModelField`, `jumptargets` only;
`multiField` (C8 15,607, C3 6,270), `nodeField` and `dataField` dropped. Neither uses the Attachment
`file_id` or `attachment_extracted_path`, so chat and contact media under `chats/`, `contacts/`, `photos/` is
never linked although 100% is on disk. v1's type list covers C8's SocialMediaActivity, Cookie, FileUpload,
Note, InstalledApplication, FileDownload, DeviceConnectivity, DictionaryWord; Loupe's old list covers none of
them (about 10.3k top-level C8 models). Neither covers DeviceInfoEntry.

## 7. Things that would trip a parser

- C8: namespace-less fragment root, truncated XML, no time zone block.
- Single field values up to 155,838 characters (C3); nesting depth 12.
- In 7.48 `file` has no `name` attribute.
- `deleted` takes Intact, "null" (465 in C3, 502 in C9) and missing; `deleted_state` includes Trash and Unknown.
- Convert-to-UTC on in C3, off in C9.
- "Additional Fields" dates are DD/MM/YYYY strings.
- Header ModelCount differs by 2 from counted top-level models in C3 and C8.
- About half of zip entries are AppleDouble, plus `.DS_Store`.
- C9 `files/Archives` holds .apex images up to 115 MB; C8 `files/` is 2.9 GB of mostly system binaries.
- Localised app names in Source fields.
- v1 makes three full passes over a 178 MB XML.
