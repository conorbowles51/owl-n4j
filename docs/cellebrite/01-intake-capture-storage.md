# Cellebrite rebuild, part 1: intake, capture, storage, reconciliation and the job

Status: specification, nothing built. Written 2026-10-29. Details sections 2, 3, 6.1, 6.2, 6.3, 6.7
(time storage only) and phases 0 to 2 of section 7 of `docs/cellebrite-rebuild-plan.md`, whose
standing decisions (section 1) this file does not revisit.

## Purpose

This file specifies how a phone extraction gets from the investigator's upload into Postgres with
nothing lost and with proof that nothing was lost. It covers recognising every input form
(including protected UFDRs and truncated split exports), hashing the container and the report XML
before anything is touched, one streaming capture pass that keeps every element, attribute and
value, the Postgres tables that hold the capture, verification of the files the report points
at, the element-level reconciliation that fails an ingest on any difference, how timestamps are
stored, the dedicated queue and worker that run all of it, and which existing Loupe Cellebrite
ingestion code is removed. Interpretation, projections and views are in later files. Every claim
about code carries a `path:line` read on branch `integration/evidence-main-reunion` on 2026-10-29.
Every claim about data comes from a measurement on the local samples (C3, C9, C8), from the
scratchpad catalogues of the 14 server phones, or from v1's `owl_ingest_report.json` files. No
measurement script printed or stored evidence content.

## Contents

1. Measurements this specification rests on
2. Intake: input forms, detection, what is recorded and said
3. Hashing and the integrity chain
4. Upload path: what is kept, changed and replaced
5. Capture: the single streaming pass
6. Postgres schema
7. Files: index, verification, attachment mechanisms, storage
8. Reconciliation
9. Time storage
10. The job: queue, worker, progress, pause, resume, cancel, staged replace
11. Removal of Loupe's existing Cellebrite ingestion
12. Units for phases 0 to 2 with acceptance tests
13. Decisions not settled by the plan
14. Not yet established

---

## 1. Measurements this specification rests on

All measured on Neil's Mac (Apple Silicon, 10 cores, 16 GB), system Python 3.14 with stdlib
`xml.etree.ElementTree` (expat) and `lxml` 6.0.2 (libxml2). Scripts are in the session scratchpad
(`measure_counter.py`, `proto_capture.py`, `lxml_counter.py`, `verify.py`, `verify2.py`,
`tsshape.py`, `tsoff.py`, `dupids.py`, `measure_records.py`); they print counts only.

### 1.1 Containers

| | C3 | C9 | C8 |
|---|---|---|---|
| Form on disk | folder, and a zip of it | zip only | folder of split sections |
| Zip entries total | 86,334 | 59,568 | n/a |
| `__MACOSX/` entries | 43,167 | 29,784 | n/a |
| AppleDouble `._*` names | 43,183 | 29,796 | 0 |
| `.DS_Store` | 12 in zip, 1 in folder | 20 | 0 |
| Real files | 43,144 (folder) | 29,784 | 2,549 |
| Wrapping folder in the zip | yes, one | yes, one | n/a |
| Report XML depth in zip | 2 (inside wrapper) | 2 (inside wrapper) | n/a |
| Report XML size / compressed | 177.7 MB / 11.5 MB | 80.3 MB / 3.7 MB | `.xmlModel` 94.5 MB, `.xmlTagged` 29.3 MB, six zero-byte siblings |
| Uncompressed total | 812 MB | 1.78 GB | 3.2 GB on disk |
| Encrypted zip entries | 0 | 0 | n/a |
| First four bytes | `50 4B 03 04` | `50 4B 03 04` | n/a |

C8 split sections: `.xmlModel` has root `decodedData`, **no XML declaration and no namespace**,
and ends with a complete `</decodedData>`. `.xmlTagged` has an XML declaration, root `project`
with the namespace `http://pa.cellebrite.com/report/2.0`, and is cut off inside
`project/taggedFiles/file/metadata` (expat: line 260037 column 8; libxml2: same line, column 54).
`.xmlExtra`, `.xmlLast`, `.xmlMdfSource`, `.xmlModelSource`, `.xmlNodeSource`, `.xmlTranslation`
are zero bytes. Consequence: a namespace sniff on the first 4 KB finds `.xmlTagged` and misses
`.xmlModel` entirely, and IPED's header-string test (`"project id"`, `"extractionType"`,
`"sourceExtractions"`, `UfedXmlReader.java:102`) also rejects `.xmlModel`.

### 1.2 Report XML structure

| Measure | C3 | C9 | C8 (both sections) |
|---|---|---|---|
| Elements | 1,451,062 | 689,601 | 1,269,819 |
| Attributes | 3,448,982 | 1,674,326 | 2,743,889 |
| Non-whitespace text nodes | 653,473 | 284,541 | 574,716 |
| Text bytes (UTF-8) | 31.6 MB | 5.8 MB | 15.4 MB |
| Longest single text | 155,838 chars | 37,075 | 108,918 |
| Whitespace-only text nodes | 522,070 | 205,408 | 619,058 |
| Non-whitespace tails (mixed content) | 0 | 0 | 0 |
| Comments / processing instructions | 0 / 0 | 0 / 0 | 0 / 0 |
| Max depth | 12 | 12 | 9 |
| Distinct qualified paths (section 8.1) | 879 | 706 | 1,120 |
| Distinct (path, attribute) | 1,826 | 1,458 | 2,327 |
| Top-level records | 16,663 | 2,941 | 37,013 |
| Nested records | 54,382 | 11,064 | 36,624 |
| `<value>` elements | 243,124 | 72,429 | 461,571 |
| `<file>` under `taggedFiles` | 43,043 | 29,536 | 11,663 complete + 1 cut off |
| `project@ModelCount` | 16,661 | 2,941 | 37,011 |
| v1 `total_xml_models` (server copy) | 16,663 | 2,941 | 36,979 |

`project@ModelCount` does not equal the number of top-level `model` elements in C3 (16,661 vs
16,663) or C8 (37,011 vs 37,013). It cannot be used as the completeness check.

libxml2 and expat produce identical element, attribute and text counts on all three, including
the truncated C8 section.

Every report section present: `sourceExtractions/extractionInfo` (3, 2, 3), `caseInformation/field`
(9 each), `metadata[section]` (C3: Additional Fields, Extraction Data, Device Info; C9 and C8:
Additional Fields, Extraction Data), `images`, `HashSetsInfo`, `MalwareScanner@ScanPerformed`,
`taggedFiles`, `decodedData`, `carvedFiles`, `infectedFiles`, `extraInfos`,
`projectConfigurations/timeZoneConfigurations`. In C8 the last five are absent because the file is
cut off before them. `images`, `HashSetsInfo`, `carvedFiles`, `infectedFiles` and `extraInfos`
have **no children in any of the three samples**; whether they are populated on any server phone
is not established. Everything outside records and tagged files (the "skeleton", section 5.3)
serialises to 14.0 KB (C3), 7.1 KB (C9), 8.8 KB (C8).

### 1.3 Record shape

| | C3 | C9 | C8 |
|---|---|---|---|
| Units per top-level record (elements + attributes), median / p99 / max | 70 / 1,253 / 36,668 | 69 / 3,878 / 33,390 | 89 / 242 / 98,679 |
| Text bytes per top-level record, max | 157,956 | 71,272 | 133,279 |
| Models in one top-level record, max | 797 | 732 | 1,485 |
| Largest record type | Chat | Chat | Chat |
| Model `id` values occurring more than once | 64 ids, 3,080 extra occurrences | 75 ids, 2,341 extra | 2 ids, 2 extra |
| Models with a repeated field name | 0 | 0 | 38 |

Repeated ids are nested `Party`, `PhoneNumber`, `UserID`, `KeyValueModel` repeated inside records,
`Contact` appearing top-level and nested, and a `DeviceEvent` and `PoweringEvent` sharing an id.
So **the Cellebrite model id is not a key**, and **a field name does not identify a field within
a record**. Both facts drive the locator design (section 6.4).

Across the 14 server phones (scratchpad `server_catalog.jsonl`), total models (top-level and
nested) and values:

| Phone | Models | Values |
|---|---|---|
| C9, 10-report case | 14,005 | 72,429 |
| C3, 3-phone case | 17,496 | 85,092 |
| 1-phone case | 32,332 | 262,355 |
| C1, 10-report case (2023 report; whether the same device as the 2022 C1 is not established) | 44,949 | 153,000 |
| C7, 10-report case | 55,361 | 297,253 |
| C5, 10-report case | 70,487 | 306,679 |
| C3, 10-report case | 71,045 | 243,124 |
| C8, 10-report case | 73,608 | 401,963 |
| C1, 10-report case (2022 extraction) | 140,608 | 639,775 |
| C2, 10-report case | 251,466 | 1,061,373 |
| C4, 10-report case | 290,509 | 1,344,612 |
| C2, 3-phone case | 523,024 | 2,455,992 |
| C6, 10-report case | 694,406 | 3,187,007 |
| C1, 3-phone case | 967,543 | 4,697,578 |

The largest phone is C1 of the 3-phone case: 338,715 top-level records (plan section 9), 967,543
models, 4.70 M values. Elements per value in the local samples are 2.8 (C3) and 2.3 (C8) inside
`decodedData`, so the largest phone's record section is in the order of 11 to 14 million
elements before tagged files. Its tagged file count is not established.

### 1.4 Prototype capture (the design in section 5, run on the samples)

| | C3 | C9 | C8 |
|---|---|---|---|
| Wall time (parse, encode, recount; no database) | 11.3 s | 6.2 s | 8.5 s |
| Peak RSS | 38.9 MB | 80.9 MB (reading from inside the zip) | 36.8 MB |
| Record rows | 71,045 | 14,005 | 73,637 |
| Record JSON | 68.7 MB | 13.3 MB | 82.8 MB |
| Largest record row | 164.1 KB | 39.4 KB | 121.0 KB |
| File rows | 43,043 | 29,536 | 11,663 (+1 partial) |
| File JSON | 94.0 MB | 59.7 MB | 27.6 MB |
| Recount from capture equals source (elements, attributes, texts) | yes | yes | yes, including the partial element |

The independent libxml2 counter ran in 3.6 s (C3), 2.0 s (C9), 2.7 s (C8).

### 1.5 Tagged files against the bytes on disk

| Outcome | C3 | C9 | C8 |
|---|---|---|---|
| MD5 match | 21,155 | 29,456 | 1,172 |
| File absent from the export | 224 (all carry SHA256) | 80 | 9,929 |
| On disk, zero bytes, report size 0, report MD5 is not the empty-content MD5 | 21,664 | 0 | 0 |
| On disk, zero bytes, report size greater than 0 | 0 | 0 | 325 |
| On disk, same size, MD5 differs | 0 | 0 | 236 (all `Application`: `.so`, `.apk`, `.odex`, `.jar`) |
| On disk, size and MD5 differ | 0 | 0 | 1 |
| Bytes hashed / time | 623 MB / 6.6 s | 1,695 MB / 9.5 s (from inside the zip) | 3,146 MB / 8.4 s |
| Tagged files sharing one content with another tagged file | 21,664 ids in 1 content (the empty one) | 228 ids in 26 contents | 327 ids in 2 contents |
| Two file ids with one Local Path | 0 | 0 | 0 |

