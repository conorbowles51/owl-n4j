# Connected recovery, transfer and identity workflows

23 September 2026. Companion to the main action inventory and completion register.

## Retain work during interruptions

```mermaid
flowchart TD
  SELECT[Choose files, folder or archive] --> MANIFEST[Save complete selection and verify chunks]
  MANIFEST --> PAUSE[Pause upload: retain verified bytes]
  PAUSE --> RETURN[Return and reselect original files if needed]
  RETURN --> MISSING[Transfer only missing chunks]
  MANIFEST --> REGISTER[Register complete selection once]
  MISSING --> REGISTER
  REGISTER --> CHOICE{Investigator chooses processing}
  CHOICE --> AI[AI evidence ingestion]
  CHOICE --> PDF[Financial PDF reading]
  CHOICE --> PHONE[Phone report ingestion]
  AI --> CHECKPOINT[Pause after current unit; retain checkpoints]
  PDF --> CHECKPOINT
  PHONE --> CHECKPOINT
  CHECKPOINT --> RESUME[Resume saved job, without redoing completed writes]
  PDF --> REVIEW[Review statements; reading is not import]
  REVIEW --> BATCH[Prepare and import accepted statements]
  BATCH --> STOP[Pause preparation after current statement]
  STOP --> SAVED[Pending imports and review edits retained]
  SAVED --> BATCH
```

The batch page keeps preparation/import controls beside progress. Already-running
PDF readings have separate controls there because a reading may serve several
financial batches. Each control names its scope. Pausing a PDF reading group does
not pause unrelated AI jobs. A safe statement commit finishes before pause is
acknowledged. Closing the page does not discard server work.

## Correct a previously combined import

```mermaid
flowchart TD
  OPEN[Open saved statement beside original PDF] --> RECOVER[Separate printed account/currency sections]
  RECOVER --> ASSIGN[Assign every current payment and incomplete record once]
  ASSIGN --> DETAILS[Review account, currency, dates and balances for each section]
  DETAILS --> PREVIEW[Preview counts and exact monetary values]
  PREVIEW --> CHECK{Source and current edits unchanged?}
  CHECK -->|No| REFRESH[Retain draft; reload and compare]
  REFRESH --> ASSIGN
  CHECK -->|Yes| SAVE[Save replacements atomically]
  SAVE --> RECEIPT[Show saved sections and counts]
  RECEIPT --> TX[Open current payments]
  RECEIPT --> REOPEN[Reopen each section and original source]
  SAVE --> LINKS[Findings, Timeline and export citations resolve correction history]
```

The original reading remains evidence. Recovery is an explicit investigator
choice; no historical mixed import is silently rewritten. Decimal rescaling
preserves a printed amount when its currency label is corrected; it is not an
exchange-rate conversion. Retrying the same accepted request returns its receipt.

## Review transfers and common ownership

```mermaid
flowchart TD
  PAYMENT[Open payment or account] --> IDENT[Review typed identifiers and account relationships]
  IDENT --> SOURCE[Record source/page or investigator knowledge]
  SOURCE --> OWNER[Save holder, control, signatory or analysis-group relation]
  OWNER --> SHARED[Shared Financial filters and profiles]
  OWNER --> GRAPH[Retryable projection to case graph]
  IDENT --> ENTITY[Explicitly connect reviewed person/business to existing case entity]
  ENTITY --> GRAPH
  PAYMENT --> TRANSFER[Select sending and receiving postings]
  TRANSFER --> PARTS[Assign principal, fees and unassigned amounts]
  PARTS --> FX[Review currencies; explicit FX comparison if needed]
  FX --> PREVIEW[Preview references, ownership and available amounts]
  PREVIEW --> LINK[Save reviewed transfer]
  LINK --> ONWARD[Allocate each receipt to later payments]
  ONWARD --> FINDING[Save explanation with linked source payments]
  FINDING --> TIMELINE[Add reviewed work to Timeline]
  PAYMENT --> MISSING[Record referenced account when opposite statement is absent]
  MISSING --> LATER[Later statements produce possible identifier matches]
  LATER --> PREVIEW
```

Identifiers are typed: account number, CLABE and IBAN can support account matches;
customer, contract and holder tax identifiers are context and never automatically
merge bank accounts. Matching names do not establish ownership. Referenced
accounts create no statement, transaction or balance. Joint holders and effective
dates remain explicit. Only a current reviewed common holder establishes an
internal transfer for the selected account scope.

A saved split transfer consumes only its reviewed principal/fee portions. Fees
and unassigned amounts remain visible as external activity; same-currency
internal principal is counted once. Cross-currency amounts remain separate with
the reviewed comparison. An onward allocation is an investigator interpretation,
not proof that a particular receipt funded a later payment.

The case graph uses stable case-scoped account/party nodes. Its visible status is
pending, current or unavailable; retry uses saved decisions. Investigator graph
names, notes and unrelated edges are retained. Retraction removes managed
ownership/identity relationships only. Generic graph deletion/merging cannot
silently destroy reviewed financial identities.
