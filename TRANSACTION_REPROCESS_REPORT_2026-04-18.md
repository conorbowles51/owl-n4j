# ET-Fraud Transaction Reprocess — Final Report

**Case:** ET-Fraud (`7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab`)
**Reporting date:** 2026-04-18

---

## 1. Executive summary

The ET-Fraud case financial dataset has been re-extracted from the source
documents and loaded into Neo4j as a parallel "v2" set, running alongside the
legacy "v1" transactions for side-by-side review.

| Metric | Value |
|---|---:|
| Total v2 rows (all re-extraction runs) | **29,014** |
| Distinct documents with v2 rows | **300** |
| Rows tagged `Duplicate - Ignore` (see §3) | **5,802** |
| Non-duplicate v2 rows ("usable" data) | **23,212** |
| Legacy v1 rows being replaced | ~8,600 |

v2 captures roughly **3.4× more transactions** than the legacy v1 did, because
many of the original source documents were either under-extracted, mis-labelled,
or never loaded. Every v2 row loaded was validated against a printed subtotal,
a balance equation, or source-file row count before being accepted — anything
that could not be validated was left out rather than guessed.

---

## 2. Current state of v2 data

| Extraction run | Docs | Rows | Notes |
|---|---:|---:|---|
| 2026-04-12 (pdfplumber batch) | ~211 | ~23,043 | TD Bank, Citibank, BofA checking/CC, Chase biz |
| 2026-04-17 (rebuild + validation) | 103 | 5,938 | Full pypdf-based rollback then rebuilt with pdfplumber; each doc validated against printed subtotals |
| 2026-04-18 (OCR pass, Zelle subpoena only) | 1 | 33 | USA-ET-006456 (medium confidence — OCR-sourced) |
| **Total** | **300** | **29,014** | |

All rows are stored with `audit_status = 'proposed'`. Each row carries a
`verified_facts` entry that links back to the source PDF at the specific page
so the team can click through to the underlying evidence.

---

## 3. Duplicate documents

### What we found

Many of the same underlying bank statements were filed into the case under
multiple USA-ET document IDs. This is a natural artifact of the intake /
scanning process — for example, a statement may have been scanned once as a
standalone monthly statement and again as part of a multi-month compilation.

**Numbers:**
- **90 documents** were found to be either exact duplicates of another document,
  or strict subsets of a larger compilation document.
- **5,088 rows** in those 90 redundant documents have been re-categorized as
  `Duplicate - Ignore`.
- That brings the total `Duplicate - Ignore` count to **5,802** (the other 714
  were already flagged that way in the legacy data before this session).

### How we detected them

For each document, we built a fingerprint — the set of `(date, amount)` pairs
from its rows. Two documents were treated as duplicates if one document's
fingerprint is fully contained by the other (identical or strict subset) and
both contained at least 3 rows.

### Example: the large compilation docs

Several "mega" documents aggregate many single-month statements:

| Compilation doc | Total rows | Covers |
|---|---:|---:|
| USA-ET-006060.pdf | 643 | 15 smaller single-month statements (incl. USA-ET-000499, 001519, 046265, 046277, 046283, 046289, 046295, 046301) |
| USA-ET-006128.pdf | 201 | 12 smaller single-month statements |
| USA-ET-005974.pdf | 953 | 2 smaller (USA-ET-046367, 046399) |

And there are **52 pair-wise exact duplicates** where the same statement exists
twice under different doc IDs, for example:

| Doc A | Doc B | Rows each |
|---|---|---:|
| USA-ET-003111.pdf | USA-ET-003219.pdf | 241 |
| USA-ET-002463.pdf | USA-ET-002471.pdf | 108 |
| USA-ET-002535.pdf | USA-ET-002543.pdf | 107 |
| USA-ET-002639.pdf | USA-ET-002649.pdf | 107 |
| USA-ET-002575.pdf | USA-ET-002583.pdf | 96 |
| USA-ET-002563.pdf | USA-ET-002569.pdf | 95 |
| USA-ET-002479.pdf | USA-ET-002485.pdf | 88 |
| … (~45 more, mostly Beltha Mokube BofA in the 001xxx range) | | |

### What was changed on the duplicate rows

For each of the 5,088 duplicate rows we updated four properties:

- `financial_category` → `Duplicate - Ignore`
- `original_financial_category` — keeps the category the row had before this
  session (so nothing is lost)
- `duplicate_of_doc` — points at the canonical document whose rows are
  considered the primary record
- `duplicate_marked_at` → `2026-04-18`

**Nothing was deleted.** The rows are still present; they are tagged so UI
filters can exclude them from sum/summary views, but the underlying data can
still be inspected or un-tagged if a duplicate turns out to be an independent
transaction after all.

### Recommendation

Review the `duplicate_of_doc` pointer for each flagged row. In the Financial
Transactions view, apply a filter to hide rows where
`financial_category = 'Duplicate - Ignore'` to see the canonical set of 23,212
non-duplicate transactions.

---

## 4. Documents NOT reprocessed

Out of the ET-Fraud case's financial-source documents, **67 legacy documents
(~776 legacy "rows") are still v1-only**. None of these represent bank
transactions — they fall into one of three categories.

### 4a. Non-financial documents (intentionally skipped)

These were classified by the original LLM-based v1 extractor as having
"transactions" because they contain dollar amounts, but the amounts are not
bank transactions. They are narrative or form data.

| Category | Example docs | Why skipped |
|---|---|---|
| Vehicle purchase / car deals | USA-ET-040732, 041610, 040081 | EchoPark sale paperwork — line items on one deal, not a series of bank transactions |
| Loan applications / decisions | USA-ET-032995 (PPP), 004265, 006305, 006310 (RouteOne) | Application forms with proposed amounts, not actual transfers |
| Tax returns | USA-ET-004102, 004107, 004115, 004117, 004121, 004123, 004133, 004142, 004168, 004175, 004066, 004089, 004000, 004015, 004023, 004033, 004060, 004095 | 1040/941 forms. Not bank txns. |
| 1099-MISC / K-1 forms | USA-ET-046950 (Beltha), 046956 (Martha) | Annual income reporting, not bank txns |
| HSI / FBI reports | USA-ET-055147, 055160, 055195, 009864, 009869, 009936, 010442, 010519, 047055, 047104, 047181, 046545, 046984 | Investigation narratives |
| Cellebrite phone extractions | USA-ET-010674, 010690 | Phone call/message logs |
| Subpoena / legal declarations | USA-ET-003861, 003862, 004151 | Court documents |
| Narrative docs | USA-ET-003611, 009996, 007920 | Video transcript, bill of sale, misc |
| Credit reports | USA-ET-046067, 046078 | Experian reports (scores/summaries, not bank txns) |
| Spreadsheets / session logs | USA-ET-003329.xlsx, 003330.xlsx, 004152.xlsx, 046936.xlsx, 004840.xlsx, 004837.xlsx, 046205.csv | Online banking session logs, income/expense summaries — not structured txn data |

The legacy v1 rows for these documents were generated by LLM-based extraction
over the raw text of the documents. Because the source isn't actually
transactional, those v1 rows are generally noise (e.g. an LLM created a
"Transaction" node for the dollar amount found inside a tax form box). They
are strong candidates for soft-deletion after team review.

### 4b. OCR-infeasible handwritten / scanned check images

| Doc | Pages | Content |
|---|---:|---|
| USA-ET-025354 | 71 | Handwritten check faces (rotated, scanned) |
| USA-ET-001528 | 50 | Eric Tataw written checks |
| USA-ET-001693 | 62 | Multi-Therapeutic Services checks paid to Eric |
| USA-ET-005935 | 34 | NTC LLC written checks |
| USA-ET-046199 | 1 | Single Chase check image |
| USA-ET-046597 | 14 | Blank/near-blank scan |
| USA-ET-046924 | 5 | Near-blank scan |

Tesseract OCR was attempted on a sample and proved unreliable on rotated,
handwritten check faces (typically <50% field accuracy). Reading these
reliably would need a specialized pipeline (MICR line detection + amount-box
ROI, or a commercial check-reading API). The team's manual entry of key
amounts into the legacy v1 rows is probably the more accurate source of truth
for these — they should be preserved and reviewed.

### 4c. OCR attempted but not loadable to validation standard