The 21,664 zero-byte C3 files are mostly Image (5,373 without extension, 3,869 `.png`, 1,700
`.0`, 776 `.jpg`), Text, Video and Audio: the production contains a placeholder where the report
describes a real file. This is a fourth outcome, distinct from a mismatch (section 7.2).

Attachment references (scratchpad `c*.json`): jump targets with `ismodel="false"` 709, 879, 491;
of the jump target ids, those matching a tagged file id 709, 877, 166; Attachment records 456, 874,
3,770; `attachment_extracted_path` fields 417, 760, 127; record values that are paths under
`chats/`, `files/`, `contacts/`, `photos/`, `useraccounts/`, `socialmedia/` 419, 852, 143, all
present on disk. Model attributes include `file_id` in all three.

### 1.6 Timestamps

| | C3 | C9 | C8 |
|---|---|---|---|
| `value[type=TimeStamp]` | 22,881 | 5,218 | 59,672 |
| with `+00:00` | 22,859 | 5,218 | 59,666 |
| with no offset | 22 (Location.TimeStamp 21, CalendarEntry.RepeatUntil 1) | 0 | 6 (Location.TimeStamp) |
| carry `formattedTimestamp` | all | all | all |
| text equals `formattedTimestamp` | 0 (text has milliseconds, the attribute does not) | 0 | 0 |
| `file/accessInfo/timestamp`, all `+00:00` | 42,850 | 10,733 | 10,840 |
| `timeZoneConfigurations@selectedTimeZone` | an IANA name prefixed `_`, UTC+0 zone | `_America/New_York` | absent (cut off) |
| `@enableAutomaticallyConvertToUTC` | True | False | absent |

C9 has conversion to UTC switched off yet every value carries `+00:00`; on this one sample the
setting does not change what the XML stores. Metadata dates use other forms: `M/DD/YYYY HH:MM:SS AM
-HH:MM` (C8 extraction start and end), `DD/DD/YYYY HH:MM:SS` with no offset (C8 creation time),
EXIF `YYYY:MM:DD HH:MM:SS` with no offset, and `M/DD/YYYY H:MM:SS PM` with no offset.

### 1.7 v1 durations (server `owl_ingest_report.json`)

| Phone | Top-level records | v1 minutes |
|---|---|---|
| 1-phone case | 2,151 | 39.3 |
| C9, 10-report case | 2,941 | 1.1 |
| C3, 3-phone | 6,915 | 21.5 |
| C1, 10-report case (2023) | 9,910 | 50.2 |
| C1, 10-report case (2022) | 15,206 | 7.8 |
| C3, 10-report case | 16,663 | 63.5 |
| C7, 10-report case | 20,863 | 53.0 |
| C5, 10-report case | 25,596 | 200.4 |
| C8, 10-report case | 36,979 | 4.5 |
| C6, 10-report case | 59,835 | 31.9 |
| C2, 3-phone | 116,967 | 292.1 |
| C4, 10-report case | 117,803 | 10.6 |
| C2, 10-report case | 121,076 | 19.1 |
| C1, 3-phone | 338,715 | 173.0 |

v1 kept a subset of the data (plan 3.1), so these are not like-for-like.

---

## 2. Intake: input forms, detection, what is recorded and said

### 2.1 Forms

| Form | Recognised by | Report documents |
|---|---|---|
| **UFDR** | file name ends `.ufdr`, or a zip whose root holds `report.xml` or `Report.xml` (IPED `UfedXmlReader.java:188-194`) | the one root `report.xml` |
| **Zip of a report folder** | zip that is not a UFDR, containing a report root (2.3) at any depth | per report root |
| **Report folder** (browser folder upload or a folder on the evidence volume) | a directory containing a report root at any depth | per report root |
| **Split-section export** | files sharing one stem with suffixes from the set in 2.2 | the non-empty sections |
| **Protected UFDR** | UFDR whose `report.xml` is encrypted in the zip, starts with `2D 06 52 6D`, or lacks the header strings | none readable |

### 2.2 Split-section suffixes

Measured on C8: `.xmlModel` (records, root `decodedData`), `.xmlTagged` (root `project`: header,
case information, metadata, tagged files and, if complete, the trailing sections), and
`.xmlExtra`, `.xmlLast`, `.xmlMdfSource`, `.xmlModelSource`, `.xmlNodeSource`, `.xmlTranslation`.
Any file whose suffix matches `^\.xml[A-Z][A-Za-z]+$` and whose stem equals a sibling's stem is
treated as a section of the same report; unknown suffixes are kept as sections with role
`unknown` and are parsed and captured like any other (decision: types are discovered, plan 1.4,
and the same holds for section suffixes).

### 2.3 Detection algorithm

Input: a path on the evidence volume (directory, zip, `.ufdr`, or a single XML). Output: an
`IntakeClassification` (2.5). Detection never writes and never extracts.

1. **Classify the container.**
   - Directory: walk it; ignore names in the skip set (step 2).
   - Regular file: read the first 4 bytes. `50 4B 03 04`, `50 4B 05 06` (empty zip) or
     `50 4B 07 08` is a zip; open with `zipfile.ZipFile` and use the central directory only.
     Otherwise, if the name ends `.xml` or matches the split suffix rule, treat as a single
     document. Anything else: `not_a_phone_report`.
2. **Skip set.** Any path component equal to `__MACOSX`, any final component starting `._`, and
   final components `.DS_Store`, `Thumbs.db`, `desktop.ini` (the same set as
   `backend/routers/evidence_upload_groups.py:37,192` and `backend/routers/evidence.py:64`).
   Skipped entries are counted and recorded (`skipped_entries` with a count per rule), never
   silently dropped.
