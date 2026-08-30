# Two defects the corpus survey found in the corpus itself

**Corpus:** ET-Fraud, 326 extraction files over 307 unique documents, batches
`2026-04-11` through `2026-04-18`, plus 36 files the harness declines to read.
**Status:** both defects specified; neither is yet fixed in the reader.
**Code:** `backend/services/financial/corpus.py`,
`backend/postgres/models/financial.py`.

Every figure below is reproducible from those files.

## What this is about

The two findings recorded here are not about the arithmetic of any statement.
They are about the corpus as an artefact: how a reading is known to be current
rather than superseded, and what happens when a date is wrong in a way no
constraint in the system is shaped to notice. Both were found while building
something else, which is the usual way, and both are cheap to fix now and
expensive to fix after an export has gone out.

## Finding 1: provenance lives in the filesystem path, not in the data

### What the harness sees, and what a naive reader sees

The corpus root holds 362 `.json` files. `iter_extraction_files` yields **326**
of them. The 36 it declines break down as:

| Skipped | Location |
|---:|---|
| 32 | `_archive_2026-04-17_pypdf_bad/` |
| 2 | `_inventory_2026-04-12.json`, `_inventory_2026-04-12_classified.json` at the corpus root |
| 1 | `2026-04-11/_audit_summary.json` |
| 1 | `2026-04-12/_queue.json` |

The shipped code is already correct here. `PRIVATE_PREFIX = "_"` is honoured at
both the batch level and the file level, and the docstring gives the reason:
the corpus uses the convention throughout, so honouring the convention is more
durable than a hand-maintained list of names, which stops excluding the moment
somebody adds a thirty-seventh file.

So this is not a bug report against `corpus.py`. It is a statement about what
that correctness rests on.

### There is no marker inside the files

Comparing the top-level keys of the 32 archived readings against the 328 files
in dated batch directories:

- top-level keys present only in archived files: **none**
- `validation` present in **40** of the live files, and in **0** archived ones

The second figure is the one that matters. `validation` looks like it could
serve as a marker of a current reading, and it cannot: seven-eighths of the
live corpus does not carry it either, so its absence means nothing. There is
no field, flag, or value anywhere in an archived reading that distinguishes it
from a current one.

An archived reading is therefore identified **only** by the directory it sits
in. Any consumer that reaches the corpus by a path other than
`iter_extraction_files` — an `rglob` in a notebook, a bulk loader, a colleague
writing a one-off script — silently ingests 32 superseded readings alongside
the 326 real ones and has no way to tell afterwards. This happened during this
investigation: the first survey script written for it used `rglob` and
overcounted before the discrepancy was noticed.

### The directory name is a claim the data contradicts

The archive is named `_archive_2026-04-17_pypdf_bad`, which asserts that its
contents are bad pypdf output. Reading the `extraction_method` field of all 32:

| Count | `extraction_method` |
|---:|---|
| 16 | Automated regex parser (10% tolerance) |
| 5 | Direct CSV parsing (format B) |
| 3 | Direct CSV parsing (format A) |
| 3 | Capital One 360 format line-based parser |
| 2 | Direct CSV parsing (format C) |
| 1 | Section-specific regex per page group |
| 1 | `pdfplumber extract_tables()` per page |
| 1 | Automated regex parser (30% tolerance) |

**Zero** of the 32 archived readings name pypdf as their extractor. Meanwhile
**7 of the 326 live readings do**, and are in active use. Whatever caused this
directory to be set aside, the name records a diagnosis that the files
themselves do not support.

### The archive is not uniformly worse than what replaced it

Comparing each archived reading's row count against the best live reading of
the same document — all 32 documents appear in both, and none is archive-only:

| Count | Archived reading vs best live reading |
|---:|---|
| 20 | same row count |
| 11 | archive has fewer rows |
| 1 | **archive has more rows** |

The exception is `USA-ET-003423.pdf`: **3,332** rows archived against **3,170**
live, from the *same* extraction method on both sides. 162 rows were discarded
by setting this file aside, and nothing in the corpus records that as a
decision.

This is the same shape as the finding already recorded in
`re-extraction-regression-2026-04.md`: the later reading is not automatically
the better one, and choosing by recency loses evidence. Here it recurs one
level up, at the directory rather than the file.

### What follows

The rule the ledger already applies to duplicate documents — nominate a
primary by evidence, exclude rather than delete, and record why — is the rule
this needs too. Concretely:

1. Supersession should be a **field in the reading**, not a property of its
   path, so that a reading carries its own status wherever it is read from.
2. Setting a reading aside should record **which reading supersedes it and on
   what basis**, so that a case like `USA-ET-003423` is visible as a
   contested choice rather than as an absence.
3. Until then, `iter_extraction_files` is the only safe door into this corpus,
   and that should be stated where people will read it rather than left to be
   rediscovered.

## Finding 2: one date is three centuries out, and the obvious check would not catch it

### The measurement

Across the 326 files the harness reads, testing every date against a window of
1990-01-01 to 2027-01-01:

| Dates parsed | Outside the window |
|---:|---:|
| 554 statement-period bounds | **1** |
| 30,570 transaction rows | **1** |

Both are the same document, `USA-ET-006456.pdf`, batch `2026-04-18`, an OCR
reading of a Zelle subpoena response with 33 rows.

