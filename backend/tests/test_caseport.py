"""The case package: the format catches damage, compatibility is stated, ids remap deterministically, and a seeded
case survives a full round trip (export, import into a new case, export again) with equal counts and evidence hashes.

The round trip needs a local PostgreSQL at the application's schema and skips without
LOUPE_TEST_LOCAL_POSTGRES_URL (the head suite provides one; TEST-BASELINE.md has the recipe).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from services.caseport import importer as M
from services.caseport import inventory as I
from services.caseport import package as P

CASE = "11111111-2222-3333-4444-555555555555"
EVIDENCE = b"EVIDENCE-PAYLOAD-0123456789-the-only-copy-of-these-bytes\n" * 20


def build_package(tmp: Path) -> Path:
    target = tmp / ("case" + P.SUFFIX)
    writer = P.PackageWriter(target)
    part = writer.part()
    part.write_line(json.dumps({"id": CASE, "title": "A case"}))
    writer.add_part("pg/cases.jsonl.gz", part)
    source = tmp / "source.bin"
    source.write_bytes(EVIDENCE)
    entry = writer.add_evidence(f"evidence/{CASE}/file.bin", source)
    index = writer.part()
    index.write_line(json.dumps({"path": f"{CASE}/file.bin", **entry, "recorded_sha256": entry["sha256"]}))
    writer.add_part("evidence-index.jsonl.gz", index)
    writer.finish({"format": P.FORMAT, "format_version": P.FORMAT_VERSION, "schema_revision": "r2",
                   "source_case": {"id": CASE, "title": "A case"}, "evidence_root": "/x"})
    return target


def test_a_whole_package_verifies_with_its_counts(tmp_path):
    target = build_package(tmp_path)
    result = P.verify(target)
    assert result["ok"], result["problems"]
    assert result["manifest"]["parts"]["pg/cases.jsonl.gz"]["rows"] == 1
    assert result["manifest"]["parts"]["evidence-index.jsonl.gz"]["rows"] == 1
    assert not result["notes"]


def test_a_changed_byte_is_caught(tmp_path):
    target = build_package(tmp_path)
    data = bytearray(target.read_bytes())
    at = data.find(b"EVIDENCE-PAYLOAD")
    assert at > 0, "the evidence bytes should be stored as they are"
    data[at] ^= 0xFF
    target.write_bytes(bytes(data))
    result = P.verify(target)
    assert not result["ok"]
    assert any("evidence file" in p and "SHA-256" in p for p in result["problems"]), result["problems"]
    assert any(".sha256 file says" in p for p in result["problems"]), result["problems"]


def test_a_truncated_package_is_not_whole(tmp_path):
    target = build_package(tmp_path)
    data = target.read_bytes()
    target.write_bytes(data[: len(data) // 2])
    result = P.verify(target)
    assert not result["ok"]


def test_an_abandoned_export_leaves_no_package(tmp_path):
    target = tmp_path / ("case" + P.SUFFIX)
    writer = P.PackageWriter(target)
    part = writer.part()
    part.write_line("one line")
    writer.add_part("pg/cases.jsonl.gz", part)
    assert not target.exists(), "an unfinished package must not carry the real name"
    writer.abandon()
    assert list(tmp_path.iterdir()) == [], "a failed export leaves nothing behind"


def _tables(columns, required=()):
    table = I.Table("cases")
    table.columns = list(columns)
    table.required = set(required)
    return {"cases": table}


def _manifest(revision="r1", columns=("id", "title")):
    return {"format_version": P.FORMAT_VERSION, "schema_revision": revision,
            "tables": {"cases": {"columns": list(columns)}}}


def test_a_package_from_a_newer_format_is_refused():
    manifest = _manifest()
    manifest["format_version"] = P.FORMAT_VERSION + 1
    reasons = M.check_compatible(manifest, target_revision="r2", known_revisions=["r1", "r2"],
                                 target_tables=_tables(["id", "title"]))
    assert any("format" in r for r in reasons), reasons


def test_a_package_from_a_newer_schema_is_refused_with_the_reason():
    for package_revision in ("r3", "unheard-of"):
        reasons = M.check_compatible(_manifest(package_revision), target_revision="r2",
                                     known_revisions=["r1", "r2", "r3"], target_tables=_tables(["id", "title"]))
        assert any("newer database schema" in r for r in reasons), (package_revision, reasons)


def test_an_older_package_loads_when_its_columns_still_fit():
    assert M.check_compatible(_manifest("r1"), target_revision="r2", known_revisions=["r1", "r2"],
                              target_tables=_tables(["id", "title", "added_later"])) == []


def test_an_older_package_is_refused_naming_the_column_that_no_longer_fits():
    gone = M.check_compatible(_manifest("r1", columns=("id", "title", "removed_here")), target_revision="r2",
                              known_revisions=["r1", "r2"], target_tables=_tables(["id", "title"]))
    assert any("cases.removed_here no longer exists" in r for r in gone), gone
    needed = M.check_compatible(_manifest("r1", columns=("id",)), target_revision="r2",
                                known_revisions=["r1", "r2"], target_tables=_tables(["id", "title"], required=["title"]))
    assert any("cases.title is required here" in r for r in needed), needed


def test_ids_remap_deterministically_and_only_listed_ones():
    new_case = str(uuid.uuid4())
    listed = str(uuid.uuid4())
    unlisted = str(uuid.uuid4())
    digest = hashlib.sha256(b"x").hexdigest()
    text = json.dumps({"cite": f"rec://{listed}", "other": unlisted, "hash": digest})
    first, second = M.Remap(new_case), M.Remap(new_case)
    for remap in (first, second):
        remap.add(listed)
        remap.add(digest)
    out = first.text(text)
    assert listed not in out and digest not in out
    assert unlisted in out, "an id the package did not list stays what it was"
    assert out == second.text(text), "the same package into the same case maps the same way"
    assert first.table[listed] == str(uuid.uuid5(uuid.UUID(new_case), listed))


# ---------------------------------------------------------------------------------------------------------------------
# The round trip, on a real PostgreSQL at the application's schema: a throwaway copy of the template database per
# test (tests/phone_pg.py), dropped afterwards, because the audit and activity trails are append-only by trigger
# and could never be cleaned out of a shared database.

from tests.phone_pg import fresh_engine, needs_template  # noqa: E402


class FakeGraph:
    """The graph store's surface, held in memory."""

    def __init__(self, nodes=()):
        self.stored = [dict(n) for n in nodes]   # {"i", "l", "p"}
        self.stored_rels = []                     # {"a", "b", "t", "p"}
        self.made = 0

    def nodes(self, case_id):
        for n in self.stored:
            if n["p"].get("case_id") == case_id:
                yield n["i"], n["l"], n["p"]

    def relationships(self, case_id):
        for r in self.stored_rels:
            yield r["a"], r["b"], r["t"], r["p"]

    def crossing(self, case_id):
        return 0

    def create_nodes(self, labels, rows):
        out = {}
        for row in rows:
            self.made += 1
            new_id = f"new:{self.made}"
            self.stored.append({"i": new_id, "l": list(labels), "p": row["p"]})
            out[row["i"]] = new_id
        return out

    def create_relationships(self, rel_type, rows):
        for row in rows:
            self.stored_rels.append({"a": row["a"], "b": row["b"], "t": rel_type, "p": row["p"]})
        return len(rows)

    def delete_case(self, case_id):
        self.stored = [n for n in self.stored if n["p"].get("case_id") != case_id]

    def close(self):
        pass