3. **UFDR check** (zip only). If `report.xml` or `Report.xml` exists at the zip root:
   - if the entry's general-purpose flag bit 0 is set: `protected_password`;
   - read its first 1,024 bytes (`UfedXmlReader.java:104,175`): if bytes 0 to 3 are
     `2D 06 52 6D`: `protected_no_password` (`UfedXmlReader.java:103,204-207`);
   - if none of `project id`, `extractionType`, `sourceExtractions` occurs in those bytes:
     `protected_or_invalid` (IPED's message: "XML report is not valid. Protection may be
     enabled", `UfedXmlReader.java:315-317`);
   - otherwise `ufdr` with one report root at `""`.
4. **Report roots** (zip without root `report.xml`, or directory). For every non-skipped entry
   whose name ends `.xml` (case-insensitive) or matches the split suffix rule, read up to the first
   8 KB (from the zip member stream or the file) and decide:
   - *full report document*: the bytes contain `http://pa.cellebrite.com/report/2.0` and the
     first start tag is `project`;
   - *section document*: the name matches the split suffix rule and either the bytes contain
     the namespace, or the first start tag is `decodedData` (measured on C8 `.xmlModel`: no
     namespace, no declaration). Zero-byte sections are recorded with role from the suffix and
     `empty=true`.
   Plain `.xml` files that are neither (C9 holds 2,410 extracted `.xml` files under `files/`) are
   ignored as report candidates.
   A report root is the directory of a full report document, or the directory holding a group of
   section documents sharing a stem.
5. **Nested roots.** If one root is an ancestor of another, the outer root owns the subtree and
   the inner one is recorded as `nested_report_ignored` with its path (the rule already in
   `evidence_upload_groups.py:242-245`), unless the outer root has no report document of its own,
   in which case it is not a root. Two sibling roots in one container are two extractions:
   documents arriving together need not be related (CLAUDE.md, Design rules).
6. **Several full documents in one root.** Two full report XMLs in one directory: each is its
   own extraction candidate and the classification says `multiple_reports_in_folder`; both are
   captured, each sharing the folder's files. Not seen in the samples.
7. **Split completeness check** (cheap): for each non-empty section, read the last 4 KB and test
   whether the document's root end tag (`</decodedData>` or `</project>`) is present after
   trailing whitespace. A missing end tag classifies the section `suspected_truncated`. The
   authoritative answer comes from the parse (5.6); this pre-check exists only to tell the
   investigator before the job runs.
8. Return the classification.

### 2.4 What the investigator is told

UI copy, no em dashes, said in the upload receipt and on the extraction's profile. Variables in
braces.

| Classification | Recorded | Message |
|---|---|---|
| `ufdr`, `folder`, `zip` (one root) | container row, document rows | "Phone report found: {document name}. It will be read in full and checked element by element." |
| several roots | one candidate per root | "{n} phone reports found in this upload. Each is read and checked separately." |
| `split_sections` complete | document per section | "This report was exported in sections. {k} sections contain data and will be read: {list}. {e} sections are empty." |
| `split_sections`, a section `suspected_truncated` | as above, flag | "The {section} section of this report ends partway through. Everything up to that point will be read and kept, and the report will be marked incomplete. The full section would be needed from whoever produced it to see the rest." |
| `protected_no_password` | container row and hashes, no extraction | "This UFDR file is protected. Loupe does not open protected UFDRs. An unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it." |
| `protected_password` | same | "This UFDR file is password protected. Loupe does not open protected UFDRs. An unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it." |
| `protected_or_invalid` | same | "The report inside this UFDR file cannot be read. It may be protected. An unprotected copy, or the report exported as an XML report folder, is needed from whoever produced it." |
| `not_a_phone_report` (via the phone path) | container row only | "No phone report was found in this upload. The files are kept as ordinary evidence." |
| `nested_report_ignored` | note on the outer extraction | "A second report was found inside this one at {path}. It is treated as part of the outer report." |
| skipped entries | counts | "{n} system files added by the computer that made this archive were left out (for example Mac resource files). They are not part of the export." |

Advice to "re-export" or "decrypt in Reader" is not given: the reader of these messages receives
productions and cannot produce them. "Needed from whoever produced it" states the fact without
telling her how to get it.

### 2.5 `IntakeClassification` shape (engine, Pydantic)

```json
{
  "container_kind": "ufdr|zip|folder|single_document",
  "outcome": "readable|protected_no_password|protected_password|protected_or_invalid|not_a_phone_report",
  "skipped_entries": {"__MACOSX": 29784, "appledouble": 12, "ds_store": 20},
  "roots": [
    {"root_path": "220..._Report", "form": "full|split_sections|ufdr",
     "documents": [{"path": "...xmlModel", "role": "model|tagged|full|extra|last|mdf_source|model_source|node_source|translation|unknown",
                    "size": 94462045, "empty": false, "root_element": "decodedData",
                    "has_namespace": false, "suspected_truncated": false}],
     "nested_report_ignored": []}
  ],
  "messages": [{"code": "split_sections", "text": "..."}]
}
```

---

## 3. Hashing and the integrity chain

Order of operations, all before any other processing of the container:

1. **Container as received.** For an upload, the browser computed SHA-256 per 4 MiB chunk and for
   the whole file; the backend verifies each chunk on receipt and the whole file on assembly
   (`backend/routers/evidence_uploads.py:118-130,154-180`) and again when copying into the group
   payload (`evidence_upload_groups.py:162-179`). The intake job then reads the stored container
   once and computes **SHA-256 and MD5** of the bytes (two digests in one read; MD5 because
   Cellebrite and examiners quote MD5). The upload's SHA-256 and the job's SHA-256 must agree;
   a difference sets `outcome=container_changed_since_upload` and stops the job (the stored bytes
   are no longer what was received; flagging and continuing would capture something nobody
   received). For a folder, the container hash is the SHA-256 of the sorted manifest lines
   `"{sha256}  {size}  {relative path}\n"` over every non-skipped file, and each member keeps its
   own hash from the upload manifest.
2. **Report documents.** Each report XML (full, or each section) is hashed SHA-256 and MD5 during
   the counter pass (8.2), which reads every byte. For a zip or UFDR the digest is over the
   decompressed member bytes; the zip's stored CRC-32 is also checked by `zipfile` on read.
3. **Storage.** Container digests on `phone_extraction_containers`; document digests on
   `phone_extraction_documents`; the report-set key (6.3) is derived from document digests.
4. **Nothing is deleted.** The container is never unpacked or removed by intake (section 7.5).
   This removes v1 defect 4.4 and the equivalent Loupe behaviour, where the uploaded zip is
   unlinked right after extraction (`backend/routers/evidence.py:1206-1214`).
5. **Report's own hashes.** Values in `metadata` items `UFDIntegrity`, and any content of
   `HashSetsInfo` and `images`, are captured like everything else (5.3); comparing them with a
   computed digest is a later unit, because the samples hold no image hashes to compare against
   (1.2) and `UFDIntegrity`'s meaning is not established.

---

## 4. Upload path: what is kept, changed and replaced

### 4.1 Current Loupe paths

| Path | What it does with a phone report | Fate |
|---|---|---|
| `POST /api/evidence/upload` (`backend/routers/evidence.py:1144-1305`) | multipart form capped at 20,000 files (`:1161`); `is_archive` unzips in the backend (`:1205-1217`, `_extract_archive_to_staging` `:335-394`), **deletes the zip** (`:1210-1214`), finds roots by namespace sniff (`:267-279`, `:397-429`), moves files without registering (`:1221-1239`), enqueues `/cases/{id}/cellebrite/jobs` (`:491-544`) | **Phone branch removed.** Lines `:1204-1285` collapse to: detect via the engine; if a phone report is found, answer 409 "Upload phone reports with the folder or archive upload" (the resumable path below). Ordinary files unchanged. |
| Resumable groups `POST /api/evidence-upload-groups` (`evidence_upload_groups.py:99-141`), `.../{id}/complete` (`:288-333`) | archive kind must end `.zip` (`:118-119`), group capped at `MAX_MEMBERS = 20_000` (`:35,56`) and the zip at 20,000 entries (`:187-188`); extracts every archive (`:222-235`); excludes phone roots from registration (`:238-266`); dispatches one engine job per root with a stable `request_id = uuid5(group, 'processing:'+root)` (`:261-263,276-285`) | **Kept as the only phone upload path**, with the changes in 4.2. |
| Single resumable session (`evidence_uploads.py`) | files up to 1 GiB (`:33`) | Unchanged; phone containers go through groups (member limit 8 GiB, `evidence_upload_groups.py:43`). |
| `POST /api/evidence/sync-filesystem` (`evidence.py:991-1120`) | skips report roots (`:1040-1052`) | Kept; its root test switches to the engine's detector so split sections are recognised. |

C3 (43,144 files as a folder, 43,167 real entries as a zip) and C9 (29,784 real entries) both
exceed the 20,000 limits, so **neither local sample can be uploaded through the resumable path
today**. v1 recorded one phone folder of 93,150 files (`v1_memory/feedback_upload_throughput_bottleneck.md`).

### 4.2 Changes to the resumable group path

Functions kept unchanged: `safe_path` (`:59-64`), `get_group` (`:67-75`), `snapshot` (`:83-96`),
`copy_verified` (`:162-179`), `uploads.assemble` (`evidence_uploads.py:154-180`), the receipt and
dispatch-retry state machine in `group_action` (`:288-333`), `folder_for_path` (`:269-273`).

Changed:

1. `StartGroup` (`:48-56`): `kind='archive'` accepts `.zip` and `.ufdr` (`:118`).
2. `MAX_MEMBERS` (`:35`) becomes `200_000` for `folder` groups. Reason: the measured largest is
   93,150; 200,000 leaves twice that. Manifest size at about 250 bytes per member is about 50 MB
   for 200,000; the start request body limit must allow it (to be confirmed against the backend's
   request size limit at implementation). *Reverse if* a production exceeds it: then the manifest
   moves to paged submission.
3. `prepare_payload` (`:222-235`): before calling `extract_archive`, call the engine
   `POST /cases/{case_id}/phone/detect` (new, 4.3) with the assembled container path. If the
   outcome is anything other than `not_a_phone_report`, **do not extract**: copy the container
   into the payload root with `copy_verified` and return one prepared entry for it. Otherwise
   extract as today. `extract_archive`'s 20,000-entry and encrypted-entry refusals
   (`:187-188,194-195`) therefore never apply to phone containers; a protected UFDR is stored,
   hashed and explained rather than refused at upload.
4. `register_payload` (`:238-266`): replace `_find_cellebrite_report_roots_from_uploads` (an import
   from `routers.evidence`, `:239`) with the detect response. For each readable root, one
   evidence row for the container (4.4) and one dispatch item
   `{request_id, container_path, root_path, evidence_folder_id, container_evidence_id}`. Members
   inside a phone root are not registered (as today, `:249-250`). Protected and unreadable phone
   containers get the evidence row and no dispatch item.
5. `dispatch_reports` (`:276-285`): call `evidence_engine_client.create_phone_capture_job`
   (new) instead of `create_cellebrite_job`. `replace_existing` (`:55`) is not passed: replacing a
   phone extraction is an explicit action on an already-captured extraction (10.7).

### 4.3 Engine endpoints (new, `evidence-engine/app/api/routes/phone.py`)

| Method and path | Body | Returns |
|---|---|---|
| `POST /cases/{case_id}/phone/detect` | `{"path": "<relative to data root>"}` | `IntakeClassification` (2.5) |
| `POST /cases/{case_id}/phone/jobs` | `{"request_id": uuid, "container_path": str, "root_path": str, "evidence_folder_id": uuid|null, "container_evidence_id": uuid, "requested_by_user_id": uuid|null}` | `JobResponse`; idempotent on `request_id` exactly as `create_cellebrite_job` is today (`evidence-engine/app/api/routes/cellebrite.py:80-110`) |
| `POST /jobs/{job_id}/cancel?case_id=` | none | `{"state": "cancelling|cancelled"}` (10.6) |

Path safety reuses `_safe_report_folder`'s rules (`cellebrite.py:36-56`), moved to
`app/phone/paths.py`, generalised to files as well as folders. The data root is
`settings.cellebrite_data_root` (`evidence-engine/app/config.py:71`, mounted at `/data/evidence`,
`docker-compose.yml:132,216`); the setting keeps its name (renaming touches compose and both
containers for no behavioural gain).

### 4.4 The container as evidence

Exactly **one `evidence_files` row per received container**, `source_type='phone_extraction'`,
`original_filename` the container name, `sha256` the container hash, `stored_path` the payload
path, `metadata_ = {"upload_group_id", "phone_extraction_container_id"}`. Tagged files are **not**
evidence rows (section 7.4). Consequences elsewhere:

- `services/financial/auto_read.py:107,515` exclude `source_type == 'cellebrite'`; both become
  `in ('cellebrite', 'phone_extraction')`.
- `GET /api/evidence` hides `source_type == 'cellebrite'` by default (`evidence.py:831-832`); the
  container row is **shown** (it is the evidence item), so the filter stays as is.
- `/api/evidence/process` and `/route-check` refuse `phone_extraction` rows with 409 "Phone
  reports are read automatically when uploaded." (Implementation reads the exact guard location
  in `process_evidence`, `evidence.py:1483`.)

---

## 5. Capture: the single streaming pass

### 5.1 Parser and process

- Capture parses with stdlib `xml.etree.ElementTree.iterparse` (expat). The reconciliation
  counter (8.2) parses with `lxml.etree.iterparse` (libxml2; `lxml>=5` is already an engine
  dependency, `evidence-engine/pyproject.toml`). Two parsers, so a defect in one cannot hide
  itself in both sides of the comparison. They agree on all three samples (1.2).
- `resolve_entities=False`, no network, no DTD loading for lxml; expat in the stdlib does not
  fetch external entities. `huge_tree=True` for lxml (texts up to 155,838 characters measured).
