# Recorded financial audit chain

New recorded decisions and PDF review events are linked in a per-case SHA-256
chain from migration `20260910_financial_audit_chain` onward. This is a prospective
record, not a reconstruction of events that occurred before installation.

| Source | Recorded operations |
| --- | --- |
| Financial adjudications | Insert |
| PDF mappings, review decisions and finalization receipts | Insert |
| Model nomination attempts | Insert and update |
| Financial ingestion runs | Insert and update |
| Ledger transactions, accounts, periods and source documents | Insert, update and delete |
| Statement review drafts | Insert, update and delete |
| Evidence file registration | Insert, update and delete |
| Workspace entries and links | Insert, update and delete |
| Workspace revisions and events | Insert |
| Prepared document text and table geometry | Insert, update and delete |
| Server ledger ZIP and tracing support ZIP | Export prepared |
| UUID-scoped engine jobs | Insert, meaningful update and delete |
| Merge jobs, graph recovery items and merge rejections | Insert, update and delete |

The additional state targets begin at migration `20260910_audit_state_changes`;
they are not backfilled. Source replacement and export preparation begin at
`20260910_audit_source_exports`. The captured policy is retained in new event payloads.
Processing/merge/recovery records begin at `20260910_audit_graph_jobs`. Engine
legacy non-UUID case labels are outside relational-case scope, and progress-only
job updates are omitted. Private execution/recovery bodies are represented by a
digest. A recorded job or recovery state does not prove that PostgreSQL and Neo4j
committed atomically or establish the actual graph contents.

Text bodies and geometry payloads are represented by hashes; they are not copied
into audit exports. Cascading file deletion retains the child-source events.
Truncation of tracked tables is refused because it would bypass row history.
In-place case ownership changes on tracked rows are refused so a before-state
cannot silently be written into a different case's chain.

Each event retains its source table, row identity, database transaction, UTC capture
time, operation, before/after state, recorded actor and reason when present. A run's
initiator is explicitly distinguished from whoever caused a later status update.
Private run configuration/errors/notes and evidence storage paths/profile metadata/
document text/error details are hashed instead of copied
into exported text. Source records can have no recorded actor; the database role
is retained separately and is not presented as an investigator's identity.

The hash is SHA-256 of the previous hash decoded to32bytes followed by the exact
UTF-8 payload text. The initial previous hash is32zero bytes. Exact text is retained
because reformatting JSON can change its bytes. A transaction-level advisory lock
serializes each case's appends; transaction rollback removes both source changes
and the corresponding events. Successful shared case authorization sets transaction-local
user attribution, scoped to that case and restored after commits in the same request.
It is cleared before a pooled connection is reused; it does not infer a human actor
for background changes. PostgreSQL rejects ordinary update, delete, truncate
and inconsistent append attempts. A database owner can disable these controls.
Concurrent transactions that take other row locks in conflicting order can still
be aborted by PostgreSQL's ordinary deadlock protection; no failed transaction is
reported as committed by this mechanism.

Select **Include wider case financial review history** in the ledger export.
The export verifies the entire available chain within10,000events/64MiB; overall
snapshot/report limits still apply. It refuses an oversized or broken history
rather than supplying a partial chain. The PDF/HTML includes its count and head;
exact events are in `case_financial_history.audit_chain` in the snapshot JSON.
The chain is separate from financial totals and can include events outside filters.

Offline verification, from the project root:

```sh
data/local-runtime/backend-venv/bin/python scripts/verify_financial_audit_export.py \
  saved-ledger.zip --output new-verification.json
```

Optionally pass `--expected-head` with the64-character hash retained independently
at capture time. A head copied from the same untrusted archive adds no independent
assurance. Verification checks every declared ZIP member first. Outputs must be new
files. Nothing is sent to a provider or written to the case database.

Server ZIP preparation records its exact bytes, scope and authenticated requester
before the response is returned. If this fails, the archive is withheld. The event
is `EXPORT_PREPARED`, with `prepared_not_delivery_confirmed`: it cannot establish
that someone received or saved the download. `X-Loupe-Export-Id`,
`X-Loupe-Export-Event-Sha256` and `X-Loupe-Export-Event-Sequence` identify the receipt.
It follows the snapshot capture and therefore appears in subsequent audit history,
not inside the archive that caused it. These receipt headers are not a checkpoint
for that archive's earlier chain head. Offline artifact generation does not append
a server event.

This is not yet the full audit spine in the original specification. Historical custody, atomic cross-database graph commits and external RFC3161
timestamp anchoring remain outside this coverage. Recorded merge/recovery states
are retained with the limitations above. Internally consistent
hashes alone cannot detect replacement of the whole chain or removal of its tail.
Older decisions/reviews retain their existing history separately and are not
retroactively authenticated by this mechanism.

Repeatable synthetic PostgreSQL acceptance:
`scripts/check_local_financial_audit_chain.py` creates and removes an isolated
schema, checks all16trigger targets, case-bound request attribution across commits,
concurrency, atomic rollback and mutation
guards without editing existing cases. The source-bound simulated nomination
acceptance in `scripts/check_local_pdf_model_nomination_flow.py` additionally checks
three audit events and rolls back its entire transaction.
