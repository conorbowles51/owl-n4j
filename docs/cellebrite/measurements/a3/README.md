# Stage A3: server measurement batch (06 section 5)

Measured read-only on the 14 server reports, one report at a time, at `nice 19` and idle IO priority under
`systemd-run --scope -p MemoryMax=2G` (3 GB for P13 and P14). Labels P01 to P14 as in 01 section 1.8.
Everything here is counts, schema names and guarded values (04 section 13); joins across phones use a salted
HMAC kept on the server and deleted after this batch. Files:

- `P01.json` to `P14.json`: per report, every measure below (written by `scripts/a3_extract.py`, with the
  `extraInfos` pass `a3_extrainfo.py` and the `RelatedModels` pass `a3_related.py`, assembled by
  `a3_report.py`).
- `cross.json`: pairs of phones within each case (`a3_cross.py`).
- `summary.json`: the seed comparison and the tables below.
- `a3_guard_check.py` passes on every file here (0 flags).

The method reproduces the Mac measurements where both exist. On P06 and P09 (the Mac's C3 and C9) X1, X2,
X4, X8, X9 and X10 equal 05 section 1.3 (X11 is 1 here against 0: this batch counts a file as attachment-linked
through any record's `file_id` or file jump target, and the local figure used `scripts/s05/attmd5.py`); on P02 and P09, X1, X2, X4 to X9 equal its A-C9 & A-C8 column (P02 is
the server's own C8 export, so its file counts X10 and X11 differ). Deleted-message counts on P02, P06 and
P09 equal 05 M10, and offset-absent TimeStamp counts on P06, P09 and P02 equal 01 section 1.6 (22, 0, 6).
X3 is counted under section 9's definitions here and does not compare with 05's figures.

## 1. 01: size, file count, timing and memory (01 section 14)

- Largest report: P14, 17,283,869 elements, 338,715 top-level records, 158,114 tagged files (1.77 GB XML).
  Most tagged files: P04, 309,779.
- Parse time at `nice 19` on the shared server: counter (lxml) 374 s on P14, 334 s on P08; peak memory 42 to
  46 MiB on every report (01 section 1.8).
- The measurement pass that keeps per-report state (this batch) peaked at 515 MiB (P14), 560 MiB (P03,
  before `extraInfos` elements were released during the parse) and under 500 MiB elsewhere.
- Folder file counts and bytes: the reference manifest (01 unit 0.1, `corpus-manifest-summary.json`).

## 2. 02-U2: the seed recomputed from the 14 reports

Recomputed directly from the reports, the seed equals the catalogue (`catalogue-14-phones.json`) type by type
on all 14 reports: 62 types, 3,246,839 records, 466 (type, field, kind, value type) rows over 465 (type,
field, kind), 54 named sets with 208 values plus `DecodingSourceOptions` = `Decoding`, and one value-type
drift field, `ChatActivity.SystemMessageId`. No type, field row or named-set value is on one side only.

That equality holds only when the models under a `RelatedModels` element are counted: 3,737 models on 5
reports (P02 2, P07 5, P08 6, P12 370, P13 3,354). They are other-source copies of a record: each has the
type of its owner, an id found on no top-level record, a different `source_index` from its owner, and
`isrelated="True"`; on P13 1,862 of 2,250 agree with their owner on every shared field. `project@ModelCount`
counts them (P12: 366 directly under records, the report's gap of 366).

Nesting relations measured on the 14: 95 (parent type, field, kind, child type), of which 18 are
`RelatedModels`; the list is `summary.json` `seed_02_U2.total.nesting_relations_list`.

## 3. 01 section 9.3: examiner zone against device setting

| Comparison | Reports |
|---|---|
| device setting equals the examiner zone (after stripping the leading `_`) | 8: P01, P02, P03, P08, P09, P10, P13, P14 |
| device setting absent; examiner zone present | 5: P04, P05, P06, P07, P11 |
| both present and different | 1: P12 (UTC offsets differ by 5 h in January and 4 h in July) |

`enableAutomaticallyConvertToUTC` is `True` on the 5 reports without a device setting and on P12, `False`
on the other 8. The reverse-if of 01 section 9.3 (agreement wherever both exist) is not met: the rule
stands.

## 4. 03 20.1: duplicate copies under D-9 at exact, 1 s and 2 s

Groups of records with an equal D-9 key (extraction, kind, direction, sender, sorted recipients, content
hash) whose instants are equal (exact) or chain within 1 s or 2 s. A 1 s chain can merge exact groups, so
its group count can be lower than the exact count while covering more records.

| Report | Messages with an instant | exact: groups / records | 1 s | 2 s | Calls exact | Calls 2 s |
|---|---|---|---|---|---|---|
| P01 | 10,421 | 6 / 12 | 14 / 40 | 18 / 51 | 21 / 42 | 21 / 42 |
| P02 | 2,814 | 24 / 53 | 27 / 59 | 28 / 61 | 0 / 0 | 0 / 0 |
| P03 | 2,694 | 1 / 2 | 14 / 28 | 17 / 34 | 0 / 0 | 0 / 0 |
| P04 | 9,723 | 353 / 729 | 742 / 1,623 | 749 / 1,638 | 0 / 0 | 1 / 2 |
| P05 | 12,920 | 191 / 422 | 214 / 559 | 217 / 570 | 0 / 0 | 21 / 51 |
| P06 | 2,889 | 23 / 50 | 52 / 175 | 53 / 177 | 0 / 0 | 2 / 4 |
| P07 | 8,499 | 277 / 555 | 293 / 601 | 303 / 622 | 0 / 0 | 0 / 0 |
| P08 | 183,236 | 1,346 / 2,754 | 1,441 / 3,064 | 1,566 / 3,324 | 0 / 0 | 0 / 0 |
| P09 | 3,420 | 16 / 48 | 17 / 74 | 19 / 78 | 0 / 0 | 0 / 0 |
| P10 | 33,073 | 1,508 / 5,056 | 1,474 / 5,318 | 1,482 / 5,345 | 0 / 0 | 3 / 8 |
| P11 | 50 | 0 / 0 | 1 / 2 | 1 / 2 | 0 / 0 | 0 / 0 |
| P12 | 2,127 | 4 / 11 | 8 / 85 | 12 / 94 | 0 / 0 | 0 / 0 |
| P13 | 44,030 | 1,925 / 6,642 | 1,700 / 7,576 | 1,782 / 7,859 | 20 / 40 | 23 / 47 |
| P14 | 54,753 | 5,443 / 13,620 | 5,354 / 14,108 | 5,411 / 14,349 | 553 / 1,214 | 554 / 1,220 |

Exact equality finds most duplicate copies; 1 s adds records on every report with duplicates (P12: 11 to
85, P06: 50 to 175, P14: 13,620 to 14,108) and 2 s adds a further 0 to 28 percent (P01: 40 to 51). Equal-key messages 2 to
60 s apart are counted separately in `P*.json` `d4_duplicates`.

## 5. 03 20.3: real row sizes

Deferred to `cb-interpret`, which builds the `StreamRow` it measures (sent through `tell.sh`).

## 6. 03 20.6: code points in captured strings

1,034,315,319 ASCII and 2,889,954 non-ASCII characters in String values. Styled and script classes:
format or control characters 924,519; characters changed by NFKC 481,828; mathematical alphanumerics
93,666; Cyrillic 70,168; regional indicators 11,225; negative circled or squared Latin 3,866; enclosed
alphanumerics 2,666; letterlike 2,509; Latin small capitals 902; Greek 823; fullwidth ASCII 563;
superscripts and subscripts 403. Per report and by Unicode block: `P*.json` `d6_codepoints`.

## 7. 03 20.5: audio and video containers and codecs

69,212 Audio and Video tagged files probed with `ffprobe` (format and stream codecs; no content decoded).
Largest groups: Ogg Opus audio 16,980; AAC-only MP4 7,543 tagged Video and 3,861 tagged Audio; MP4 H.264 7,480; MP4 AAC with H.264
4,191; MP4 AV1 3,264; MP3 3,066; MP4 HEVC 2,140; CAF AAC 1,907; CAF PCM 1,729; AMR-NB 1,515; Ogg Vorbis
1,465; MP4 AAC with HEVC 1,242; WebM VP9 471; AIFF PCM 815; MPEG-TS H.264 262; MP4 or 3GP with H.263 79. Unrecognised by
ffprobe (no streams): 3,950 video and 1,080 audio. Not on disk: 562 video, 495 audio. Full list:
`summary.json` `d7_media`. Which of these each browser plays: `browser-playback/README.md`.

## 8. 04 M1 to M12 (04 section 13)

Per report in `P*.json`: M1 `m1_*`, M2 `m2_*`, M3 `m3_*`, M4 `m4_*`, M5 `m5_*`, M6 `m6_party_dates`, M7
`m7_*`, M8 `m8_power`, M9 `m9_*`, M11 `m11`, M12 `m12`; M10 is in `cross.json`.

M3: every TimeStamp value's text differs from its `formattedTimestamp` attribute (the text carries
milliseconds). Values without an offset:

| Report | TimeStamp values | offset absent | text differs from formattedTimestamp |
|---|---|---|---|
| P01 | 14,548 | 2 | 14,548 |
| P02 | 59,673 | 6 | 59,673 |
| P03 | 10,423 | 2,089 | 10,423 |
| P04 | 178,159 | 2,245 | 178,159 |
| P05 | 30,192 | 81 | 30,192 |
| P06 | 22,881 | 22 | 22,881 |
| P07 | 36,725 | 0 | 36,725 |
| P08 | 275,119 | 0 | 275,119 |
| P09 | 5,218 | 0 | 5,218 |
| P10 | 50,755 | 0 | 50,755 |
| P11 | 353,205 | 3,479 | 353,205 |
| P12 | 10,533 | 33 | 10,533 |
| P13 | 567,024 | 4,005 | 567,024 |
| P14 | 595,975 | 368 | 595,975 |

M5, locations:

| Report | Location records | with coordinate | accuracy P50 / P90 m (n) | BSSIDs placed on >= 2 days (accuracy <= 100 m / radius <= 100 m) |
|---|---|---|---|---|
| P01 | 1,220 | 1,220 |  | 0 / 0 |
| P02 | 206 | 35 |  | 0 / 0 |
| P03 | 617 | 597 | 149000.0 / 149000.0 (3) | 0 / 0 |
| P04 | 42,607 | 42,562 | 40.0 / 1414.0 (13,255) | 3,068 / 3,068 |
| P05 | 110 | 110 |  | 0 / 0 |
| P06 | 31 | 31 |  | 0 / 0 |
| P07 | 477 | 471 |  | 0 / 0 |
| P08 | 17 | 16 |  | 0 / 0 |
| P09 | 7 | 7 |  | 0 / 0 |
| P10 | 0 | 0 |  | 0 / 0 |
| P11 | 1,482 | 191 | 17.963 / 1414.0 (9) | 0 / 0 |
| P12 | 103 | 53 |  | 0 / 0 |
| P13 | 3,533 | 3,521 | 57.0 / 2000.0 (2,608) | 0 / 0 |
| P14 | 13,355 | 13,324 | 39.0 / 60.0 (12,728) | 0 / 0 |

M11 and M12 (UTC days; the device zone is not applied):

| Report | Days with a candidate interaction | Days with >= 12 observed hours | Observed hours | Quiet run (hours, start UTC) at 0.05 / 0.10 / 0.20 | Extraction start in header | Events after extraction start |
|---|---|---|---|---|---|---|
| P01 | 32 | 0 | 0 | - / - / - | yes | 0 |
| P02 | 86 | 0 | 0 | - / - / - | yes | 2 |
| P03 | 42 | 0 | 3 | - / - / - | absent |  |
| P04 | 300 | 24 | 474 | 0 h / 1 h / 3 h from 07 | yes | 12 |
| P05 | 574 | 0 | 0 | - / - / - | yes | 2 |
| P06 | 112 | 0 | 0 | - / - / - | yes | 0 |
| P07 | 128 | 0 | 0 | - / - / - | yes | 0 |
| P08 | 1,073 | 0 | 0 | - / - / - | yes | 0 |
| P09 | 56 | 0 | 0 | - / - / - | yes | 0 |
| P10 | 739 | 0 | 0 | - / - / - | yes | 0 |
| P11 | 443 | 668 | 14,265 | 15 h from 05 / 24 h from 00 / 24 h from 00 | yes | 13 |
| P12 | 32 | 0 | 0 | - / - / - | yes | 0 |
| P13 | 434 | 638 | 15,310 | 4 h from 06 / 11 h from 04 / 24 h from 00 | yes | 79 |
| P14 | 414 | 546 | 13,120 | 2 h / 4 h from 06 / 10 h from 04 | absent |  |

M10: Bluetooth detections naming the other phone are skipped: they need each phone's own device name from
the identity work (02), which does not exist yet. The other M10 counts are in `cross.json`.

## 9. 05 measurements

Per report:

| Report | Messages | M-1b amounts S1 / S2 / S3 / S9 | M-3d replies+quotes / with id on phone / without | M-3e chats >= 20 / with a deletion | M-4a incoming / owner DateRead | M-8a attachment-linked with MD5 / camera | M-9a pages / searches timed / untimed | M-10a calendar / with location / check-ins / notes | M-11a contacts / TimeCreated |
|---|---|---|---|---|---|---|---|---|---|
| P01 | 10,432 | 0 / 6 / 0 / 2 | 16 / 11 / 4 | 35 / 2 | 4,472 / 29 | 556 / 647 | 0 / 71 / 0 | 9 / 0 / 0 / 13 | 0 / 0 |
| P02 | 2,829 | 0 / 15 / 3 / 0 | 35 / 35 / 0 | 22 / 12 | 1,378 / 23 | 335 / 14 | 4,129 / 739 / 13 | 0 / 0 / 5 / 2 | 241 / 10 |
| P03 | 2,696 | 0 / 0 / 34 / 0 | 477 / 14 / 0 | 41 / 14 | 867 / 457 | 263 / 0 | 838 / 355 / 422 | 129 / 0 / 0 / 1 | 3,983 / 182 |
| P04 | 9,733 | 0 / 12 / 2,975 / 8 | 2,573 / 201 / 2 | 51 / 4 | 4,797 / 2,471 | 1,178 / 264 | 1,703 / 420 / 140 | 249 / 0 / 0 / 6 | 2,303 / 529 |
| P05 | 13,032 | 0 / 36 / 222 / 9 | 42 / 42 / 0 | 58 / 7 | 9,421 / 0 | 2,141 / 427 | 9,658 / 0 / 0 | 3 / 0 / 0 / 0 | 1,517 / 0 |
| P06 | 2,917 | 0 / 12 / 169 / 4 | 22 / 22 / 0 | 36 / 0 | 1,858 / 0 | 654 / 152 | 6,936 / 10 / 9 | 80 / 3 / 0 / 0 | 1,612 / 0 |
| P07 | 8,527 | 0 / 4 / 56 / 2 | 687 / 685 / 2 | 24 / 2 | 4,619 / 872 | 789 / 16 | 4,255 / 24 / 8 | 81 / 0 / 0 / 2 | 464 / 7 |
| P08 | 186,787 | 0 / 10 / 19 / 102 | 887 / 887 / 0 | 923 / 11 | 81,064 / 0 | 10,749 / 269 | 4,282 / 71 / 0 | 40 / 0 / 0 / 2 | 13,005 / 0 |
| P09 | 3,421 | 0 / 0 / 0 / 1 | 13 / 13 / 0 | 39 / 1 | 2,029 / 0 | 827 / 151 | 213 / 5 / 8 | 1 / 0 / 0 / 0 | 235 / 0 |
| P10 | 33,084 | 0 / 0 / 4,899 / 10 | 411 / 256 / 38 | 90 / 68 | 19,379 / 77 | 1,489 / 0 | 0 / 0 / 0 | 0 / 0 / 0 / 0 | 2,940 / 1,530 |
| P11 | 51 | 0 / 1 / 3,161 / 0 | 2 / 0 / 0 | 0 / 0 | 2 / 0 | 40 / 148 | 55,590 / 897 / 7,884 | 133 / 0 / 0 / 0 | 2,552 / 2,357 |
| P12 | 2,144 | 0 / 7 / 0 / 0 | 177 / 177 / 0 | 22 / 0 | 1,466 / 0 | 481 / 130 | 1,771 / 192 / 31 | 0 / 0 / 0 / 0 | 1,447 / 0 |
| P13 | 44,064 | 9 / 38 / 50 / 502 | 5,242 / 4,560 / 239 | 205 / 5 | 11,880 / 291 | 5,930 / 90 | 2,137 / 14 / 80 | 137 / 0 / 2 / 5 | 8,497 / 280 |
| P14 | 57,826 | 3 / 42 / 2 / 342 | 10,281 / 8,073 / 1,648 | 317 / 48 | 19,263 / 124 | 12,011 / 1,115 | 9,269 / 179 / 1,340 | 138 / 0 / 2 / 0 | 4,679 / 101 |

Notifications exist on P13 (3,951, 21 distinct `ServiceIdentifier`) and P14 (3,089, 19). `ChatType` exists
on P01, P12, P13 and P14 only, so M-4b and M-4c count there only. Deleted InstantMessage records
(`deleted_state` Deleted): P10 7,974; P14 11,579; P08 3,894; P03 968; P02 802; P07 195; P05 51; under 50
elsewhere.

Phone pairs within each case (X1: owner identifiers of the first phone seen as a party on the second, and the
reverse; X3: distinct / frequent common bodies of at least 10 characters; X7: median, MAD, exactly zero;
M-5a: 15-minute bins where both phones are placed, with the together/apart verdict; 1,000 m assumed for a
point without accuracy):

| Pair | X1 | X2 | X3 | X4 | X5 | X6 | X7 | X9 | X10 | X11 | M-8b | M-5a bins | M-5a WiFi bins | M-5b strong | M-5c days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P02 & P03 | 0 of 10; 0 of 8 | 13 | 13 / 5 | 0 | 0 | 0 |  | 1 | 125 | 0 | 0 | 0 | 0 | no | 23 |
| P02 & P04 | 1 of 10; 1 of 6 | 26 | 22 / 14 | 20 | 14 | 15 | 2.818 s / 0.579 s / 0 | 1 | 417 | 0 | 0 | 0 | 0 | no | 45 |
| P02 & P05 | 0 of 10; 0 of 4 | 10 | 8 / 2 | 0 | 0 | 0 |  | 1 | 9847 | 9 | 9 | 0 | 0 | no | 56 |
| P02 & P06 | 0 of 10; 0 of 6 | 26 | 11 / 1 | 0 | 0 | 0 |  | 40 | 10816 | 0 | 0 | 0 | 0 | no | 35 |
| P02 & P07 | 1 of 10; 0 of 7 | 22 | 16 / 4 | 0 | 0 | 0 |  | 32 | 27136 | 6 | 6 | 0 | 0 | no | 56 |
| P02 & P08 | 1 of 10; 1 of 5 | 15 | 15 / 20 | 0 | 0 | 0 |  | 0 | 4967 | 6 | 6 | 0 | 0 | no | 56 |
| P02 & P09 | 1 of 10; 2 of 5 | 21 | 56 / 9 | 18 | 18 | 0 | 0.0 s / 0.0 s / 18 | 15 | 16679 | 14 | 14 | 0 | 0 | no | 36 |
| P02 & P10 | 0 of 10; 0 of 16 | 6 | 16 / 7 | 0 | 0 | 0 |  | 1 | 6 | 0 | 0 | 0 | 0 | no | 24 |
| P02 & P11 | 0 of 10; 0 of 5 | 5 | 0 / 0 | 0 | 0 | 0 |  | 0 | 24 | 0 | 0 | 0 | 0 | no | 35 |
| P03 & P04 | 1 of 8; 0 of 6 | 31 | 14 / 15 | 0 | 0 | 0 |  | 10 | 157642 | 4 | 4 | 43 (apart (assumed radius) 14, indeterminate 11, together 1, together (assumed radius) 17) | 0 | no | 41 |
| P03 & P05 | 0 of 8; 0 of 4 | 9 | 4 / 5 | 0 | 0 | 0 |  | 2 | 8 | 0 | 0 | 0 | 0 | no | 42 |
| P03 & P06 | 0 of 8; 0 of 6 | 20 | 11 / 2 | 0 | 0 | 0 |  | 6 | 38 | 1 | 1 | 0 | 0 | no | 30 |
| P03 & P07 | 0 of 8; 0 of 7 | 8 | 11 / 6 | 0 | 0 | 0 |  | 4 | 69 | 0 | 0 | 0 | 0 | no | 39 |
| P03 & P08 | 1 of 8; 1 of 5 | 7 | 25 / 15 | 6 | 6 | 6 | 0.786 s / 0.132 s / 0 | 4 | 30 | 0 | 0 | 0 | 0 | no | 42 |
| P03 & P09 | 0 of 8; 0 of 5 | 2 | 8 / 1 | 0 | 0 | 0 |  | 1 | 2 | 0 | 0 | 0 | 0 | no | 0 |
| P03 & P10 | 0 of 8; 0 of 16 | 11 | 21 / 13 | 0 | 0 | 0 |  | 3 | 15250 | 0 | 0 | 0 | 0 | no | 34 |
| P03 & P11 | 0 of 8; 0 of 5 | 5 | 0 / 0 | 0 | 0 | 0 |  | 0 | 140860 | 1 | 1 | 1 (apart (assumed radius) 1) | 0 | no | 28 |
| P04 & P05 | 0 of 6; 0 of 4 | 21 | 10 / 12 | 0 | 0 | 0 |  | 2 | 385 | 0 | 0 | 0 | 0 | no | 165 |
| P04 & P06 | 4 of 6; 4 of 6 | 118 | 85 / 9 | 74 | 0 | 0 | 0.0 s / 0.0 s / 74 | 53 | 805 | 23 | 23 | 0 | 0 | yes | 88 |
| P04 & P07 | 0 of 6; 0 of 7 | 23 | 20 / 10 | 1 | 0 | 0 | 111.428 s / 0.0 s / 0 | 0 | 609 | 0 | 0 | 3 (apart (assumed radius) 1, indeterminate 2) | 0 | no | 84 |
| P04 & P08 | 1 of 6; 1 of 5 | 28 | 301 / 51 | 259 | 259 | 0 | 0.594 s / 0.46 s / 0 | 7 | 99 | 5 | 5 | 0 | 0 | no | 196 |
| P04 & P09 | 0 of 6; 0 of 5 | 5 | 8 / 6 | 0 | 0 | 0 |  | 3 | 226 | 0 | 0 | 0 | 0 | no | 10 |
| P04 & P10 | 0 of 6; 0 of 16 | 38 | 23 / 23 | 0 | 0 | 0 |  | 3 | 10799 | 0 | 0 | 0 | 0 | no | 119 |
| P04 & P11 | 0 of 6; 0 of 5 | 31 | 1 / 0 | 0 | 0 | 0 |  | 0 | 157430 | 1 | 6 | 1 (together (assumed radius) 1) | 0 | no | 84 |
| P05 & P06 | 0 of 4; 0 of 6 | 19 | 9 / 6 | 0 | 0 | 0 |  | 4 | 5135 | 3 | 3 | 0 | 0 | no | 101 |
| P05 & P07 | 0 of 4; 0 of 7 | 11 | 10 / 5 | 0 | 0 | 0 |  | 0 | 9869 | 10 | 10 | 0 | 0 | no | 119 |
| P05 & P08 | 1 of 4; 1 of 5 | 50 | 170 / 92 | 73 | 71 | 61 | 0.518 s / 0.387 s / 1 | 424 | 2496 | 46 | 46 | 0 | 0 | no | 539 |
| P05 & P09 | 0 of 4; 0 of 5 | 2 | 4 / 4 | 0 | 0 | 0 |  | 1 | 6458 | 0 | 0 | 0 | 0 | no | 14 |
| P05 & P10 | 0 of 4; 0 of 16 | 14 | 22 / 12 | 0 | 0 | 0 |  | 0 | 4 | 0 | 0 | 0 | 0 | no | 415 |
| P05 & P11 | 0 of 4; 0 of 5 | 8 | 0 / 0 | 0 | 0 | 0 |  | 1 | 928 | 0 | 0 | 0 | 0 | no | 341 |
| P06 & P07 | 0 of 6; 0 of 7 | 19 | 10 / 2 | 0 | 0 | 0 |  | 43 | 10728 | 0 | 0 | 0 | 0 | no | 63 |
| P06 & P08 | 2 of 6; 1 of 5 | 22 | 62 / 29 | 43 | 43 | 0 | 0.39 s / 0.328 s / 0 | 2 | 6874 | 7 | 7 | 0 | 0 | no | 102 |
| P06 & P09 | 0 of 6; 3 of 5 | 12 | 4 / 2 | 0 | 0 | 0 |  | 19 | 7030 | 1 | 1 | 0 | 0 | no | 10 |
| P06 & P10 | 0 of 6; 0 of 16 | 20 | 11 / 9 | 0 | 0 | 0 |  | 0 | 2 | 0 | 0 | 0 | 0 | no | 59 |
| P06 & P11 | 0 of 6; 0 of 5 | 16 | 0 / 0 | 0 | 0 | 0 |  | 0 | 10 | 0 | 0 | 0 | 0 | no | 52 |
| P07 & P08 | 0 of 7; 0 of 5 | 18 | 42 / 31 | 0 | 0 | 0 |  | 0 | 5004 | 8 | 8 | 0 | 0 | no | 125 |
| P07 & P09 | 0 of 7; 2 of 5 | 7 | 9 / 4 | 0 | 0 | 0 |  | 13 | 16626 | 0 | 0 | 0 | 0 | no | 16 |
| P07 & P10 | 0 of 7; 0 of 16 | 21 | 29 / 8 | 0 | 0 | 0 |  | 0 | 6 | 1 | 1 | 0 | 0 | no | 75 |
| P07 & P11 | 1 of 7; 1 of 5 | 20 | 0 / 0 | 0 | 0 | 0 |  | 0 | 159 | 0 | 0 | 0 | 0 | no | 64 |
| P08 & P09 | 0 of 5; 1 of 5 | 8 | 16 / 11 | 0 | 0 | 0 |  | 6 | 4317 | 1 | 1 | 0 | 0 | no | 14 |
| P08 & P10 | 0 of 5; 0 of 16 | 17 | 85 / 66 | 0 | 0 | 0 |  | 0 | 3 | 0 | 0 | 0 | 0 | no | 729 |
| P08 & P11 | 0 of 5; 0 of 5 | 8 | 0 / 0 | 0 | 0 | 0 |  | 2 | 26 | 0 | 0 | 0 | 0 | no | 435 |
| P09 & P10 | 0 of 5; 0 of 16 | 5 | 8 / 6 | 0 | 0 | 0 |  | 0 | 1 | 0 | 0 | 0 | 0 | no | 0 |
| P09 & P11 | 1 of 5; 0 of 5 | 2 | 0 / 0 | 0 | 0 | 0 |  | 0 | 31 | 0 | 0 | 0 | 0 | no | 11 |
| P10 & P11 | 2 of 16; 2 of 5 | 2270 | 0 / 2 | 0 | 0 | 0 |  | 0 | 2138 | 0 | 0 | 0 | 0 | no | 353 |
| P12 & P13 | 1 of 2; 1 of 6 | 19 | 9 / 5 | 7 | 5 | 3 | 2.34 s / 0.194 s / 0 | 0 | 736 | 6 | 6 | 0 | 0 | no | 32 |
| P12 & P14 | 1 of 2; 1 of 9 | 29 | 13 / 12 | 0 | 0 | 0 |  | 0 | 782 | 0 | 1 | 0 | 0 | no | 20 |
| P13 & P14 | 1 of 6; 2 of 9 | 38 | 633 / 44 | 564 | 2 | 0 | 0.0 s / 0.0 s / 555 | 33 | 35608 | 35 | 39 | 2 (together (assumed radius) 2) | 0 | no | 332 |
Per case: keys on two or more phones (M-6b): 10-report case owner E.164 2 (strong), account usernames 21
and saved-login accounts 325 (medium), Bluetooth names 6, BSSIDs 2, SSIDs 1, cookie domains 367 (weak);
3-phone case no strong key, account usernames 2, saved-login accounts 462, Bluetooth names 3, BSSIDs 7,
SSIDs 4, cookie domains 130. Exact MD5 groups spanning phones among attachment-linked and camera files
(M-8b): 112 in the 10-report case, 46 in the 3-phone case. X8 equal `InstantMessage.Identifier`: per source
in `cross.json`.

M-12 (P03 and P10, the two C1 reports): hardware identifiers IMEI, IMSI and MSISDN are present in one report
and absent in the other; ICCID, Android ID, Bluetooth and WiFi MAC and factory number are absent in both
(M-12a: absent). Content markers equal across the two: 4 (Contact 3, InstantMessage 1) over 23 record types,
overall Jaccard 0.0002 (M-12b). Record ids equal: 0 of 9,910 and 15,206 (M-12c). M-12d (the two C8 exports) is not
measurable: the second C8 export exists only on the Mac.

## 10. Source records (`extraInfos`, 05 section 17.2)

| Report | extraInfo | id is a record or model | nodeInfo | resolves to a tagged file (by id / by path) | verified Database files referenced | records to a present, verified Database file |
|---|---|---|---|---|---|---|
| P01 | 31,919 | 12,572 | 46,686 | 0 / 0 | 0 | 0 |
| P02 | 149,569 | 76,720 | 182,585 | 100,526 / 0 | 44 | 8,028 |
| P03 | 234,208 | 25,372 | 241,286 | 233,993 / 0 | 34 | 6,733 |
| P04 | 0 | | | | | 0 |
| P05 | 0 | | | | | 0 |
| P06 | 0 | | | | | 0 |
| P07 | 102,205 | 49,710 | 134,441 | 82,615 / 0 | 44 | 3,785 |
| P08 | 625,546 | 483,158 | 1,098,836 | 952,331 / 0 | 55 | 37,052 |
| P09 | 0 | | | | | 0 |
| P10 | 0 | | | | | 0 |
| P11 | 399,722 | 165,004 | 421,032 | 401,462 / 0 | 26 | 77,446 |
| P12 | 36,008 | 16,030 | 44,608 | 17,381 / 0 | 15 | 1,306 |
| P13 | 581,520 | 327,826 | 664,928 | 417,773 / 0 | 42 | 42,604 |
| P14 | 553,909 | 394,448 | 643,954 | 11,910 / 0 | 0 | 0 |

The `extraInfo` elements whose id is no record or model describe file entries: their number equals
`NodeCount` on P02, P07, P08, P12 and P14, is 1 below it on P13 and 4 above it on P11, equals the tagged file
count on P03, and differs from both on P01. No `nodeInfo` `path` equals a tagged file's `path` on any report,
so resolution is by id only and the last column is a lower bound (on P01 and P14 no record reaches a
verified Database file by id).
