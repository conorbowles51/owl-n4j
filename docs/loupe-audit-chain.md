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


## Offline timestamp checkpoint support

Prepare a request from an export containing wider case history:

```sh
data/local-runtime/backend-venv/bin/python scripts/financial_audit_timestamp.py \
  --openssl /opt/homebrew/opt/openssl@3/bin/openssl prepare saved-ledger.zip \
  --output new-timestamp-request
```

The new directory retains `checkpoint.json` and `request.tsq`. The checkpoint binds
case identity, event count, chain head, snapshot digest and exact ZIP digest. Only
the opaque imprint and nonce are in the timestamp request. This command does not
contact a timestamp authority. Retain the original ZIP and request directory.

After obtaining a response from an authority selected through your own trust process:

```sh
data/local-runtime/backend-venv/bin/python scripts/financial_audit_timestamp.py \
  --openssl /opt/homebrew/opt/openssl@3/bin/openssl verify saved-ledger.zip \
  --request new-timestamp-request --response authority-response.tsr \
  --ca-file trusted-roots.pem --output new-timestamp-verification.json
```

Optional `--untrusted intermediates.pem` supplies intermediate certificates, not
additional trusted roots. Verification uses explicit supplied roots and empty
fallback trust locations. It checks both the original nonce-bearing query and the
reconstructed checkpoint data. A replacement query/response for different data
cannot pass merely because its signature is valid. All outputs must be new.

The retained result includes input hashes, OpenSSL version and response details.
It establishes verification against the supplied trust, not authority independence,
current revocation status, complete custody or evidence truth. Public-service interoperability on a synthetic checkpoint is now verified as
recorded below. No production case anchoring schedule is configured.
The repeatable `scripts/check_financial_audit_timestamp.py saved-ledger.zip` uses
only a temporary synthetic root/signer and deletes its private keys afterward.

Protocol implementation reference: [OpenSSL timestamp utility documentation](https://docs.openssl.org/3.0/man1/openssl-ts/).


## Public TSA interoperability — 10 September 2026

A single synthetic-only request to the published DigiCert RFC3161 endpoint returned
a signed response that passes the application verifier: signature chain, nonce and
checkpoint data imprint. The request was70bytes; response6008bytes. The signed time
is10September2026 at20:48:24GMT, policy2.16.840.1.114412.7.1. OpenSSL3.6.1 performed
the verification. No actual case archive, source PDF or financial record was sent.

The trust anchor was downloaded over HTTPS from DigiCert's root directory and its
DER SHA-256 checked against the published fingerprint:
`552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988`.
The timestamp article's similarly named certificate is cross-signed, so it was
correctly refused against that pin before any request was sent. The subsequent
request used the matching self-signed root and the published intermediate.

Reference: [DigiCert timestamp instructions](https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server)
and [published root fingerprints](https://knowledge.digicert.com/general-information/digicert-trusted-root-authority-certificates).

The opt-in acceptance script accepts no case-file input:

```sh
data/local-runtime/backend-venv/bin/python scripts/check_public_financial_timestamp.py \
  --submit-synthetic --output new-synthetic-timestamp-check
```

Without the explicit flag it exits before creating artifacts or making a request.
The retained local acceptance artifacts are in
`data/local-runtime/public-timestamp-check-20260910-v2`. They include the synthetic
archive, exact request, signed response, downloaded certificates and verification.
This tests real service interoperability, not qualified timestamp status, current
revocation checking, production trust policy or periodic anchoring of case events.
