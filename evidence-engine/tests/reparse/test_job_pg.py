"""05 section 17.3: a whole re-parse run on the worker's own connection (autocommit), over a captured synthetic phone,
with the pinned ALEAPP. Opt-in: ``LOUPE_TEST_PHONE_PG_URL`` (a scratch PostgreSQL at the alembic head) and the tools
installed under /opt/leapp (the engine image)."""
from __future__ import annotations

import os

import pytest

from tests.phone import fixture_builder as fb
from tests.phone.test_files_timestamps import PG, pg_case  # noqa: F401 (fixture)

needs = pytest.mark.skipif(not (PG and os.path.isdir("/opt/leapp")),
                           reason="Requires LOUPE_TEST_PHONE_PG_URL and the pinned tools under /opt/leapp")


@needs
def test_a_run_over_a_captured_phone_completes_on_an_autocommit_connection(pg_case, tmp_path):  # noqa: F811
    from app.phone.runner import run_capture
    from app.pipeline.reparse import job
    conn, case_id = pg_case
    assert conn.autocommit  # as the worker's connection (app.phone.store.connect)
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=5)
    spec = fb.PhoneSpec("S1", like="P09", scale=0.05, contacts=[p.key for p in people[1:]], seed=7)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S1")
    files = sorted(p for p in (root / "S1" / "files").rglob("*") if p.is_file())
    files[0].unlink()  # one listed file absent: it is never placed in the tree
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S1", root_path="")
    assert res["state"] == "captured", res
    ext = res["extraction_id"]
    matched, unmatched = conn.execute(
        "SELECT count(*) FILTER (WHERE outcome = 'match' AND disk_relpath IS NOT NULL), "
        "count(*) FILTER (WHERE outcome <> 'match' OR disk_relpath IS NULL) FROM phone_files WHERE extraction_id = %s",
        (ext,)).fetchone()
    assert matched > 0 and unmatched >= 1
    run = job.create_run(conn, case_id, ext, "Android", "synthetic@example.org")
    out = job.execute(conn, run["id"], str(root), str(tmp_path / "storage"), wall_seconds=900)
    assert out["status"] == "completed", out
    row = conn.execute("SELECT status, tool, tool_commit, command_line, tree, exit_code, output_manifest_sha256, "
                       "outputs, artefact_counts FROM phone_reparse_runs WHERE id = %s", (run["id"],)).fetchone()
    status, tool, commit, cmd, tree, code, manifest, outputs, counts = row
    assert (status, tool, commit) == ("completed", "aleapp", "7a8dc905283b868bcc4767be8bea470e1a231ea2")
    assert "-t" in cmd and "fs" in cmd and len(manifest) == 64 and outputs["files"] > 0
    assert tree["placed"] == matched and tree["not_verified"] + tree["no_path"] >= 1
    assert "columns" in counts and "artefacts" in counts
    assert not os.path.exists(os.path.join(job.scratch_root(str(tmp_path / "storage")), run["id"]))
    stored = conn.execute("SELECT count(*) FROM phone_reparse_rows WHERE run_id = %s", (run["id"],)).fetchone()[0]
    assert stored == counts["stored_rows"]