class FakeVectors:
    def __init__(self, rows_by_collection=None):
        self.stored = {c: list((rows_by_collection or {}).get(c, ())) for c in ("chunks", "entities")}

    def rows(self, collection, case_id):
        for row in self.stored[collection]:
            if row["metadata"].get("case_id") == case_id:
                yield row

    def existing(self, collection, ids):
        held = {r["id"] for r in self.stored[collection]}
        return {i for i in ids if i in held}

    def dimension(self, collection):
        rows = self.stored[collection]
        return len(rows[0]["embedding"]) if rows else None

    def add(self, collection, rows):
        self.stored[collection].extend(rows)

    def delete_case(self, case_id):
        for c in self.stored:
            self.stored[c] = [r for r in self.stored[c] if r["metadata"].get("case_id") != case_id]


def _seed(conn, tmp_path):
    """A user, a case, one evidence file on disk and one activity event. The evidence insert writes the financial
    audit chain through the real trigger (capture_financial_audit), so the chain is the production one."""
    case_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    email = f"caseport-{case_id[:8]}@example.test"
    conn.execute("INSERT INTO users (id, email, name, password_hash, global_role, is_active) "
                 "VALUES (%s, %s, 'Round Trip', 'x', 'user', true)", (user_id, email))
    conn.execute("INSERT INTO cases (id, title, description, status, created_by_user_id, owner_user_id) "
                 "VALUES (%s, 'Round trip case', 'seeded', 'active', %s, %s)", (case_id, user_id, user_id))
    conn.execute("INSERT INTO case_memberships (case_id, user_id, membership_role, permissions, added_by_user_id) "
                 "VALUES (%s, %s, 'owner', '{}'::jsonb, %s)", (case_id, user_id, user_id))
    evidence_root = tmp_path / "evidence-src"
    folder = evidence_root / case_id
    folder.mkdir(parents=True)
    (folder / "file.bin").write_bytes(EVIDENCE)
    sha = hashlib.sha256(EVIDENCE).hexdigest()
    file_id = str(uuid.uuid4())
    conn.execute("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status) "
                 "VALUES (%s, %s, 'file.bin', 'file.bin', %s, %s, 'processed')",
                 (file_id, case_id, len(EVIDENCE), sha))
    conn.execute("INSERT INTO activity_events (action, user_id, user_name, user_email, case_id, source_address, details) "
                 "VALUES ('evidence_upload', %s, 'Round Trip', %s, %s, '127.0.0.1', %s::jsonb)",
                 (user_id, email, case_id, json.dumps({"file_id": file_id})))
    chain = conn.execute("SELECT sequence, entry_sha256 FROM financial_audit_events WHERE case_id = %s "
                         "ORDER BY sequence DESC LIMIT 1", (case_id,)).fetchone()
    assert chain is not None, "the evidence insert should have written the audit chain through its trigger"
    return dict(case_id=case_id, user_id=user_id, email=email, evidence_root=evidence_root, sha=sha,
                file_id=file_id, audit_rows=chain[0], audit_head=chain[1])


