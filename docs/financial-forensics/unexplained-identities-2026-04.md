# The twelve documents whose balance identity does not close

**Corpus:** ET-Fraud, 326 extraction files over 307 unique documents, batches
`2026-04-11` through `2026-04-18`.
**Status:** all twelve explained; none of the explanations changes a proof class.
**Code:** `backend/services/financial/adjudication.py`,
`backend/tests/test_financial_adjudication.py`.

## What this is about

A bank statement prints its own control totals: opening balance, deposits,
withdrawals, checks, fees, closing balance. Those six figures are the most
valuable evidence a statement carries, because the institution computed them
and we did not. Checking extracted rows against them is the only mechanism in
this system that can detect a transaction that was never extracted at all — a
dropped row produces no low-confidence signal, so nothing else notices it.

Of the 326 extraction files, 197 carry enough of that block to test. 182 close
under the majority dialect, in which printed outflows are positive magnitudes
to be subtracted. Two close under the minority dialect, in which outflows are
already negative and are added; those two are arithmetically perfect and a
check hard-coded to the majority would have reported them as the worst
documents in the case. One cannot be assigned a dialect. That leaves **twelve
that close under neither**, and a document whose control block is internally
inconsistent cannot be used to validate anything until somebody says why.

This note says why, for each of the twelve.

## The rule the verdicts are held to

An explanation of a failing identity is the one thing in this pipeline that a
human supplies, and therefore the one thing that can be self-serving. The
danger is not a wrong explanation. It is an unfalsifiable one. "Extraction
error" explains every failing document equally well, costs nothing to write,
reads as diligence, and carries no information.

So each verdict here owes an arithmetic debt specific to the mechanism it
alleges, and the document either pays it or the verdict is refused:

- A **dropped sign on the opening balance** predicts a residual of *exactly
  twice* the printed opening — once for the balance sitting on the wrong side
  of the equation, once for it not sitting on the right one. Any other
  residual refutes the claim.
- **Rows lost in extraction** predicts a residual equal to the net of the
  amounts named. Naming approximately-right amounts fails.

Both obligations are enforced at construction in `adjudication.py`, so a
verdict that does not pay cannot be recorded and then caught in review.

## How the two mechanisms were told apart

Not by preference. By whether the printed flow totals are independent
evidence.

Each extraction carries a `totals_check` block holding both the header's
deposits and withdrawals figures and the sum of the extracted rows. Where
those differ, the header figures came off the page: they are the institution's
own, they are independent of our extraction, and a failing identity therefore
implicates one of the three **balances**. Where they agree to the cent, the
header was computed from the rows, carries no independent information, and
cannot corroborate anything — so the only thing left that can be wrong is the
**rows**.

The corpus splits cleanly. Ten of the twelve show header flows differing from
row sums in at least one direction, by amounts ranging from $20.00 to $550.00.
The remaining two — both Capital One — show header flows equal to row sums to
the cent in *both* directions. The test was run before the verdicts were
written, not after.

## Ten files, seven statements: the opening balance lost its sign

All ten are Bank of America statements on overdrawn accounts. In each, the
reader recorded an opening balance that the statement printed as negative as a
positive number. Negating it closes the identity to exactly zero in all ten,
and — this was checked — it is the **unique** single sign flip that does so.
Negating the closing balance, the checks total or the fees total closes none
of them.

| Document | Printed opening | Residual | Restated opening | Corroboration |
|---|---|---|---|---|
| USA-ET-002551 | 1,049.57 | 2,099.14 | −1,049.57 | USA-ET-002543 |
| USA-ET-002557 | 1,049.57 | 2,099.14 | −1,049.57 | USA-ET-002543 |
| USA-ET-002659 | 4.68 | 9.36 | −4.68 | USA-ET-002649 |
| USA-ET-002665 | 4.68 | 9.36 | −4.68 | USA-ET-002649 |
| USA-ET-002689 | 3.68 | 7.36 | −3.68 | USA-ET-002671 |
| USA-ET-002713 | 2.14 | 4.28 | −2.14 | USA-ET-002701 |
| USA-ET-002719 | 10.91 | 21.82 | −10.91 | USA-ET-002713 *(chained)* |
| USA-ET-046337 | 213.91 | 427.82 | −213.91 | USA-ET-046327 |
| USA-ET-001291 | 12.00 | 24.00 | −12.00 | *arithmetic only* |
| USA-ET-001299 | 12.00 | 24.00 | −12.00 | *arithmetic only* |

Three of the seven statements were extracted twice; both copies carry the
identical defect, which is consistent with the separate finding on
re-extraction.

### The corroboration is a different document

For six of the seven statements, the *preceding* statement on the same account
covers the contiguous period and prints the disputed figure as a **negative
closing balance**: −1,049.57, −4.68, −3.68, −2.14, −10.91, −213.91. Those are
separate documents, produced by the institution, that were not themselves in
question. Five of them close on their own arithmetic exactly.

