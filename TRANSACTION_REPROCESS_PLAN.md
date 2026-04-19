# Transaction Reprocess Plan — ET-Fraud case, all financial-source documents

**Status:** Active as of 2026-04-12. Phase 0 (code changes) complete. Phase 1.3
(extraction) in progress — 12/198 docs done (8 pre-existing + 4 new this
session, 1,032 rows in Neo4j, verify pass confirmed clean). 186 docs
remaining, queued by bank family in `_queue.json`. Full scope: 198 confirmed
bank-statement PDFs in the ET-Fraud case.

---

## 1. Background

### 1.1 What last night's work produced

- Re-read 8 bank statements from the ET-Fraud case via the audit v2 extraction
  pipeline and wrote cleaned JSON under
  `ingestion/data/audit_results/2026-04-11/*.json` (plus `_audit_summary.json`
  and `_audit_summary.md`).
- `scripts/build_audit_v2_nodes.py` loaded those JSONs into Neo4j as new
  Transaction nodes flagged `audit_status='proposed'`. 742 rows.
- The 1,165 legacy transaction rows for those same 8 documents are **still
  present** — both old and new are visible in the Financial Transactions view,
  interleaved, so the team can diff them in-app.
- `scripts/audit_compare.py` can produce re-extracted-JSON vs. stored-Neo4j
  diffs per document or across a batch.
- Cleanup mechanism (uncommitted, in `backend/services/neo4j_service.py`):
  `Neo4jService.bulk_soft_delete_financial_for_document()`. Walks
  `(n)-[:MENTIONED_IN]->(:Document {name, case_id})`, soft-deletes every node
  with a non-null `amount`, excludes Documents/Cases/FinancialCategories and
  (by default) excludes `audit_status='proposed'` so the 742 survive. Defaults
  to `dry_run=True`.

### 1.2 Characteristics of the new (audit v2) rows

- Name format: `{Channel} {from|to} {Entity} (${amount})`, e.g.
  `Zelle from Alemanji, Ajua ($1,050.00)`.
- Both sides of `from → to` always filled. One side is always an account
  holder: NATIONAL TELEGRAPH LLC, ERIC TANO TATAW, Beltha Bume Mokube, or
  FILM TRIP AUTO GROUP LLC.
- Category ∈ {Transfer, Personal, Subscription, Payroll/Salary, Other}.
- Summary includes `Source: {doc}.pdf, page N.` with a clickable PDF link.

### 1.3 Team feedback (2026-04-12) — three amendments