@needs_template
def test_a_seeded_case_survives_the_round_trip(tmp_path):
    import psycopg
    from services.caseport import export as X
    with fresh_engine() as engine:
        url = engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg://", "postgresql://")
        engine.dispose()
        conn = psycopg.connect(url, autocommit=True)
        seeded = _seed(conn, tmp_path)
        case_id = seeded["case_id"]
        node_a, node_b = f"old:{uuid.uuid4()}", f"old:{uuid.uuid4()}"
        graph = FakeGraph(nodes=[{"i": node_a, "l": ["Entity"], "p": {"case_id": case_id, "key": f"entity:{case_id}:1"}},
                                 {"i": node_b, "l": ["Entity"], "p": {"case_id": case_id, "key": f"entity:{case_id}:2"}}])
        graph.stored_rels = [{"a": node_a, "b": node_b, "t": "LINKED", "p": {"case_id": case_id}}]
        vectors = FakeVectors({"chunks": [{"id": f"{case_id}:chunk:1", "document": "a chunk",
                                           "metadata": {"case_id": case_id}, "embedding": [0.25, -0.5]}]})
        exporter = dict(id=seeded["user_id"], email=seeded["email"], name="Round Trip")
        try:
            out = X.run_export(url, case_id, exporter=exporter, target=tmp_path / ("one" + P.SUFFIX),
                               evidence_root=seeded["evidence_root"], graph=graph, vectors=vectors, whole=True)
            package = Path(out["path"])
            result = P.verify(package)
            assert result["ok"], result["problems"]
            manifest = result["manifest"]
            assert manifest["financial_audit_head_sha256"] == seeded["audit_head"]
            assert manifest["parts"]["pg/evidence_files.jsonl.gz"]["rows"] == 1
            assert manifest["parts"]["pg/financial_audit_events.jsonl.gz"]["rows"] == seeded["audit_rows"]
            assert manifest["graph"] == {"nodes": 2, "relationships": 1, "crossing_cases": 0}

            target_root = tmp_path / "evidence-dst"
            target_graph = FakeGraph()
            target_vectors = FakeVectors()
            report = M.run_import(url, package, by_email=seeded["email"], evidence_root=target_root,
                                  graph=target_graph, vectors=target_vectors, title="Round trip import")
            new_case = report["case_id"]
            assert new_case != case_id
            for name, loaded in report["rows_per_table"].items():
                assert loaded == manifest["parts"][f"pg/{name}.jsonl.gz"]["rows"], name
            assert report["graph"] == {"nodes": 2, "relationships": 1}
            assert report["vectors"]["loaded"] == {"chunks": 1, "entities": 0}
            assert report["source_financial_audit_head_sha256"] == seeded["audit_head"]

            # The copied evidence file holds the same bytes under the new case.
            copies = list((target_root / new_case).rglob("*.bin"))
            assert len(copies) == 1
            assert hashlib.sha256(copies[0].read_bytes()).hexdigest() == seeded["sha"]

            # Provenance: who did what stays theirs, and the audit chain still proves itself over the moved payloads.
            row = conn.execute("SELECT user_name, user_email FROM activity_events WHERE case_id = %s "
                               "AND action = 'evidence_upload'", (new_case,)).fetchone()
            assert row == ("Round Trip", seeded["email"])
            previous = "0" * 64
            for prev, entry, payload in conn.execute(
                    "SELECT previous_sha256, entry_sha256, payload_text FROM financial_audit_events "
                    "WHERE case_id = %s ORDER BY sequence", (new_case,)):
                assert prev == previous
                assert entry == hashlib.sha256(bytes.fromhex(previous) + payload.encode()).hexdigest()
                assert new_case in payload and case_id not in payload
                previous = entry

            # The audit trail says who imported what from where.
            imported = conn.execute("SELECT user_email, details FROM activity_events WHERE case_id = %s "
                                    "AND action = 'case_imported'", (new_case,)).fetchone()
            assert imported is not None
            details = imported[1]
            assert imported[0] == seeded["email"]
            assert details["source_case"]["id"] == case_id
            assert details["package_sha256"] == result["sha256"]

            # Round trip: the new case exports with equal counts per part and equal evidence hashes. The one
            # difference is its own trail: the import wrote the case_imported entry above.
            again = X.run_export(url, new_case, exporter=exporter, target=tmp_path / ("two" + P.SUFFIX),
                                 evidence_root=target_root, graph=target_graph, vectors=target_vectors, whole=True)
            second = P.verify(again["path"])
            assert second["ok"], second["problems"]
            for name, want in manifest["parts"].items():
                if not name.startswith("pg/"):
                    continue
                got = second["manifest"]["parts"][name]["rows"]
                assert got == want["rows"] + (1 if name == "pg/activity_events.jsonl.gz" else 0), name
            assert second["manifest"]["evidence"]["files"] == manifest["evidence"]["files"]

            # The two packages hold the same evidence bytes: equal hash sets.
            def hashes(verified):
                reader = P.PackageReader(verified)
                try:
                    return sorted(json.loads(line)["sha256"] for line in reader.lines("evidence-index.jsonl.gz"))
                finally:
                    reader.close()
            assert hashes(package) == hashes(Path(again["path"]))
        finally:
            conn.close()


def test_progress_line_is_not_swallowed_by_a_liveness_beat():
    from services.caseport.jobs import make_heartbeat
    seen, now = [], [100.0]
    beat = make_heartbeat(lambda *a: seen.append(a), clock=lambda: now[0])
    beat()                                   # liveness beat, as the cancel check does on every file
    now[0] += 1
    beat("Evidence files: 500", 3, 9)        # progress one second later must still be written
    assert seen == [(None, None, None), ("Evidence files: 500", 3, 9)]
    now[0] += 1
    beat("Evidence files: 1000", 3, 9)       # throttled: same kind inside the interval
    assert len(seen) == 2