The sixth is the exception and it is recorded as one. USA-ET-002719's
corroborator is USA-ET-002713, which is itself one of the twelve. That
verdict is graded `chained_statement` rather than `adjacent_statement` so
that a chain of dependent findings cannot be presented as a set of
independent ones: if the earlier verdict is overturned, this one loses its
support. A test asserts that no `adjacent_statement` corroborator is itself
adjudicated, which is what stops the grade quietly drifting.

### Why the defect is read as specific to the opening line

Because negative *closing* balances survive extraction intact throughout the
corpus — including on USA-ET-002713 itself, which records its own closing
balance as −10.91 with the sign present while losing the sign on its opening
balance of −2.14 in the same document. The reader is not generally
mishandling negatives. It is mishandling one line.

### The two that rest on arithmetic alone

USA-ET-001291 and USA-ET-001299 are two extractions of a statement whose
predecessor is not in the corpus: the nearest earlier statement on that
account ends more than four weeks before this period begins, so a statement is
missing rather than merely unhelpful. The closing balance is corroborated
*forward* — the following statement opens at the same figure — but the opening
balance is corroborated by nothing except the residual being exactly twice it.

That is admissible and it is weak, and the record says so rather than
flattening it in with the other eight. A residual that matches a prediction is
consistent with the mechanism, not proof of it.

## Two documents: rows lost at page boundaries

Both are Capital One statements whose header flows equal their own row sums,
so the rows are what can be wrong. In both, the text of a transaction that was
never emitted as a row survives at the *start* of a neighbouring row's
description: the reader consumed a page boundary and swallowed what preceded
it.

**USA-ET-004539**, residual $20.00. Row 62's description opens with
`Debit - $20.00 $45.26` — an amount and a running balance, the stranded tail
of a debit — then page furniture, then the transaction the row actually
records. Restoring a single $20.00 debit closes the identity exactly.

**USA-ET-004573**, residual $113.29, from two separate losses. Row 18 strands
`Debit - $13.29 $408.16`. Row 52's description swallows three further
transactions outright: debits of $100.00 and $50.00 and a credit of $50.00, a
net outflow of $100.00. $13.29 + $100.00 = $113.29 exactly. The running
balances quoted inside that description are internally consistent with one
another — 15.72 − 100 = −84.28, −84.28 − 50 = −134.28, −134.28 + 50 = −84.28 —
which corroborates the reading without reference to any other document.

### One caution recorded with the verdicts

The residual alone cannot distinguish a *lost* debit from an *invented* credit
of the same size; both leave the identity short by the same amount. The first
reading of USA-ET-004539 was in fact the invented-credit hypothesis, and it
was wrong: the row it suspected turned out to end with a genuine transaction
once its full description was read rather than only its opening line. Only the
document text separates the two stories. That is written
into the failure class's own docstring so the next person does not repeat it.

## What every row in those two documents claims about itself

`high` confidence. Including row 52, which swallowed three transactions, and
row 62, which swallowed a debit. Neither document contains a single row at any
other confidence level.

This is the empirical demonstration of the claim the package docstring already
makes: model confidence is not a completeness signal, and only the arithmetic
can detect an absence. Had these documents been triaged by confidence they
would have been passed as clean, and $133.29 of movement across two statements
would have been silently missing from the case.

## What these verdicts do not do

They do not promote any document to a higher proof class. `ProofClass` is
assigned mechanically from the source format and the outcome of the
arithmetic, and it is never user-settable — a class a person could raise would
be an opinion, and the point of the taxonomy is that it is not one. A document
whose arithmetic does not close is p3. A well-corroborated adjudication
explains why it is p3. It does not make it p2.

Only fixing the reader and re-ingesting the document can do that, because only
then does the arithmetic actually close. Under cross-examination the honest
sentence is "we know why this one fails and here is the corroborating
statement", not "we decided this one is fine."

## Consequences for the reader

Two defects are now specified precisely enough to fix and to verify:

1. The opening-balance line loses a leading minus sign, on Bank of America
   statements, while the closing-balance line does not. Seven statements
   affected in this corpus.
2. Page-boundary handling merges the transaction preceding a page break into
   the following row rather than emitting it. Two statements and five lost
   transactions here; the same mechanism plausibly affects documents
   whose identity happens to close anyway, which is not detectable from the
   arithmetic and needs its own search.

Each verdict records a restated figure, so after a reader fix the correction
can be confirmed or refuted mechanically by re-extraction rather than by
re-reading the pages.

## Where the records live

The twelve verdicts are Python data in
`backend/tests/test_financial_adjudication.py`, carrying document identifiers
and amounts only — no account numbers, no account holders, no transaction
descriptions, because the corpus is case material and is not in this
repository. The record type has no field for any of those, and a test asserts
it, so adding one takes an argument rather than a commit.