1. **Swap Payments/Receipts labels.** Negative amounts = Payments, positive =
   Receipts. (Currently it's the other way round.)
2. **Sign-normalize on reprocess.** Outgoings must be ingested as negative,
   incoming as positive, across all bank statement types — even ones where
   the source PDF shows money-out as a positive number in an "outgoings"
   section. Sign should encode direction.
3. **Preserve manual categories.** Don't recategorize on reprocess — copy the
   category from the existing row being replaced. (Team has manually curated
   categories elsewhere in the app and is happy with them.)

Note on amendment #3: the testing report identifies the *legacy* ET-Fraud
categories as mostly junk (`"Zelle Transactions Need More Info"`, `"Check
Card"`, `"Ignore"`, blanks). A blanket copy would poison the clean new
categories with legacy junk. Rule: copy legacy only if it is **not** in the
junk allowlist (see §3.0.3).

### 1.4 Scope definition — refined 2026-04-12

**Phase 1 scope = 198 confirmed bank/credit-card statement PDFs.**

The raw inventory (all docs with attached Transaction nodes) returned 596
documents. Of those, 198 were classified as `bank_statement` via an
LLM-summary-based keyword classifier. The remainder includes:

- **24 ambiguous** PDFs (vehicle sale contracts, tax forms, check images,
  loan payment histories, etc.) — excluded from Phase 1.
- **9 not_statement** PDFs (Zelle subpoena reports, real estate closing,
  HSI investigation narratives) — excluded.
- **365 low-count docs** (<10 legacy txns — narrative evidence with
  incidental monetary mentions, not structured financial records).
- **17 CSV/xlsx files** — crypto uploads not yet ingested, plus bank
  export spreadsheets. Different ingest path; not covered by the PDF
  extraction approach. Excluded from Phase 1, deferred (see §5 Q6).

Classification data saved at
`ingestion/data/audit_results/_inventory_2026-04-12_classified.json`.
Processing queue (sorted by bank family then ascending size) at
`ingestion/data/audit_results/2026-04-12/_queue.json`.

**Bank family breakdown of the 198 in-scope docs:**

| Family | Docs | Note |
|---|---:|---|
| bofa_personal | 6 | Beltha Mokube + Eric Tataw personal checking |
| bofa_business | 8 | NATIONAL TELEGRAPH LLC business checking |
| bofa_cc | 7 | BofA credit cards (Beltha, Eric) |
| bofa_other | 128 | BofA docs where sub-type not yet classified |
| suntrust | 10 | Eric Tataw SunTrust/Truist checking |
| capital_one_360 | 10 | Eric Tataw Capital One 360 savings |
| capital_one_cc | 1 | Capital One credit card |
| citi_checking | 3 | Martha Atemlefac Citibank |
| citi_cc | 1 | Citi Cards credit card |
| chase | 3 | JPMorgan Chase |
| wells_fargo | 4 | Wells Fargo credit cards |
| td_bank | 1 | TD Bank (Superstore International) |
| ameris | 1 | Ameris Bank |
| other | 15 | Misc or unclassified bank statements |

Everything outside the 198 — ID documents, narrative evidence,
spreadsheet imports, ambiguous PDFs — is **out of Phase 1 scope** and
will not be touched. To be revisited after Phase 1 completes (see §5 Q6).

---

## 2. Current state of the code (as of 2026-04-12)

Relevant locations found during code reconnaissance:

- **Storage shape**
  - `scripts/build_audit_v2_nodes.py:135-137, :696` — `fmt_amount` drops the
    sign; amounts are written as `"$1,500.00"` strings, always positive.
  - `backend/services/neo4j_service.py:3915, :3920` — legacy parser uses
    `safe_float(record["amount"])` and already tolerates a leading `-` via
    `toFloat(replace(...))`.
  - Direction is currently encoded via `from_entity`/`to_entity` pair, not
    the sign of `amount`.

- **Summary tallies (the swap)**
  - `backend/services/neo4j_service.py:4176-4177` — `total_outflows` is
    computed as `sum(abs) where amt >= 0` and labelled **Payments**;
    `total_inflows` is `sum(abs) where amt < 0` labelled **Receipts**. This
    mapping needs to flip.
  - `frontend/src/components/financial/FinancialSummaryCards.jsx:13-56` —
    labels "Payments" and "Receipts" tied to the same backwards mapping in
    its header comment and derived totals.
  - `frontend/src/components/financial/FinancialView.jsx:333-362` — consumes
    the tally fields for the header cards.

- **Money Flow visualization (the safety check)**
  - `frontend/src/components/financial/FinancialView.jsx:242, 286, 401, 450,
    482, 516` — every aggregation already uses `Math.abs(parseFloat(t.amount))`.
  - `frontend/src/components/financial/MoneyFlowSection.jsx` — uses the
    abs-normalized totals from `FinancialView`.
  - `backend/services/neo4j_service.py:4229` — entity-mode money flow query
    already uses `abs(amt)` and derives direction from entity keys, not sign.
  - **Conclusion:** sign flips will not break Money Flow. Needs a regression
    eyeball, not a rewrite.

- **Category recategorization**
  - `scripts/build_audit_v2_nodes.py:70-94` — `channel_to_category` mapping.
    This is where amendment #3 plugs in: before falling back to this mapping,
    look up the legacy row's category and copy it unless it's in the junk
    allowlist.

- **Uncommitted WIP**
  - `backend/services/neo4j_service.py` —
    `bulk_soft_delete_financial_for_document()` (99 lines, dry_run default).
  - `scripts/audit_compare.py`, `scripts/build_audit_v2_nodes.py` (both
    untracked but already used to produce the 742 rows).

---

## 3. Combined workflow

### Phase 0 — Code changes (amendments #1, #2, #3)

**0.1 Sign normalization in the audit v2 builder**

- In `scripts/build_audit_v2_nodes.py`, stop calling `fmt_amount` in a way
  that drops the sign. Decide sign from the extraction JSON's direction
  field (outgoing → negative, incoming → positive), then format with the
  sign preserved. Audit v2 JSONs under
  `ingestion/data/audit_results/<date>/` are the source of truth for
  direction.
- Add a regression check inside the script: after building, assert that
  for every new row, `sign(amount) == -1 if to_entity == account_holder_entity
  else +1` (i.e. sign agrees with the from/to pair). Abort the load on
  mismatch.
- Nothing in the Cypher layer needs to change — the existing
  `toFloat(replace(..., "$", ""))` parses signed strings fine.

**0.2 Label swap in summary tallies**

Shipped unconditionally across every case — no per-case gate, no warning
banner. This is a product decision (§5 Q5): cases that haven't been
sign-normalized yet will show misleading tallies until their turn comes.
Accepted temporarily in exchange for a simpler rollout.

- `backend/services/neo4j_service.py:4176-4177` — flip the `CASE` so
  `total_outflows` aggregates `amt < 0` and `total_inflows` aggregates
  `amt >= 0`. Keep field names stable (they're just totals); labels change
  on the frontend.
- Or, cleaner: rename the server-side fields to `total_payments` /
  `total_receipts` and update the two frontend consumers. Preferred if it
  doesn't ripple into too many files — check `financial_export_service.py`
  and `routers/financial.py` first.
- `frontend/src/components/financial/FinancialSummaryCards.jsx` — update
  the file header comment and the derivation to match. "Payments = sum of
  absolute values of negative-amount transactions" and vice versa.
- `frontend/src/components/financial/FinancialView.jsx:333-362` — verify
  the consuming code still binds to the right totals after any field
  rename.
- **Known side-effect during rollout:** on every case that has not yet
  been sign-normalized (i.e. every case other than ET-Fraud, until their
  own reprocess happens), the Payments card will show $0 and the
  Receipts card will show the full transaction volume. This is wrong but
  obvious and self-healing as each case gets reprocessed. No banner, no
  conditional render — the whole point of choosing this option is that
  it requires zero extra code.

- **Amount cell rendering in the transactions table:** show the sign.
  Negative amounts render red with a leading minus (`-$1,050.00`),
  positive amounts render green (`$1,050.00`). The sign lives in the
  data already (§3.0.1); the table just stops stripping it. Find the
  amount formatter used by the transactions table row component (likely
  in a `FinancialTransactionsTable.jsx` / `FinancialRow.jsx` or directly
  in `FinancialView.jsx`) and add a `className` toggle based on
  `parseFloat(amount) < 0`. Use existing theme tokens for red/green if
  present; otherwise reuse whatever colour `FinancialSummaryCards`
  already uses for the Receipts card. Leave Money Flow and aggregate
  displays untouched — they keep rendering abs values.

**0.3 Category preservation in the audit v2 builder**

- In `scripts/build_audit_v2_nodes.py`, before calling the
  `channel_to_category` fallback, look up the legacy node being replaced
  (match on doc + date + abs(amount), via `fetch_legacy_category_index`
  which runs one Cypher query per doc and returns a `(date, round(mag,2))`
  keyed dict) and read its `financial_category`.
- Copy the legacy category **only if** it is one of the 5 valid values
  in the app's taxonomy. **Strict allowlist approach** (decided
  2026-04-12 after the dry-run surfaced junk like "Duplicate - Ignore"
  and channel-derived tags like "Cash App" / "Check Payment"):
  ```python
  CATEGORY_VALID = {
      "transfer": "Transfer",
      "personal": "Personal",
      "subscription": "Subscription",
      "payroll/salary": "Payroll/Salary",
      "other": "Other",
  }
  ```
  Anything not in this set (including None, empty, "Unknown", "Ignore",
  "Check Card", "Zelle Transactions Need More Info", "Duplicate - Ignore",
  "Cash App", "ATM Cash Deposit", etc.) falls through to
  `channel_to_category`. When copying, the canonical casing is applied
  via `_canonical_category()`.
- On ET-Fraud, the dry-run showed 40/742 categories preserved (Transfer=21,
  Other=15, Subscription=3, Personal=1) with 702 fallback — confirming
  that ET-Fraud's legacy categories were mostly system-generated, not
  manually curated.
- Log a per-document summary of copied vs. fallback categories so we can
  eyeball the split after each run.

**0.4 Verify Money Flow under abs() — deferred into Phase 1 verification**

- **Decision 2026-04-12:** skip the synthetic dev-fixture check. The existing
  code at `FinancialView.jsx:242, 286, 401, 450, 482, 516`,
  `MoneyFlowSection.jsx`, and `neo4j_service.py:4229` is already using
  `Math.abs` / `abs(amt)` at every aggregation point — grep-verified during
  the initial recon. The regression risk of signs leaking through is genuinely
  low.
- Replaced with an **in-situ eyeball during Phase 1.5** (`audit_compare.py`
  case-wide run): after the first rebuild produces real signed data, open
  the app and confirm Money Flow viz renders approximately the same shape
  as before the rebuild. Sum of flows per entity pair shouldn't change,
  only the per-row sign in the underlying data.

**0.5 Pre-flight extractor sanity check**

Before committing to a full-case extraction run, spot-check the extractor
on 2–3 statement formats from the remaining (not-yet-audited) set that are
*structurally different* from the 8 already-audited ones. The 8 we have
were already homogeneous-ish (National Telegraph + SunTrust). If the
remaining set includes Chase, BofA, credit-union, or card-only statements
with different layouts, we want to catch extractor coverage gaps *before*
an overnight run, not after.

### Phase 1 — Reprocess every financial-source document in ET-Fraud

Single merged sweep. No more 8-then-45 split.

**1.1 Build the authoritative scope list.** Run the Cypher from §1.4 against
the live ET-Fraud database. Save the result as
`ingestion/data/audit_results/<run-date>/_inventory.json` with at minimum:
`doc_name`, `legacy_txn_count`, `already_audited` bool. This is the
manifest Phase 1 and Phase 3 iterate.

**1.2 Rebuild existing proposed rows under Phase 0 rules.** The original
742 proposed rows (from the 8 2026-04-11 audited docs) were built under
the old code (positive-only amounts, channel-based categories). Rather
than recycling and re-creating them, `build_audit_v2_nodes.py --apply`
uses MERGE-by-key so it **updates them in place** with new properties
(signed amounts, strict-allowlist categories). No recycle needed — the
key format `audit-v2-{doc-slug}-{row_index:04d}` is deterministic.

- **Done 2026-04-12.** Ran `python scripts/build_audit_v2_nodes.py --date
  2026-04-11 --apply`. 742 rows updated. Dry-run verified first.

**1.3 Extract all in-scope documents to JSON.** This is the long pole of
the plan. Write JSONs to `ingestion/data/audit_results/2026-04-12/*.json`.

**Extraction approach — Claude reads each PDF directly, not a script:**

The "extractor" is not a rigid Python pipeline — it is the Claude Code
session itself. For each document, Claude:

1. Reads the full PDF via `pypdf` (all pages, raw text extraction).
2. Identifies the bank, account holder, account number, statement period,
   and header totals (beginning balance, deposits, withdrawals, checks,
   service fees, ending balance) from page 1.
3. Walks through each transaction section (Deposits, Withdrawals, Checks,
   Service Fees) page by page, extracting every row individually with
   full judgment on:
   - `date` (YYYY-MM-DD, from the statement's date column)
   - `amount` (positive float, magnitude only — sign is in `direction`)
   - `direction` ("in" for deposits/credits, "out" for withdrawals/debits)
   - `from_party` / `to_party` (account holder on one side, counterparty
     on the other — inferred from section + description text)
   - `channel` (Zelle, Check Card, ACH, ATM Withdrawal, Cash App, etc.)
   - `reference` (Conf#, check#, transaction ID, etc.)
   - `location` (merchant city/state when present)
   - `confidence` ("high" / "medium" / "low")
   - `source_page` (physical PDF page number)
   - `source_section` (e.g. "Deposits and other credits")
   - `notes` (first-name-only counterparties, unusual entries, etc.)
4. Validates the extraction: sum of extracted deposits must match the
   header's deposits total, sum of extracted debits must match the header's
   debits total, and `beginning + deposits − debits − checks − fees =
   ending` must hold to the penny. If validation fails, the extraction is
   reviewed and corrected before saving.
5. Writes the JSON to disk in the same schema as the 8 reference files
   under `ingestion/data/audit_results/2026-04-11/`.

**Why not a scripted extractor:** The original automated extraction
dropped 80–90% of transactions on some documents and mis-labelled
direction on many of the rest. Bank statement formats vary significantly
across institutions (BoA vs SunTrust vs Capital One vs Citi vs Chase vs
Wells Fargo) and even across account types within the same bank (business
checking vs personal checking vs credit card). A rigid script can't
handle this diversity reliably. The Claude session applies per-row
judgment while maintaining per-doc totals reconciliation as a safety net.

**Accuracy-first commitment:** No shortcuts on metadata (every field
extracted for every row), no regex pre-parser (risk of silent row
drops), no schema loosening. The approach trades throughput for
correctness: ~4–8 docs per session, ~186 remaining docs, ~30–45
sessions total.

**Processing order:** Sorted by bank format family then by ascending
legacy count (smallest docs first within each family). Bank families
processed in sequence so the format pattern stays cached:
bofa_personal → bofa_business → bofa_cc → bofa_other → suntrust →
capital_one_360 → capital_one_cc → citi_checking → citi_cc → chase →
wells_fargo → td_bank → ameris → other. Queue saved at
`ingestion/data/audit_results/2026-04-12/_queue.json`.

**Progress tracking:** After each session, update
`ingestion/data/audit_results/2026-04-12/_progress.md` with which docs
were processed, transaction counts, and any issues found. A future
Claude Code session should read `_progress.md` and `_queue.json` to
know exactly where to resume.

**Current state (as of 2026-04-12):**

- 8 docs already had JSONs from the 2026-04-11 run (reloaded under
  Phase 0 code via `--date 2026-04-11 --apply` — 742 rows updated)
- 4 docs extracted this session:
  - USA-ET-000143.pdf (137 txns, BoA Business NTL, May 2021)
  - USA-ET-001035.pdf (4 txns, BoA Core Checking Beltha, Nov-Dec 2017)
  - USA-ET-001403.pdf (93 txns, BoA Adv Plus Beltha, Aug-Sep 2020)
  - USA-ET-004335.pdf (56 txns, SunTrust Eric, Mar-Apr 2021)
- All 4 loaded via `--date 2026-04-12 --apply` (290 rows created)
- **Verified in the app: signed amounts (red/green), summary cards,
  PDF page links, direction accuracy — all confirmed correct.**
- 186 docs remaining (see `_queue.json`)

**Key finding — legacy extractor dropped 80–90% of transactions:**
USA-ET-001403.pdf had 93 real transactions; legacy stored 10.
USA-ET-004335.pdf had 56 real; legacy stored 10. The reprocess will
significantly INCREASE the total transaction count in the case, not
just clean it up. Money flow totals will rise by roughly 5× on the
reprocessed slice.

**1.4 Load extracted JSONs incrementally via build_audit_v2_nodes.py.**
After each extraction session (or batch of sessions), run:

```bash
python scripts/build_audit_v2_nodes.py --date 2026-04-12          # dry-run
python scripts/build_audit_v2_nodes.py --date 2026-04-12 --apply  # real
```

This creates/updates `audit_status='proposed'` Transaction nodes for
every JSON in the `2026-04-12/` directory. MERGE-by-key is idempotent —
safe to re-run after adding more JSONs. Each run exercises Phase 0.1
(sign normalization), Phase 0.3 (category preservation), and the
sign/direction sanity assertion.

**1.5 Run `audit_compare.py` case-wide** and produce a case-level summary
(`_audit_summary.md`) covering every in-scope doc. For each, log:

- Legacy row count vs. new row count
- Rows where sign disagrees with the from/to pair (should be zero)
- Rows where category was copied vs. fallback, with copied-category
  distribution
- Per-doc delta counts (added / removed / modified)

**1.6 Review the category copy-vs-fallback split at scale.** If a new
junk label is dominating the "copied" side of the split for some docs
(e.g. a category string we haven't seen), grow
`CATEGORY_JUNK` and rebuild those docs. This is the place where the
allowlist question (§5 Q2) becomes actionable.

**1.7 Review the extraction failure log.** For every doc that failed
extraction, decide: (a) fix the extractor and retry, (b) accept and leave
its legacy rows in place (document this decision in the case's audit
summary), or (c) exclude the doc from cleanup in Phase 3 so its legacy
rows survive. Most likely (a) for anything that looks fixable, (c) for
anything structurally unusual.

### Phase 2 — Sampled spot-check

At full-case scale, row-by-row review isn't feasible. Two tiers:

**2.1 The five canonical ET-Fraud rows** (still from the original testing
note — these are the sharpest examples of each bug class):

1. **ALEMANJI** — 2020-06-04, $1,050.00. New row should read
   `ALEMANJI, AJUA → NATIONAL TELEGRAPH LLC`, sign **positive**
   (incoming / Receipt). Source: USA-ET-000388.pdf p.3.
2. **COMFORT SISI** — 2020-06-09, $1,000.00. `Comfort Sisi Healthcare, LLC
   → National Telegraph LLC`, positive. Same doc p.3.
3. **NTOH** — 2020-06-30, $500.00. `Ntoh, Florence → National Telegraph LLC`,
   positive. Same doc.
4. **A EKWEN** — post-2021-05-28 transactions must now be present, including
   a 2021-06-14 `Zelle to A Ekwen ($200.00)` from ERIC TANO TATAW.
   USA-ET-004342.pdf. Sign **negative** (outgoing / Payment).
5. **MOKUBE, BELTHA** — no self-referential rows. Either
   `Mokube, Beltha → National Telegraph LLC` (positive, on business
   statements) or `Beltha Bume Mokube → [merchant]` (negative, on her
   personal statement).

Three questions per row:

1. Does the direction match the bank statement?
2. Is the account holder named on one side of `from → to`?
3. Does the PDF page link land on the correct page?

**2.2 Stratified random sample of the new (previously unaudited) docs.**
Pull 3–5 rows per document from the docs that were *not* in last night's
8-doc batch. Prioritize rows whose counterparty name appears in multiple
transactions (high-impact to get right) and rows on docs from
statement-format families that are new to the extractor. Target ~50 rows
total for team review.

**Proceed to Phase 3 only if:** all five canonical rows pass cleanly, and
the stratified sample shows direction/from-to/pdf-link correctness on
≥95% of rows. Any systemic failure pattern (one doc, one format, one
counterparty) triggers a targeted rebuild of the affected slice, not a
global re-extraction.

### Phase 3 — Cleanup sweep (all in-scope documents)

**3.1 Full Neo4j point-in-time backup.** Non-negotiable. This is the
rollback line for the entire operation. Record the backup path and a
timestamp of the live DB state in the run log.

**3.2 Dry-run the soft-delete sweep.** Iterate the inventory from §1.1.
For each doc, call `bulk_soft_delete_financial_for_document` with
`dry_run=True`, `exclude_audit_proposed=True`. Aggregate:

- Total candidate count across the full case (expect ~7,000–8,000 legacy
  rows based on 1,165 / 8 ≈ 146 per doc × ~50 docs).
- Confirm zero candidates carry `audit_status='proposed'`.
- Per-doc candidate count matches the `legacy_txn_count` from the
  inventory. Any divergence ⇒ investigate before proceeding.

**3.3 Real run.** Iterate the inventory again with `dry_run=False`. Log
per-doc `deleted_count` / `failed_count`. On the first failure, **stop
the sweep**, investigate, and resume from the next doc — don't let a
silent failure pattern run through the whole case. Expected total soft-
delete load is large enough that transaction batching inside
`bulk_soft_delete_financial_for_document` may matter (see §5 Q4).

**3.4 Post-sweep verification.**

- Searches: ALEMANJI returns one row. A EKWEN returns the full extended
  set. Each of the account holders (NTL, Eric, Beltha, Film Trip) returns
  a clean count with no duplicates.
- Financial Summary Cards show plausible totals under the new
  Payments/Receipts labels. Sign convention: sum of all amounts ≈ net
  balance change across the case period, not zero, not doubled.
- Money Flow viz renders. Top counterparties look right.
- From/To entity panels show clean single-version rows.
- Spot-check the RecycleBin: the soft-deleted rows are visible and
  restorable.

---

## 4. Safety rails

### 4.1 Backups

- **Before Phase 1.2** (recycling the 742 already-proposed rows): snapshot.
  The 742 represent real verification work against PDFs; don't trust the
  rebuild to be identical.
- **Before Phase 3** (soft-delete sweep across the full case): full
  point-in-time Neo4j snapshot. This is the backup the testing note
  promised the team, now scaled to the full case.

Soft-delete is reversible via the RecycleBin, but a real snapshot lets us
roll back schema / relationship state that a per-node restore can't.

### 4.2 Scope guarantees

Only nodes attached to a document *that has at least one transaction* are
touched, and within those documents, only nodes with a non-null `amount`.
Untouched:

- People, organisations, banks, documents themselves
- Non-financial documents (no attached Transaction nodes)
- Manual notes or classifications on entities
- Any other case in the system
- `audit_status='proposed'` nodes (protected by default exclude flag)

### 4.3 Dry-run discipline

`bulk_soft_delete_financial_for_document` defaults to `dry_run=True`. Never
pass `dry_run=False` on the first invocation for a document. Always log
the candidate count from the dry run, compare against the §1.1 inventory
`legacy_txn_count`, and only then re-run with `dry_run=False`.

### 4.4 Stop-the-sweep rule

At case-wide scale, a bug that affects one document can silently affect
dozens. Any unexpected result — candidate count mismatch, sign-agreement
assertion failure, category-copy ratio anomaly, soft-delete failure —
pauses the sweep at the current doc. Resume only after root-causing.

---

## 5. Open questions

1. **Field rename vs. in-place flip for tallies.** **Resolved 2026-04-12
   — in-place flip.** Field names `total_outflows`/`total_inflows` kept
   stable. "Outflow = money leaving the account holder = Payment" is
   semantically accurate under both conventions; renaming would have
   rippled through 5 files for zero clarity gain.
2. **Category allowlist approach.** **Resolved 2026-04-12 — strict
   allowlist.** Replaced the original junk-blocklist with a valid-set
   allowlist: only the 5 app-recognised categories (Transfer, Personal,
   Subscription, Payroll/Salary, Other) are preserved from legacy.
   Everything else (channel tags like "Cash App", junk like "Duplicate -
   Ignore") falls through to `channel_to_category`. On ET-Fraud, 40/742
   preserved vs 702 fallback — confirming legacy categories were mostly
   system-generated, not manually curated.
3. **Sign source of truth in extraction JSONs.** **Resolved 2026-04-12.**
   Confirmed the extraction JSONs carry `direction: "in"/"out"` per row,
   derived from the bank statement's section headers (Deposits vs
   Withdrawals). The `signed_amount()` helper in `build_audit_v2_nodes.py`
   derives sign from this field. A per-row assertion aborts the load if
   sign and direction disagree.
4. **Soft-delete batching under load.** **Resolved 2026-04-12:** investigated
   `soft_delete_entity` — it opens its own session per call and runs 4
   auto-commit queries. At ~7k rows a full sweep is ~28k round-trips,
   estimated 5–15 minutes wall time. Correctness is fine (no transaction
   limit risk — each call is a tiny 4-query sequence). Throughput is
   suboptimal but acceptable for a one-off console-run sweep. No code
   change to `soft_delete_entity` or `bulk_soft_delete_financial_for_document`.
   Phase 3 needs an operational wrapper script with per-doc progress
   logging and a resumability log (`_phase3_done.log`), not library changes.
   **Operational constraint:** do NOT call the sweep from an HTTP request
   handler — it will outlast any reasonable client timeout. Run from a
   console, a shell script, or a background task.
5. **Label-swap blast radius across cases.** **Resolved 2026-04-12 —
   option (b):** ship the label swap immediately and accept that
   non-reprocessed cases look wrong until their turn. Rollout side-effect
   captured in §3.0.2. When other cases come up for reprocess later,
   their Payments/Receipts cards will self-heal the first time a
   negative-amount transaction lands against them — no follow-up code
   change needed.
6. **Non-bank-statement financial sources.** Phase 1 covers only PDF bank
   statements (198 docs). The remaining ~400 financial-source documents
   (Zelle reports, check images, vehicle sales, tax forms, narrative
   evidence, spreadsheet imports) need different extraction approaches
   per source type. See §7 for the deferred inventory. To be scoped as a
   separate sprint after Phase 1 completes and the bank-statement data is
   verified clean.

---

## 6. Order of operations — checklist

**Phase 0 — Code** ✅ COMPLETE
- [x] 0.1 — Sign normalization in `build_audit_v2_nodes.py`
- [x] 0.2 — Label swap in tallies + frontend (in-place flip, no rename)
- [x] 0.3 — Category preservation (strict 5-value allowlist)
- [x] 0.4 — Money Flow regression (deferred to in-situ check during Phase 1)
- [x] 0.5 — Extractor sanity check (folded into Phase 1.3 — extracting by
      bank family, diverse formats encountered organically)
- [x] §5 Q4 — Soft-delete batching investigation (resolved: no code change)

**Phase 1 — Case-wide reprocess** 🔄 IN PROGRESS
- [x] 1.1 — Build inventory + classify docs (198 bank statements confirmed)
- [x] 1.2 — Rebuild 742 existing proposed rows under Phase 0 code (MERGE
      in place, no recycle needed — ran `--date 2026-04-11 --apply`)
- [ ] **1.3 — Extract all 198 bank statements to JSON (12/198 done, 186
      remaining)**. Progress tracked in
      `ingestion/data/audit_results/2026-04-12/_progress.md`. Queue in
      `_queue.json`. ~30–45 sessions remaining at current pace.
      **To resume:** read `_progress.md` and `_queue.json`, pick next doc
      in queue, read PDF via pypdf, extract to JSON, write to
      `2026-04-12/` dir.
- [ ] 1.4 — `build_audit_v2_nodes.py --date 2026-04-12 --apply` (run
      incrementally after each extraction batch — already done for
      first 4 docs, 290 rows created and verified in-app)
- [ ] 1.5 — `audit_compare.py` case-wide + Money Flow regression eyeball
- [ ] 1.6 — Review category distribution at scale
- [ ] 1.7 — Triage any extraction failures

**Phase 2 — Sampled spot-check**
- [ ] 2.1 — Five canonical rows verified by the team
- [ ] 2.2 — Stratified sample (~50 rows) across previously unaudited docs
- [ ] Proceed gate: all five pass + ≥95% sample success rate

**Phase 3 — Cleanup sweep**
- [ ] 3.1 — Full Neo4j snapshot
- [ ] 3.2 — Dry-run soft-delete across the full inventory; reconcile counts
- [ ] 3.3 — Real run, per-doc, with stop-the-sweep on first anomaly
- [ ] 3.4 — Post-sweep verification (ALEMANJI / A EKWEN / totals /
      RecycleBin round-trip)

## 7. Non-bank-statement sources — deferred from Phase 1

The following sources have financial transactions in Neo4j but are NOT
covered by Phase 1's PDF bank-statement extraction approach:

| Source type | Doc count | Legacy txns | Notes |
|---|---:|---:|---|
| Zelle / Early Warning subpoena reports | 6 | ~1,100 | Structured but different format from statements |
| Check image bundles | 6 | ~200 | Each check = 1 txn; needs OCR-style approach |
| Vehicle sale / financing paperwork | 5 | ~250 | One real txn per doc; rest are line items |
| Tax forms / IRS notices | 4 | ~60 | Aggregate figures, not individual transactions |
| Real estate closing docs | 2 | ~260 | Wire transfers buried in closing disclosures |
| Loan payment histories | 2 | ~20 | Statement-shaped; could be handleable |
| Narrative evidence (interview, HSI) | ~350 | ~1,100 | Claims, not authoritative records |
| CSV/xlsx files | 17 | ~1,290 | Crypto not yet ingested; bank exports TBD |

To be revisited after Phase 1 completes. See §5 Q6.
