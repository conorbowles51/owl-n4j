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

Each event retains its source table, row identity, database transaction, UTC capture
time, operation, before/after state, recorded actor and reason when present. A run's
initiator is explicitly distinguished from whoever caused a later status update.
Private run configuration, errors and notes are hashed together instead of copied
into exported text. Source records can have no recorded actor; the database role
is retained separately and is not presented as an investigator's identity.

The hash is SHA-256 of the previous hash decoded to32bytes followed by the exact
UTF-8 payload text. The initial previous hash is32zero bytes. Exact text is retained
because reformatting JSON can change its bytes. A transaction-level advisory lock
serializes each case's appends; transaction rollback removes both source changes
and the corresponding events. PostgreSQL rejects ordinary update, delete, truncate
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

This is not yet the full audit spine in the original specification. Evidence intake,
all raw state changes/deletions, entity merges, Workspace activity, export events,
and external RFC3161 timestamp anchoring are not covered. Internally consistent
hashes alone cannot detect replacement of the whole chain or removal of its tail.
Older decisions/reviews retain their existing history separately and are not
retroactively authenticated by this mechanism.

Repeatable synthetic PostgreSQL acceptance:
`scripts/check_local_financial_audit_chain.py` creates and removes an isolated
schema, checks all trigger targets, concurrency, atomic rollback and mutation
guards without editing existing cases. The source-bound simulated nomination
acceptance in `scripts/check_local_pdf_model_nomination_flow.py` additionally checks
three audit events and rolls back its entire transaction.
