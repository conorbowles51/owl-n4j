"""05 section 17.3: the re-parse runner. The real-tool test runs where the pinned tools are installed (/opt/leapp)."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys

import pytest

from app.pipeline.reparse import leapp_runner as R
from tests.reparse import synthetic_android

HAVE_TOOLS = os.path.isdir(os.path.join(R.LEAPP_ROOT, "aleapp-v2026.4.5"))
needs_tools = pytest.mark.skipif(not HAVE_TOOLS, reason="Requires the pinned tools under /opt/leapp (engine image)")

PROBE = r'''
import socket, urllib.request
out = {}
for name, call in (("connect", lambda: socket.create_connection(("192.0.2.1", 80), timeout=2)),
                   ("raw_socket", lambda: socket.socket().connect(("192.0.2.1", 443))),
                   ("lookup", lambda: socket.getaddrinfo("example.com", 443)),
                   ("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("192.0.2.1", 53))),
                   ("urllib", lambda: urllib.request.urlopen("http://example.com/", timeout=2))):
    try:
        call()
        out[name] = "connected"
    except Exception as exc:
        out[name] = str(exc)
print("PROBE " + __import__("json").dumps(out))
'''


def test_an_outbound_attempt_from_the_tool_process_fails(tmp_path):
    src = tmp_path / "tool"
    src.mkdir()
    (src / "probe.py").write_text(PROBE)
    cmd = [sys.executable, "-I", "-c", R._LAUNCH, str(src), "probe.py"]
    out = subprocess.run(cmd, capture_output=True, text=True, env=R.child_env(), timeout=60)
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("PROBE ")]
    assert line, out.stderr
    got = json.loads(line[0][6:])
    assert set(got) == {"connect", "raw_socket", "lookup", "udp", "urllib"}
    for name, result in got.items():
        assert "network access is refused while re-parsing evidence" in result, (name, result)
    assert R.child_env()["HTTPS_PROXY"] == "http://127.0.0.1:9" and "PYTHONPATH" not in R.child_env()


def test_the_tree_holds_only_verified_files_at_their_original_paths(tmp_path):
    a = tmp_path / "a"
    a.write_bytes(b"synthetic a")
    files = [("/data/data/x/databases/a.db", lambda: open(a, "rb"), True),
             ("/data/data/x/databases/b.db", lambda: open(a, "rb"), False),
             ("/../../etc/passwd", lambda: open(a, "rb"), True),
             ("", lambda: open(a, "rb"), True),
             ("/data/data/x/databases/a.db", lambda: open(a, "rb"), True)]
    counts = R.build_tree(files, str(tmp_path / "tree"))
    assert counts == {"placed": 2, "bytes": 22, "not_verified": 1, "no_path": 1, "duplicate_path": 1,
                      "path_conflict": 0}
    assert (tmp_path / "tree" / "data/data/x/databases/a.db").read_bytes() == b"synthetic a"
    assert (tmp_path / "tree" / "etc/passwd").exists()  # '..' cannot climb out: it lands inside the tree
    assert not (tmp_path / "etc").exists()


def test_a_file_and_files_beneath_the_same_path_keep_the_first_and_count_the_conflict(tmp_path):
    a = tmp_path / "a"
    a.write_bytes(b"synthetic")
    op = lambda: open(a, "rb")  # noqa: E731
    files = [("/data/apex/pkg.apex", op, True), ("/data/apex/pkg.apex/assets/x", op, True),  # file, then beneath it
             ("/data/d/inner", op, True), ("/data/d", op, True)]  # beneath a path, then the path as a file
    counts = R.build_tree(files, str(tmp_path / "tree"))
    assert (counts["placed"], counts["path_conflict"]) == (2, 2)
    assert (tmp_path / "tree" / "data/apex/pkg.apex").is_file() and (tmp_path / "tree" / "data/d/inner").is_file()


def test_the_tool_is_chosen_by_operating_system():
    assert R.tool_for("Android") == "aleapp" and R.tool_for("iOS") == "ileapp"
    with pytest.raises(R.RunRefused, match="No re-parse tool is pinned"):
        R.tool_for("BlackBerry")


def test_a_run_past_the_wall_clock_limit_is_stopped(tmp_path):
    src = tmp_path / "tool"
    src.mkdir()
    (src / "slow.py").write_text("import time\ntime.sleep(60)\n")
    pin = {"tool": "aleapp", "version": "v0", "commit": "0" * 40, "licence": "MIT", "src": str(src),
           "python": sys.executable, "entry": "slow.py"}
    rec = R.run(pin, str(tmp_path), str(tmp_path / "out"), wall_seconds=2,
                cmd=[sys.executable, "-I", "-c", R._LAUNCH, str(src), "slow.py"])
    assert rec["stopped"] == "Stopped after 2 s, the wall-clock limit." and rec["seconds"] < 10


@needs_tools
def test_the_pinned_aleapp_reads_a_synthetic_tree_and_the_run_is_recorded(tmp_path):
    pin = R.pinned("aleapp")
    assert pin["installed_commit"] == "7a8dc905283b868bcc4767be8bea470e1a231ea2" and pin["licence"] == "MIT"
    tree = tmp_path / "tree"
    synthetic_android.build(str(tree))
    rec = R.run(pin, str(tree), str(tmp_path / "out"), wall_seconds=900)
    assert rec["exit_code"] == 0, rec["log_tail"]
    assert rec["version"] == "v2026.4.5" and rec["commit"] == pin["installed_commit"]
    assert rec["command_line"][-6:] == ["-t", "fs", "-i", str(tree), "-o", str(tmp_path / "out")]
    assert rec["peak_rss_mb"] > 0 and len(rec["output"]["manifest_sha256"]) == 64
    lava = R.lava_db(str(tmp_path / "out"))
    assert lava, "no LAVA output"
    with sqlite3.connect(lava) as c:
        names = [n for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    print("LAVA TABLES", json.dumps(names))


@needs_tools
def test_the_mapping_reads_the_pinned_tools_real_output_on_the_synthetic_tree(tmp_path):
    import datetime as dt

    from app.pipeline.reparse import mapping as M
    tree = tmp_path / "tree"
    synthetic_android.build(str(tree))
    rec = R.run(R.pinned("aleapp"), str(tree), str(tmp_path / "out"), wall_seconds=900)
    counts, rows = M.read_lava(R.lava_db(str(tmp_path / "out")), "aleapp")
    assert counts["mapped"] == {"sms": 3, "call": 2}, counts
    assert "get_sms_mms" not in counts["missing_roles"] and "get_calllog" not in counts["missing_roles"]
    assert "date" in counts["columns"]["get_sms_mms"] and "call_date" in counts["columns"]["get_calllog"]
    sms = sorted((r for r in rows if r["kind"] == "sms"), key=lambda r: r["row_index"])
    want = [(a, dt.datetime.fromtimestamp(d // 1000, dt.timezone.utc), b) for _, _, a, d, _, b in synthetic_android.SMS]
    assert [(r["values"]["roles"]["party"], r["instant"], r["values"]["roles"]["body"]) for r in sms] == want
    assert [r["values"]["roles"]["direction"] for r in sms] == ["Received", "Sent", "Received"]
    calls = sorted((r for r in rows if r["kind"] == "call"), key=lambda r: r["instant"])
    assert [(r["values"]["roles"]["party"], r["values"]["roles"]["direction"], r["values"]["roles"]["duration"])
            for r in calls] == [("+12025550143", "2", "61"), ("+12025550188", "3", "0")]
    assert all(r["values"]["app"] in ("SMS", "Phone") and r["values"]["row"] for r in rows)
    assert rec["exit_code"] == 0
