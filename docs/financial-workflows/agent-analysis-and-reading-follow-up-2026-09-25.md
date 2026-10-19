# Imported-ledger analysis and statement review follow-up

## Investigator objective

From a case's Agent screen, ask for an analysis of all imported payments and get
an evidence-backed account of the available records: complete matching totals,
separate currencies and bank/card accounts, dated activity, counterparties,
sources and explicit gaps. Supporting rows and exported artifact tables must not
be represented as the complete ledger when they are only one page or selection.

The parallel statement-review work keeps the path from an original document to
a saved correction and an admissible import understandable. Existing evidence,
manual additions and previous readings remain retained. This release does not
automatically reprocess, append, replace or remove client records.

## Implemented locally

- Agent financial tools read the same relational ledger as Financial, rather
  than relying on a separate graph projection. They return exact minor-unit
  totals for the complete bounded matching population, with currency scale and
  account type. Account/month/counterparty/category groups are paged explicitly.
- Coverage distinguishes saved periods, known accounts, admitted payments,
  excluded readings and incomplete records. Unknown activity is not zero
  activity. Working and verified populations remain distinct.
- Each PostgreSQL tool call uses a dedicated read-only repeatable-read
  transaction. Query revisions prevent mixed-version pagination; a separate
  ledger revision pins related analyses. A new call can see committed edits.
  Overflow or unavailable scope produces an explicit unavailable result, never
  partial totals or a graph substitute.
- Both agent execution paths preserve complete bounded tool pages for the
  model. Activity labels and table/chart notes explain financial scope. Reports
  use available scope rather than repeatedly asking an investigator to define
  an already requested full-case analysis. Source references and returned links
  are retained. Evidence text remains data, never instructions.
- The existing free-form graph-query guard now verifies every matched node and
  relationship's case scope independently. A documented restricted query grammar rejects unsupported complex
  forms before driver access. Significant-layer runs cannot use case-wide
  financial tools or free-form queries to bypass their selection.
- Flagged source rows display the original extraction reason, current exact
  blockers and their editable targets. A checked or corrected source warning
  is distinguished from a remaining arithmetic/required-field problem. The
  existing explicit check action is available beside the source, with current
  saved/unsaved status. Excluding a row does not verify it.
- Opening a batch has a bounded one-minute read timeout, no hidden repeated
  retries, and a way back while loading. Leaving cancels only the read request;
  it does not stop extraction or import jobs.
- Batch progress separates PDF files from prepared statement reviews. Each
  review occupies one status, while the reasons below can overlap. The primary
  save/import action appears above counts and warnings, with the number of
  statements and payments affected. Verified no-payment statements explicitly
  save account details, dates and balances to Financial without adding payment
  rows. Zero parsed rows alone never establish an inactive statement.
- Saving without payments opens the affected accounts and their recorded period
  history, with a return to the same batch and review filter. The destination
  uses the persisted operation receipt, resolves consolidated accounts and keeps
  transaction filters intact. Receipts now include saved-period accounts even
  when no transaction rows exist; unrelated case accounts cannot enter this view.
- Santander continuation pages attach only to an immediately preceding open
  account section with matching printed customer/period and movement columns.
  Closing controls missed by ordinary OCR can be reread from measured source
  regions using four agreeing bounded observations. Uncertain values remain
  explicit review items. This is reusable reader capability, not a file-specific
  exception; see [processing capabilities](processing-capabilities.md).

## Verification and limits

- Registered-tool and runner journeys exercise both invocation and streaming,
  more than one page of payments, exact large amounts, multiple currencies and
  account types, corrections, stale pages, source ownership and unavailable
  results. The deterministic model fixture verifies tool wiring, not the
  quality of a live provider's final narrative.
- Isolated PostgreSQL tests prove a stable snapshot during a concurrent
  committed correction, freshness in the next call, SQL write rejection and
  restoration of ordinary pooled-connection settings after success or failure.
- Browser journeys at wide and narrow viewports exercise row reasons,
  correction/check/save/reopen, a remaining missing field, delayed batch loading,
  timeout recovery and return. These use synthetic HTTP responses and PDFs.
- Batch browser journeys also exercise the visible ready action, exclusive
  status counts, save receipts, scoped account history and return. A separate
  real-service synthetic test saves an explicitly confirmed no-activity period
  through strict admission and the batch worker, then resolves the persisted
  operation receipt into account history without creating payments. Additional
  checks cover canonical accounts, foreign periods and removed source context.
  The final connected batch/import/receipt suite passed 93 tests. The frontend
  production build passed; the batch browser suite passed 11 journeys.
- Existing and new recovery tests retain manual additions and old corrections
  when a new reading expands continuation coverage or shifts physical row
  indices. New import remains held for explicit comparison; old row IDs are
  never blindly applied to a changed reading.
- A supplied private source was replayed through the production reader and
  inspected against its pages. The missing continuation cause and recovered
  closing-control provenance were verified. Some damaged cells still require
  investigator review. Source files, rendered pages, extracted values and the
  private audit stay outside Git.
- All additional locally supplied Santander samples were also checked privately.
  Their movement and closing controls were readable, but they represent the same
  supported Mexican statement family, not every Santander product. Existing
  stored readings are not automatically replaced. Checking for additional
  periods only reuses stored geometry; recovering omitted pixels requires an
  explicit retained new reading and comparison with saved work.
- The live Transactions screen was inspected read-only: registered EUR
  accounts were visible separately from payment activity. This does not prove
  that every supplied EUR statement has been fully processed.
- Alex's report that recent additions appeared after a page refresh is retained
  as an unconfirmed refresh-delay report, not data loss. Real query-observer
  tests confirm automatic list refresh for admitted and pending additions and
  retain lost-response retry coverage. No speculative cache change was made.
- Two older statement-review fixtures fail because their synthetic rows omit
  required IDs. The same failures were reproduced using their unchanged HEAD
  version, independently of the Santander reader. They are not counted as
  passing checks for this change.

Publication and live acceptance are pending until the verified code-only push
and its automatic deployment are inspected. A live agent response must then be
compared with Financial's counts, currencies and source navigation. No claim of
complete extraction, automatic repair of earlier imports or resolution of every
historical source is made by the local tests.