- The parse runs in a worker thread (`asyncio.to_thread`), as the old pipeline does
  (`evidence-engine/app/pipeline/cellebrite_ingestion.py:223-235`), with the pause boundary bridge
  of `:210-216`. Writes use a **synchronous psycopg 3 connection opened inside the thread**,
  DSN derived locally from `settings.database_url` by replacing `postgresql+asyncpg://` with
  `postgresql://`. The process environment is never mutated (the old code rewrites
  `os.environ["DATABASE_URL"]` for the whole process, `cellebrite_ingestion.py:45-51`) and no
  backend package is imported (`:35-44` inserts `backend/` on `sys.path`; the Dockerfile copies the
  whole backend into the engine image, `evidence-engine/Dockerfile:12,20`). The capture tables are
  mirrored as plain SQLAlchemy Core `Table` objects in `evidence-engine/app/models/phone.py`, the
  pattern `EvidenceTableGeometry` already uses ("The backend's alembic tree owns the schema; this
  mirror only writes to it", `evidence-engine/app/models/job.py:103-109`).
- Source streams: a directory document is opened directly; a zip or UFDR member through
  `zipfile.ZipFile.open` (streaming inflate; measured C9 4.0 s count, 80 MB RSS).

### 5.2 The pass, in steps

State: an explicit stack of `(element, local_name, qualified_path)`; `ordinal` counters for
records and files; a write buffer.

1. On `start`: push. If the element is `model`, assign `record_ordinal += 1` (document order of
   model start tags, top-level and nested alike) and remember it against the element.
   If it is `file` directly under `taggedFiles`, assign `file_ordinal += 1`.
2. On `end` of `model`: encode it (5.3) with nested model children replaced by
   `["@", child_ordinal]`; emit a record row; `clear()` the element. Its parent keeps the cleared
   child only until the parent itself is encoded, so memory holds at most one top-level record
   (largest measured: 98,679 units, 133 KB of text).
3. On `end` of `taggedFiles/file`: encode, emit a file row, clear.
4. On `end` of `modelType` or `taggedFiles`: detach the already-emitted children so the skeleton
   does not grow (measured skeleton under 15 KB).
5. On `end` of any other element: nothing; it stays in the skeleton tree.
6. At end of document: encode the skeleton (root with record and file subtrees removed) and
   store it on the document row.
7. Buffer flush (5.5) whenever 2,000 rows or 16 MB of encoded JSON are buffered, whichever first,
   and at the end.
8. On parse error: section 5.6.

All seven field kinds and every other child are captured by the same generic encoding, with no
list of known tags: `field`, `multiField`, `modelField`, `multiModelField`, `nodeField` (with its
`id` children), `dataField`, `jumptargets/targetid`, `empty`, and anything new. Every attribute
of every element, every `value` with its `type` and `formattedTimestamp`, every value of a
`multiField` (not only the first: v1 kept the first only, plan 3.1).

### 5.3 Encoding

Every element is a JSON array `[tag, attrs, text, children]`:

- `tag`: local name. If the namespace is not `http://pa.cellebrite.com/report/2.0` or absent, the
  tag is `"{ns}local"` (none measured; this keeps a foreign namespace visible).
- `attrs`: object of attribute local name to string value, or `null` when none.
- `text`: the element's text exactly as parsed, or `null`. For an element with child elements,
  whitespace-only text is formatting and is stored as `null`; for a leaf it is kept verbatim,
  including whitespace-only and empty strings. Non-whitespace text before or between children
  (mixed content) is stored as text; non-whitespace tails fail reconciliation (8.3), because the
  encoding has nowhere to put them and none were measured.
- `children`: array or `null`; a nested record is `["@", record_ordinal]`.

CDATA and character references are lexical forms: the parse yields their characters, which is
what is stored. The exact bytes remain in the hashed container (3).

### 5.4 Memory budget

- Parse plus encode measured at 37 to 81 MB RSS (1.4).
- Write buffer at most 16 MB of JSON plus psycopg's copy buffer.
- Budget: **512 MiB RSS for the capture thread's process**. Checked after every flush with
  `resource.getrusage`; exceeding it raises `CaptureMemoryBudgetExceeded`, which fails the job
  with "Reading stopped because the report needed more memory than allowed. Nothing read so far
  is lost." and leaves the cursor (10.5) for a resume after the limit is raised.
- Container limit: `mem_limit: 1g` on the phone worker (10.2). Host: 31 GB RAM plus 32 GB swap,
  with Neo4j and Nominatim pressure noted (`v1_memory/MEMORY.md:41`, index line; the linked note
  `project_host_no_swap_oom.md` was not available to read).

### 5.5 Writing

- Rows go through `COPY ... FROM STDIN` (psycopg 3 `cursor.copy`), one transaction per flush,
  and **the same transaction** updates the document's capture cursor (10.5). A flush is therefore
  all-or-nothing and its cursor names exactly what is stored.
- Records are written before the record that contains them only in document end order, which is
  children first: a nested model ends before its parent. Rows reference parents by ordinal, not
  by foreign key, so ordering is not a constraint problem (CLAUDE build-state note: flush ordering
  does not follow raw foreign keys; here there is no foreign key to follow).
- Second load of the same extraction is a no-op (6.3).

### 5.6 Truncated documents

On `ParseError`:

1. Record on the document row: `parse_state='truncated'`, `error_line`, `error_column`,
   `error_message` (parser text), `bytes_read`, and `open_path` (the qualified path of the open
   stack, e.g. `project/taggedFiles/file/metadata[MetaData]`).
2. The innermost open `file` or `model` element is encoded from what was read and stored as a
   row with `is_partial=true`. Everything completed before the break is already stored.
3. The skeleton is stored with the open ancestors as they were read, marked
   `{"partial": true}` in the document row.
4. The extraction's capture state becomes `captured_incomplete` (6.2) and the extraction carries
   the flag `incomplete_source` with the document name and break position. Plan 1.7: flagged, not
   refused.

Measured on C8 `.xmlTagged`: 11,663 complete files plus one partial, and the recount from capture
equals the source count including the partial element (1.4).

---

## 6. Postgres schema

### 6.1 Storage decision: one row per model, body as JSONB

| Option | Rows for the largest phone | Judgement |
|---|---|---|
| One row per element | 11 to 14 million record elements plus files (1.3) | Indexes and write volume for no query that needs it; reassembling a record costs a join over dozens of rows. |
| One row per top-level record | 338,715 | A Chat row holds up to 1,485 messages (1.3); every message query would unpack its chat. |
| **One row per model, top-level and nested, body JSONB** | 967,543 | A message, party or coordinate is addressable as a row; the largest row measured is 164 KB; JSON per row averages 0.97 KB (C3), 0.95 KB (C9), 1.12 KB (C8). |
| Plus one row per value | 4.70 M more | Deferred: the interpretation layer (later files) builds indexed projections (timeline, text, identifiers) from the bodies. |

Estimated record JSON for the largest phone: about 0.9 to 1.1 GB before Postgres TOAST compression.
*Reverse if* registry or interpretation queries over JSONB bodies are measured too slow on the
largest phone; then add a value table populated from the bodies without re-reading the XML.

### 6.2 Tables

Migration `backend/postgres/alembic/versions/20261101_phone_capture.py` (date set on the day it is
written), `revision = "20261101_phone_capture"`, `down_revision` = the head at that time; today
the single head is `"20261019_workspace_setup"` (computed from all 95 revision files). Style as
the existing files: module docstring, `revision`, `down_revision`, `branch_labels = None`,
`depends_on = None`, `upgrade()` and `downgrade()`; the `evidence-db-migrate` service runs it
(`docker-compose.yml:60-69`). Backend ORM models in `backend/postgres/models/phone_extraction.py`,
registered in `backend/postgres/models/__init__.py`; engine Core mirrors in
`evidence-engine/app/models/phone.py`.

```sql
CREATE TYPE phone_capture_state AS ENUM (
  'received',            -- container row exists, nothing read
  'detecting',
  'not_readable',        -- protected or not a report; terminal
  'counting',            -- source counter pass
  'capturing',
  'reconciling',
  'captured',            -- reconciled exactly, complete source
  'captured_incomplete', -- reconciled exactly, source truncated
  'reconciliation_failed',
  'failed',
  'cancelled');

CREATE TYPE phone_extraction_standing AS ENUM ('pending', 'active', 'superseded');

CREATE TABLE phone_extraction_containers (
  id                 uuid PRIMARY KEY,
  case_id            uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_file_id   uuid REFERENCES evidence_files(id) ON DELETE SET NULL,
  upload_group_id    uuid REFERENCES evidence_upload_groups(id) ON DELETE SET NULL,
  container_kind     varchar(20) NOT NULL CHECK (container_kind IN ('ufdr','zip','folder','single_document')),
  stored_path        text NOT NULL,          -- relative to the evidence data root
  original_name      varchar(1024) NOT NULL,
  size_bytes         bigint NOT NULL,
  sha256             char(64) NOT NULL,      -- computed by the job (section 3)
  md5                char(32) NOT NULL,
  upload_sha256      char(64),               -- as verified at upload
  intake_outcome     varchar(40) NOT NULL,   -- IntakeClassification.outcome
  classification     jsonb NOT NULL,         -- full IntakeClassification
  received_at        timestamptz NOT NULL DEFAULT now(),
  received_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX ix_phone_containers_case ON phone_extraction_containers(case_id);
CREATE INDEX ix_phone_containers_sha ON phone_extraction_containers(case_id, sha256);

CREATE TABLE phone_extractions (
  id                    uuid PRIMARY KEY,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  report_set_sha256     char(64) NOT NULL,   -- section 6.3
  first_container_id    uuid NOT NULL REFERENCES phone_extraction_containers(id),
  root_path             text NOT NULL,       -- report root inside the container
  form                  varchar(20) NOT NULL CHECK (form IN ('full','split_sections','ufdr')),
  capture_state         phone_capture_state NOT NULL DEFAULT 'received',
  standing              phone_extraction_standing NOT NULL DEFAULT 'pending',
  supersedes_id         uuid REFERENCES phone_extractions(id),
  superseded_at         timestamptz,
  superseded_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  report_version        varchar(32),         -- project@reportVersion
  producer_version      varchar(64),         -- metadata item UFED_PA_Version
  extraction_type       varchar(64),         -- project@extractionType
  device_zone           varchar(64),         -- section 9.3, NULL when not stated
  device_zone_source    varchar(64),
  flags                 jsonb NOT NULL DEFAULT '{}',  -- incomplete_source, nested_report_ignored, ...
  record_count          integer,
  file_count            integer,
  engine_job_id         uuid REFERENCES jobs(id) ON DELETE SET NULL,
  capture_code_version  varchar(32) NOT NULL, -- e.g. 'phone-capture-1'
  created_at            timestamptz NOT NULL DEFAULT now(),
  captured_at           timestamptz,
  CONSTRAINT uq_phone_extraction_report UNIQUE (case_id, report_set_sha256, root_path)
);
CREATE UNIQUE INDEX uq_phone_extraction_supersedes ON phone_extractions(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX ix_phone_extractions_case_standing ON phone_extractions(case_id, standing);

CREATE TABLE phone_extraction_container_links (   -- a second receipt of the same report
  extraction_id uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  container_id  uuid NOT NULL REFERENCES phone_extraction_containers(id) ON DELETE CASCADE,
  PRIMARY KEY (extraction_id, container_id)
);

CREATE TABLE phone_extraction_documents (
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index   smallint NOT NULL,        -- 0..n in sorted path order
  path             text NOT NULL,            -- inside the container
  role             varchar(20) NOT NULL,     -- full|model|tagged|extra|last|mdf_source|model_source|node_source|translation|unknown
  size_bytes       bigint NOT NULL,
  sha256           char(64) NOT NULL,
  md5              char(32) NOT NULL,
  root_element     varchar(64),
  parse_state      varchar(16) NOT NULL DEFAULT 'pending' CHECK (parse_state IN ('pending','complete','truncated','empty')),
  truncation       jsonb,                    -- line, column, message, bytes_read, open_path
  skeleton         jsonb,                    -- section 5.3 encoding, record/file subtrees removed
  source_counts    jsonb,                    -- counter output, section 8.2
  capture_cursor   jsonb NOT NULL DEFAULT '{"record_ordinal":0,"file_ordinal":0}',
  PRIMARY KEY (extraction_id, document_index)
);

CREATE TABLE phone_records (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,         -- document order of the model start tag
  parent_ordinal   integer,                  -- NULL for top-level
  top_ordinal      integer NOT NULL,         -- the top-level record it belongs to (itself if top-level)
  depth            smallint NOT NULL,        -- 0 top-level
  model_type       varchar(128) NOT NULL,    -- model@type
  source_model_id  varchar(128),             -- model@id, NOT unique (section 1.3)
  deleted_state    varchar(32),              -- model@deleted_state, copied for indexing
  is_partial       boolean NOT NULL DEFAULT false,
  body             jsonb NOT NULL,           -- the full element, section 5.3
  PRIMARY KEY (extraction_id, document_index, ordinal),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_records_type ON phone_records(extraction_id, model_type);
CREATE INDEX ix_phone_records_top ON phone_records(extraction_id, document_index, top_ordinal);
CREATE INDEX ix_phone_records_source_id ON phone_records(extraction_id, source_model_id);

CREATE TABLE phone_files (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,
  source_file_id   varchar(128),             -- file@id (unique in all three samples, not assumed)
  local_path       text,                     -- metadata[File]/item[Local Path], backslashes kept
  declared_size    bigint,                   -- file@size
  declared_md5     varchar(64),
  declared_sha256  varchar(128),
  tags             varchar(64),              -- metadata[File]/item[Tags], e.g. Image
  is_partial       boolean NOT NULL DEFAULT false,
  body             jsonb NOT NULL,
  -- verification, section 7.2
  disk_relpath     text,
  disk_size        bigint,
  disk_md5         char(32),
  disk_sha256      char(64),
  outcome          varchar(24),              -- section 7.2
  verified_at      timestamptz,
  PRIMARY KEY (extraction_id, document_index, ordinal),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_files_source_id ON phone_files(extraction_id, source_file_id);
CREATE INDEX ix_phone_files_path ON phone_files(extraction_id, lower(replace(local_path, '\', '/')));
CREATE INDEX ix_phone_files_content ON phone_files(disk_sha256) WHERE disk_sha256 IS NOT NULL;

CREATE TABLE phone_container_entries (          -- every file in the container, referenced or not
  extraction_id uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  relpath       text NOT NULL,                  -- relative to the report root, '/' separators
  size_bytes    bigint NOT NULL,
  sha256        char(64),                       -- filled by verification when hashed
  md5           char(32),
  PRIMARY KEY (extraction_id, relpath)
);

CREATE TABLE phone_file_references (
  extraction_id   uuid NOT NULL,
  document_index  smallint NOT NULL,
  record_ordinal  integer NOT NULL,
  body_path       text NOT NULL,                -- section 6.4
  mechanism       varchar(24) NOT NULL CHECK (mechanism IN ('jumptarget','file_id_attribute','extracted_path_value')),
  reference_text  text NOT NULL,                -- the id or path as written
  file_document_index smallint,                 -- resolved phone_files row, if any
  file_ordinal    integer,
  container_relpath text,                       -- resolved entry on disk, if any
  resolution      varchar(24) NOT NULL CHECK (resolution IN ('tagged_file','container_entry','model','unresolved')),
  PRIMARY KEY (extraction_id, document_index, record_ordinal, body_path, mechanism)
);
CREATE INDEX ix_phone_file_refs_file ON phone_file_references(extraction_id, file_document_index, file_ordinal);

CREATE TABLE phone_timestamps (                 -- section 9
  extraction_id   uuid NOT NULL,
  document_index  smallint NOT NULL,
  owner_kind      varchar(8) NOT NULL CHECK (owner_kind IN ('record','file','skeleton')),
  owner_ordinal   integer NOT NULL,             -- 0 for skeleton
  body_path       text NOT NULL,
  model_type      varchar(128),
  field_name      varchar(256),                 -- field@name, timestamp@name or item@name
  value_type      varchar(64) NOT NULL,         -- 'TimeStamp', 'accessInfo', 'metadata_item'
  original_text   text NOT NULL,
  formatted_text  text,                         -- formattedTimestamp attribute
  instant         timestamptz,
  local_wall_time timestamp,                    -- only when no offset was written
  original_offset_minutes smallint,
  offset_state    varchar(12) NOT NULL CHECK (offset_state IN ('explicit','absent','unparsed')),
  parse_rule      varchar(48) NOT NULL,
  PRIMARY KEY (extraction_id, document_index, owner_kind, owner_ordinal, body_path)
);
CREATE INDEX ix_phone_timestamps_instant ON phone_timestamps(extraction_id, instant);
CREATE INDEX ix_phone_timestamps_absent ON phone_timestamps(extraction_id) WHERE offset_state <> 'explicit';

CREATE TABLE phone_reconciliations (
  id              uuid PRIMARY KEY,
  extraction_id   uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index  smallint NOT NULL,
  ran_at          timestamptz NOT NULL DEFAULT now(),
  counter_version varchar(32) NOT NULL,
  result          varchar(8) NOT NULL CHECK (result IN ('exact','differs')),
  source_totals   jsonb NOT NULL,
  captured_totals jsonb NOT NULL,
  differences     jsonb NOT NULL DEFAULT '[]',   -- every difference, section 8.4
  difference_count integer NOT NULL DEFAULT 0
);
```

`phone_records`, `phone_files`, `phone_file_references` and `phone_timestamps` carry no foreign key
from child to parent row beyond the document: rows are bulk-loaded in document end order (5.5).
Deleting an extraction cascades from `phone_extraction_documents`; an extraction is never deleted
automatically (10.7).

Estimated rows for the largest phone: 967,543 records; timestamps about 13 percent of values
(C8: 59,672 of 461,571) gives about 0.6 M plus file timestamps; files not established.

### 6.3 Idempotency keys

- **Report-set key** `report_set_sha256 = sha256("\n".join(sorted(f"{role}:{sha256}" for each non-empty document)))`.
  Two uploads of byte-identical report XML (zip and folder of the same export, or the same file
  twice) produce the same key. Unique per `(case_id, report_set_sha256, root_path)`.
- On a job start where an extraction with that key exists in the case:
  - `captured` or `captured_incomplete`: link the new container
    (`phone_extraction_container_links`), write nothing else, finish with
    "This phone report is already in the case. The new upload is recorded as a second copy of the
    same report." That is the plan's "second load is a no-op".
  - any non-terminal or failed state: resume it (10.5).
- **Row keys** `(extraction_id, document_index, ordinal)`. Ordinals come from document order,
  which is a function of the bytes, so a re-run on the same bytes produces the same keys.
- **Engine job** idempotent on `request_id` (4.3).

### 6.4 Locators

A locator names one element in the capture:

```
{extraction_id}/{document_index}/r{ordinal}/{body_path}
{extraction_id}/{document_index}/f{ordinal}/{body_path}
{extraction_id}/{document_index}/s/{body_path}           (skeleton)
```

`body_path` is the dot-joined list of child positions from the row's root element, e.g. `4.0` is
the first child of the fifth child: for a record, the fifth child `field[TimeStamp]` and its first
`value`. Positions, not names, because a name can repeat within a model (38 models in C8) and
the model id can repeat (1.3). Every locator also has a readable form generated from the body,
e.g. `InstantMessage#4512 / field[TimeStamp] / value[0]`, used in the UI; the positional form is
the stored key. The plan's "(extraction, record id, field path, value index)" is this locator:
record id is `(document_index, ordinal)`, field path and value index are the positions.

---

## 7. Files

### 7.1 Tagged file index

Built from `phone_files` after capture: `source_file_id`, `local_path` (normalised to `/`,
compared case-sensitively first, then case-insensitively with a flag when only the latter
matches), declared size and hashes, `tags`. In all three samples every `file` has a Local Path,
an MD5 item and a SHA256 item (the SHA256 item is empty except for 224, 80, 3 files), a Tags item
and timestamps (1.5, scratchpad `c*.json` `file_hash`, and the `file` shape measurement).

### 7.2 Verification outcomes

For each `phone_files` row, read the bytes at `local_path` relative to the report root (directly
for a folder, via `zipfile` for a zip or UFDR), computing MD5 always and SHA-256 always (SHA-256 is
the Loupe content key; MD5 is what the report states). Outcome, first matching rule wins:

| Outcome | Rule | Measured |
|---|---|---|
| `no_local_path` | Local Path empty | 0, 0, 0 |
| `missing` | no entry at that path | 224, 80, 9,929 |
| `empty_placeholder` | on disk size 0, declared size 0, declared MD5 is not `d41d8cd98f00b204e9800998ecf8427e` | 21,664, 0, 0 |
| `size_mismatch` | on disk size differs from declared size | 0, 0, 326 |
| `match` | MD5 equals declared (and SHA-256 equals declared when declared) | 21,155, 29,456, 1,172 |
| `mismatch` | MD5 or declared SHA-256 differs | 0, 0, 236 |
| `no_hash` | no declared MD5 or SHA-256 | 0, 0, 0 |

UI copy per outcome (shown on the file and summarised on the extraction profile):

| Outcome | Text |
|---|---|
| `match` | "Matches the fingerprint in the report." |
| `missing` | "The report lists this file but it is not in the production." |
| `empty_placeholder` | "The production contains an empty placeholder for this file. The report describes the original, which was not included." |
| `size_mismatch` | "The file in the production is a different size from the one the report describes. It may be incomplete." |
| `mismatch` | "The file in the production does not match the report's fingerprint. It is not the same file the report describes." |
| `no_hash` | "The report gives no fingerprint for this file, so it cannot be checked." |

All files are kept and flagged; none is refused (plan 1.7). Hashing runs inside the capture job
after reconciliation (10.3), measured at 94 to 373 MB/s single-threaded (1.5).

### 7.3 The three attachment mechanisms

Resolved after capture by scanning record bodies (no XML re-read) and written to
`phone_file_references`:

1. **Jump targets**: every `jumptargets/targetid` child. `ismodel="true"` resolves against
   `phone_records.source_model_id` (`resolution='model'`). When the id repeats (1.3), one reference row is
   written per candidate record, with `body_path` suffixed `#k` (k = 0, 1, ...), and the
   reference is flagged ambiguous; none is chosen silently. `ismodel="false"` resolves against
   `phone_files.source_file_id`. Measured: 709, 879, 491 file targets; v1 linked only these
   (`file_linker.py` in v1; Loupe copy `evidence-engine/app/pipeline/cellebrite/file_linker.py:350-382`).
2. **`file_id` attribute** on a model (Attachment and others): resolves against
   `phone_files.source_file_id`.
3. **Extracted path values**: any `value` whose text, after `\` to `/`, begins with a top-level
   directory that exists in `phone_container_entries` for this extraction (measured prefixes
   `chats/`, `files/`, `contacts/`, `photos/`, `useraccounts/`, `socialmedia/`) and which names an
   existing entry; this covers `attachment_extracted_path` and the contact-photo equivalent
   (IPED reads both, `UfedXmlReader.java:110-111`). Measured 419, 852, 143 such values, all
   present. The rule uses the container's own directory listing, not a fixed prefix list, so a
   new folder name is covered without code.

A record may resolve through more than one mechanism; each is a separate row, and disagreement
between mechanisms (two mechanisms on one record pointing at different content hashes) sets the
extraction flag `attachment_reference_conflict` with the locators.

### 7.4 Registration without one evidence row per file

v1 registered extracted files as evidence rows, producing the 164k-plus artifact rows in one case
(`v1_memory/archive/project_cellebrite_v2_migration.md:24`) and an empty Process Evidence list
once they were filtered (`v1_memory/project_cellebrite_zero_evidence_rows.md`). Loupe's copy
registers Image, Audio, Video and Text files as `evidence_files` rows
(`evidence-engine/app/pipeline/cellebrite/file_linker.py:159-271`,
`backend/services/evidence_db_storage.py:573-642`).

Decision: **tagged files and container entries live only in `phone_files` and
`phone_container_entries`.** The container is the one evidence row (4.4). An `evidence_files` row
for an individual phone file is created later and only on demand, by the media track, when a file
is sent for OCR or transcription (plan section 13), with `metadata_` pointing back to the
`phone_files` locator. *Reverse if* a Loupe-wide feature that must see phone media can only read
`evidence_files`; then register lazily per feature, never in bulk.

### 7.5 Media category

Stored as `phone_files.tags` from the report's own `Tags` item (measured values Image, Audio,
Video, Text, Archives, Document, Application, Configuration, Database, Uncategorized). The Local
Path folder (`files/Image/...`) is the same information and is not used. Loupe's current
category detection tests `parts[0]` of the Local Path against Image/Audio/Video/Text
(`file_linker.py:52-69`), but the first component is `files`, so it only ever falls back to the
extension; it is removed with the rest of the old code.

### 7.6 Deduplication without losing attribution

Loupe's copy skips any file whose SHA-256 was already seen in the same run
(`file_linker.py:189,210-213`), so the second tagged file with the same content gets no record and
whatever referenced it loses its link. Measured: 228 C9 file ids share 26 contents; 327 C8 ids
share 2.

Decision: every tagged file keeps its own row and every reference its own row. Identical content
is recognised by `disk_sha256` (indexed), so "the same image on several phones" (plan 12, item 8)
is a query, not a merge. Bytes are never copied, so there is nothing to deduplicate on disk.

### 7.7 Storage layout

```
{EVIDENCE_DATA_ROOT}/{case_id}/_upload_groups/{group_id}/payload/{container name}   zip or ufdr, as received
{EVIDENCE_DATA_ROOT}/{case_id}/_upload_groups/{group_id}/payload/{folder tree}/       folder uploads, as uploaded
```

The first line is new behaviour (4.2 item 3); the second is today's `payload_root`
(`evidence_upload_groups.py:158-159`). Zip and UFDR containers are **read in place and never
unpacked**: the counter, the capture and file verification all stream members (measured C9: count
2.0 s, capture 6.2 s, hash all files 9.5 s from inside the zip). This removes the 64 GB expanded
copy limit and its doubled disk use for phones. *Reverse if* serving individual media for playback
from inside a deflated zip is measured too slow; then extract on first view into a cache that is
never treated as evidence.

---

## 8. Reconciliation

### 8.1 Qualified path

Each element's path is the `/`-joined list of its ancestors' and its own qualified names, where a
qualified name is the local name, plus `[@type]` for `model` and `modelType`, plus `[@name]` for
`field`, `multiField`, `modelField`, `multiModelField`, `nodeField`, `dataField`, `item`,
`timestamp`, `jumptargets`, and `[@section]` for `metadata`. Example:
`decodedData/modelType[Chat]/model[Chat]/multiModelField[Messages]/model[InstantMessage]/field[TimeStamp]/value`.
Measured distinct paths 706 to 1,120 per report (1.2), so per-path counters are small.

### 8.2 What is counted

Per document, per qualified path:

| Measure | Definition |
|---|---|
| `elements` | count of start tags |
| `attributes[name]` | count per attribute local name |
| `attr_hash[name]` | sum mod 2^64 of the first 8 bytes of BLAKE2b of each attribute value (UTF-8) |
| `texts` | count of elements with text that is non-whitespace, or any text on a leaf |
| `text_chars` | sum of their lengths in code points |
| `text_hash` | sum mod 2^64 of the first 8 bytes of BLAKE2b of each text (UTF-8) |
| `bad_tails` | non-whitespace tail text count (must be 0) |

Plus document totals and the open path at a parse error. The sums are order-independent, so
records written in a different order still match, while any changed, lost or added value changes
a sum. Counter code: `evidence-engine/app/phone/counter.py`, using lxml (5.1), output stored as
`phone_extraction_documents.source_counts`.

The captured side is computed by `evidence-engine/app/phone/recount.py`, which streams
`phone_records`, `phone_files` and the skeleton for the document back out of Postgres in ordinal
order, reconstructs qualified paths (nested records are rejoined by `["@", ordinal]`; top-level
records and files are rejoined under their `modelType` and `taggedFiles` skeleton nodes by
`document_index`), and computes the same measures. It never reads the XML.

### 8.3 Exact-match rule

For every path and every measure, captured equals source. Any difference, any path present on one
side only, or any `bad_tails > 0`, makes the result `differs`. There is no tolerance.

### 8.4 Failure report

`phone_reconciliations.differences` holds **every** difference as
`{"path": ..., "measure": "elements|attributes|attr_hash|texts|text_chars|text_hash|bad_tails", "attribute": "<name or null>", "source": n, "captured": n}`,
sorted by path. `difference_count` is the total. The job message names the first path and the
total: "The check found {total} differences between the report and what was read, starting at
{readable path}. The report has not been added to the case views. Nothing read has been deleted."
The extraction moves to `reconciliation_failed`, its standing stays `pending`, so nothing
downstream (later files) uses it.

### 8.5 When it runs

- Every ingest, after capture (10.3).
- As a test over the reference corpus (12, unit 0.2 and 1.4) on C3, C9 and the readable C8.
- On demand: `POST /cases/{case_id}/phone/extractions/{id}/reconcile` re-runs both sides and adds
  a new `phone_reconciliations` row (useful after a capture code change).

---

## 9. Time storage

### 9.1 What is stored

One `phone_timestamps` row for: every `value` with `type="TimeStamp"`; every
`file/accessInfo/timestamp`; every `metadata/item` in the skeleton or a file body whose
`name` is in the parse-rule table (9.2) or ends in `Time`, `Date` or `DateTime`. The original
text and the `formattedTimestamp` attribute are always kept, and remain in the body as captured.

### 9.2 Parse rules

| `parse_rule` | Matches | Result |
|---|---|---|
| `iso8601_offset` | `YYYY-MM-DDTHH:MM:SS(.fff)?(+|-)HH:MM` or `Z` | `instant`, `original_offset_minutes`, `offset_state='explicit'` |
| `iso8601_no_offset` | same without offset | `local_wall_time`, `instant` NULL, `offset_state='absent'` |
| `us_ampm_offset` | `M/D/YYYY H:MM:SS AM|PM +|-HH:MM` | explicit |
| `us_ampm_no_offset` | `M/D/YYYY H:MM:SS AM|PM` | absent |
| `exif` | `YYYY:MM:DD HH:MM:SS` | absent |
| `slash_24h_no_offset` | `DD/DD/YYYY HH:MM:SS` | absent, and day-month order recorded as ambiguous in `parse_rule='slash_24h_ambiguous'` when both first fields are 12 or less |
| `unparsed` | anything else | `offset_state='unparsed'`, text kept |

Fractional seconds are kept to microseconds (Postgres `timestamptz` precision); the original text
holds the rest.

### 9.3 Device zone

**Settled 2026-10-29 (overrides the first draft of this section; 02 governs device zone):** the
device zone comes only from the device's own setting in the report metadata (metadata item
`Time zone settings (ID)`, present in C9) or from a recorded decision. Stored on
`phone_extractions.device_zone` with `device_zone_source` (`device_metadata` or `decision`); NULL
otherwise. Never a constant (v1 hard-coded America/New_York, plan 4.6). C8 has no zone (the section is
lost to truncation) and says so.

`projectConfigurations/timeZoneConfigurations@selectedTimeZone` is the examiner's display setting in
Physical Analyzer, a fact about the examiner and not the phone. It is captured (leading `_` stripped,
validated as an IANA name) into `phone_extractions.flags.examiner_selected_zone`, together with
`enableAutomaticallyConvertToUTC` and `enableDaylightSavings`, and shown on the Extraction profile as
"Examiner's display zone". It is never used to place the phone's events. *Reverse if* the 14 server
phones show the examiner zone and the device setting agree wherever both exist.

### 9.4 Offset-less values

Flagged, not guessed: `instant` stays NULL, `local_wall_time` holds the wall-clock value, and the
row is indexed by `ix_phone_timestamps_absent`. Measured: 22 in C3, 6 in C8, mostly
`Location.TimeStamp`. Applying the device zone to them is a recorded decision through the
decision log in a later file, never a default at capture. The field name and model type are
stored on each row so that the later timestamp-meaning mapping (plan 11.2 principle 2) can label
each one without re-reading bodies.

---

## 10. The job

### 10.1 Job record

Engine `jobs` row (`evidence-engine/app/models/job.py:28-79`), `job_type='phone_capture'`,
`file_path` the container path, `merge_payload` the request body of 4.3, `pipeline_state`
`{"batch_dispatch": {...}, "processing_queue": "arq:phone-capture", "phone": {"extraction_id": ..., "stage": ...}}`.
Dispatch goes through `dispatch_ingestion_batch`, which already honours
`pipeline_state['processing_queue']` (`evidence-engine/app/services/batch_dispatch.py:44-45`) and
calls a non-`process_file` function with `(batch_id, case_id)` (`:39-40`).

### 10.2 Queue, worker, container

`evidence-engine/app/services/processing_queues.py` gains `PHONE_CAPTURE_QUEUE = 'arq:phone-capture'`
beside `PDF_REVIEW_QUEUE` (`:4`). `evidence-engine/app/worker.py` gains, on the pattern of
`PdfReviewWorkerSettings` (`:91-102`):

```python
async def process_phone_capture(ctx: dict, job_id: str, case_id: str) -> None:
    async with async_session() as db:
        await run_controlled(job_id, case_id,
            lambda: run_phone_capture(job_id, db), batch=False)

class PhoneCaptureWorkerSettings:
    """Phone extractions get their own slot so a long read never blocks statements or documents."""
    from app.services.processing_queues import PHONE_CAPTURE_QUEUE as queue_name
    from app.phone.recovery import recover_waiting_phone_jobs
    functions = [process_phone_capture]
    cron_jobs = [cron(recover_waiting_phone_jobs, minute=set(range(0, 60)), run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1
    job_timeout = 14400
    job_completion_wait = 14430
    retry_jobs = True
    max_tries = 3
```

`max_jobs = 1`: one phone at a time bounds memory and disk read contention on a host with known
memory pressure; at the targets in 10.8 the queue drains a full 10-report case in well under a
day. *Reverse if* measured capture time makes queueing the bottleneck.

`docker-compose.yml` gains, after `evidence-pdf-worker` (`:226-229`):

```yaml
  evidence-phone-worker:
    <<: *evidence-worker
    container_name: owl-v2-evidence-phone-worker
    command: arq app.worker.PhoneCaptureWorkerSettings
    mem_limit: 1g
```

`process_cellebrite` is removed from `WorkerSettings.functions` (`worker.py:73`) in unit 1.7.
`evidence-engine/app/api/routes/jobs.py` adds `phone_capture` to the job types that support
pause and resume (`:22`) and maps it to `process_phone_capture` (`:60-61`).

### 10.3 Stages and progress

`run_phone_capture` (`evidence-engine/app/phone/job.py`) runs these stages; each records its
stage in `pipeline_state.phone.stage` and `phone_extractions.capture_state`:

| Stage | Work | Progress range |
|---|---|---|
| `verifying_container` | hash container, compare with upload hash (3) | 0.00 to 0.05 (by bytes) |
| `detecting` | classification (2.3) | 0.05 |
| `counting` | lxml counter per document, document hashes | 0.05 to 0.20 (by bytes read) |
| `capturing` | capture pass (5) | 0.20 to 0.65 (by bytes read) |
| `reconciling` | recount from Postgres and compare (8) | 0.65 to 0.75 (by rows) |
| `indexing_files` | container entry listing, file verification, references, timestamps | 0.75 to 0.98 (by files) |
| `finishing` | state `captured` or `captured_incomplete`, standing `active` unless superseding (10.7) | 1.00 |

Progress is published on Loupe's existing channel `job:{job_id}:progress`
(`evidence-engine/app/services/redis_client.py:25-27`), at most once per second and at every
stage change, with the existing keys plus structured ones, never parsed back from log text (the
old pipeline derives progress by regex over log lines, `cellebrite_ingestion.py:80-101`):

```json
{"job_id": "...", "status": "capturing", "progress": 0.41,
 "message": "Reading records: 182,400 of about 338,000",
 "stage": "capturing",
 "counts": {"bytes_read": 512000000, "bytes_total": 1240000000,
            "records": 182400, "files": 0, "documents_done": 1, "documents_total": 2}}
```

The backend subscriber only acts on `completed` and `failed` (`backend/services/job_status_subscriber.py:224-242`),
so new non-terminal statuses pass through it. `jobstatus` gains `verifying_source`, `capturing`
and `reconciling` (migration in unit 2.1: `ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS ...`),
`JobStatus` (`job.py:14-25`) gains the members, and `JobCard.tsx` `STAGE_LABELS` and
`STAGE_COLORS` (`frontend_v2/src/features/evidence/components/JobCard.tsx:31-60`) gain "Checking
source", "Reading report", "Checking completeness"; without the labels the card shows the raw
status string (`:111`). `counting` maps to `verifying_source`; `indexing_files` and `detecting`
map to `capturing`.

### 10.4 Failure states

| State | Cause | Message to the investigator |
|---|---|---|
| `not_readable` | protected or no report (2.4) | per 2.4 |
| `failed` with `container_changed_since_upload` | 3 step 1 | "The stored upload no longer matches what was received. It has not been read. Upload it again." |
| `reconciliation_failed` | 8.3 | per 8.4 |
| `failed` with `memory_budget` | 5.4 | per 5.4 |
| `failed` with `database_error` | write failed after retries | "Reading stopped because the database could not save it. Nothing saved so far is lost. Resume to continue." |
| `cancelled` | 10.6 | "Reading was cancelled. The upload is kept and can be read again." |

A failed job keeps its cursor and is resumable through the existing Resume control
(`jobs.py:40-63`).

### 10.5 Pause, resume, checkpoints

- `run_controlled` (`evidence-engine/app/services/ingestion_control.py:33-58`) supplies the
  exclusive lock per scope (`ingestion_checkpoints.py:169-187`, flock on a shared volume, a
  second resume waits with `Retry(defer=5)`), the 30-second heartbeat that keeps `updated_at`
  fresh against the 2-hour janitor (`ingestion_control.py:14-26`, `jobs/janitor.py:21`), and the
  pause request check. The JSON checkpoint store itself (`ingestion_checkpoints.py:99-121`) is not
  used: durable progress lives in Postgres (plan lesson 5.4).
- The capture thread calls the pause boundary after each flush (the bridge pattern of
  `cellebrite_ingestion.py:210-216`). A pause therefore stops at a committed flush.
- **Cursor.** `phone_extraction_documents.capture_cursor` holds the highest record ordinal and
  file ordinal committed, updated in the flush transaction (5.5). On resume the document is
  re-parsed from the start (C3 capture is 11 s of parsing; re-reading is cheaper and simpler than
  seeking into a deflate stream), rows with ordinals at or below the cursor are encoded but not
  written, and writing resumes after them. The counter pass result is reused if
  `source_counts` is present and the document hash is unchanged. File verification resumes from
  the first `phone_files` row with `verified_at IS NULL`.
- Kill at any point (SIGKILL, OOM, host restart): arq retries (`max_tries = 3`), or the janitor
  marks the job failed and Resume continues it; in both cases the cursor makes the result
  identical to an uninterrupted run (acceptance test 2.4).

### 10.6 Cancel

New action `cancel` on `POST /jobs/{job_id}/cancel?case_id=` for `phone_capture` only. It sets
`pause_requested`; once stopped, it deletes the extraction's `phone_records`, `phone_files`,
`phone_file_references`, `phone_timestamps` and `phone_container_entries` rows **only if the
extraction's standing is `pending`**, sets `capture_state='cancelled'`, and keeps the container
row, its hashes, the evidence row and the job record. An `active` or `superseded` extraction can
never be cancelled away.

### 10.7 Staged replace

Replacing an extraction never deletes first (v1 defect 4.2, and Loupe's copy:
`cellebrite_ingestion.py:163-173` deletes the old graph and evidence rows before writing the new).

1. The new extraction is captured and reconciled like any other, standing `pending`.
2. On success it becomes `active`. If the case already holds an `active` extraction that the
   capture identifies as possibly the same device (the device identity rule belongs to a later
   file; until it exists the test is: same `project@id`, or the same set of `extractionInfo@id`
   values), both stay active and the investigator is told: "This case already has a
   report that appears to be from the same phone ({name}). Both are kept. Use Replace on the newer
   one to retire the older one."
3. `POST /api/phone-extractions/{new_id}/supersede {"previous_id": ...}` (backend, case
   permission `evidence:upload`) runs in one transaction: previous `standing='superseded'`,
   `superseded_at`, `superseded_by_user_id`; new `supersedes_id=previous_id`. Requires the new one
   to be `captured` or `captured_incomplete`. Projections (later files) switch on that flip.
4. Superseded extractions are kept. Purging one is a separate, explicit action not specified here.

### 10.8 Performance targets

Measured parse-and-encode rate is about 130,000 elements per second (C3: 1.45 M in 11.3 s);
the counter about 400,000 per second (lxml). Targets, on the production host, measured in unit
2.4 and recorded:

| Phone | v1 minutes | Target, upload complete to `captured` |
|---|---|---|
| C9, 10-report case | 1.1 | 2 min |
| C3, 10-report case | 63.5 | 4 min |
| C8, 10-report case (readable part) | 4.5 | 6 min (3.1 GB of files to hash) |
| C1, 3-phone (largest) | 173.0 | 30 min |

The largest-phone figure is an estimate from 1.3 (11 to 14 M record elements: about 2 min of
parsing, plus COPY of about 1 M rows and file hashing at 100 MB/s or more); it is not measured
because that report is on the server only. A miss by more than double is a defect to investigate,
not a reason to cap anything.

---

## 11. Removal of Loupe's existing Cellebrite ingestion

Removed in unit 1.7, after the new capture passes on all three samples. The read side (views
over the Neo4j nodes the old ingester wrote) is replaced by later files and removed with them.

| Item | Location | Action |
|---|---|---|
| Old pipeline package | `evidence-engine/app/pipeline/cellebrite/` (`detection.py`, `file_linker.py`, `ingestion.py`, `models.py`, `neo4j_client.py`, `neo4j_writer.py`, `parser.py`, `recovery.py`, `__init__.py`; 3,982 lines) | delete |
| Old job runner | `evidence-engine/app/pipeline/cellebrite_ingestion.py` (302 lines) | delete |
| Worker function | `evidence-engine/app/worker.py:13,64-69,73` | remove `process_cellebrite` |
| Engine routes | `evidence-engine/app/api/routes/cellebrite.py`; `app/main.py:10,53` | delete, replaced by `routes/phone.py` |
| Job type handling | `evidence-engine/app/api/routes/jobs.py:22,60-61` | `cellebrite_ingestion` kept only so old job rows still display; no new ones created |
| Engine tests | `evidence-engine/tests/test_cellebrite_ingestion.py`, `test_cellebrite_dispatch_receipt.py`, `test_phone_report_recovery.py`, `test_phone_graph_recovery_integration.py` | delete; the dispatch-receipt behaviour is re-tested against `phone_capture` |
| Backend client | `backend/services/evidence_engine_client.py:150-195` | replace with `detect_phone_container` and `create_phone_capture_job` |
| Upload route phone branch | `backend/routers/evidence.py:63-65,267-279,335-429,491-544,575-592` (phone use only), `:1204-1285` | remove the phone branch (4.1); `_extract_archive_to_staging` stays for ordinary zips |
| Upload groups | `backend/routers/evidence_upload_groups.py:239-263,276-285` | change per 4.2 |
| Evidence storage helpers | `backend/services/evidence_db_storage.py:573-642` (`add_cellebrite_files`), `:644-670`, `:672-690` (`delete_by_cellebrite_report_key`) | delete once no caller remains; `:692` `list_cellebrite_files` stays while the old Files tab exists |
| Backend tests | `backend/tests/test_evidence_cellebrite_routes.py`, `test_cellebrite_evidence_db_storage.py`; `test_resumable_upload_groups.py:142-151` | delete the first two; rewrite the third against the new dispatch |
| Columns `evidence_files.source_type`, `cellebrite_*`, `capture_time`, `creation_time`, `modify_time`, `latitude`, `longitude`, `has_geotag`, `tags`, `linked_entity_ids` | migrations `20260515_add_cellebrite_evidence_metadata.py`, `20260518_add_cellebrite_file_metadata.py` | **kept**. Migrations are history and are never edited; `source_type` is now used for `phone_extraction`. Dropping the `cellebrite_*` columns is a later migration, after a count shows no rows use them in the deployed database. |
| Read side | `backend/routers/cellebrite.py` (prefix `/api/cellebrite`, `:28`), `backend/services/neo4j/cellebrite_service.py`, `backend/services/cellebrite_intersection_service.py`, `backend/services/neo4j/__init__.py:20,125-156`, `frontend_v2/src/features/cellebrite/`, route `frontend_v2/src/app/routes.tsx:39,163` | kept until the replacement views land (later files); they show only data written by the old ingester |
| Upload toolbar | `frontend_v2/src/features/evidence/components/FileListToolbar.tsx:72,100,257,286-290` ("Cellebrite ZIP", replace checkbox) | the replace checkbox is removed; the option text becomes "Phone report (ZIP, UFDR or folder)" |

---

## 12. Units for phases 0 to 2

Engine tests run in the engine's environment (Python 3.12, `evidence-engine/Dockerfile`); note the
build-state warning that the full engine suite does not run on 3.10 (`docs/loupe-build-state.md`,
"The full engine pytest suite cannot run on 3.10"). New engine code under `evidence-engine/app/phone/`.
Corpus tests read `LOUPE_PHONE_CORPUS`, a local JSON mapping `c3`, `c9`, `c8` to paths, and are
skipped (with a visible skip reason) when it is unset. Case material is never committed.

### Phase 0

**Unit 0.1: reference corpus manifest.**
`evidence-engine/tests/phone/corpus.py` loads `LOUPE_PHONE_CORPUS`. A committed file
`evidence-engine/tests/phone/corpus_expected.json` holds **counts only** for C3, C9, C8: the totals
in 1.2, the per-path element counts, record and file counts. Hash sums are not committed (they are
derived from content); they live in a local file next to the corpus.
*Acceptance:* the manifest's totals equal 1.2 exactly (C3 1,451,062 / 3,448,982 / 653,473; C9
689,601 / 1,674,326 / 284,541; C8 1,269,819 / 2,743,889 / 574,716).

**Unit 0.2: element-level counter.** `app/phone/counter.py` (lxml) per 8.1 to 8.2, with document
SHA-256 and MD5. Unit tests on synthetic XML for each measure, including a truncated document, a
non-whitespace tail, a repeated field name, a leaf with whitespace-only text, a foreign namespace.
*Acceptance:* on the corpus, totals equal unit 0.1; two runs give identical output including hash
sums (stable); an independent expat count gives identical elements, attributes, texts and hash
sums for every path (this extends the measured count agreement to the hash sums, which is not yet
measured); C8 `.xmlTagged` reports the open path `project/taggedFiles/file/metadata[MetaData]`.

### Phase 1

**Unit 1.1: schema.** Migration and models of 6.2; engine mirrors. Downgrade drops the tables and
types. *Acceptance:* `alembic upgrade head` then `downgrade -1` then `upgrade head` on an empty
database; `alembic heads` shows one head; a unit test inserts and reads one row in each table.

**Unit 1.2: intake detection and container hashing.** `app/phone/detect.py`, `app/phone/intake.py`,
endpoint `POST /cases/{id}/phone/detect`. *Acceptance:* C3 folder and C3 zip each give one root,
form `full`, skipped counts `__MACOSX` 43,167 (zip) and `.DS_Store`; C9 zip one root, `__MACOSX`
29,784; C8 folder one root, form `split_sections`, documents `model` and `tagged` non-empty, six
empty, `tagged` `suspected_truncated=true`, `model` false; synthetic fixtures: a `.ufdr` whose
`report.xml` starts `2D 06 52 6D` gives `protected_no_password`; an encrypted entry gives
`protected_password`; a `report.xml` without header strings gives `protected_or_invalid`; a zip
with two report folders gives two roots; a report inside a report gives one root and
`nested_report_ignored`; a zip of ordinary documents gives `not_a_phone_report`. Container SHA-256
on C9.zip equals `shasum -a 256`.

**Unit 1.3: capture.** `app/phone/capture.py` per section 5, writing through COPY with the cursor.
*Acceptance:* on the corpus, record rows 71,045 / 14,005 / 73,637 and file rows 43,043 / 29,536 /
11,664 (one partial); C8 extraction `captured_incomplete` with the truncation recorded; peak RSS
under 512 MiB; capturing the same container again creates no rows and links the container (6.3);
uploading C3 as folder and as zip yields one extraction with two containers.

**Unit 1.4: reconciliation.** `app/phone/recount.py`, `app/phone/reconcile.py`. *Acceptance:*
`exact` for C3, C9 and C8 (both documents); a test that deletes one `value` from one stored body,
alters one attribute value, and appends one element each gives `differs` with the right path and
measure, and every difference listed.

**Unit 1.5: files.** Container entry listing, verification (7.2), references (7.3). *Acceptance:*
outcome counts equal 1.5 for all three (C3 match 21,155, empty_placeholder 21,664, missing 224;
C9 match 29,456, missing 80; C8 match 1,172, missing 9,929, size_mismatch 326, mismatch 236);
jump-target file references resolved 709 (C3) and 877 of 879 (C9); every `attachment_extracted_path`
value present on disk resolves (`container_entry`) in C3 and C9; the 228 C9 file ids sharing 26
contents each keep their own row and references.

**Unit 1.6: timestamps.** `app/phone/timestamps.py` per section 9. *Acceptance:* `explicit` rows
22,859 / 5,218 / 59,666 for record TimeStamp values, `absent` 22 / 0 / 6; device zone C9
`America/New_York` from `timeZoneConfigurations`, C3 the configured zone, C8 NULL with source
`not_stated`; `formatted_text` kept on every row.

**Unit 1.7: upload path and removal.** Section 4 and 11. *Acceptance:* backend test: a resumable
archive group whose zip holds a report is not extracted, registers one `phone_extraction` evidence
row, dispatches one `phone_capture` job, and a repeated `complete` after a lost response
dispatches nothing new (`request_id` stable); a folder group of 43,144 members is accepted; a
`.ufdr` archive group is accepted; `POST /api/evidence/upload` with a phone zip returns 409; the
removed files are gone and both suites pass (financial suite baseline per
`docs/loupe-build-state.md`); auto-read skips `phone_extraction` rows.

### Phase 2

**Unit 2.1: queue, worker, container.** Section 10.1 to 10.3. *Acceptance:* a phone job is
enqueued on `arq:phone-capture` and runs on the phone worker while the default and PDF workers
are each busy with a long job; progress messages on `job:{id}:progress` carry `stage` and
`counts`, are at most one per second, and every stage appears in order; `JobCard` shows the new
labels (unit test).

**Unit 2.2: pause, resume, cancel.** *Acceptance:* pause during `capturing` stops after a committed
flush; resume completes; captured rows and the reconciliation result equal an uninterrupted run
(compare a SHA-256 over all rows ordered by key); cancel on a `pending` extraction removes its rows
and keeps the container and evidence row; cancel on an `active` one returns 409.

**Unit 2.3: staged replace.** *Acceptance:* with C9 active, capture a second copy of C9 altered by
one byte in one value (synthetic, built in a temp directory from C9, never committed) and
supersede: the old one becomes `superseded` only after the new one is `captured`; a forced
failure of the new capture leaves the old one `active` and untouched.

**Unit 2.4: kill and resume.** *Acceptance:* on C3 and C8, `SIGKILL` the phone worker at a random
point in each stage (verifying, counting, capturing, reconciling, indexing_files), restart, resume;
final rows, reconciliation and file outcomes are byte-for-byte equal (row digest) to an
uninterrupted run. Durations of uninterrupted runs recorded against 10.8.

---

## 13. Decisions not settled by the plan

| # | Decision | Reason | Reverse if |
|---|---|---|---|
| D1 | One row per model (top-level and nested) with a JSONB body; no per-value table at capture | 1.3 and 6.1: addressable messages, 0.97 to 1.12 KB per row, 967,543 rows for the largest phone versus 4.7 M values | JSONB queries measured too slow for registry or interpretation |
| D2 | Record identity is `(extraction, document, document-order ordinal)`; Cellebrite `id` is an indexed non-unique attribute | ids repeat 2,341 to 3,080 times per report (1.3) | never; ordinals are a function of the bytes |
| D3 | Locators use child positions, with a generated readable form | field names repeat within a model (38 in C8) | never |
| D4 | Counter uses lxml, capture uses expat | independent parsers, measured to agree on all three samples including the truncated section | a sample where the parsers legitimately differ; then count with both and require all three to match |
| D5 | Reconciliation includes order-independent hash sums of every attribute and text, not only counts | counts cannot detect a changed value | never |
| D6 | Zip and UFDR containers are never unpacked; read in place | avoids the 64 GB expanded limit and double disk, keeps the original bytes as the only copy; streaming reads measured fast | media playback from inside a zip too slow |
| D7 | Tagged files are not `evidence_files` rows; the container is one evidence row | v1's 164k-row problem and its filter side effects | a Loupe-wide feature can only read `evidence_files` (then register lazily) |
| D8 | `empty_placeholder` is its own verification outcome | 21,664 C3 files are zero bytes with size 0 declared and a non-empty MD5: not a mismatch, not a match | never |
| D9 | The resumable group path is the only phone upload path; `MAX_MEMBERS` 200,000 for folder groups | the old multipart path deletes the zip and caps at 20,000; C3 and C9 exceed 20,000 | a production exceeds 200,000 files (then page the manifest) |
| D10 | Detection lives in the engine, the backend asks through an endpoint | one implementation; the backend already calls the engine to check folders | never |
| D11 | Container hash recomputed by the job and compared with the upload hash; mismatch stops the job | the stored bytes must be the received bytes before anything is read | never |
| D12 | Capture writes with sync psycopg in the worker thread, DSN derived locally, no backend import, no environment mutation | the old in-process backend import mutates `DATABASE_URL` process-wide (`cellebrite_ingestion.py:45-51`) | never |
| D13 | Durable cursor in Postgres updated in the same transaction as each flush; resume re-parses and skips | exactly-once without seeking into deflate streams; re-parse of C3 costs 11 s | parse cost on the largest phone makes resume slow (then add a byte offset for uncompressed sources) |
| D14 | `max_jobs = 1`, `mem_limit: 1g`, 512 MiB internal budget | measured peak RSS 37 to 81 MB; host memory pressure | measured queueing delay |
| D15 | A matching device never auto-replaces; Replace is an explicit supersede after the new capture completes | removes delete-before-write; device identity is not yet defined | the identity file defines a reliable device key and Neil wants auto-supersede |
| D16 | Cancel deletes partial capture rows only for `pending` extractions | partial capture is not evidence; the container is | never |
| D17 | Offset-less times keep `local_wall_time` and a NULL instant | flag, don't guess (plan 6.7) | never |
| D18 | Split-section suffixes recognised by pattern, unknown suffixes captured as `unknown` role | types and sections are discovered, not listed | never |
| D19 | Three new `jobstatus` values and JobCard labels instead of reusing "Extracting Text" | the card would otherwise mislabel the stage | never |
| D20 | Upload messages say what is needed "from whoever produced it", never how to re-export | the reader receives productions | Neil rules otherwise |
| D21 | Old Cellebrite columns on `evidence_files` kept; read side kept until replaced | migrations are history; the deployed database may hold old rows | counts show no rows use them |

---

## 14. Not yet established

- Whether any server phone has populated `images`, `HashSetsInfo`, `carvedFiles`, `infectedFiles`
  or `extraInfos` (empty in all three local samples).
- What `metadata` item `UFDIntegrity` states and whether it can be checked against a digest.
- Real UFDR structure, including whether its `report.xml` uses the same root and namespace as the
  folder reports, and how media inside it is laid out. No `.ufdr` sample exists.
- Whether a split export can hold more than one non-empty records section, and what the six other
  section kinds contain when non-empty (all zero bytes in C8).
- Tagged file count and total size of the largest phone, hence its exact capture time.
- Whether libxml2 and expat agree on value and attribute hash sums (counts measured equal; sums
  are tested in unit 0.2).
- Whether `enableAutomaticallyConvertToUTC` ever changes the stored XML values (one sample with it
  off still stores `+00:00`).
- Whether the deployed Loupe database holds rows written by the old Cellebrite ingester.
- The backend's request body limit for a 200,000-member manifest.
- The content of `v1_memory/project_host_no_swap_oom.md` (only its index line was available).
- Whether `project@ModelCount` excludes a definable set of records (it differs from the counted
  top-level models by 2 in C3 and C8).