### The root is a row, not the header

I first recorded this as a bad statement period. That was wrong, and the way it
came apart is worth keeping. The document did not appear in a separate check
for period ends far from the last transaction — which it should have, if the
header alone were wrong. It did not appear because the last transaction *is*
2321-10-08.

Row 3 of 33:

| Field | Value |
|---|---|
| `date` | `2321-10-08` |
| `amount` | 3000.0 |
| `direction` | out |
| `confidence` | **medium** |
| `source_page` | 4 |

Its raw description is visibly garbled OCR containing the fragment
`10/8/2321`, where neighbouring rows on the same page read `10/12/2021` and
`6/6/2020`. The rows either side are dated 2020-06-06 and 2021-10-12; the
second-latest date in the document is 2022-11-22. A misread `2021` as `2321`
in a single row is the whole of it.

Two secondary observations fall out. The rows are **not** stored in date
order — the latest date sits at index 3 of 33 — so any code that assumes
ordering is wrong on this corpus. And the header inherited the error: the
period reads `2020-05-18` to `2321-10-08`, which are exactly the minimum and
maximum of the document's own rows.

### Why the natural check is circular

Of the 276 documents with both parseable period bounds and dated rows,
**172 — 62% — have bounds exactly equal to the minimum and maximum of their
own transaction rows.** Those bounds were not read off the page. They were
computed from the rows.

This is what makes the defect invisible. The intuitive validation is to check
that transactions fall inside the statement period, and on 62% of this corpus
that check is comparing the rows against themselves. `USA-ET-006456` passes it
perfectly while being 300 years wrong.

The remaining 104 documents have bounds independent of their rows, and there
the check does carry information. It fires on **4** of them:

| Document | Printed period | Row span |
|---|---|---|
| USA-ET-004653.pdf | 2022-01-14 → 2023-07-13 | 2019-01-02 → 2022-12-07 |
| USA-ET-004862.pdf | 2021-11-24 → 2023-06-14 | 2021-11-24 → 2023-09-13 |
| USA-ET-006246.pdf | 2021-04-15 → 2021-10-14 | 2021-04-14 → 2021-10-14 |
| USA-ET-004366.pdf | 2021-12-17 → 2022-01-14 | 2021-01-03 → 2021-12-31 |

Four hits in 104 is a check worth having. But it is worth having *only* on
documents whose bounds are printed, and the system does not currently record
which those are — which is precisely what `PeriodBoundsSource` was added to
the schema to carry, and what the continuity check already refuses to run
without.

### Nothing in the pipeline is shaped to catch it

There is no date plausibility bound anywhere in `services/financial/`. The
only ordering constraint on a period is in the model:

```
period_start IS NULL OR period_end IS NULL OR period_start <= period_end
```

2020-05-18 ≤ 2321-10-08 is true, so the row is accepted. A separate check
comparing the period end against the last transaction is similarly silent,
because both are the same corrupt value.

The check that would have caught this is the crude one: an absolute window on
every date at the point of extraction, applied to **rows** and not only to
headers. One row in 30,570 fails it. That is a false-positive rate low enough
that the check can quarantine rather than warn.

### What the row says about itself

`medium`. Not `low`.

Of the 30,570 transaction rows in the corpus, **29,932** carry a self-declared
`confidence`, across 319 of the 326 documents:

| Value | Rows |
|---|---:|
| `high` | 28,110 |
| `medium` | 1,821 |
| `low` | 1 |
| *(field absent)* | 638 |

A row whose date is three hundred years out and whose description is
unreadable rated itself in the same band as 1,820 unremarkable rows, and the
single `low` in the entire corpus is some other row. Triaging by this field
would not have surfaced this document, and reviewing the 1,821 `medium` rows by
hand to find the one that matters is not a process anybody will run twice.

This is the second independent demonstration of the point already recorded in
`unexplained-identities-2026-04.md`, where five transactions lost at page
boundaries all sat inside rows marked `high`. There the model's confidence
missed an absence; here it missed a corruption present on the page. The field
records what the model felt and nothing consumes it, which is the right
treatment — and the reason the self-declaration short-circuit in
`extract_entities.py` has to come out.

## What these two findings have in common

Both are cases where a fact about the evidence lives somewhere that cannot be
checked. Supersession lives in a directory name, so it is lost the moment a
file is read by any other route. A statement period is derived from the rows
and then presented as though the institution printed it, so it cannot be used
to test the rows it came from.

The remedy in both cases is the same and it is already the house rule
elsewhere in this package: **record where a value came from, next to the
value.** `PeriodBoundsSource` does this for period bounds and is why the
distinction above is measurable at all. The corpus needs the equivalent for
supersession, and the reader needs to stop deriving a period from rows without
saying that is what it did.

## Reproducing these figures

The corpus is case material and is not in this repository. With it mounted at
`bundle/extraction-json`, every count above comes from walking that tree with
`iter_extraction_files` for the live set and `rglob` for the comparison, and
reading only `statement_period`, `transactions[].date`,
`transactions[].confidence`, `extraction_method` and `doc_name`. No account
numbers, account holders, or transaction descriptions appear in this document,
except the OCR fragment `10/8/2321`, which is the defect itself.
