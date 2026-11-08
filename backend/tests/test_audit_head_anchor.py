"""Daily outside time-stamp of each case's audit chain head (Neil 8 Nov agreed: switch it on).

The existing anchor stamped a full ledger export, which 7 of 25 live cases refuse (ledger summary unavailable) and
whose chain capture refuses the largest case (268,881 events, over the export limit): those cases could never be
stamped. This one streams the chain and stamps its head, so every case is. A local authority made with openssl
signs the answers; nothing leaves the test.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.financial_audit import FinancialAuditEvent
from services.financial import audit_head_anchor as anchor


def _ssl(*args, cwd):
    subprocess.run(["openssl", *map(str, args)], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def tsa(tmp_path, monkeypatch):
    """A root, a time-stamping signer under it, and a _post that answers like an authority."""
    d = tmp_path / "tsa"
    d.mkdir()
    _ssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Test Root", "-keyout", "root.key",
         "-out", "root.pem", "-days", "2", "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign", cwd=d)
    _ssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Test TSA", "-keyout", "tsa.key", "-out", "tsa.csr",
         cwd=d)
    (d / "ext.cnf").write_text("extendedKeyUsage=critical,timeStamping\nkeyUsage=critical,digitalSignature\n")
    _ssl("x509", "-req", "-in", "tsa.csr", "-CA", "root.pem", "-CAkey", "root.key", "-CAcreateserial",
         "-out", "tsa.pem", "-days", "2", "-extfile", "ext.cnf", cwd=d)
    (d / "serial").write_text("01\n")
    (d / "tsa.cnf").write_text(f"""[ tsa ]
default_tsa = t
[ t ]
serial = {d}/serial
signer_cert = {d}/tsa.pem
certs = {d}/tsa.pem
signer_key = {d}/tsa.key
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256
accuracy = secs:1
ordering = no
tsa_name = no
ess_cert_id_chain = no
ess_cert_id_alg = sha256
""")
    sent = []

    def post(url, query):
        sent.append(query)
        (d / "q.tsq").write_bytes(query)
        _ssl("ts", "-reply", "-config", "tsa.cnf", "-queryfile", "q.tsq", "-out", "r.tsr", cwd=d)
        return (d / "r.tsr").read_bytes()
    monkeypatch.setattr(anchor, "_post", post)
    return SimpleTSA(d / "root.pem", sent)


class SimpleTSA:
    def __init__(self, root, sent):
        self.root, self.sent = root, sent


@pytest.fixture()
def engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[FinancialAuditEvent.__table__])
    return engine


def _append(engine, case_id, n, start=1, previous="0" * 64, operation="INSERT"):
    with Session(engine) as session:
        for sequence in range(start, start + n):
            payload = json.dumps(dict(schema_version="loupe.financial.audit_event/1", case_id=str(case_id),
                sequence=sequence, source_table="evidence_transcript_state", operation=operation),
                sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(bytes.fromhex(previous) + payload.encode()).hexdigest()
            session.add(FinancialAuditEvent(case_id=case_id, sequence=sequence, previous_sha256=previous,
                                            entry_sha256=digest, payload_text=payload,
                                            **_required(FinancialAuditEvent)))
            previous = digest
        session.commit()
    return previous


def _required(model):
    """Columns this test does not care about but the table needs."""
    extra = {}
    for column in model.__table__.columns:
        if column.name in ("case_id", "sequence", "previous_sha256", "entry_sha256", "payload_text"):
            continue
        if not column.nullable and column.default is None and column.server_default is None \
                and not column.primary_key:
            extra[column.key] = "x"
    return extra


def _stamp(engine, case_id, tmp_path, tsa):
    return anchor.anchor_audit_head(engine, case_id, output=tmp_path / "out", tsa_url="http://tsa.test/",
                              ca_file=tsa.root)


def test_a_case_is_stamped_and_the_stamp_verifies_against_the_database(engine, tmp_path, tsa):
    case = uuid4()
    head = _append(engine, case, 5)
    out = _stamp(engine, case, tmp_path, tsa)
    assert out["status"] == "timestamp_verified" and out["event_count"] == 5 and out["head_sha256"] == head
    assert out["stamped_at"]
    # Only the request leaves: its imprint is the checkpoint's SHA-256, nothing else of the case.
    folder = tmp_path / "out" / str(case) / out["attempt"]
    imprint = hashlib.sha256((folder / "checkpoint.json").read_bytes()).hexdigest()
    request_text = subprocess.run(["openssl", "ts", "-query", "-in", folder / "request.tsq", "-text"],
                                  capture_output=True, text=True, check=True).stdout.replace(" ", "").replace("-", "")
    assert imprint[:16] in request_text.lower().replace("\n", "")
    assert len(tsa.sent) == 1 and len(tsa.sent[0]) < 200
    checked = anchor.verify_audit_head(engine, case, output=tmp_path / "out")
    assert checked["status"] == "verified" and checked["event_count"] == 5


def test_no_new_events_sends_nothing_and_new_events_extend_the_stamp(engine, tmp_path, tsa):
    case = uuid4()
    head = _append(engine, case, 3)
    assert _stamp(engine, case, tmp_path, tsa)["status"] == "timestamp_verified"
    assert _stamp(engine, case, tmp_path, tsa)["status"] == "unchanged_verified_head"
    assert len(tsa.sent) == 1
    _append(engine, case, 2, start=4, previous=head)
    second = _stamp(engine, case, tmp_path, tsa)
    assert second["status"] == "timestamp_verified" and second["event_count"] == 5
    assert anchor.verify_audit_head(engine, case, output=tmp_path / "out")["event_count"] == 5


def test_a_rewritten_chain_is_reported_never_stamped_over(engine, tmp_path, tsa):
    case = uuid4()
    _append(engine, case, 3)
    assert _stamp(engine, case, tmp_path, tsa)["status"] == "timestamp_verified"
    with Session(engine) as session:
        session.query(FinancialAuditEvent).filter_by(case_id=case).delete()
        session.commit()
    _append(engine, case, 4, operation="UPDATE")  # a whole, valid chain, longer, but another history
    out = _stamp(engine, case, tmp_path, tsa)
    assert out["status"] == "attention_required" and "does not extend the last stamped head" in out["reason"]
    assert len(tsa.sent) == 1


def test_an_unverifiable_answer_is_not_recorded_as_a_stamp(engine, tmp_path, tsa, monkeypatch):
    case = uuid4()
    _append(engine, case, 2)
    monkeypatch.setattr(anchor, "_post", lambda url, query: b"not a time-stamp answer")
    out = _stamp(engine, case, tmp_path, tsa)
    assert out["status"] == "attention_required" and "Not stamped" in out["reason"]
    assert not (tmp_path / "out" / str(case) / "latest.json").exists()


def test_a_case_with_no_events_sends_nothing(engine, tmp_path, tsa):
    assert _stamp(engine, uuid4(), tmp_path, tsa)["status"] == "no_recorded_events"
    assert tsa.sent == []
