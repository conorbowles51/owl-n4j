"""Daily outside time-stamp of each case's audit chain head (RFC 3161).

For each case the whole recorded audit chain is read from the database in sequence and checked event by event
(services/financial/audit_chain.AuditChainVerifier), without holding it in memory, so no case is too large. The
checkpoint is a small JSON document: case, number of events and the hash of the last event (the head). Only that
checkpoint's SHA-256 fingerprint leaves the server, inside an RFC 3161 request to the time-stamping authority; the
signed answer is kept beside the checkpoint, the exact request and the trusted root, and verified offline at once.

What a stamp shows: the case's audit chain, up to that event with that head, existed no later than the stamped
time. A later reader re-reads events 1..N, gets the same head, and checks the stamp (verify_audit_head). A chain whose
earlier stamped head is no longer an ancestor of the current chain is reported, never stamped over.

Kept per case under ``<output>/<case_id>/``: one folder per stamp, and ``latest.json`` naming the newest verified one.
A day with no new events makes no request.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.financial_audit import FinancialAuditEvent
from services.financial.audit_chain import AuditChainVerifier
from services.financial.audit_timestamp import MAX_RESPONSE_BYTES, _read, _run, _trust_directory
from services.financial.ledger_summary import LedgerSummaryError

SCHEMA = "loupe.financial.audit_head_checkpoint/1"
LIMITATION = ("Shows that this case's audit chain, up to the stated event with the stated head, existed no later "
              "than the signed time. It does not show that the events are true, complete before the audit "
              "migrations, or that the authority is independent of anyone in the case.")


def _json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _save(path: Path, value) -> None:
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    with temporary.open("xb") as target:
        target.write(_json(value))
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def read_head(engine, case_id, *, hash_at: int | None = None, stop_at: int | None = None) -> dict:
    """Stream the case's chain in one read-only snapshot. ``hash_at``: also return the head after that event;
    ``stop_at``: stop after that event (to recompute a stamped head)."""
    case_id = str(UUID(str(case_id)))
    verifier = AuditChainVerifier(case_id)
    at = None
    postgres = engine.dialect.name == "postgresql"
    with engine.connect().execution_options(**({"isolation_level": "REPEATABLE READ"} if postgres else {})) \
            as connection:
        with connection.begin():
            if postgres:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            with Session(bind=connection, autoflush=False) as session:
                query = (select(FinancialAuditEvent.sequence, FinancialAuditEvent.previous_sha256,
                                FinancialAuditEvent.entry_sha256, FinancialAuditEvent.payload_text)
                         .where(FinancialAuditEvent.case_id == UUID(case_id)).order_by(FinancialAuditEvent.sequence))
                if stop_at is not None:
                    query = query.where(FinancialAuditEvent.sequence <= stop_at)
                for row in session.execute(query.execution_options(yield_per=500)):
                    verifier.add(dict(sequence=row.sequence, previous_sha256=row.previous_sha256,
                                      entry_sha256=row.entry_sha256, payload_text=row.payload_text))
                    if hash_at is not None and verifier.count == hash_at:
                        at = verifier.previous
    return dict(case_id=case_id, event_count=verifier.count, head_sha256=verifier.previous, hash_at=at)


def checkpoint_bytes(case_id, event_count, head_sha256) -> bytes:
    return _json(dict(schema_version=SCHEMA, case_id=str(case_id), event_count=event_count,
                      head_sha256=head_sha256, limitation=LIMITATION))


def _check_endpoint(tsa_url):
    endpoint = urlsplit(tsa_url)
    if endpoint.scheme not in ("http", "https") or not endpoint.hostname or endpoint.username \
            or endpoint.password or endpoint.fragment:
        raise ValueError("Choose an HTTP(S) time-stamping endpoint without credentials or a fragment.")
    return f"{endpoint.scheme}://{endpoint.hostname}"


def _post(tsa_url, query: bytes) -> bytes:
    import httpx
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        with client.stream("POST", tsa_url, content=query, headers={
                "Content-Type": "application/timestamp-query", "Accept": "application/timestamp-reply"}) as response:
            response.raise_for_status()
            if response.headers.get("content-type", "").split(";")[0] != "application/timestamp-reply":
                raise ValueError("Unexpected time-stamp response type.")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("Time-stamp response exceeds its byte limit.")
                chunks.append(chunk)
    return b"".join(chunks)


def verify_stamp(directory: Path, *, openssl="openssl") -> dict:
    """Offline: the signed answer matches the request and the checkpoint, under the root kept beside them."""
    import tempfile
    directory = Path(directory)
    names = ("checkpoint.json", "request.tsq", "response.tsr", "roots.pem")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        _trust_directory(work)
        for name in names:
            (work / name).write_bytes(_read(directory / name))
        common = ["ts", "-verify", "-in", work / "response.tsr", "-CAfile", work / "roots.pem",
                  "-CApath", work / "empty-trust", "-CAstore", work / "empty-trust"]
        _run(openssl, common + ["-queryfile", work / "request.tsq"], work)
        _run(openssl, common + ["-data", work / "checkpoint.json"], work)
        detail = _run(openssl, ["ts", "-reply", "-in", work / "response.tsr", "-text"], work)
    stamped = next((line.split(":", 1)[1].strip() for line in detail.splitlines()
                    if line.startswith("Time stamp:")), None)
    return dict(status="verified", stamped_at=stamped,
                checkpoint_sha256=hashlib.sha256(_read(directory / "checkpoint.json")).hexdigest())


def anchor_audit_head(engine, case_id, *, output, tsa_url, ca_file, openssl="openssl") -> dict:
    """One case: stamp its current head if it has new events. Never raises for a case's own problem: the
    answer's status says what happened (timestamp_verified, unchanged_verified_head, no_recorded_events,
    already_running, attention_required with the reason)."""
    case_id = str(UUID(str(case_id)))
    origin = _check_endpoint(tsa_url)
    roots = _read(ca_file)
    folder = Path(output) / case_id
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / "runner.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return dict(case_id=case_id, status="already_running")
        latest = folder / "latest.json"
        previous = json.loads(_read(latest)) if latest.exists() else None
        try:
            head = read_head(engine, case_id, hash_at=previous["event_count"] if previous else None)
        except LedgerSummaryError as error:
            return dict(case_id=case_id, status="attention_required", reason=f"Audit chain did not verify: {error}")
        if previous is not None:
            if head["event_count"] < previous["event_count"] or head["hash_at"] != previous["head_sha256"]:
                return dict(case_id=case_id, status="attention_required",
                            reason="The current audit chain does not extend the last stamped head. Nothing was "
                                   "stamped; this needs investigation.",
                            stamped_event_count=previous["event_count"], event_count=head["event_count"])
            if head["head_sha256"] == previous["head_sha256"]:
                return dict(case_id=case_id, status="unchanged_verified_head", event_count=head["event_count"])
        if head["event_count"] == 0:
            return dict(case_id=case_id, status="no_recorded_events", event_count=0)
        attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        directory = folder / attempt
        directory.mkdir(mode=0o700)
        content = checkpoint_bytes(case_id, head["event_count"], head["head_sha256"])
        (directory / "checkpoint.json").write_bytes(content)
        (directory / "roots.pem").write_bytes(roots)
        journal = dict(status="request_prepared", endpoint_origin=origin,
                       endpoint_sha256=hashlib.sha256(tsa_url.encode()).hexdigest(),
                       checkpoint_sha256=hashlib.sha256(content).hexdigest())
        _save(directory / "submission.json", journal)
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary)
                _trust_directory(work)
                _run(openssl, ["x509", "-in", directory / "roots.pem", "-noout"], work)
                _run(openssl, ["ts", "-query", "-data", directory / "checkpoint.json", "-sha256", "-cert",
                               "-out", directory / "request.tsq"], work)
            journal["status"] = "submission_started"
            _save(directory / "submission.json", journal)
            (directory / "response.tsr").write_bytes(_post(tsa_url, _read(directory / "request.tsq", 8192)))
            journal["status"] = "response_received_unverified"
            _save(directory / "submission.json", journal)
            verified = verify_stamp(directory, openssl=openssl)
        except Exception as error:  # noqa: BLE001 - one case's failure is reported, the others still run
            journal.update(status="failed", failure_type=type(error).__name__, failure=str(error)[:500])
            _save(directory / "submission.json", journal)
            return dict(case_id=case_id, status="attention_required", attempt=attempt,
                        reason=f"Not stamped: {type(error).__name__}: {str(error)[:200]}")
        journal["status"] = "verified"
        _save(directory / "submission.json", journal)
        _save(directory / "verification.json", verified)
        _save(latest, dict(attempt=attempt, case_id=case_id, event_count=head["event_count"],
                           head_sha256=head["head_sha256"], stamped_at=verified["stamped_at"]))
        return dict(case_id=case_id, status="timestamp_verified", attempt=attempt, event_count=head["event_count"],
                    head_sha256=head["head_sha256"], stamped_at=verified["stamped_at"])


def verify_audit_head(engine, case_id, *, output, openssl="openssl") -> dict:
    """The newest stamp of a case: offline signature check, and its head recomputed from the database now."""
    case_id = str(UUID(str(case_id)))
    folder = Path(output) / case_id
    latest = json.loads(_read(folder / "latest.json"))
    directory = folder / latest["attempt"]
    stamp = json.loads(_read(directory / "checkpoint.json"))
    verified = verify_stamp(directory, openssl=openssl)
    now = read_head(engine, case_id, stop_at=stamp["event_count"])
    if now["event_count"] != stamp["event_count"] or now["head_sha256"] != stamp["head_sha256"]:
        return dict(case_id=case_id, status="mismatch", stamped=stamp, recomputed=now)
    return dict(case_id=case_id, status="verified", event_count=stamp["event_count"],
                head_sha256=stamp["head_sha256"], stamped_at=verified["stamped_at"], attempt=latest["attempt"])
