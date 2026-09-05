# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 6 September 2026 (records `71d859d`, the second frontend chunk
of the decisions screen: `decision-format.ts`, which narrows `subject_type` and
`decision` off the wire and gives every member of both vocabularies words, plus
its unit test. **Still no screen** — this is the layer between the wire and the
hook. **Item 8 is still in progress** and the standing flag about the log being
readable-but-invisible is **still open**; nothing a user can see changed again
this session. Read the disk note under Standing flags **before running
anything**: the documented `CLAUDE.md` bootstrap still fails, and the working
form needs one more environment variable than this file previously recorded.)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `71d859d`
  (`71d859d20bc97d55f25305e61c3deddf2e69f71a`), "Put the decision vocabulary into
  words the screen can show", parent `f18e6eb` (which was the state-file commit
  for `0fa07d5`). **Confirm the real tip with `git log --oneline -5`** at the
  start of every session rather than trusting this line — the state-file commit
  that follows this one will already have moved it.
- **Nothing is pushed.** Push is blocked; Neil pushes.
- **The build order lives in `docs/loupe-wiring-plan.md`,** not in this file. Read
  it before picking up work. It is an agreed plan and is not to be resequenced
  without a ruling from Neil.

### Uncommitted

Nothing tracked. The tree is clean.

Still untracked and still un-removable from a session (workspace denies
`unlink`) — Neil has to delete these from his side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts` — a diagnostic left by the vitest
  investigation ten sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents and case material, left
alone. `docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`, and a large amount of Cellebrite and bundle
material at the repo root. **Do not delete any of it to free disk;** see the
disk note under Standing flags.

### Scale

**128 commits** since `c4246c0` (27 August), counting `71d859d`; 129 once the
state-file commit lands on top of it. Counted with
`git rev-list --count c4246c0..HEAD`, not incremented from the previous figure.

`backend/services/financial/` **51 modules** excluding `__init__.py` (unchanged —
this commit is frontend only); `backend/tests/test_financial_*.py` **58 files**,
**3,381 tests**.

### Gate baselines as of `71d859d`

- **Frontend unit: 74 files, 686 tests, all passing.** Measured at this head over
  the whole project. Up 1 file and 28 tests from `0fa07d5`'s 73/658, accounted
  for exactly by the new `decision-format.test.ts`. **Nothing else moved.**
- **`tsc -b --force` 0; `eslint .` 0.** Both measured at this head over the whole
  project.
- **Backend financial suite: `Ran 3381 tests in 13.049s, OK (skipped=12)`.** NOT
  re-run at this head and it did not need to be: the commit is two TypeScript
  files and no Python. The figure carries forward from `2eefc4d`, where it was
  measured in full, through `0fa07d5`, which was likewise TypeScript only. **The
  Python bootstrap has therefore not been run for three sessions**, which is why
  a fresh session picking up backend work must still do it — see the disk note.
- **Frontend browser: NOT RUN, and it could not be.** See the disk note. Last
  known-good figure is 2 files, 4 tests. **Do not carry "browser green" forward
  as though it were verified at this head.**

**Eight tracebacks on stderr during the backend run are expected and are not
failures — this figure was wrong here for several sessions and read "six".** It
was corrected at `2eefc4d` by counting the *baseline* tree at `dfb9715` as well
as this head; both give eight, so the extra two are **not** a regression from any
recent change. Eight `^Traceback` lines, **seven logged events**, because one
event prints a chained pair. In run order:

1. `RuntimeError: database gone`, logged by `routers/financial_ingest.py:214`
   under "Failed to ingest file ...". A router test injects it through a mock
   `side_effect` to exercise the route's error handler. **This is one of the two
   the old "six" omitted.**
2 and 3. One event, two tracebacks. `sqlite3.IntegrityError: UNIQUE constraint
   failed: financial_transactions.case_id, financial_transactions.ref_id`,
   followed by "The above exception was the direct cause of the following
   exception" and the `sqlalchemy.exc.IntegrityError` wrapping it. Raised from
   `native_ingest_file.py:331` and logged as "Writing evidence file ... failed";
   `tests/test_financial_native_ingest_file.py` ingests the same file twice on
   purpose. **The chaining is the other half of the old undercount** — one
   failure, two `Traceback` headers.
4, 5, 6. `test_financial_quarantine_row.py`: two
   `SQLAlchemyError("connection lost")` injected into each writer to exercise the
   `write_failed` path, and — since `35cc6be` — one
   `services.financial.money.MoneyError: currencies do not match` injected into
   the rescue check to prove an unanswerable question does not stop a quarantine.
   `quarantine_row.py` logs all three with `logger.exception`.
7, 8. The reconciliation pair from `dfcef2b`:
   `test_financial_reconcile_case.py` injects an `OperationalError ... locked` on
   a liveness `SELECT 1` and a disk-full failure on `COMMIT`.

All eight are the code working. **Do not spend a session chasing them.** Count
them directly rather than trusting this list:
`grep -c '^Traceback' <run output>`.

Separately, several **single-line** log messages with no traceback also print,
and are equally expected: "Failed to precheck file ... : database gone",
"Failed to list ledger transactions ... : db exploded", and — new at `2eefc4d` —
"Failed to list decisions ... : db exploded", which is the new route's 500 path
being exercised. A `logger.error` without a traceback is not a failure either.

---

## What this session did

**The decision vocabulary now has words, as `71d859d`.** Two files, 784
insertions, no deletions. **Frontend only; no Python was touched.**

This is chunk (a) of the three named as the next unit last session, taken in the
order named. `0fa07d5` deliberately typed `subject_type` and `decision` as
`string` on the record so a backend one version ahead could not smuggle an
unrecognised member through a union claiming it could not exist. This is the edge
where that narrowing happens, and both the hook and the panel sit on top of it.

**Nothing a user can see changed, so the standing flag about the adjudication log
being readable-but-invisible is still open.** It was narrowed at `2eefc4d` and
has not moved since. It clears when a panel renders, which is chunk (c).

### What landed

**`frontend_v2/src/features/financial/lib/decision-format.ts`** (new, 420 lines)
— placed beside `ledger-format.ts`, `run-format.ts` and `adjudication-format.ts`,
whose shape it follows. Exports `DECISION_SOURCE`,
`DECISION_ORDER_IS_NOT_SEQUENCE`, `readDecisionSubject`, `DecisionReading` and
`readDecision`, `DecidedBy` and `readDecidedBy`, `formatDecisionTime`, and
`describeDecisionPage`. Internal: `SUBJECT_COPY` (5 members), `DECISION_COPY`
(8), `DECISION_VARIANT`, `CHANGED_STORED_STATE`. Narrowing goes through `narrow`
from `ledger-format.ts` rather than a second implementation, so an unrecognised
word is handled the way it is handled on every other screen: named, marked, never
blank.

**`frontend_v2/src/features/financial/lib/decision-format.test.ts`** (new, 364
lines, **28 tests**) — modelled on `run-format.test.ts`.

### Every phrase was written from the writer, not from the member's name

This is the reason the session spent as much of its window reading Python as
writing TypeScript. **Two of the eight members read backwards from their own
names**, and describing them from the name would have put a false statement on
screen:

- **`admit_financial_document` does not mean a document was admitted into the
  ledger.** It means a file the router held back — because it recognised bank
  data, and indexing a statement as prose turns its figures into searchable text
  no total can be traced to — was sent out to that text pipeline anyway, by a
  named person, against the router's finding. `financial` describes the document,
  not the destination. Nothing enters the ledger by it, and it changes no stored
  column: "held" was never a stored state, only the absence of a job.
- **`explain_balance_failure` is not a disposition.** It records a finding about
  why a statement's own figures do not add up, and changes no status and never
  can. A well-corroborated explanation of a weakly-proved document leaves it
  weakly proved.

Both senses are pinned by named tests, so an edit tidying the wording cannot
reverse either one quietly. The source for both is the `AdjudicationDecision`
docstring in `backend/postgres/models/enums.py`, corroborated against the actual
writers.

### The four calls that were decisions, not defaults

**`changedStoredState` is three-valued, not a boolean.** False means the entry
recorded a view and moved nothing. **Null means this build cannot read the
member**, and so cannot say which of the two it was. Collapsing null into false
would report an unknown decision as having changed nothing, which is the
reassuring answer and the one it has not earned. This is the same shape as
`QuarantineGrounds.decidedByPerson` in `ledger-format.ts` and was copied from it
deliberately. Six members change stored state; the two named above do not.

**`by_machine` is read off the record and never re-derived.** The backend makes
the comparison once, in `decision_log.to_record`, case-insensitively against
`RECONCILIATION_ACTOR_EMAIL` (`reconciliation@loupe.invalid`, a reserved domain
no person's account can hold). `api.ts` already says why it is not repeated: a
reader that got the comparison wrong would show software moving a document as
though an analyst had, which is the most misleading thing this log could be made
to say. **A named test pins it** — a record carrying the reconciliation stage's
own address with the flag false must read as a person.

**`describeDecisionPage` never claims "showing all" from `truncated` alone.**
`DecisionPage.truncated` is `self.offset + len(self.decisions) < self.total`,
which **looks forward only**: it is false on the last page even though pages came
before it. So "Showing all N decisions" is claimed only when `offset === 0 &&
!truncated`. This trap was found by reading `decision_log.py` rather than by
inference, and there is a test for the last-page case specifically.

**No `needsAttention`.** `run-format.ts` has one because a broken run is a fact
about the ledger being short. Every record here is a decision somebody or
something already took deliberately, and no member of the vocabulary is by itself
a problem. Which of them matters is a question about the case, not about the
word, so this module does not answer it.

Three smaller ones, recorded because they are the kind of thing a later session
would otherwise redo differently. `DECISION_SOURCE` is "the case's record of
decisions", not "the ledger", because a decision is not a column on a
transaction and outlives its subject — a purge writes its decision before
deleting the row. `formatDecisionTime` delegates to `formatRunTime` rather than
reimplementing it, so the two surfaces give one answer to a fixed locale, an
unparseable value and a missing one. And `before`/`after` are **not**
interpreted here: they are the writer's shape, differing per member (a purge has
no `after` at all), so reading them belongs to whatever renders one decision in
detail.

### Colours

`DECISION_VARIANT` follows the ledger's so the same event reads the same on both
screens: `quarantine_row` amber because a set-aside row badges amber there,
`release_row` success. `warning` is used for **no** member, because `LedgerTable`
and `adjudication-format.ts` both reserve it for "this build cannot read this
value" — which is exactly the unrecognised case here. `purge_duplicate` takes the
solid `destructive` rather than the softer `danger` because it is the only member
in the vocabulary that cannot be undone.

`Badge` falls through to its loud `default` variant for a key a map does not
carry, so a member missing from the table would render as the most important
thing on the screen. `Record<AdjudicationDecision, BadgeVariant>` makes the
compiler catch that instead, and the same applies to `CHANGED_STORED_STATE` and
both copy tables.

### What the 28 tests pin

Three on subjects: every member gets a non-empty label and description that is
not "unrecognised"; `evidence_file` is kept distinct from `source_document`,
because it names the one subject the ledger has never held and a reader who
conflated them would go looking for totals that were never going to exist; and an
unrecognised subject names its raw value and cites `DECISION_SOURCE`.

Eight on decisions: every member gets words; **labels are all distinct** (a
shared label would show one phrase for two different things and nothing else on
the row distinguishes them); no recognised member wears the unrecognised colour;
`changedStoredState === false` is true of **exactly**
`admit_financial_document` and `explain_balance_failure`, asserted as a sorted
list so a third would fail; `destructive` is worn by exactly `purge_duplicate`;
the two backwards-reading members are pinned to the sense the backend states; and
an unrecognised decision returns `value: null`, `variant: "warning"`,
`changedStoredState: null` and a non-empty effect.

Six on who decided, including the two that matter: the machine's stored name
(`Loupe reconciliation stage`) is **replaced**, not shown, because it reads like
a person in a column of people; and the flag is never re-derived from the
address. Then name-over-address-over-`"Not recorded"`, whitespace-only names
falling through, and an entry with neither reading as *incomplete* rather than as
nobody having decided.

Three on time and seven on the page sentence, the latter covering every branch:
empty log, singular "1 decision", start-of-record, **last page with
`truncated: false` and `offset > 0`**, mid-record with more following, and an
empty page past the end (which must not read as an empty log — the two call for
opposite next moves). One on `DECISION_ORDER_IS_NOT_SEQUENCE`.

### Verification

The new test file was run alone first — **28 tests, all passing** — and only then
the whole unit project: **74 files, 686 tests, all passing**, `STATUS=0`. The
delta was checked rather than eyeballed: 73 → 74 files and 658 → 686 tests is
+1 and +28, which is this file exactly. **Nothing unaccounted for.**

`npx tsc -b --force` returned 0. `npx eslint .` returned 0, and both output files
were read to confirm the only content was npm's version notice.

**The vite cache was pointed at `/dev/shm`, never `/tmp`.** `/` is 99% full and a
cache directory there is one of the three ways the gate reports a silent "no
tests". The path carries `$(id -un)` for the usual reason, as do the three gate
output files.

Backend gates not run and **not claimed** — the commit is two TypeScript files
and no Python. This is symmetric with `2eefc4d`, where the frontend gates were
not run and not claimed for a Python-only commit.

**Every gate command was redirected to a file and its status read from `$?`,
never through a pipe.**

The staged tree (`634a464dc7b2a223fa78a5657ed734fd0e3c32d6`) was diffed against
`HEAD` before committing and held exactly the two intended files, 784 insertions
and no deletions, with the untracked `.bak` files, the probe test and all of
Neil's case material correctly excluded. `git status --porcelain` showed no
tracked modifications afterwards.

### What the next unit is

**The `use-case-decisions` hook, then the panel.** Chunk (a) landed this session,
so what remains of the decisions screen is (b) a `use-case-decisions` hook
following `use-ingestion-runs`, and (c) a `DecisionsPanel` and its tab on
`FinancialPage`. **Only when (c) lands does the standing flag clear.**

The hook is the small one and should be a single session's work. Read
`use-ingestion-runs` first and follow it rather than inventing a second shape:
this hook has one thing that one does not, which is paging, and `limit`/`offset`
have to reach `getCaseDecisions` **without being coerced through truthiness** —
`0fa07d5` guards them with `!== undefined` for exactly that reason and a hook
that drops a zero would undo it one layer up.

After the screen: the admission path, which is what finally gives
`record_admission` a caller, and then proof class and `requires_adjudication`.
The three-way split of item 8, and the reasoning for that order, is under the
`a40bb61` entry in "The previous sessions, in brief" below.

### One fact found this session that is not about this commit

**`explain_balance_failure` has no production writer.**
`grep -rn "explain_balance_failure" --include=*.py .` from the repo root returns
the enum, the model, the migrations and tests — and nothing in
`services/financial/` that records one. Every other member has a writer:
`admission.py:150`, `documents.py:654`, `duplicates.py:577/643/783`,
`quarantine.py:680/745`.

This is **not** a defect and nothing was changed for it. The member is in the
vocabulary, the database will accept it, and `decision-format.ts` gives it words
because a screen must be able to read one if it ever appears. But a live case
cannot currently produce one, so **the decisions panel will never show it against
real data yet**, and a future session should not read its absence from a case as
a bug in the panel. Whether a writer is wanted is a question for Neil when the
balance-failure work comes up; it is not blocking anything now.

---

## The previous sessions, in brief

**`0fa07d5`, the wire shape and the client call.** Two files, 618 insertions,
frontend only. A new "Reading back what was decided" section in
`features/financial/api.ts` (+208): `ADJUDICATION_SUBJECTS` and
`ADJUDICATION_DECISIONS` as `as const` arrays, `DecisionRecord` (15 fields),
`DECISION_FIELDS`, `DecisionsResponse`, `CaseDecisionsParams`, and
`getCaseDecisions`. Plus `api.decisions.test.ts` (410 lines, 25 tests), which
reads the Python with `readFileSync` and asserts the wire still is what the
TypeScript believes.

Three calls from that session that still bind: **the limit and offset bounds are
not mirrored on the frontend** (`DEFAULT_DECISION_LIMIT` 100 and
`MAX_DECISION_LIMIT` 500 stay in `decision_log.py`; a bound written down twice
drifts the moment one side moves, so the client sends an over-cap limit as asked
and trusts the limit the response reports); **zero is sent, not dropped**
(`!== undefined`, never truthiness — a `if (params.limit)` would swallow
`limit: 0` and `offset: 0` and turn an explicit request into a default); and
**`subject_type` and `decision` are typed `string` on the record**, matching
`LedgerTransaction.ledger_status`, with narrowing pushed to the edge — which is
`decision-format.ts`, landed at `71d859d`.

Two traps in writing contract tests over Python, both still live for anyone
adding one: **`decision_log.py` declares `as_dict` twice** (on `DecisionRecord`
and on `DecisionPage`), so the `pythonBlock(source, header)` idiom from
`api.runs.test.ts` finds the first one both times — key the scan off the class
first. And **the route docstring contains the literal `` le= ``** in the sentence
explaining why a `le=` is absent, so a naive `not.toMatch(/le=/)` fails on the
prose justifying the assertion; scope it to the `limit` parameter. Also:
`api.runs.test.ts` extracts keys with `/"([a-z_0-9]+)":\s*self\./g`, which misses
`DecisionPage`'s list comprehension; `api.decisions.test.ts` uses the looser
`/"([a-z_0-9]+)":/g` scoped to the `as_dict` slice.

**`2eefc4d`, the HTTP read over the adjudication log.** Two files, 309
insertions, 5 deletions, backend only. `GET /api/financial/decisions` on
`routers/financial_ledger.py`, with `case_id` required and `subject_type`,
`subject_id`, `decision`, `limit`, `offset` optional; 8 tests in a new
`GetCaseDecisionsTests` class.

**The route is on the ledger router and not the adjudication one, and that was
the decision of that session.** `routers/financial_adjudication.py` is the
obvious home because the two routes that *write* these records live there, but
`_adjudication_case_permission` resolves **every** route to `("case", "edit")`
unconditionally and its comment says why: anything added there inherits the write
bar. A read dropped in would take a permission it does not need *and* would make
that comment false. `routers/financial_ledger.py` resolves to `("case", "view")`
unconditionally on the stated grounds that none of its routes write, which stays
true of a decisions read. (`routers/financial_reconciliation.py` was read as the
third pattern: it resolves by HTTP method, which is right for a router serving
both a read and a recompute and wrong for either of the other two, each of which
is uniformly one thing.) **Both comments stayed true and neither had to change.**
The ledger router's module docstring did change — it opened "Two reads of the
same store" and now says three, with the router-choice reasoning written into it.
*Reversed by:* the decisions read ever needing something from the adjudication
router that the ledger router does not have.

Three calls from that session worth keeping: **no `ge=1` or `le=` on the `limit`
`Query`**, because the service refuses a low limit and caps a high one and a
`le=` would turn a servable request into a 422; **the page is handed back whole
as `page.as_dict()`** rather than rebuilt field by field, because a hand-built
response is one careless edit away from silently dropping `truncated`; and **the
two existing routes were not refactored** to use the new `_parsed_member` helper,
because changing working routes with tests pinned to them to save four lines is
churn. The reason is in the helper's own docstring so nobody "tidies" it.

No wiring change was needed: `financial_ledger_router` was already registered in
`routers/__init__.py` and `main.py`, and that the new path is actually served was
verified by printing `router.routes` rather than assumed.

**That session is also where the traceback count in this file was found to be
wrong.** It had read "six" for several sessions. The run gave eight; the baseline
tree at `dfb9715` was run and counted as well and also gave eight, so the extra
two are not a regression. The corrected account is under Gate baselines above.


**`a40bb61`, the first half of chunk 1 of item 8: a reader for the adjudication
log, scoped to a case.** Three files, 1,112 insertions, no deletions, backend
only. `adjudications` had had production writers since `150084a` and **no reader
at all**, so every quarantine, release, purge and machine reclassification
written since then was sitting in a table nothing could read back.
`decision_log.py` (new, 372 lines) added `list_case_decisions` plus
`DecisionRecord`, `DecisionPage`, `DecisionLogError`, `DEFAULT_DECISION_LIMIT`
(100) and `MAX_DECISION_LIMIT` (500), with 37 tests.

**Item 8 was split into three there, and the order was decided by reading the
source rather than by preference.** The wiring plan gives item 8 as
"`assign_proof_class`, `requires_adjudication`, `record_admission`, the decisions
surface", which is three separable things. (1) **The decisions surface** first,
because it is data that exists on disk today and is unreachable, so it has the
shortest path from nothing to something worth having, and it is a read, so it
cannot break a write path. (2) **The admission path**, which is what gives
`record_admission` a caller — it has none today, and
`hooks/use-guarded-process.ts` offers `release` and `dismiss` with no "send the
held file through anyway" action at all. (3) **Proof class and
`requires_adjudication`** deliberately last: proof class is already computed and
already rendered, and what is missing is the *explanation* of what a class means
and what an adjudication changed about it, which is easier to write once the
decisions surface exists to point at. *What would reverse this order:* Neil
wanting the admission override in front of a user sooner than a history nobody
has asked to see yet.

**Why `decisions.history()` could not be the reader**, which is the fact the whole
chunk turns on and is not obvious from the function's name.
`history(session, subject, subject_type)` takes a **loaded subject object** and
filters on `subject_type` and `subject_id`. **It never filters on `case_id`.** So
it answers "what happened to this row" and structurally cannot answer "what has
been decided in this matter". It also cannot bound a route: subject ids are
unguessable, but a caller who has already seen one can name it against any case
at all, and `history` would answer. `list_case_decisions` therefore puts the case
**in the filter rather than checking it afterwards**, the pattern
`quarantine_row.find_case_transaction` already uses and states the reason for: a
subject in another matter is indistinguishable from one that does not exist.

**Three things were decided there, not assumed,** each recorded at length in the
module docstring too. *Ordering:* `subject_sequence` is per subject, so comparing
one subject's 3 with another's 1 means nothing, and `created_at` is Postgres
`now()`, which is **transaction start time**, so events written in one transaction
share it exactly. The order is `created_at DESC, subject_type, subject_id,
subject_sequence DESC` — newest first at the resolution the timestamp actually
has, authoritative within any one subject, and **total**, so paging is stable and
a row cannot appear on two pages. The docstring explicitly refuses to claim that
two events about *different* subjects sharing a timestamp happened in the order
shown. *Bounding:* this **diverges from `transaction_query.list_transactions`,
which is unbounded**, for a specific reason — `reclassify_document` is written by
the reconciliation stage on every pipeline run, so the log grows without any
person deciding anything, and the cost of an unbounded read is set by how often
the pipeline ran. `total` is counted over the **same filters**, so a filtered page
describes its own population. *`by_machine`:* derived from the actor address
against `documents.RECONCILIATION_ACTOR_EMAIL` (`reconciliation@loupe.invalid`)
rather than stored, because a second home for the same fact drifts; **surfaced
rather than left to callers**, because a reader that gets the comparison wrong
shows a machine's reclassification as a person's judgement, which is the most
misleading thing this log could be made to say; matched case-insensitively and
**on equality**, so an address merely *containing* the machine's is not the
machine's. The `RECONCILIATION_ACTOR_EMAIL` import is deferred into the function
because `services.financial.documents` is heavy.

**Two smaller calls, so they are not re-litigated.** `to_record` is public in the
module but deliberately **not** in the package `__all__`: at package level a bare
`to_record` is vague, `transaction_query` already contributes a `to_view` there,
and `tests/test_financial_exports.py` states in its own docstring that the guard
is *module reachability*, at least one name per module. And the constants are
`DEFAULT_DECISION_LIMIT` / `MAX_DECISION_LIMIT`, not `DEFAULT_LIMIT` / `MAX_LIMIT`,
because `services.financial.__init__` is a flat surface shared by fifty-one
modules and a bare `DEFAULT_LIMIT` there would read as the package's limit for
anything paged.

**What the 37 tests pin,** grouped by the claim rather than the function. *The
case bounds the read:* another case's decisions are absent, **naming another
case's subject id returns nothing**, an empty case is a page and not an error, a
read with no case is refused. *The order says only what it can support:* newest
first; events sharing a timestamp on one subject come back with the reversal
leading; six events across two subjects on a single shared timestamp, paged two at
a time, yield six **distinct** ids, which is the property that would break first
if the order were not total; the same read twice returns the same order. *Paging
cannot mislead:* `total` counts the population and not the page, `truncated` is
true and false in the right places, an offset past the end is empty with a true
total, a limit over the cap is **capped not refused**, and a limit of `True` is
refused because `isinstance(True, int)` and a boolean reaching a `LIMIT` clause is
a silent 1. *A machine's decision is not read as a person's:* both directions,
plus the case-insensitive match and the substring near-miss. Two fixture routes
were used on purpose: most tests write through `decisions.record`, so what is read
back is what the **real writer** writes, while the ordering tests insert
`AdjudicationEvent` rows directly because `created_at` is a server default and
those tests are precisely about which timestamps events carry.

**`e64c2ca`, chunk 5 of the quarantine screen, which closed Phase 2 item 6.**
Eleven files, 718 insertions, 39 deletions, frontend only. Chunks 1 to 4b built
pieces and wired none of them: the dialog existed and no screen opened it, the
quarantined list existed and no tab showed it. This is the commit that connected
them. The financial page gained a **"Held out"** tab and **every ledger row
gained a button** offering the one change that row admits of, read from a single
place — `changeAvailableFor` in `lib/ledger-format.ts`, with `RowChange` and
`ROW_CHANGE_LABELS`. The action column on `LedgerTable.tsx` is drawn only when
`onAdjudicate` is given, so the general ledger and the held-out list share one
table without the general list growing a control it has no use for. Quarantine is
complete end to end: write path, localisation reader, and screen.

**`519895e`, chunk 4b of the quarantine screen.** Six files, 747 insertions, 9
deletions, frontend only. The list of rows a case is holding out of its own
totals, plus a column saying what put each one there: `readQuarantineGrounds` in
`lib/ledger-format.ts`, the grounds column on `LedgerTable.tsx` behind
`showQuarantineGrounds` (off by default), and `components/QuarantinePanel.tsx`.
**The open question — a conditional column on the existing table or a second
table — was settled in favour of the column by reading `LedgerTable.tsx`:** three
of its seven cells are correctness rather than presentation (the amount cell
marks a figure it could not scale, the balance cell says a running balance was
absent, every closed vocabulary renders an unrecognised member loudly), and a
second table would be a second copy of all three. **The copy is what drifts** —
not on the day it is written, on the day one of the three is corrected in one
place only. *Reversed by:* the quarantined list needing a cell the general list
has no use for. **The status column stays when the grounds column appears**,
because a row that is somehow not quarantined inside a quarantined list is
exactly what a reader must be able to see. **`QuarantinePanel` is its own
component and not `<LedgerPanel params={{ ledgerStatus: "quarantined" }} />`**
because the empty state means the opposite thing: zero rows there means rows are
sitting outside the filter uncounted, zero rows here means nothing is being held
out, which is a good result. A test asserts the borrowed sentence is *not*
present. The rest of its rules are under "And on the frontend" below.

**`66d1e67`, chunk 4 of the quarantine screen.** Two files, 1,103 insertions,
frontend only. Added `components/RowAdjudicationDialog.tsx` (523 lines) plus 28
tests — the first thing in the five a person can see and use. **Chunk 4 as agreed
was the dialog, the table and the panel in one commit; the dialog landed alone
and the rest became chunk 4b**, on measured size: the three chunks before it were
496, 765 and 644 insertions and the dialog alone was 1,103, so the whole of chunk
4 would have been roughly three times the largest thing in the sequence. **Which
of the two changes it offers is read off the row, not passed in** —
`ledger_status === "quarantined"` means release, anything else means set aside;
a verb prop would be a second copy of a fact the row states and the two can
disagree (*reversed by* a screen needing to offer a verb the row does not imply,
which none in the plan does). **A status this build cannot read gets neither
verb**, because the verb is derived from the status and a guess would send a
write nobody asked for. **Non-admitted rows are not screened out:** a superseded
row is offered "set aside", the ledger refuses, and the refusal is shown as the
ledger's own answer rather than pre-empted in the browser, because a second copy
of the ledger's rules in the browser is a second thing to keep in step. **The
empty-`reason` guard deferred from chunk 3 landed here** and is not a rule
invented in the browser: every writer refuses a blank reason, in four separate
places, three of them with an ordinary refusal, so disabling the button spares a
round trip whose only answer is no. The guard is **at least as strict as the
database's own and never looser** — `trim` treats more strings as blank than the
stored check does, so nothing it accepts can hit a constraint the person cannot
see; the asymmetry is deliberate, do not "fix" it. **Whether the row moved is
reported from `applied` alone**, and where `applied` and the outcome word
contradict each other the contradiction is shown rather than settled. **The
statement-balance fact is said here or nowhere:** `rescues_period` is in this
answer and no other, so it is rendered whenever the reading has anything to say
and suppressed only when there is no fact about a statement at all. Two test
traps found the hard way: **a defaulted parameter cannot express "no case is
open"** (use an options object and `"caseId" in options`), and **`isPending` is
not true synchronously after `fireEvent.click`** (wrap in `await waitFor`).

**`610df9b`, chunk 3 of the quarantine screen.** Two files, 644 insertions,
frontend only. Added `hooks/use-row-adjudication.ts` (119 lines) plus 17 tests.
**One mutation over both routes, not two hooks:** `quarantineRow` and
`releaseRow` take the same three parameters and answer with the same shape, so
the verb travels in `variables.action`; two hooks would hand one button two
`isPending` flags and two `data` objects, and the bug that follows is a screen
reading the answer to the call it did not make (*reversed by* a screen needing a
quarantine and a release in flight at once, which none in the plan does). **A
refusal is a resolved promise,** so `isSuccess` means the question was answered
and `data.applied` is the fact a caller wants. **The answer is read whole before
it is handed back** — `mutationFn` maps through `readRowAdjudication`, so `data`
and the promise from `mutateAsync` are both a `RowAdjudicationReading`, which
matters because `rescues_period` is said in that response and nowhere else and a
caller handed the raw object can render the outcome and lose it. Safe to compose
inside `mutationFn` because the readers cannot throw. **`reason` is passed
through unexamined,** settled by reading `routers/financial_adjudication.py`
(`reason: str = Body(..., embed=True)`, required, no `min_length`) and
`quarantine_row.py`, which does not check it either; the guard was left for the
dialog, where the field is filled in, and landed at `66d1e67`. **A missing
`caseId` rejects rather than asserting,** differing from `use-ledger-ingest.ts`
on purpose because this path changes what a case's totals count. One deviation:
the plan said invalidate on `applied` alone, and it invalidates on `applied ||
outcome.changedTheRow === true`, because refetching when nothing moved costs a
request while not refetching when something did leaves a row on screen in a list
it has left, and the costs are not symmetrical (*reversed by* the disagreement
turning out to be reachable in normal operation rather than only across
versions). What a person is told about whether the row moved still comes from
`applied` alone. Two testing decisions worth keeping: the tests stub
`globalThis.fetch` rather than `vi.mock("../api")`, and invalidation is checked
by seeding a real `QueryClient` and reading `getQueryState(key)?.isInvalidated`
rather than by spying on `invalidateQueries`, because a spy goes on passing after
somebody changes the key the reading side uses.

**`19bffae`, chunk 2 of the quarantine screen.** Two files, 765 insertions,
frontend only. Added `lib/adjudication-format.ts` (414 lines) —
`readRowAdjudicationOutcome`, `readRescueOutcome`, `readAdjudicationReason` and
`readRowAdjudication` composing all three — plus 31 tests. It exists to stop a
screen doing three things, each settled by reading `quarantine_row.py` and
`routers/financial_adjudication.py`. **Treating the outcome as a success flag:**
only two of the six outcomes leave the happy path as HTTP errors, so a refusal is
an ordinary 200 carrying the refusal and the outcome is the content. **Labelling
`reason` as the person's stated grounds:** it is one field carrying four
different things and none of them is what the person typed — the system's rescue
note on a quarantine, `str(exc)` on a refusal, a canned sentence on `unchanged`,
and `None` on a release, because `release_case_row` puts the person's words on
the record and defaults `reason` out of the response.
`ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` is the sentence to show beside it.
**Rendering `false` and `null` alike on `rescues_period`:** four presentations and
not three, because `null` on a quarantine means the question was asked and could
not be answered, while `null` on any other outcome means no row came out so it
never arose. Two decisions inside it: `ledger_status` and `quarantine_reason` are
**not** re-narrowed against a new provenance string, against the letter of the
chunk plan, because `_current()` copies both straight off the stored row so "it
came from the ledger" is the true sentence (*reversed by* a backend change that
computes either rather than copying it); and `changedTheRow` is `null` for an
outcome word this build cannot read, with a disagreement against the wire's
`applied` reported through `appliedDisagreesWithOutcome` rather than resolved
(*reversed by* nothing short of `applied` leaving the wire). One inconsistency
found and deliberately not fixed: `UNRECOGNISED_VARIANT` is `"warning"` in
`LedgerTable.tsx`, which is where the rule is actually written down, and
`"outline"` for the same case in `run-format.ts`. New code follows `LedgerTable`.
It is one line in `run-format.ts` if the ledger's rule is meant to be global, and
a question for whoever next touches the runs screen.

**`1894fc4`, chunk 1 of the quarantine screen.** Two files, 496 insertions,
frontend only. Added the two calls (`quarantineRow`, `releaseRow`), the
`RowAdjudication` shape, `ROW_ADJUDICATION_OUTCOMES`, `ROW_ADJUDICATION_FIELDS`
and `RowAdjudicationParams`, plus `api.adjudication.test.ts`. Three things from
it that the rest of the screen rests on. **The wire fields are typed `string`,
not unions**, because a backend one version ahead can send a member this build
has never heard of and a union would let it through while claiming it had been
checked; narrowing is a runtime job, which is what chunk 2 then did. **`reason`
is required on both calls with no default**, because the backend requires it on
both routes. **Sixteen tests, seven of which read the Python off disk** and
assert the enum members match `ROW_ADJUDICATION_OUTCOMES`, the `as_dict()` keys
match `ROW_ADJUDICATION_FIELDS`, both routes still take `case_id` as a `Query`
and `reason` as an embedded `Body`, and the set of outcomes `_respond` raises on
is exactly `{not_found, write_failed}` — so a future change that starts throwing
on a refusal fails there rather than silently turning a shown refusal into a
thrown one.

*Why the screen and the write path were built as one unit:* a read-only screen
would be a permanently empty state by construction. The only production writer of
`ledger_status = "quarantined"` is `quarantine_case_row`, reachable only over the
POST route, so a screen that could only read would have nothing to read. *What
would reverse it:* a production path that writes computed grounds at ingest,
which is Phase 2 item 8.

**`35cc6be`, the arithmetic half of Phase 2 item 6.** Six files, 1,211
insertions. Built `services/financial/localisation.py` — the reader that turns
rows and periods already in the database into the inputs `would_rescue` and
`localise` want, both of which were fully written, fully tested and unreachable
before it. `quarantine_row.py` gained `_rescue` and `RowAdjudication` gained
`rescues_period`. Three rules from that unit that the screen work depends on:
**the chain is walked over `admitted` rows only**, because the residual it is
compared against sums admitted rows; **the identity is recomputed, never read off
the stored `reconciliation_status` column**, which on a live case is usually
`not_attempted`; and **the system refuses nothing and warns about nothing** when a
removal makes a period balance, it only records the fact, because that balance is
an arithmetic necessity whatever the row was and so is not evidence on its own.
The `rescues_period` authorship rule and its recorded gap are under Standing
decisions.

**`74d9bdf`, the run reaper test race.** No build item moved; one test file
changed. The suite was intermittently failing with `no logs of level WARNING or
higher triggered on services.financial.run_reaper` and the state file was
claiming green. Cause: `reap_stale_runs_forever` runs its sweep on a worker
thread via `asyncio.to_thread`, and **everything the loop says about a sweep is
logged afterwards, back on the event loop.** The harness released the waiting
test from the worker thread, so the test could cancel the loop before the line it
asserted on was written. Measured, not reasoned about: the old harness failed
**5 runs in 30**, the fixed one passed **30 in 30**. Four assertions rode on the
race; a fifth used `assertNoLogs` and so never failed — it had simply stopped
testing. Fix is in the harness only; no production code was touched. The general
lesson is in Durable facts.

**`dfcef2b`, Phase 2 item 7, reconciliation.** Seven files, 2,126 insertions.
Built `services/financial/reconcile_case.py` (the driver `reconcile_period` never
had, plus the read) and `routers/financial_reconciliation.py` (GET reports the
stored column, POST recomputes). The finding that shaped it: **`reconcile_period`
had never run in production**, its only caller being an unwired module, so every
period sat at `not_attempted` for the life of a case. **All the durable rules
from that unit are in "The reconciliation subsystem's own rules" below** and are
not repeated here.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the storybook limitation and the git procedure all
live in **`CLAUDE.md`**. Deliberately not duplicated here.

### Learned recently, newest first

These accumulate. The heading used to say "new this session", which stopped being
true the first time a session added to the list instead of replacing it.

- **`TMPDIR` must be moved to `/dev/shm` as well as `--target`, or pip fails
  with `[Errno 28] No space left on device` even though the target has room.**
  This file previously recorded only the `--target /dev/shm/pylibs-$(id -un)`
  half, and that half alone still fails: pip builds and unpacks in `TMPDIR`,
  which defaults to `/tmp` on the root filesystem, and the root filesystem is
  99% full. The whole install aborts having written nothing, so the failure
  looks like the package list being wrong rather than a disk problem. The
  working form is the bootstrap line with
  `TMPDIR=/dev/shm/tmp-$(id -un)` in front of it — and the directory has to
  exist first. Note the error names `[Errno 28]` and **not** the path that ran
  out, which is what makes it misleading.
- **The expected-traceback count in the backend run was wrong in this file for
  several sessions, and the way it was wrong is worth remembering.** It said six;
  a `grep -c '^Traceback'` gives eight. Two causes, neither a regression. One
  logged failure prints **two** `Traceback` headers because it is a chained
  exception ("The above exception was the direct cause of the following
  exception"), so counting headers and counting failures give different numbers.
  And one traceback — the ingest router's injected `RuntimeError: database gone`
  — was simply never listed. **The method that settled it is the reusable part:
  when a count on stderr does not match this file, run the *baseline* tree at
  the previous head and count there too before assuming your own change caused
  it.** Both gave eight.
- **In this feature a panel test mocks the hook, not the network.**
  `vi.mock("../hooks/use-ledger-transactions", ...)` with a `vi.hoisted` factory,
  which is what `LedgerPanel.test.tsx` already does. What is under test is the
  panel's reading of a query result, not the query, and the query has its own
  tests. The `fetch` stub stays right for api and hook tests, `vi.spyOn` on the
  API object for component tests that assert what was sent. **Still never
  `vi.mock("../api")`** — it replaces the closed vocabularies the format readers
  import and every outcome silently becomes "unrecognised".
- **A prop type that excludes a field does not prove the runtime excludes it.**
  Where a component fixes a value a caller must not override, cast past the type
  in one test (`const params = { ledgerStatus: "admitted" } as never`) and assert
  the fixed value still went out. The compile-time guarantee protects this
  repository; the runtime one protects the screen from anything else.
- **Guard an enum once.** `api.ledger.test.ts` already reads the Python off disk
  and closes `QUARANTINE_REASONS` against the backend enum, so a new member fires
  there. A second copy of that assertion elsewhere is a second thing to update.
  What is worth testing separately is **coverage of a derived table** — a member
  present in the list but missing from a `Record<Member, T>` lookup would report
  as unrecognised while being perfectly recognised, and nothing else catches it.
  In TypeScript a `Record<Member, T>` already fails `tsc` on a missing key, so the
  test is the runtime belt to that braces.
- **A test helper cannot express "not supplied" with a defaulted parameter.**
  Passing `undefined` to `caseId: string | undefined = CASE_ID` **takes the
  default**, so a test written to prove the no-case rejection ran with a case
  open and failed on a real `fetch` instead — which reads like a broken harness,
  not like the test asserting the wrong thing. Take an options object and read it
  with `"caseId" in options`. This applies to every fixture that has an
  "absent" case to test.
- **`isPending` on a mutation is not true synchronously after the click that
  starts it.** It arrives a microtask later. Reading a disabled state straight
  after `fireEvent.click` fails with `expected false to be true`; wrap it in
  `await waitFor`. The same shape as the `result.current.data` trap below, and
  worth assuming for anything React Query sets.
- **`vi.spyOn(financialAPI, "quarantineRow")` works because the hook calls it as
  a property of the exported object,** confirmed by reading
  `use-row-adjudication.ts` before writing the test rather than by trying it.
  This is the right stub for a **component** test in this feature, because it
  lets the trimmed reason and the chosen verb be asserted directly
  (`toHaveBeenCalledWith({ caseId, transactionId, reason })`). The `fetch` stub
  stays the right one for **api and hook** tests. Both precedents exist; neither
  is `vi.mock("../api")`, which is still forbidden here for the reason below.
- **A `new Promise(() => {})` used to hold a mutation in flight must be typed.**
  `mockReturnValue(new Promise(() => {}))` infers `Promise<unknown>` and fails
  `tsc` against a `Promise<RowAdjudication>` return. Write
  `new Promise<RowAdjudication>(() => {})`.
- **`result.current.data` on a mutation is not flushed when
  `await act(async () => { await mutateAsync(...) })` returns**, even though
  `onSuccess` has already run. Three tests failed with `expected undefined to
  be ...` before this was understood, and the ones that passed did so only
  because they happened to have a `waitFor` in front of them. **Put every
  assertion on `result.current.data` inside `await waitFor(...)`.** Where the
  value matters, assert on what `mutateAsync` resolved to as well: the two are
  separate paths a caller can take, and either one carrying the raw wire object
  instead of the reading would let a fact be dropped silently.
- **`vi.mock("../api")` is the wrong tool in this feature and would fail
  quietly.** `api.ts` exports both the callers and the closed vocabularies
  (`ROW_ADJUDICATION_OUTCOMES`, `LEDGER_STATUSES`, `QUARANTINE_REASONS`) that the
  `lib/*-format.ts` readers import. Mocking the module replaces the vocabularies
  with nothing, every value then narrows against an empty list, and **every
  outcome in the file becomes "unrecognised" while the tests still look like they
  are exercising the real thing.** Stub `globalThis.fetch` instead; there is no
  `importOriginal` precedent anywhere in `src`.
- **Test invalidation by seeding a real `QueryClient` and reading
  `getQueryState(key)?.isInvalidated`, not by spying on `invalidateQueries`.** A
  spy asserts the argument the hook passed, so it goes on passing after somebody
  changes the key the reading side uses, which is the exact failure the test is
  there to catch. Seed both the key that should move and one that should not.
- **`routers/financial_adjudication.py` declares `reason: str = Body(...,
  embed=True)` with no `min_length`, and `quarantine_row.py` does not check it
  either.** So the ledger requires the field and requires nothing of its
  contents. Read before writing the hook, not assumed. A client-side non-empty
  rule is a rule the backend does not have, and belongs at the layer where a
  person fills the field in.
- **`mockResolvedValue(new Response(...))` hands every call the same object, and
  a `Response` body can only be read once.** The second call in a test dies with
  `TypeError: Body is unusable: Body has already been read`, thrown from inside
  `fetchAPI` at `api-client.ts:86` — **which reads exactly like the code under
  test having failed**, not like a bad stub. Cost a debugging round here. Use
  `mockImplementation(() => Promise.resolve(new Response(...)))` so a fresh
  response is built per call. `api.ledger.test.ts` never hit this because every
  one of its tests makes exactly one call; `api.adjudication.test.ts` compares
  the two routes, so several of its tests make two.
- **The repo is on a different filesystem from `/sessions`.** See the expanded
  environment note above: tens of gigabytes free on the repo mount, so the gates run
  even while `/sessions` reports zero bytes. The state file previously implied
  the whole environment was blocked; only the backend bootstrap is.
- **Two rows identical in amount, date and direction inside one document collide
  on the content hash.** `uq` is `(source_document_id, content_hash)` and the
  hash is computed from the reading, so a fixture making several rows on one
  period must vary something real — `description=f"row {i}"` is what the
  localisation and rescue fixtures use. Real statements tell such rows apart by
  narrative, so this is the schema being right, not the fixture being awkward.
- **A fixture making several periods for one document and account must vary the
  dates,** for the same reason: the uniqueness rule is
  `(source_document_id, account_id, period_start, period_end)`. A month counter
  is enough. And **a `closing=None` that means "the statement printed none" needs
  a sentinel default**, not `None` as the default, or the helper cannot tell "not
  supplied" from "deliberately absent".
- **`rescue_if_removed` is imported by name into `quarantine_row`'s namespace**
  (`quarantine_row.py:65`), so `patch.object(quarantine_row, "rescue_if_removed",
  ...)` is the working patch target. Checked by reading the import before writing
  the test rather than by trying and debugging.
- **`_UNANSWERABLE` in `quarantine_row.py` is
  `(QuarantineError, ReconciliationError, PeriodError, MoneyError)`.** Anything
  outside that tuple propagates and stops the quarantine.
- **`routers/financial_adjudication._respond` returns `result.as_dict()` with no
  response model,** so a new field on `RowAdjudication` reaches the interface with
  no schema work — **and breaks any router test asserting an exact response
  dict.** There are two, both named
  `test_the_service_is_called_with_the_row_case_actor_and_reason`. Expect to
  update them whenever that dataclass grows a field.
- **`services/financial/localisation.py` has no `__all__`.** The package surface
  comes from the import block and `__all__` in
  `services/financial/__init__.py`, and `tests/test_financial_exports.py` checks
  the module contributes at least one name. Confirmed again here.
- **The bootstrap in `CLAUDE.md` cannot complete: `/sessions` has zero bytes
  free.** Install to `/dev/shm` instead and carry `PYTHONPATH`. **Check
  `df -h /sessions` and `df -h /dev/shm` before assuming either.** The commands
  are written out here rather than referenced, because the section they used to
  be quoted from gets rewritten every session. Two steps, and **both** matter —
  `--target` alone still fails, for the `TMPDIR` reason recorded at the top of
  this list:

  ```
  mkdir -p /dev/shm/pylibs-$(id -un) /dev/shm/tmp-$(id -un)
  TMPDIR=/dev/shm/tmp-$(id -un) pip install --break-system-packages --quiet \
    --target /dev/shm/pylibs-$(id -un) <the seventeen packages from CLAUDE.md>
  ```

  Then every Python invocation carries:

  ```
  env PYTHONPATH=/dev/shm/pylibs-$(id -un) \
      PYTHONPYCACHEPREFIX=/dev/shm/pyc-$(id -un) \
      PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 python3 ...
  ```

  About twenty seconds and roughly 150M installed. Verify by importing
  `sqlalchemy` and `fastapi` and printing their versions before trusting it —
  a partial install fails later in a way that looks like a code error.
- **`PYTHONPYCACHEPREFIX` must not point at `/tmp` either.** `/tmp` is on the
  root filesystem, which is at 99% with about 120M free. Send it to `/dev/shm`.
  Same reasoning as `TMPDIR`: anything that defaults to `/tmp` in this sandbox
  has to be moved by hand.
- **A "no logs ... triggered" failure from a loop test is a scheduling race, not
  a broken loop.** Anything the reaper loop logs is written on the event loop
  after `asyncio.to_thread` returns, so a harness that releases from the worker
  thread can cancel the task first. Fixed for `run_reaper`; **the same shape
  would appear in any future test of a loop built the same way.**
- **A racing `assertNoLogs` does not fail, it stops testing.** Worth checking
  for wherever a negative log assertion sits over a thread hand-off.
- **To compare against an original file without dirtying the tree,** write
  `git show HEAD:<path>` into `/dev/shm`, add `/dev/shm` to `PYTHONPATH`, and
  run it by module name from `backend/`. The workspace denies `unlink`, so a
  scratch copy placed in the repo could not have been removed afterwards.
- **`unittest discover` needs the current working directory to be `backend/`,**
  and the bash cwd resets between invocations, so a run that reports a
  plausible-looking test count may still not be the suite you meant. Put the
  absolute `cd` in the same command every time.

### From the reconciliation session

- **`services/financial/__init__.py` re-exports a *function* named
  `reconcile_case`, which shadows the submodule of the same name.** This is a
  live trap for any test that needs the module object:
  `from services.financial import reconcile_case` binds the **function**, so
  `patch.object(that, "reconcile_period")` fails with "does not have the
  attribute". **And the obvious alternative fails identically** —
  `patch("services.financial.reconcile_case.reconcile_period")` resolves a dotted
  target with `getattr` before it falls back to importing, so it hits the same
  function. The working form is
  `import services.financial.reconcile_case` followed by
  `module = sys.modules["services.financial.reconcile_case"]`. **Any future
  module whose name matches one of its own exported callables has this problem.**
- **Use `session.expire(obj)` and never `session.refresh(obj)` to throw away an
  in-flight mutation.** `refresh` autoflushes first, which writes the thing you
  are trying to discard. This matters wherever a service mutates an ORM object
  and then hits a validation that can raise.
- **`reconcile_period` mutates before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which raises
  `LedgerOverflowError`. **`MixedCurrencyError` is different** — it is raised
  inside `evaluate_identity`, *before* any mutation. Any caller has to handle
  both, and only one of them leaves state behind.
- **Ordering a period list needs `nullslast()` and a secondary key on `id`.**
  `period_start` is nullable, and NULL ordering differs between SQLite and
  Postgres, so an ordering without it is not portable **and** not total. This is
  the same class of bug as the runs list needing a secondary sort on `id`.
- **`IdentityOutcome`'s field order is `status, totals, opening,
  printed_closing, computed_closing, delta, independent, unavailable_reason`,**
  with properties `is_balanced`, `was_attempted`, and `proves_completeness`
  (balanced **and** independent **and** `totals.is_complete`). Constructing one
  by hand in a test needs all eight.
- **`PeriodBounds` has exactly three constructors:** `printed(start, end)`,
  `derived(start, end)`, `absent()`. `supports_continuity` requires **both**
  bounds be `printed`.
- **`financial_statement_periods` has a second uniqueness rule for the undated
  case.** Beyond
  `uq_financial_statement_periods_document_account_period` on
  `(source_document_id, account_id, period_start, period_end)`, nulls are
  distinct inside a unique constraint, so there is a **partial** index
  `uq_financial_statement_periods_document_account_undated` on
  `(source_document_id, account_id)` `WHERE period_start IS NULL AND period_end
  IS NULL`. A fixture that makes two undated periods for one document and account
  will collide.
- **Four coherence check constraints tie each balance to its source**, of the
  form `(opening_balance_source = 'absent') = (opening_balance_minor IS NULL)`,
  for opening and closing, start and end. A fixture cannot set a source of
  `printed` and leave the amount null.

### From earlier sessions, still true

- **The `playwright install chromium` fix recorded here previously has stopped
  working, and the reason is different from the one it fixed.** The old failure
  was `os.tmpdir()` pointing at the full root filesystem, cured by
  `TMPDIR=/sessions/<session>/tmpdl`. The failure now is that **`/sessions`
  itself is full**, against a 179.6M download that then has to extract. It fails
  with `ENOSPC: no space left on device` **after** downloading 100%, twice, once
  per mirror, so it looks like a network problem and is not. **The free-space
  figure in this bullet was going stale every session, so it now lives in one
  place only: the disk note under Standing flags.** As of `35cc6be` it is zero,
  and the browser gate is unrunnable. Assume that until measured otherwise.
- **The repo mount is a different, much larger filesystem** —
  `/sessions/<session>/mnt/owl-n4j` is 461G with 39G free — but **do not stage
  the browser download there.** It is Neil's working repo, the workspace denies
  `unlink`, and 350M of undeletable browser binaries would be left in his tree.
- **When only backend files change, say so and skip the browser project rather
  than reporting a stale figure as fresh.** Check with
  `git status --porcelain` before deciding.
- **`quarantine.py`'s two writers return the transaction, not the event.** So
  naming the adjudication that was just appended means reading it back:
  `history(session, transaction, AdjudicationSubject.transaction)[-1]`. Safe
  because `decisions.record` ends in `session.flush()` and `history` orders by
  `subject_sequence`, which is assigned, rather than by `id`, which is a random
  uuid4, or `created_at`, which two rows can share.
- **`quarantine_row.actor_from_user` builds a `decisions.Actor` from a logged-in
  user.** It uses `getattr` rather than importing the auth model, the same way
  `runs.py` deliberately does, so nothing under `services/financial/` gains a
  dependency on `postgres.models.user`.
- **`_current()` in the quarantine driver reads the row's attributes after
  `session.commit()`.** With `expire_on_commit=True` that triggers a refresh
  round trip. It works and is tested, but it is worth knowing before anyone
  moves the commit.
- **The permission templates define far less than the routers use.**
  `postgres/permissions.py` defines only `case:{view,edit,delete}`,
  `collaborators:{invite,remove}` and `evidence:upload`. **`evidence:process`
  and `evidence:delete` are referenced by existing routers and do not exist in
  the templates at all.** Do not assume a permission string is real because a
  router asks for it.
- **A component that throws for want of a provider does not fail a
  `FinancialPage` test — it vanishes.** Every panel on that page is wrapped in
  its own `ErrorBoundary`, which catches the throw and renders a fallback, so
  the suite stays green while the thing under test is dead. Mock every hook the
  page reaches for, and assert presence explicitly.
- **`tsc -b` alone is not enough after writing test fixtures.** Vitest does not
  typecheck. Use `--force`; the incremental build will otherwise skip a project
  it thinks is current.
- **The git ref file must be `Read` before it can be `Write`n.** `Write` refuses
  with "File has not been read yet" unless that exact path was `Read` earlier in
  the same session. Read it first; its contents are the old head.
- **`Edit`'s read precondition is inconsistent about slices, so do not plan
  around it.** Try a slice on a large file — it may be enough — and fall back to
  a full read rather than assuming either way.
- **The vitest unit project takes about 80 seconds** at 67 files. Not a hang.
- **Never read a "no tests" result as green.** A stale vite cache path, a
  missing chromium and the `unlink` denial all produce it.
- **Radix tab triggers activate on `mousedown`, not `click`.** `fireEvent.click`
  leaves the tab where it was, and **every assertion after it silently describes
  the previous tab** — the test still passes, it just tests the wrong panel.
- **`TooltipProvider` is mounted app-wide at `app/providers.tsx:13`,** so any
  page test rendering a component that uses a tooltip needs one too.
- **A `Transaction` fixture needs six fields minimum.** `BaseFinancialRecord`
  (`financial/api.ts:3–86`) requires `key`, `amount`, `from_entity`,
  `to_entity`, `financial_record_kind`, `financial_view_mode` and
  `is_financial_event`; `TransactionRecord` adds
  `is_evidence_backed_transaction`.
- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) requires an IBAN, a routing number, or an identifier
  **plus an institution name**; otherwise `_account_draft`
  (`native_subjects.py:202`) falls back to `AccountDraft.unidentified` with
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that
  prints an account number and names no bank lands **unidentified with the
  number still visible**. **Do not describe the flag as "no account number
  found" anywhere in the interface.**
- **The `distinguisher` is the file's own sha256,** stable across re-reads, so a
  precheck account key equals the key that gets written.
- **The ledger cannot silently double, and it is the schema that guarantees it.**
  `ref_id` is deterministic from `(file sha256, row content)` and
  `uq_financial_transactions_case_ref` is on `(case_id, ref_id)`. **Do not
  restate the old claim that a second run doubles the money; it is wrong.**
- **A failure inside a `with ingestion_run(...)` block must roll back the
  caller's session before it leaves.** Otherwise the open write transaction
  contends with the run's own bookkeeping session, `_terminate_quietly` swallows
  it by design, and the run is left `running`.
- **`IntegrityError` text is not portable.** SQLite names the offending
  **columns**, Postgres names the **constraint**. Assert the table name.
- **`completed_at` cannot be asserted against a literal.** The column is
  `DateTime(timezone=True)`: Postgres returns it with its offset, SQLite returns
  it naive. Assert against the row's own value plus a prefix check.
- **DB-backed financial tests need file-on-disk SQLite, not `:memory:`** — and
  doubly so for anything that runs on a worker thread.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`.
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
- **No module under `services/financial/` imports `config`.** That is why the
  financial tests need no environment. A new module takes its knobs as
  arguments.
- **NACHA yields accounts and no periods.** camt 3/3 rows and a period, BAI2 3/3
  and a period, MT940 2/2 and a period, NACHA 1/1 and **no** period. Junk bytes
  give `unrecognised`.
- **The century window is required and never defaulted.** Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400.
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file.
- **`wouldStore` and `didStore` read the endpoint's flag, never the outcome
  word.** The same applies to `applied` on the adjudication and reconciliation
  endpoints.
- **An unrecognised vocabulary member is named, never rendered blank,** and **no
  outcome maps to the `default` badge variant** — `Badge` falls through to
  `default` for an unmapped key, so a forgotten member would arrive looking like
  the most important thing on screen.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note
  in `CLAUDE.md`. Confirmed at `dfcef2b`: `reconcile_case` was picked up with no
  edit to that file.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index,
  the vite cache, and any file used only to capture output.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it passes the tree hash you already verified.** A commit
  message with awkward punctuation is safest passed with `-F <file>`.
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code**, and `$?` after a pipe is the pipe's status.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when
  the question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether something is
  reached.** Grep for the import and list the files. **This is what found the
  central fact of both the reconciliation unit and the one before it.**
- **The house component-test conventions** are `render`/`screen` from
  `@testing-library/react`, `MemoryRouter`/`Routes`/`Route` for a routed page,
  `vi.hoisted` for a mock that has to capture something, `data-testid` for
  anything a test needs to find, and `fireEvent` never `userEvent`.
- **Radix `DialogContent` renders a corner X carrying an `sr-only` "Close",** so
  a footer button named "Close" makes `getByRole` ambiguous. Tell them apart by
  `data-slot="dialog-close"`. Related: **`TooltipTrigger asChild` overwrites the
  child's `data-slot`**, so a badge inside a tooltip is found by `data-variant`.
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Any new code touching `amount_minor` must use `formatLedgerAmount`,** whose
  `currency` parameter is a **required `string`**.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()`, commit the parent row first, then the dependent row.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The storybook vitest project cannot run here** and no story covers financial
  code. "vitest is green" only ever means the unit and browser projects.
- **`--reporter=basic` is not a valid vitest v4 reporter.** Use the default.
- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades and warns; the warning is expected output.
- **No live Postgres is needed for the financial suite.**

### The reconciliation subsystem's own rules

New section. Read it before touching item 6's remaining half or item 8.

- **The identity is `opening + (credits - debits) = closing`, in exact integer
  minor units.** The answer is yes or no, never a score. It is the **only** check
  in the subsystem that can detect a transaction that is simply missing: a
  dropped row does not arrive flagged as doubtful, it does not arrive at all, and
  the printed closing balance is the only witness to it.
- **It declines rather than assumes.** A missing balance gives `unavailable` with
  a reason, never a zero. A zero would make the arithmetic close and would be a
  lie.
- **It counts only `admitted` rows,** and the excluded counts travel with the
  result. This is what makes the identity live: quarantine a row and re-running
  changes the answer.
- **`independent` says whether it proved anything.** An identity computed against
  a balance carried forward from the neighbouring period is arithmetic against
  *that period's figure*, not against this document. Worth having, but not
  evidence that this statement was read completely. `proves_completeness` is
  balanced **and** independent **and** the totals complete.
- **The recompute is a POST and the read is a GET, and the split is load
  bearing.** The stored result is the one recorded against the run that produced
  it, at the time it was produced. If a read recomputed, a figure an analyst
  quoted would be a figure that no longer exists anywhere, and two people opening
  the same case minutes apart could see different arithmetic with nothing to say
  which was which.
- **`not_attempted` is reported, not filtered.** It is the default of the read
  and it is the point of the read: **a ledger nobody has reconciled must not be
  able to present itself as a reconciled one.**
- **A refusal leaves the previously stored verdict alone.** It is not reset to
  `not_attempted`. That verdict was a real result when it was taken, and a
  failure to re-derive it today is not evidence that it was wrong.
- **Nothing here moves a proof class.** Deliberately. Moving a class on this
  result is `assign_proof_class` and `record_admission`, which is Phase 2 item 8.
  Two code paths writing that column on two definitions of the same word is how
  it comes to mean neither.
- **A sweep is safe to run repeatedly.** Re-running after nothing changed
  rewrites the same numbers and a new timestamp.
- **`no_periods` and an all-refused sweep are both `200`.** They are facts about
  the case, and an interface has to render them beside the ledger rather than in
  an error path. Only a failed write is a `500`.
- **The parse-time verdict at `native_ingest.py:249` is a different claim from
  this one** and the two can legitimately disagree. That one is about whether the
  file parsed; this one is about whether the stored, admitted rows add up. **Do
  not reconcile them.**

### The localisation reader's own rules

New at `35cc6be`. Read before anything touches `localisation.py` or the rescue
report.

- **`localisation.py` is a reader and nothing else.** It writes no column and
  takes no decision. It turns stored rows and periods into the inputs
  `localise` and `would_rescue` already wanted. **Do not give it a write path**;
  anything that records a verdict belongs with the thing that owns the column.
- **The chain is walked over `admitted` rows only,** because the residual it is
  measured against comes from `total_transactions`, which sums admitted rows.
  Walking a wider population would prove something about a set nobody is looking
  at. **Consequence: the localisation answer moves when a row is quarantined,
  and that is correct.**
- **The identity is recomputed on every call, never read off
  `period.reconciliation_status`.** That column holds whatever the last sweep
  wrote, and on a live case it is usually `not_attempted`, because nothing calls
  the sweep automatically. A reader that trusted it would report against
  arithmetic from another moment or against none at all.
- **Removing the row whose amount equals the residual makes the period balance by
  arithmetic necessity.** This is true whatever the row was and whatever the
  grounds were, so **the balance is not evidence.** Never build anything that
  treats a post-quarantine balance as confirmation that the quarantine was right.
- **The report refuses nothing and warns about nothing.** It states what happened
  so the grounds and the effect can be weighed together. There is a named test
  holding the write path to not refusing a quarantine that rescues a period.
- **`rescues_period` is three-valued and `None` is meaningful.** `True`/`False`
  are findings; `None` means no finding was reached, by one of four routes: no
  period on the row, an unanswerable check, a refused quarantine, or a release.
  **Anything rendering it must distinguish "does not balance" from "no answer".**
- **An unanswerable check never blocks the write.** `_rescue` catches
  `_UNANSWERABLE`, logs with `logger.exception` and returns `(None, None)`. The
  quarantine still happens; the question is recorded as unanswered.
- **The rescue sentence is returned, not logged.** See the authorship rule in the
  quarantine section immediately below — this is the same rule and it is the one
  most likely to be broken by a well-meaning change.

### The quarantine subsystem's own rules

Read it before touching anything in item 6's remaining half.

- **A machine observation must never be merged into a string attributed to a
  person.** `QuarantineBasis.from_adjudication` stores its detail as
  `"<actor>: <reason>"`. Appending the rescue sentence to `reason` would produce
  a log entry in which the person appears to have written words nobody wrote.
  **An evidence log cannot do that.** There is a test asserting the stored reason
  is exactly what the person typed, prefixed only by their name.

- **Grounds are a proof or a person, and nothing else.** `QuarantineBasis` has
  three constructors and **none of them takes a `Candidate`**, by design. A
  class a person can raise must not be able to pass for one the arithmetic
  proved, which is the settled rule that proof class is computed and never set
  by hand. The endpoints therefore always record `QuarantineReason.adjudicated`
  and the computed grounds are unreachable from HTTP.
- **`ck_financial_transactions_quarantine_coherent` is
  `(quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')`.** A
  released row **must** have its reason nulled, so a row that was quarantined
  and let back in is, on the row alone, indistinguishable from one that was
  never held. **The adjudication log is the only place that history exists.**
  Anything reporting on quarantine has to read the log, not the row.
- **`quarantine_transaction` refuses a row that is not `admitted`.** So a
  superseded or rejected row cannot be quarantined, and the driver reports that
  as `refused` with the writer's own words.
- **`quarantine_transaction` is idempotent for identical grounds and refuses
  different ones.** Same grounds: returns the row, appends nothing. Different
  grounds: raises `UngroundedQuarantineError` containing "already quarantined".
  The refusal is deliberate — it stops a person's opinion overwriting a computed
  class.
- **`release_transaction` refuses a row that is not quarantined** with a message
  containing "nothing to release", and requires both a real `Actor` and a
  non-empty reason.
- **An unchanged row is reported separately from a changed one.** Reporting an
  idempotent no-op as `quarantined` would hand back an `adjudication_id` naming
  **somebody else's earlier decision** as though it were this request's. The
  status is read before the call and that case comes back `unchanged` with no id.
- **The 404 is worded identically for a row in another case and a row that does
  not exist,** so asking cannot be used to learn what a case the caller cannot
  see contains. There is a test asserting the two routes word it the same.

### The ledger screen's own rules

- **The ledger read defaults to `admitted`** (`transaction_query.py`). Zero rows
  does not mean no financial material; quarantined, superseded and rejected rows
  sit outside the filter. The empty state names the status it filtered on.
- **`total` is `len(transactions)` of the same response.** No paging behind it.
  The panel takes its count from `rows.length` and surfaces a disagreement.
- **Rows arrive ordered by `ordering_date.asc(), row_index.asc()`.** The table
  does not sort. **Do not add client-side sorting without dealing with that.**
- Three things in the table are correctness, not presentation: an unscaled
  amount is marked, an absent running balance is stated in words rather than
  left blank, and an unrecognised vocabulary member renders loudly with
  `data-unrecognised="true"`.
- **The ledger query key is `["financial-ledger", caseId, ...]`,** deliberately
  outside `["financial", caseId, ...]`. `useIngestFile` invalidates the former
  only.

### The runs subsystem's own rules

- **`GET /api/financial/runs` returns every status by default,** the opposite of
  the ledger read. Anything built on top must not "helpfully" filter to
  completed runs; the failures are the payload.
- **The run read makes no staleness judgement, and must not start.** Deciding a
  run is abandoned is the reaper's call and the reaper writes it down.
- **The counts on a run are historical.** `documents_seen`,
  `transactions_admitted` and `transactions_quarantined` were true when the run
  ended. **Adjudication moves rows afterwards**, and **so does a reconciliation
  sweep's effect on what those rows mean**, so they will legitimately disagree
  with a `COUNT(*)` over the ledger today. **Do not reconcile them.**
- **`started_by_email` outlives `started_by_user_id`.** The FK is
  `ON DELETE SET NULL`. Prefer the email.
- **`reap_stale_runs` is global, not case-scoped.** This is why it is a lifespan
  loop and not an endpoint.
- **Ordering runs needs the secondary sort on `id`.** `started_at` alone is not
  a total order. Same rule now applies to ordering periods.

### And on the frontend, as of `e64c2ca`

Rules from the quarantine screen, now complete in six commits.

From the wiring, `FinancialPage.tsx`, `LedgerTable.tsx`, `financial.store.ts` and
`ledger-format.ts`:

- **`RowAdjudicationDialog` is mounted by `FinancialPage`, on page state, outside
  `Tabs` and outside both panels. Do not move it into either.** A successful
  change invalidates `["financial-ledger", caseId]`, which is a prefix of both
  lists, so the row leaves the list it was clicked in and the panel returns its
  early empty state; and Radix `Tabs` mounts only the active tab's content, so a
  tab change would do the same one level up. Either way the dialog is torn down
  at the moment its answer arrives, **and `rescues_period` with it**, which is
  said in that one response and on no record.
- **Two tests pin the mount point, one per panel:** the row goes on being passed
  to the dialog after it has left every list on screen. **There is no test for a
  tab change while the dialog is open and there cannot be one** — the dialog is
  modal, Radix marks the rest of the document `aria-hidden`, and the tab strip
  cannot be reached by role behind it. Do not file this as missing coverage.
- **`changeAvailableFor` in `lib/ledger-format.ts` is the single reading of which
  change a row admits of,** and `ROW_CHANGE_LABELS` the single source of the two
  words. It is in `lib/` and not a hook because **`lib/` must not import from
  `hooks/`** and both the table and the dialog need it. A second copy of either
  lets the word on the row and the word on the confirm button disagree.
- **`null` from it means "this build cannot read the status", not "no change is
  possible".** The cell says "Status unread, no change offered" rather than going
  blank; a blank cell in a column of buttons reads as *nothing can be done to
  this row*, when what is true is that the build cannot tell whether the row
  counts toward the totals. **Do not render an empty cell here.**
- **Every readable status other than `quarantined` is offered a setting aside,
  including `superseded` and `rejected`.** The ledger may refuse; the refusal is
  the answer and it arrives in the response. **Do not add a client-side status
  filter to the button** — same rule as the dialog's, one layer up.
- **The action column is drawn only when `onAdjudicate` is passed.** A column of
  buttons that do nothing states that a change can be asked for from a screen
  that cannot ask for one.
- **`LedgerTable` never mutates.** It hands the row back and stops, which is what
  keeps every case in its test file assertable against rows alone.
- **`changeAvailableFor`'s tests loop over `LEDGER_STATUSES`,** so a fifth member
  added to the backend enum cannot silently fall through to `"quarantine"`. **The
  table's tests assert `data-change`, not the button text,** so the labels can be
  reworded without the rule going quiet.
- **`mainView` is omitted from `partialize` and deleted in `merge`, so it is
  never persisted and a new member needs no migration.** Read there, not assumed.
  **If `mainView` is ever added to `partialize`, that changes: the store then
  needs a version and a migration**, and a browser holding an older value could
  otherwise put the page in a state the build cannot render.

From the list, `QuarantinePanel.tsx`, `LedgerTable.tsx` and `ledger-format.ts`:

- **`QuarantinePanel` fixes `ledger_status=quarantined` and its `params` type
  excludes the field.** Every sentence on it is only true of quarantined rows,
  starting with the empty state. Do not turn it back into `<LedgerPanel
  params={{ ledgerStatus: "quarantined" }} />`; that panel's empty copy states
  the reverse of what was checked.
- **Zero quarantined rows is a good result and must read as one.** "Nothing is
  being held out of this case's totals", not "no rows found". The general ledger
  panel's "change the status filter to see them" must never appear here, and a
  test asserts it does not.
- **The count on it comes from `rows.length`; `total` disagreeing is reported as
  a fault.** The endpoint returns `total` as `len(transactions)` of the same
  response, so a mismatch can only mean paging appeared without this screen
  knowing, and a page of quarantined rows shown as the whole set understates what
  is being excluded.
- **`showQuarantineGrounds` on `LedgerTable` moves the reason out of the status
  cell into a column; it does not duplicate it, and the status column stays.** A
  row that is somehow not quarantined inside a quarantined list is precisely what
  a reader has to be able to see. The default is off, so the general ledger list
  is unaffected.
- **`readQuarantineGrounds`, not `readQuarantineReason`, wherever the
  classification matters.** It wraps the other and adds `decidedByPerson`
  (three-valued: `true`, `false`, `null`) and `origin`. `adjudicated` is the only
  member that is a person's decision — `from_adjudication` is its only
  constructor and `quarantine_case_row` refuses to let a person type any other.
- **The words behind an adjudicated hold are not on the ledger read, so any
  screen showing the category must say where they are.** `AdjudicationEvent`
  (`adjudications` table) carries `reason` as `Text, nullable=False`; the ledger
  row carries the category and no detail field. Saying "a person decided" and
  stopping reads as a decision with no reason given.
- **Quarantine badges stay outline in both positions.** Filled reads as a second
  status when stacked under one; colouring them once they have their own column
  ranks five different grounds as a severity scale, which they are not.

From the dialog, `RowAdjudicationDialog.tsx`:

- **`RowAdjudicationDialog` must be kept mounted until the person closes it.** A
  successful change invalidates the ledger lists, so the row leaves the list the
  dialog was opened from. The mutation, and therefore the answer, lives in the
  dialog: unmounting it when the row disappears destroys the answer before it has
  been read, **and the statement-balance fact with it**, which exists nowhere
  else. Its `open` and `onClose` are what the caller drives, not conditional
  rendering on the row still being present.
- **It takes `row`, not a verb.** Which change it offers is derived from
  `row.ledger_status`. Do not add an `action` prop; two copies of that fact can
  disagree, and the disagreement asks the ledger to do something already done
  while telling the person otherwise.
- **A status it cannot read offers no change at all,** deliberately, and still
  draws the row and the raw value. Not a client-side refusal — there is simply
  nothing to derive the verb from.
- **It does not screen out rows the ledger will refuse.** A superseded row is
  offered "set aside" and the refusal is displayed as the ledger's answer. **Do
  not add a client-side status check;** it is a second copy of the ledger's rules
  and it is the copy that drifts.
- **The non-empty `reason` guard lives here and nowhere else,** and it is
  `trim()`-based, which is **stricter than** the database's own blank check on
  purpose. The asymmetry is the safe direction: nothing the dialog accepts can
  hit a constraint the person cannot see. Do not "fix" it into an exact match.
  What is sent is the trimmed text, which is what the writer would store anyway.
- **The sentence about whether the row moved comes from `applied` only.** Where
  `applied` and the read outcome word contradict, the contradiction is rendered,
  not resolved.
- **`rescues_period` is rendered whenever the reading has anything to say and
  suppressed only where no statement was checked** — in practice the release
  path. It is in this answer and on no record. A screen that drops it loses it.

From the hook and the layers below it:

- **`useRowAdjudication(caseId)` is the only way a component asks for a row to be
  set aside or let back in.** One mutation for both routes; the verb is
  `variables.action`, `"quarantine"` or `"release"`. It resolves to a
  `RowAdjudicationReading`, already mapped — **do not re-read the wire object,
  there isn't one to read.**
- **`isSuccess` on it does not mean anything moved.** `data.applied` does. A
  screen that reports off the mutation's success flag will tell a person a row
  was held when the ledger refused.
- **It invalidates `["financial-ledger", caseId]` and nothing else,** which is a
  prefix of both the admitted and the quarantined list — right, because an
  adjudication moves a row between them rather than adding or removing one. The
  Neo4j keys under `["financial", caseId, ...]` are a different store and are
  deliberately untouched.
- **It rejects when `caseId` is undefined** rather than sending
  `case_id=undefined`. This differs from `use-ledger-ingest.ts`, which asserts;
  that difference is intended and is not to be tidied away.
- **`reason` is not validated here.** The backend requires the field and not its
  content. The non-empty guard goes in the dialog.
- **Never `vi.mock("../api")` in this feature's tests.** It replaces the closed
  vocabularies the format readers import from the same module, and every outcome
  in the file silently becomes "unrecognised" while the tests still look real.
  Stub `globalThis.fetch`, building a **fresh `Response` per call** — a shared
  one reads its body once and the second call dies with "Body is unusable",
  which looks exactly like the code under test failing.

- **`financialAPI.quarantineRow` and `.releaseRow` exist and are the only way to
  change a stored row's standing.** Both take `{ caseId, transactionId, reason }`,
  all three required. `case_id` goes in the query string, `reason` in the JSON
  body under its own key, the row id percent-encoded into the path.
- **A refusal is a 200, not a throw.** Only `not_found` (404) and `write_failed`
  (500) leave the happy path. Callers must read the returned `outcome`, not treat
  a resolved promise as success. `applied` is true for exactly `quarantined` and
  `released`.
- **`RowAdjudication.reason` is overloaded by outcome and must not be presented
  as one thing.** Established by reading `quarantine_row.py` at `19bffae`, and
  the earlier wording of this bullet was wrong on two of the four: on
  `quarantined` it is the machine's rescue note or null; on `refused` it is
  `str(exc)` from the writer; on `unchanged` it is a canned sentence; on
  `released` it is **`None`**, because `_current()` defaults it and the person's
  words go to the record instead. On the two error outcomes it does arrive — as
  the `detail` of the 404 or the 500.
- **None of the four is the person's own words**, on any outcome. A screen that
  labels the field as somebody's stated grounds is putting words in their mouth.
  `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` in `lib/adjudication-format.ts` is
  the sentence to show beside it.
- **`ledger_status` and `quarantine_reason` on an adjudication answer are ledger
  values, not adjudication values.** `_current()` copies both straight off the
  stored row, so they narrow through `readLedgerStatus` / `readQuarantineReason`
  and their unrecognised copy correctly says the value came from the ledger.
  Only `outcome` gets its own provenance string.
- **`ROW_ADJUDICATION_FIELDS` is typed `readonly (keyof RowAdjudication)[]`** so
  a name the interface does not declare fails to compile, and
  `api.adjudication.test.ts` closes the other direction against the Python.
  **A new field on the backend `as_dict()` must be added to both.**
- **`UNRECOGNISED_VARIANT` is `"warning"` in `LedgerTable.tsx` and
  `adjudication-format.ts`, and `"outline"` in `run-format.ts`.** The two
  disagree and neither is wrong on its own; `LedgerTable` is the one that states
  the rule ("used for nothing else"), so new code follows it. Left as is.
- **`outcome`, `ledger_status` and `quarantine_reason` are `string` on purpose.**
  Narrowing is `adjudication-format.ts`'s job. Do not "fix" them into unions.

Everything below is from `bc23570`, **except the two `FinancialMainView` bullets,
which were updated at `e64c2ca` when the sixth tab landed.**

- **`readRunStatus(raw).needsAttention`** is true for `pending`, `running`,
  `failed`, `aborted`, and **false for an unrecognised status**, deliberately,
  with a named test.
- **`RUN_COUNTS_ARE_HISTORY` must accompany the three counts** wherever they are
  shown; `IngestionRunsTable` renders it itself so a caller cannot separate them.
- **`readRunStarter` prefers the email**, falls back to `User <id>`, and says
  "Not recorded" rather than rendering an empty cell.
- **`formatRunTime` is fixed to `en-GB`,** matching `formatLedgerAmount`. An
  unparseable value is shown as it arrived, not as "Invalid Date".
- **`runDuration` returns `null` rather than `0`,** with two distinct
  presentations keyed `run-no-end` and `run-no-duration`. Do not collapse them.
- **`IngestionRunNotice` calls `useIngestionRuns(caseId)` with no params,** so
  its cache entry is `["financial-runs", caseId, null]`. **Anything else wanting
  every attempt on the case must call it the same way** or it opens a second
  cache entry and a second request for identical data.
- **The runs query key is outside both other keys, and nothing invalidates it.**
  Ruled closed by Neil.
- **The notice is a sibling of `LedgerPanel`, not inside it.** `LedgerPanel`'s
  four early returns would otherwise hide it exactly when the ledger is empty.
  **Do not "tidy" this by nesting them.**
- **`FinancialMainView` has six members** as of `e64c2ca`, `"ledger" | "runs" |
  "quarantine" | "transactions" | "counterparties" | "trends"`. **The order is
  load bearing:** the first three read Postgres, the last three read the graph,
  and `"quarantine"` is placed with the first group for that reason.
- **The ledger, attempts and held-out tabs take no graph chrome.** A case with an
  empty graph must still reach all three.
- **`api.runs.test.ts` reads the Python source** to prove the two languages
  still agree. A backend change to the route, the parameters, the envelope keys
  or the ordering clause fails a frontend test. That is the intended alarm.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and
committed before the next begins. **Do not reorder without a ruling.** If a unit
turns out to depend on something later in the list, stop and ask.

- **Phase 1, make rows exist — COMPLETE.** Precheck endpoint ✅ `a4eb3dc`,
  ingest endpoint ✅ `43f8358`, the interface action on a held file ✅ `17d94ac`,
  mount the ledger ✅ `4324b24`.
- **Phase 2, make the rows trustworthy** — runs ✅ item 5 complete (backend
  `cde43c5`, notice `8924668`, attempts list `bc23570`); quarantine ✅ item 6
  **complete end to end** (write path `150084a`, localisation reader and rescue
  reporting `35cc6be`, screen chunks 1 to 5 `1894fc4`, `19bffae`, `610df9b`,
  `66d1e67`, `519895e` and `e64c2ca`); reconciliation ✅ item 7 (`dfcef2b`).
  **Item 8, adjudication and proof class, is in progress** — chunk 1 of 3, the
  decisions surface, has its case-scoped reader `a40bb61` and its route `2eefc4d`;
  the screen is outstanding and is the next unit. Then duplicates, suspect
  amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

### Current unit: item 8, adjudication and proof class — the decisions screen

**Start here.** The wiring plan's own words for it: *"`assign_proof_class`,
`requires_adjudication`, `record_admission`, the decisions surface. Proof class
is computed and never set by hand; the interface shows it and shows what an
adjudication changed, and never offers a control that sets it."*

**The chunking, decided at `a40bb61` and reasoned about at length under "What
this session did":**

1. **The decisions surface.** `services/financial/decision_log.py` ✅ `a40bb61`.
   `GET /api/financial/decisions` on the **ledger** router ✅ `2eefc4d`.
   `financialAPI.getCaseDecisions` and its contract test ✅ `0fa07d5`.
   `lib/decision-format.ts` and its test ✅ `71d859d`.
   **Still to do, in this order: the hook, then the panel.** The log is readable
   over HTTP, callable from TypeScript, and now readable as English, and no user
   can see it. Nothing needs deciding about where the route lives, what the wire
   looks like, or what the vocabulary means; all three are settled and built. The
   remaining two are frontend units, so the `/dev/shm` pip bootstrap is *not*
   needed for either — the vitest and Chromium notes are. Specifically:
   - ~~**`decision-format.ts`.**~~ Landed at `71d859d`. Exports
     `readDecisionSubject`, `readDecision` (with `variant`, three-valued
     `changedStoredState` and an always-safe `effect`), `readDecidedBy`,
     `formatDecisionTime`, `describeDecisionPage`, `DECISION_SOURCE` and
     `DECISION_ORDER_IS_NOT_SEQUENCE`. **The hook and the panel use these rather
     than touching `subject_type` or `decision` as strings.**
   - **`use-case-decisions`.** Follow `use-ingestion-runs`. The page envelope
     carries `total` and `truncated`, and both have to reach the component —
     a hook that returns only `decisions` throws away the fact that the history
     was cut short, which is the one thing this read exists to be honest about.
   - **`DecisionsPanel` and its tab on `FinancialPage`.** Note the keep-mounted
     rule under Standing flags before touching `FinancialPage`:
     `RowAdjudicationDialog` is mounted outside `Tabs` on purpose and two tests
     hold it there.
2. **The admission path**, which gives `record_admission` its first caller.
3. **Proof class and `requires_adjudication`**, last, because the class is
   already computed and already rendered; what is missing is the explanation of
   what it means and what an adjudication changed about it.

**Four facts established by grepping the source at `e64c2ca`, not remembered.**
They change the shape of the unit, so check them again before building but do not
re-derive them from scratch:

- **`assign_proof_class` already has production callers and is not dark code.**
  It is called from `camt053.py`, `bai2.py`, `mt940.py`, `nacha.py` and
  `documents.py` (three call sites there, including `proof_class=...` on a draft).
  So proof class is **already being computed and stored at parse time**. This
  unit is not "start computing it"; it is the surface that shows it.
- **`requires_adjudication` has zero production callers.** It is defined at
  `proof_class.py:206` and exported from `__init__.py`, and nothing else calls
  it. That is the gap.
- **`record_admission` has zero production callers.** Defined at
  `admission.py:104`, exported, and referenced only in docstrings —
  `reconcile_case.py:28` and `routers/financial_reconciliation.py:33` both say in
  so many words that it is *"a later unit"*. **This unit is that later unit.**
- **`routers/financial_adjudication.py` exists but has only two routes,** both
  from item 6: `POST /transactions/{id}/quarantine` and
  `.../release`. There is **no admission route and no proof-class route.** The
  router, its permission dependency `_adjudication_case_permission` and its
  `_respond` helper are already built and are the natural home.

**Read before building the screen:** `backend/routers/financial_ledger.py` for
the contract the screen consumes — the route's parameters and the shape of
`DecisionPage.as_dict()`, including `total` and `truncated`, which a history
screen has to render rather than quietly drop —
`frontend_v2/src/features/financial/api.ledger.ts` and its test for how a read
is added to the API object, and the quarantine screen's own files as the nearest
worked precedent for a tab on the financial page. The frontend conventions are
under "And on the frontend, as of `e64c2ca`" above and they are not optional.

**Read before building chunks 2 and 3:** `services/financial/proof_class.py`,
`services/financial/admission.py`, `services/financial/adjudication.py` (which
carries `AdjudicationError`, `UnpaidObligationError`, `MalformedVerdictError` and
the `Adjudication` class at line 180), and `routers/financial_adjudication.py`.
**Do not plan those chunks from this file** — plan them from those four.

**The screen is frontend work, so the `/dev/shm` pip bootstrap is not needed for
it.** What *is* needed is the vitest cache path on `/tmp` carrying the current
user and the per-session Chromium install, both in `CLAUDE.md`; all three of the
frontend failure modes report a silent "no tests", so **never read "no tests" as
green.** Chunks 2 and 3 are backend and do need the bootstrap — the documented
`CLAUDE.md` one still fails on `ENOSPC`, and the working form is under "Carried
forward", now including the `TMPDIR` flag that was missing from it.

**The settled rule that constrains the whole unit** is already in `CLAUDE.md`:
*proof class is computed, never set by hand, including by us. A class a person
can raise is an opinion.* So the surface shows the class and shows what an
adjudication changed; it never offers a control that sets a class.

### The quarantine screen, as built — item 6 is closed

Six commits, the last of them `e64c2ca`. The screen was planned in five; chunk 4
was split in two because the dialog alone came to 1,103 insertions. **Nothing in
this list is outstanding.** It is kept because the chunk boundaries record where
each rule was decided, and the rules themselves are under "And on the frontend"
above.

- **Chunk 1 ✅ `1894fc4`.** `api.ts`: the two calls, the `RowAdjudication` shape,
  `ROW_ADJUDICATION_OUTCOMES`, `ROW_ADJUDICATION_FIELDS`, `RowAdjudicationParams`,
  plus `api.adjudication.test.ts` holding the contract against the Python.
- **Chunk 2 ✅ `19bffae`.** `lib/adjudication-format.ts` plus its tests.
  `readRowAdjudicationOutcome`, `readRescueOutcome`, `readAdjudicationReason`,
  `readRowAdjudication`. What chunk 3 and chunk 4 need to know about it: **read
  the whole answer with `readRowAdjudication`, not the outcome on its own** —
  it composes the rescue reading in deliberately, because `rescues_period` is
  said nowhere else and a caller reading only the outcome would drop it.
  `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` must be shown wherever `reason` is.
  The reading exposes `outcome.changedTheRow` (this build's reading, `null` when
  it cannot read the word) separately from `applied` (the wire's own), and
  `appliedDisagreesWithOutcome` when they contradict.
- **Chunk 3 ✅ `610df9b`.** `hooks/use-row-adjudication.ts` plus its tests. One
  mutation over both routes, the verb in `variables.action`. What chunk 4 needs
  to know: it resolves to a **`RowAdjudicationReading`, already mapped**;
  `isSuccess` means the question was answered and **`data.applied` is the fact**;
  it invalidates `["financial-ledger", caseId]` itself, so a caller does not; and
  it does **not** check that `reason` says anything, because the backend does not
  either. The plan's "invalidate on `applied` only" was widened to `applied ||
  outcome.changedTheRow === true`; the reasoning and what would reverse it are in
  the session notes above and in the commit message.
- **Chunk 4a ✅ `66d1e67`.** `components/RowAdjudicationDialog.tsx` plus its
  tests. The first surface a person can see. **The empty-`reason` guard deferred
  from chunk 3 landed here.** What 4b and 5 need to know: it takes `row`, not a
  verb, and derives the change from `row.ledger_status`; it must be **kept
  mounted until the person closes it**, because the answer lives in its mutation
  and the row will leave the list underneath it; and it reports movement from
  `applied` alone. Its rules are under "And on the frontend" above.
- **Chunk 4b ✅ `519895e`.** `readQuarantineGrounds` in `lib/ledger-format.ts`,
  the grounds column on `LedgerTable.tsx` behind `showQuarantineGrounds`, and
  `components/QuarantinePanel.tsx`, plus tests. The conditional-column-versus-
  second-table question was **answered against `LedgerTable.tsx` in favour of the
  column**; reasoning and reversal in the session notes above and in Standing
  decisions below. **`QuarantinePanel` takes `caseId: string | undefined` and an
  optional `params` that cannot carry `ledgerStatus`**, and it handles the
  no-case, loading, error and empty states itself, so a caller mounts it and
  passes the case.
- **Chunk 5 ✅ `e64c2ca`.** The "Held out" tab wired into `financial.store.ts`
  and `FinancialPage.tsx`, the action column on `LedgerTable.tsx` driven by
  `changeAvailableFor`, and the dialog mounted on page state outside `Tabs` and
  outside both panels. `FinancialMainView` took its sixth member with **no
  migration**, because `mainView` is omitted from `partialize` and deleted in
  `merge`. Rules under "And on the frontend" above.

**One guard considered and not written, recorded so it is not silently
forgotten.** The row identity the dialog sends is `row.key`, which the backend
sets at `services/financial/transaction_query.py:184` as `key=str(row.id)` — read
there, not remembered. A test walking the Python to prove the adjudication route
and the ledger read still name the same identity, the way `api.runs.test.ts`
does, would be a real guard and does not exist. **It is not blocking anything;
pick it up if a session has room.**

### Two questions settled by reading the source, not open

**The two-value grounds column ships now.** `from_proof` is reachable from the
reader but **no production path calls it** — computed grounds are unreachable
from HTTP by design — so on a live case every quarantined row currently reads
`adjudicated`. The column is correct, costs nothing, and its second value arrives
with item 8. *What would reverse it:* nothing short of item 8 being dropped.
**Settled; do not raise it with Neil.**

**The screen and the write path are one unit.** A read-only screen would be a
permanently empty state by construction: `quarantine_case_row`, over the
adjudication route, is the only production writer of `quarantined`. *What would
reverse it:* item 8 giving the list a second source.

### The screen question, settled by reading the source

- **The read is the same endpoint.** `GET /api/financial/ledger` already takes
  `ledger_status`, and `ledger_status=quarantined` returns exactly the
  quarantined population. **No new read endpoint is needed and none was built.**
- **But a quarantined row carries a field an admitted row structurally cannot.**
  `quarantine_reason` is non-null for exactly the quarantined rows and null for
  everything else, guaranteed by the check constraint. A column that is
  meaningful for one status and structurally empty for every other is a column
  that does not belong in the shared table *by default*.
- **So: a filter on the read, and the column behind a flag rather than a second
  table.** Settled at `519895e` by reading `LedgerTable.tsx`, which is what this
  bullet used to defer. `showQuarantineGrounds` is off by default, so the general
  ledger list is unchanged; `QuarantinePanel` turns it on. `FinancialMainView`
  gained its sixth member at `e64c2ca`, placed with the first two because it reads
  Postgres. **This bullet is now history rather than plan; nothing here is
  outstanding.**

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, **is no longer blocked.** It maps onto Phase 2 item 10,
and the direction is settled in Standing decisions below.

12 is absorbed into Phase 1, which is now complete.

13, user-defined view tabs, is **not in the wiring plan** — new capability
rather than connecting built capability, so it stays parked. Two things, not
one: named persisted snapshots of filter state, and exposing source document
type onto the transaction row. **This interacts with a decision already
taken:** the financial page no longer persists which tab you were on.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Standing decisions, and what would reverse each one

**This section is not a queue of questions for Neil.** By standing instruction, a
session does not open by asking him to rule on things. Every entry below states
the direction the build takes by default, so a session can proceed without a
conversation. Each one also says exactly what evidence or instruction would
reverse it. Raise one with Neil only when the unit in front of you actually
turns on it, and then raise it oriented and with a recommendation.

**New: a read whose cost is set by a machine writer is bounded and reports its
own total; a read whose cost is set by the evidence is not.**
`transaction_query.list_transactions` is unbounded, and stays unbounded, because
its size is the size of the bank statements someone actually produced.
`decision_log.list_case_decisions` is bounded at 100 by default and 500 at the
cap, because `reclassify_document` is written by the reconciliation stage on
every pipeline run, so the log grows without any person deciding anything and the
cost of an unbounded read is set by how often the pipeline ran. Wherever a read
is bounded, `total` is returned beside the page and counted over the **same**
filters, because a truncated history that does not say it was truncated is worse
than no history. **What would reverse it:** a decision log that stops taking
machine writes, at which point its growth is bounded by human effort like the
ledger's is.

**New: a fact that can be derived from a stored field is derived, but it is
derived once, in the service, not by each caller.** `by_machine` on a decision
record is the actor address compared with `RECONCILIATION_ACTOR_EMAIL`. It is not
stored, because a second home for the same fact drifts. It is also not left to
callers, because a caller that gets the comparison wrong shows a machine's
reclassification as a person's judgement, which is the most misleading thing that
log can be made to say. The comparison is case-insensitive and **on equality**,
never `in` — an address that merely contains the machine's is not the machine's.
**What would reverse it:** more than one machine writer, at which point the
service needs a set of addresses rather than one, but still one place that knows
them.

**New: an ordering across subjects claims only what its columns can support.**
`subject_sequence` is per subject, so one subject's 3 is not comparable with
another's 1; Postgres `created_at` is transaction-start time, so events written
together share it exactly. So a cross-subject read orders by `created_at DESC`
then by subject then by `subject_sequence DESC`: newest first at the resolution
the timestamp actually has, authoritative within any one subject, and **total**,
so paging cannot show a row twice. The docstring states plainly that two events
about different subjects sharing a timestamp are **not** claimed to have happened
in the order shown. `decisions.history` carries the same warning from its own
history: an earlier draft ordered by `created_at` with an `id` tiebreak, and that
"looked authoritative and was a coin toss." **What would reverse it:** a
monotonic per-case sequence being added to the log, which would make a true
cross-subject order available for the first time.

**New: a list that differs from the ledger list by one column is a flag on
`LedgerTable`, not a table of its own.** Three of that table's seven cells are
correctness rather than presentation — the amount cell marks a figure it could
not scale rather than printing a plausible wrong one, the balance cell says a
running balance was absent rather than leaving a blank, and every closed
vocabulary renders an unrecognised member loudly rather than going empty. A
second table is a second copy of all three, and the copy is what drifts: not on
the day it is written, on the day one of the three is corrected in one place
only. So `showQuarantineGrounds` is a prop, off by default, and the general
ledger list is byte-for-byte unaffected. **What would reverse it:** a
status-specific list needing cells the general ledger list has no use for, at
which point the shared table is carrying a second layout rather than a second
column and the copy has become the cheaper of the two.

**New: a panel whose copy is only true of one population fixes that population
rather than defaulting it.** `QuarantinePanel` sets `ledger_status=quarantined`
and types its `params` so a caller cannot pass it. This is not defensiveness
about a prop: `LedgerPanel`'s empty state tells a reader that quarantined rows
are outside the filter and to change the filter to see them, which is the exact
reverse of what was checked when the filter *is* quarantine. A panel that can be
repointed is a panel whose every sentence can become false. **What would reverse
it:** a screen that genuinely needs one panel over two populations, which would
mean the copy had been made status-neutral first, and status-neutral copy is what
`LedgerPanel` already is.

**New: "a person decided this" and "a check established this" are three-valued,
and the third value is not "a check".** `readQuarantineGrounds` returns
`decidedByPerson: null` for a member this build cannot read, surfaced as
`data-decided-by-person="unknown"`. `false` is the more trusted of the two real
answers — it means the ledger's own arithmetic against the source document — and
a member arriving from a backend one version ahead has not earned it. Same
reasoning as the closed-vocabulary rule it sits on top of. **What would reverse
it:** nothing; this is the unrecognised-member rule applied to a derived fact,
and if it ever looks like noise the fix is to teach the build the member.

**New: a cache refetch is decided on the wider of the two "did the row move"
readings; what a person is told is decided on the narrower one.**
`useRowAdjudication` invalidates the ledger when `applied` is true **or** when
this build's reading of the outcome word says the row moved. The two cannot
disagree on a backend of the same version, and `readRowAdjudication` already
raises `appliedDisagreesWithOutcome` when they do — but a disagreement must not
be settled at the call site by picking a winner. The costs are not symmetrical:
refetching when nothing moved costs one request, while failing to refetch when
something did leaves a row on screen in a list it has left, and a person reads
that stale screen as the ledger's answer. **What is reported to a person about
whether the row moved still comes from `applied` alone**, which is the standing
rule and did not change. **What would reverse it:** the disagreement turning out
to be reachable in normal operation rather than only across versions, at which
point it needs handling rather than absorbing.

**New: the rescue sentence travels in the response and is not written into the
adjudication log.** `QuarantineBasis.from_adjudication` stores its detail as
`"<actor>: <reason>"`, so anything appended to the reason is read afterwards as
words the person wrote. A machine observation attributed to a person is the one
thing an evidence log must not contain, and that outweighs durability here.
**The cost is stated plainly: the fact is on screen at the moment of the decision
and does not survive in the record.** **What would reverse it:** a durable home
for the observation that is neither the person's reason nor the row's
`before`/`after` columns — a third field on the adjudication event, which is a
change to `quarantine_transaction` and a schema change, not a change to this call
site. Worth doing when item 8 touches the adjudication log anyway.

**New: the rescue check is asked of every quarantine, not only suspicious ones.**
Whether a removal is legitimate is not visible in the arithmetic — a row proved
wrong by the statement's own chain *should* come out and the period *should* then
balance. So the check cannot be used as a filter and is not one. **What would
reverse it:** nothing short of a demonstrated performance problem, and the check
is one pass over a period's admitted rows.

**New: the check runs before the write, inside the same `try`.** Afterwards the
residual has already moved, and recovering it would mean adding the row's own
effect back onto the new figure — a reconstruction rather than an observation,
and wrong the moment anything else about the period changed in between. Being
inside the same block means a database fault reading the period is handled by the
same clause as a fault writing the row. **What would reverse it:** nothing.

**New: reconciliation is a fourth financial router rather than a route on an
existing one.** Decided by reading the two neighbours' docstrings.
`routers/financial_ledger` states that every route resolves to `case:view`
because none of them writes; the recompute writes.
`routers/financial_adjudication` states that every route resolves to `case:edit`
because all of them do; the read does not. Either merge would make an existing
module's stated rule false. **What would reverse it:** a decision to let a router
carry mixed permissions and drop those docstring claims, which would be a
readability judgement rather than a correctness one and is not worth making now.

**New: the recompute requires `case:edit`, not `evidence:upload`.** Nothing is
added to the case — rows already in the ledger are summed and the answer is
written onto periods already in the ledger. That is the case's own content being
edited, which is the bar the adjudication routes already apply for the same kind
of change. **What would reverse it:** the same new adjudication permission
category that would reverse the adjudication decision below; they should move
together.

**New: the read reports the stored column and never recomputes.** So a period
that has never been checked comes back `not_attempted`, and re-running is an act
a person takes. **What would reverse it:** a demonstrated case where a stale
stored figure is worse than an unstable one. Note the asymmetry — the current
choice is recoverable by pressing a button, and the reverse is not recoverable at
all, because a figure that was quoted and then silently recomputed cannot be got
back.

**New: a refusal during a sweep leaves the stored verdict alone.** It is not
reset to `not_attempted`. **What would reverse it:** evidence that a stale
`balanced` on a period whose data has since become unreadable misleads someone in
practice. The counter-argument, and why the current direction was taken, is that
resetting throws away a real result on the strength of a transient failure.

**The adjudication endpoints require `case:edit`, not `evidence:upload`.**
Decided by reading `postgres/permissions.py`, which defines only
`case:{view,edit,delete}`, `collaborators:{invite,remove}` and
`evidence:upload`. Ingest asks for the evidence permission because it **adds
evidence** to the case. Nothing is added by quarantine or release; an existing
row is moved out of every total or moved back into them, which is the case's own
content being edited. **What would reverse it:** a new permission category for
adjudication, which would be reasonable if Owl ever wants a role that can load
evidence but not change what counts. That is a schema and seeding change, not a
one-line one, and nothing needs it today.

**Quarantine's write path was built before its screen.** Not a resequencing —
item 6 is still item 6 — but a decision about which half of it comes first, taken
because **nothing in production wrote `ledger_status='quarantined'`**, so a
screen built first would have listed an empty set forever. **What would reverse
it:** nothing; the write path is landed. Recorded so the order is not later
mistaken for an oversight.

**Correction storage: a correction inserts a replacement row, it does not edit
the row.** This is the direction for Phase 2 item 10, and item 11 of the old
numbering is unblocked by it. Researched on 5 September by reading the source.

- **The relational ledger has no correction columns at all.** Verified against
  `postgres/models/financial.py`: no `amount_corrected`, no `original_amount`,
  no `correction_reason`. What it has is supersession —
  `ledger_status IN ('admitted', 'quarantined', 'superseded', 'rejected')` with
  `superseded_by_id` on `FinancialTransaction` (line 807) and the same pair on
  `FinancialSourceDocument` (line 321). The model docstring at line 21 states
  the intended behaviour outright.
- **Corrections today happen only on the graph side**, in
  `services/neo4j/financial_service.py:599`, `update_transaction_amount`. That
  is edit-in-place, and it is the competing design. It is not wrong for the
  graph; `projection.py` lists those properties in `USER_OWNED_PROPERTIES` and
  refuses to write them, so a projection run cannot undo a person's work.
- **The citation reference decides it.** `references.py` computes the reference a
  report cites a row by from the row's content, deliberately, so a row whose
  figure changed gets a new one. Under supersession that falls out for free.
  Under edit-in-place the reference either changes underneath a report that
  already cited it, or is frozen and then names a figure it was not computed
  from. `ref_id` also carries `UniqueConstraint("case_id", "ref_id")`, so the
  two designs collide rather than merely differ.
- **The cost, stated honestly:** two rows exist for one corrected transaction,
  and every reader of the ledger has to be status-aware. The ledger endpoint
  already defaults to `admitted`, so existing readers are correct by default;
  new ones are the risk.
- **What would reverse it:** an instruction from Neil, or a downstream unit that
  genuinely cannot work across a supersession pair. The graph's edit-in-place
  path is not evidence against it — the graph is not the ledger.

**Whether a correction re-runs the arithmetic: still not decided, and it is now
one item away from being decidable.** The proposal is that a correction re-runs
the balance identity and only a re-run that closes moves the proof class. It has
support in the source: `adjudication.py`'s `restated_opening` (line 332) and
`restatement_delta` (line 357). It is consistent with the settled rule that proof
class is computed and never set by hand. **But it makes a correction an event
that can change how much of a document is trusted, not a local edit.**
Reconciliation is now built, so half the machinery exists and
`reconcile_case(db, case_id, account_id=...)` is the call a correction would
make. **Proof class (item 8) still lands before the correction unit. Decide it
then, from the built code.**

**Removing `reingest` stands.** The override could not succeed for unchanged
bytes, and where it could succeed it would leave two contradictory readings of
one file in one case with nothing able to resolve them until `duplicates.py` is
wired at Phase 2 item 9. **Reversible at any time and cheap to reverse** — item
9 is the natural moment to revisit it.

**Content-hash de-duplication stays call-scoped.** `document_content_hashes`
disambiguates duplicate content within one `record_transactions()` call and not
across two calls. **What would reverse it:** an override existing. If `reingest`
comes back, this has to be answered in the same session, not after.

**The engagement period stays off the case.** The dialog asks for the window
every time. If a case ever grows a date range, the dialog **defaults from it and
keeps asking** rather than stopping, because a file can legitimately fall
outside the engagement period and the reader has to be able to say so.

**`exhibit.py` stays in the plan at Phase 4 item 15.** Its provenance is a
proposed build order rather than a stated Owl requirement, and that is recorded
so nobody later mistakes it for a requirement Neil gave.

**The financial page will say nothing about the two stores disagreeing until
Phase 3 item 12.** Explaining a disagreement before the thing that removes it is
built means shipping an explanation with a short life. **What would reverse
it:** a real case where the two visibly disagree in front of an investigator
before item 12 lands.

---

## Standing flags

- **Phase 1 is closed: a bank file can be sent to the ledger from seven places
  and the rows it creates are now visible.**
- **The balance identity now runs, but only through the API.** Nothing in the
  interface calls either reconciliation endpoint yet, and **nothing calls the
  recompute automatically** — not ingestion, not adjudication. So on a live case
  every period stays `not_attempted` until somebody POSTs to
  `/api/financial/reconciliation/run`. **That is deliberate for this unit** (the
  recompute is an act a person takes) **but it means the read will report
  `not_attempted` everywhere until a caller exists.** Do not read that as a
  defect in the arithmetic.
- **Whether ingestion should trigger a sweep at the end of a run is not
  decided and was not decided here.** It is the obvious next caller, and item 8
  (proof class) is the unit that will actually need one. Flagged, not parked.
- **The adjudication log is readable over HTTP, the frontend has a call for it
  and words for it, and no screen shows it.** Narrowed at `2eefc4d`, at
  `0fa07d5`, and again at `71d859d`, **not cleared.**
  `decision_log.list_case_decisions` landed at `a40bb61`,
  `GET /api/financial/decisions` at `2eefc4d`, `financialAPI.getCaseDecisions`
  at `0fa07d5`, and `lib/decision-format.ts` at `71d859d`, all tested, and the
  route is confirmed mounted. **Two lines this flag used to carry — "nothing in
  `frontend_v2` calls that path" and "no format module" — are now false and have
  been removed.** What is still missing is the hook, the panel and the tab. So on
  a live case the history remains invisible to the person using the product, even
  though every layer beneath the component now exists. **This flag clears when a
  panel renders it, not before.** Until then, do not describe the history as
  something anybody can see — "reachable", "callable", "readable" and "visible"
  are four different claims and only the first three are true.
- **The quarantine screen is reachable as of `e64c2ca`, and this flag is
  cleared.** It read, for four commits, that every part existed and none of it
  was reachable. That is no longer true: the "Held out" tab is in the tab strip,
  `QuarantinePanel` renders under it, every ledger row carries an action button,
  and `RowAdjudicationDialog` is mounted on the page and opened by it. The two
  calls, the reader, the hook, the dialog and the grounds column are all wired
  end to end. **What remains true and still worth stating: the ledger tab's own
  totals exclude quarantined rows.** That is the point of quarantine, but it
  means the held-out tab is the only place the excluded population is visible,
  and nothing on the ledger tab says a total is net of anything.
- **The write path reports when a quarantine is what makes a statement balance,
  and as of `66d1e67` something finally renders it.** The fact is deliberately
  not stored in the log, so if it is not on screen at the moment of the decision
  it is not anywhere. `readRescueOutcome` gives all four readings words,
  `readRowAdjudication` composes it in so a caller cannot read the outcome and
  quietly drop it, `useRowAdjudication` hands the composed reading back on both
  `data` and the `mutateAsync` promise, and `RowAdjudicationDialog` renders it
  whenever the reading has anything to say. **This is closed as a gap, and it
  converts into the keep-mounted rule:** the only copy of the fact lives in the
  dialog's mutation, so a caller that unmounts the dialog when the row leaves the
  list destroys it. **`e64c2ca` is the commit that had to honour that, and does:**
  the dialog is mounted on `FinancialPage` outside `Tabs`, not inside either
  panel, so an invalidation that empties the list the row came from cannot take
  the answer with it. Two tests hold it, one per panel. Anything that later moves
  the mount point back inside a panel breaks this silently.
- **`QuarantineBasis.from_proof` is still unreachable from HTTP,** by design —
  computed grounds must not be settable by a person. So on a live case every
  quarantined row's reason reads `adjudicated`, and the second value in that
  column arrives with item 8. **Do not read the single value as evidence the
  distinction is not implemented** — the grounds column, its `decidedByPerson`
  classification and the tests over all five members are all built and, as of
  `e64c2ca`, on screen; there is simply only one member a live case can currently
  produce. **Item 8 is what will produce the second one**, which is one reason it
  is the next unit.
- **`localisation.py` has no production caller except `_rescue`.**
  `localise_period` and `current_identity` are reachable and tested but nothing
  in the product asks them anything yet. Item 8 is the expected first caller.
- **The Neo4j financial view is not a projection of the ledger.**
  `projection.py` has zero production callers. The two stores can disagree and
  nothing detects it. Phase 3 item 12 closes this. **Do not describe the graph
  as derived from the ledger until it is.** Note that quarantining a row and
  reconciling a period both change the ledger and **do not** touch the graph, so
  this gap now has two more ways to show itself.
- **A run whose process died is now closed, but only by the loop.** Six hours
  stale, five minute interval. **Until it fires, a dead run and a live one are
  indistinguishable through the API**, deliberately: the read declines to guess.
  The threshold is a knob (`FINANCIAL_RUN_STALE_AFTER_HOURS`).
- **The notice is only on the ledger tab, and the attempts list only on its
  own.** Deliberate for now, because the other three tabs read the graph, but it
  stops being defensible at Phase 3 item 12. **Revisit the mounting then.**
- **Nothing on screen explains that the tab strip spans two stores.** Deliberate
  and already ruled. Listed only so it is not rediscovered as an oversight.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. So on real data **every** row will show "No running balance".
  That is the component working, not failing. **This bears directly on
  reconciliation:** a period whose balances are absent reconciles `unavailable`,
  not `unbalanced`, and on the current corpus that will be the common answer.
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no Postgres.
  First deployment needs an `alembic upgrade head` on Neil's side.
- **Disk: `/sessions` is completely full and this is the first thing to check
  every session.** Measured again at `2eefc4d`: 9.8G of 9.8G, **zero bytes
  available** — unchanged for ten sessions, against 129M eleven sessions ago.
  Root is at 99% with 120M free. `/dev/shm` is 2.0G, showing 1.5G free *after*
  this session's 463M of installed packages, so budget for roughly 1.5G of
  genuinely free space at the start. This is a steady state rather than something
  still getting worse.
  - **This does not block the repo, and an older wording implied it did.**
    `df -h` on the repo path shows a **separate virtiofs mount with 35G free**
    (36G at `e64c2ca`, 37G at `19bffae`; it drifts a little and is nowhere near
    tight). The working tree writes normally and the **frontend gates run
    normally**, provided the vite cache goes to `/dev/shm` rather than
    `CLAUDE.md`'s `/tmp`, which is on the 99%-full root.
  - **The backend suite is runnable** via the `/dev/shm` bootstrap recorded
    above, and that workaround was exercised in full at this head: bootstrap,
    baseline, and two complete suite runs, all clean. It is reliable. A session
    that touches Python must still budget the twenty seconds for the bootstrap
    rather than assuming a warm environment — **`/dev/shm` does not survive
    between sessions**, so it is a fresh install every time.
  - **The browser gate is not runnable and will not become runnable.** Chromium
    needs roughly 700M to install and there is nowhere to put it: `/dev/shm` is
    2.0G but is RAM, and spending most of it on browser binaries to run four
    tests is not a good trade. **Say plainly that the gate could not run** rather
    than repeating a previous session's figure.
  - **None of this is Loupe's doing and no session can clear it.** The space is
    held by other session directories that are not readable or removable from
    inside a session. **This needs Neil to reclaim space on his side**, and
    until he does, every session starts by working around it.
  - The repo mount has room but is Neil's tree, and the workspace denies
    `unlink`, so anything staged there could not be removed. **Do not use it as
    scratch.** Use `/dev/shm`.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **`reconcile_period` mutates the period before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which can raise
  `LedgerOverflowError`, leaving a half-written verdict in the session.
  `reconcile_case` defends against it with `session.expire(period)` and there is
  a named test for the path, **so nothing is broken today** — but the ordering is
  a trap for the next caller, and the next caller is item 8. **Direction: swap
  the order inside `reconcile_period` when item 8 touches it**, rather than
  making every caller remember to expire.
- **`docs/loupe-wiring-plan.md`'s premise for item 6 is wrong.** It says
  quarantined rows are written today and never shown. Nothing in production ever
  wrote one. **And item 7's premise was wrong in the same way** — the plan
  treats reconciliation as something that runs and needs surfacing, when
  `reconcile_period` had no reachable production caller at all. The plan text is
  left in place as history. **Do not build from those sentences.** Assume other
  items carry the same kind of error: the plan describes intent, and the source
  is what is true.
- **The graph's correction path takes the new amount as a `float`.**
  `services/neo4j/financial_service.py:599`. The ledger side handles money
  exactly through `Money`, so a corrected figure entered on the graph and a
  total computed from the ledger can disagree at the cent. **Direction: fix it
  as part of Phase 2 item 10.** If anything starts relying on graph corrections
  before then, fix it immediately instead.
- **`IngestionRunHandle.terminate()` does not check the row's stored status.** A
  run the reaper closed as `failed` that then turns out to be alive and finishes
  will overwrite the status with `completed` **while leaving the reaper's
  abandonment text in `run.error`.** **If the six-hour threshold is ever
  lowered, fix this first.**
- **`evidence:process` and `evidence:delete` are asked for by routers and are
  not defined in `postgres/permissions.py`.** Whether those routes are
  therefore open, closed, or handled elsewhere was not established, and it
  should be before anyone relies on them.
- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against list
  paging at 250.
- 11 Capital One pages carry a full-page white image XObject, most likely
  whole-page redaction.
- `merging_properties` missing from `_ACTIVE_JOB_STATUSES`, plus a silent
  fall-through in `_sync_db_record_from_job`.
- `safe_float` does `round(f, 2)` and defaults to `0`.
- The `7d8289b` commit message understates what the commit did.
- Append-only is not enforced at the database.
- The p3 early-return limitation.
- `_get_dataset_metadata` uses all-or-nothing legacy detection.
- `execute_cypher_batch` takes unparameterised strings.
- `get_financial_transactions` compares `n.date` as a string.
- `RECOMMENDED_CONSTRAINTS` and `RECOMMENDED_INDEXES` need out-of-band
  application.
- Two defects in the mutation harness.
- `scripts/categorize_transactions.py:443` hardcodes `national telegraph`.
- `ProcessConfirmDialog.tsx` contains dead code.
- `frontend_v2/node_modules/.__dom_probe_leftover` left behind.
- The engine docstring in `evidence-engine/app/pipeline/pdf_extraction.py` claims
  table text is byte-identical to the pre-geometry path; false whenever the
  recovery pass replaces a `table_rectangle_only` reading.
- Recovered text-alignment chunks collapse empty cells in the `" | "` join and
  sweep footer prose into the table chunk. Geometry unaffected; full diagnosis
  in the `72d1b1a` revision of this file.
- **`docs/loupe-wiring-plan.md` lines 117–123 are superseded** by the work and by
  two rulings. Left in place as history; do not act on them.
- **The wiring plan names `_cleanup_stale_chunks` as the loop shape to copy.**
  It is the wrong precedent (no error handling); `poll_forever` is the right one.