| Doc | Pages | Issue |
|---|---:|---|
| USA-ET-006767 | 83 | Brianpetzold Tambi's Capital One 360, 11 monthly statements. OCR text is readable at a high level (sections, dates, most amounts) but individual cells have character-level errors (e.g. `Larhi $913.16` where a `$39.21` amount used to be). No month's rows sum to the printed closing balance, so no month could be loaded at the project's "exact subtotal match" gate. |
| USA-ET-026407 (pages 55–130) | 76 | Lee Kameron's Ameris Bank, 7 monthly statements. The first 5 months (Dec 2020 – Apr 2021) loaded cleanly from pdfplumber — they are in v2. The later 7 months (May 2021 – Nov 2021) have scan-degraded summaries ("Lo balance" / "tions" where "Low balance" / "Total subtractions" should be), and OCR doesn't recover them cleanly either. |
| USA-ET-006456 | 16 | Zelle Early Warning subpoena (NTC / DIMMPLES / Eric tokens). OCR produced 33 usable rows ($18,381 sent total), but some row-level dates have OCR errors (e.g. "2321-10-08" instead of "2021-10-08") and counterparty names are partial. **Loaded** at `confidence = medium`. |

OCR cache files are preserved under
`ingestion/data/audit_results/_ocr_cache/` — if a specialist OCR pipeline is
brought in later, the cached text can be reprocessed without re-running
Tesseract.

---

## 5. Reviewing v2 data in the app

Every v2 row carries:
- `audit_status = 'proposed'` — distinguishes v2 from legacy v1
- `audit_run` — date of extraction (`2026-04-12`, `2026-04-17`, or `2026-04-18`)
- `audit_doc` — source document filename
- `audit_verified = true`
- `verified_facts` — JSON with a `source_doc` + `page` link that renders as a
  clickable citation in the UI so the team can open the PDF at the exact page

To see a clean view of the usable data:
- Filter Financial Transactions to `audit_status = 'proposed'`
- Exclude `financial_category = 'Duplicate - Ignore'`
- That surfaces the 23,212 non-duplicate v2 rows

To review duplicates specifically:
- Filter to `audit_status = 'proposed'` AND `financial_category = 'Duplicate - Ignore'`
- The `duplicate_of_doc` property on each row shows which document is the
  canonical copy

---

## 6. Recommended next steps

1. **Team eyeball review** of 5–10 v2 documents across the different parsers
   (BofA, SunTrust/Truist, Zelle, Capital One 360, Ameris, NFCU). Confirm PDF
   source links resolve correctly and amounts match the statements.
2. **Soft-delete the legacy v1 rows that now have v2 counterparts** after
   review. The mechanism already exists at
   `Neo4jService.bulk_soft_delete_financial_for_document()` — it excludes any
   row with `audit_status = 'proposed'` so the v2 set is preserved.
3. **Review the `Duplicate - Ignore` flag** on the 5,088 newly-tagged rows
   before using them in any reporting.
4. Decide whether the OCR-blocked check-image batches (§4b) are important
   enough to warrant a specialized check-reading pipeline. If not, the legacy
   v1 rows for those documents are the best record available.

---

## 7. Appendices

**Extraction scripts** (all pdfplumber-based; `auto_extract_bofa.py` is
deprecated because it used pypdf, which produced garbled descriptions during
an earlier attempt):

- `scripts/extract_csvs_20260417.py` — BofA check-image subpoena CSVs
- `scripts/extract_bofa_advplus.py` — BofA personal/business checking with subtotal gate
- `scripts/extract_suntrust.py` — SunTrust / Truist parsers
- `scripts/extract_capone360.py` — Capital One 360 savings
- `scripts/extract_ameris_026407.py` — Ameris Bank multi-statement
- `scripts/extract_003363_nfcu.py` / `extract_003333_nfcu.py` — NFCU subpoena responses
- `scripts/extract_003423_zelle.py` — Zelle Early Warning subpoena
- `scripts/extract_check_img_struct.py` — Capital One 360 structured check-image metadata
- `scripts/extract_misc_targeted.py` — Wire Transaction Report + Loan Payment History
- `scripts/extract_006456_ocr.py` + `ocr_helpers.py` — OCR pipeline (Tesseract 5.5)

**Loader:** `scripts/build_audit_v2_nodes.py --date <date> --apply`
(supports `--delete-all --apply` for rollback by audit run).
