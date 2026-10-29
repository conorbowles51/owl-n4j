# Measurements

Structure-only measurements behind the Cellebrite plan and specifications, taken read-only on
2026-10-29. Nothing here is case content: no names, numbers, message text, addresses, file names or
evidence numbers. Counts, Cellebrite's own field and type names, and Cellebrite's own named-value
vocabularies only (the `Guid` and `UInt32` value lists were removed because they held record ids).

## Phone labels

Two labelling schemes are used across the specifications. They refer to the same 14 reports v1 ingested
on the server (`/mnt/owl-data/ingestion-data/`), in the same order.

| Spec 04 | Spec 05 | Case | Report | All models (incl. nested) | Local copy |
|---|---|---|---|---|---|
| P01 | 1P | 1-phone case | single report | 32,332 | |
| P02 | A-C8 | 10-report case | C8 | 73,608 | local C8 is a different export (report version 8.5, split sections, file index cut off) |
| P03 | A-C1a | 10-report case | C1, extraction 2023-01 | 44,949 | |
| P04 | A-C2 | 10-report case | C2 | 251,466 | |
| P05 | A-C5 | 10-report case | C5 | 70,487 | |
| P06 | A-C3 | 10-report case | C3 | 71,045 | local C3 |
| P07 | A-C7 | 10-report case | C7 | 55,361 | |
| P08 | A-C6 | 10-report case | C6 | 694,406 | |
| P09 | A-C9 | 10-report case | C9 | 14,005 | local C9 |
| P10 | A-C1b | 10-report case | C1, extraction 2022-11 | 140,608 | |
| P11 | A-C4 | 10-report case | C4 | 290,509 | |
| P12 | B-C3 | 3-phone case | C3 | 17,496 | |
| P13 | B-C2 | 3-phone case | C2 | 523,024 | |
| P14 | B-C1 | 3-phone case | C1 | 967,543 | |

Whether A-C1a and A-C1b are the same device is not established (06 section 5 measures it). v1's own
reconciliation counts top-level models only, so its largest figure (338,715 for P14) is smaller than the
all-models figure above.

## Files

| File | What it holds | Produced by |
|---|---|---|
| `catalogue-14-phones.json` | Per phone: `model_types` {type: count, nested included}; `catalog` [[type, field, field kind, {value data type: count}]]; `enums` {named set: values, at most 50 kept per set} | `scripts/catalog_remote.py`, run on the server at lowest priority |
| `catalogue-local-samples.json` | The same for local C3, C9 and C8 (C8 from the `.xmlModel` section) | `scripts/catalog.py` |
| `v1-ingest-reconciliation.json` | v1's per-phone `owl_ingest_report.json`: ingest duration in minutes and v1's per-type reconciliation (XML count, persisted count, status). Report key, case id and report name removed | copied from the server |
| `scripts/` | Every measurement script used by the research and the specifications. Paths and identifiers are replaced by placeholders such as `<C3_REPORT_PATH>`, `<CASE_A_ID>`, `<REPO>`, `<SCRATCH>`; the real paths come from the reference corpus manifest built in unit 01-0.1, which stays on the development machine and is never committed | research session and spec writers |
| `scripts/s05/` | Spec 05's measurements (M1 to M16, X1 to X11): counts and salted hashes only | spec 05 |
| `scripts/spec02/` | Spec 02's registry, coordinate, fold and nesting checks; `nest_c*.txt` are nesting counts per sample | spec 02 |

## Headline figures

| Measure | Value | Where used |
|---|---|---|
| Distinct record types across the 14 phones | 62 | plan 3.2, 02 section 3 |
| Distinct (type, field, field kind) | 470 (471 field rows) | plan 3.2, 02 |
| Named value sets | 55 with 210 values, plus `DecodingSourceOptions` (the plan's earlier "57" counted `Guid` and `UInt32`) | 02 |
| Types present in every report / in one only | 6 / 5 | plan 3.2 |
| New types contributed by each report in turn | 16, 25, 7, 1, 1, 0, 0, 0, 0, 0, 5, 1, 4, 2, 0, 0, 0 (17 files: 14 server plus 3 local) | plan 3.2 |
| Values without a data-type label | 0 | plan 3.3 |
| Field whose data type differs between reports | 1 (`ChatActivity.SystemMessageId`: String and Guid) | 02 |
| Field kinds v1 never read, C3 / C9 / C8 (`multiField`, `nodeField`, `dataField`) | 7,004 / 1,190 / 18,796 | plan 3.1 |
| v1 ingest duration, longest | 292 minutes (P13); 200 minutes for P05 | plan 4.9 |

## Rerunning

Run read-only. On the server: `nice -n 19 ionice -c3`, one report at a time; the VM ran out of memory
on 2026-10-24 under other load. Python with `-I`, scripts outside the evidence folders, outputs to a
private scratch directory, and only aggregate counts brought back.
