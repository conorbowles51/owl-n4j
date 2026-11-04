"""Run a pinned ALEAPP or iLEAPP over a phone's verified files (05 section 17.3, points 1 and 2).

- The tool is chosen by the extraction's operating system; each pinned release lives in its own virtual environment
  under ``/opt/leapp/<tool>-<version>/`` (``venv/``, ``src/``, ``PIN.json`` with version, git commit and licence),
  installed by ``evidence-engine/leapp/install.sh`` at image build. It never runs in the backend or the engine's own
  interpreter.
- The input is a tree rebuilt from the production: every tagged file whose MD5 verified, placed at its original
  ``path`` (the file element's ``path`` attribute). Nothing else goes in; a path that would leave the tree is
  refused and counted.
- No network: the tool runs as a child that replaces every socket connect, address lookup and send before the
  tool's code is loaded, with proxy variables pointing at a closed local port. A wall-clock limit ends it.
- The run record holds the tool, version, commit, licence, the exact command line, the tree's counts, exit code,
  run time, peak memory and a SHA-256 for every output file and for the whole output.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time
from posixpath import normpath

LEAPP_ROOT = os.environ.get("LOUPE_LEAPP_ROOT", "/opt/leapp")
TOOL_FOR_OS = {"android": "aleapp", "ios": "ileapp"}
DEFAULT_WALL_SECONDS = int(os.environ.get("LOUPE_LEAPP_WALL_SECONDS", str(4 * 3600)))
DEAD_PROXY = "http://127.0.0.1:9"

# first in the child: nothing can leave the process, whatever the tool or a library tries
GUARD = r'''
import socket
def _refuse(*a, **k):
    raise OSError("network access is refused while re-parsing evidence")
socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.socket.sendto = _refuse
socket.socket.sendmsg = _refuse
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
socket.gethostbyname = _refuse
socket.gethostbyname_ex = _refuse
'''
_LAUNCH = GUARD + r'''
import os, runpy, sys
src, entry = sys.argv[1], sys.argv[2]
sys.argv = [os.path.join(src, entry)] + sys.argv[3:]
sys.path.insert(0, src)
os.chdir(src)
runpy.run_path(os.path.join(src, entry), run_name="__main__")
'''


class RunRefused(Exception):
    pass


def tool_for(os_family: str | None) -> str:
    t = TOOL_FOR_OS.get((os_family or "").strip().lower())
    if not t:
        raise RunRefused("No re-parse tool is pinned for this phone's operating system (%s)." % (os_family or "unknown"))
    return t


def pinned(tool: str, root: str = LEAPP_ROOT) -> dict:
    """The installed pin of ``tool`` (exactly one version is installed per tool)."""
    if not os.path.isdir(root):
        raise RunRefused("No re-parse tool is installed on this server.")
    found = [d for d in sorted(os.listdir(root)) if d.startswith(tool + "-") and
             os.path.isfile(os.path.join(root, d, "PIN.json"))]
    if len(found) != 1:
        raise RunRefused("Expected one installed %s, found %d." % (tool, len(found)))
    base = os.path.join(root, found[0])
    pin = json.load(open(os.path.join(base, "PIN.json")))
    pin.update(tool=tool, base=base, python=os.path.join(base, "venv", "bin", "python"),
               src=os.path.join(base, "src"))
    return pin


def safe_relpath(original_path: str | None) -> str | None:
    """The tree path for a file's original ``path``; None when it is empty or would leave the tree."""
    if not original_path:
        return None
    p = original_path.replace("\\", "/")
    rel = normpath("/" + p).lstrip("/")
    if not rel or rel.startswith("..") or rel in (".",):
        return None
    return rel


def build_tree(files, dest: str) -> dict:
    """``files``: iterable of ``(original_path, opener, verified)``. Places each verified file at its path under
    ``dest``. Returns counts by outcome (placed, not verified, no or unsafe path, same path twice, path conflict).

    A report can list a file and also files beneath the same path (measured on P12: an Android ``.apex`` package and
    the files read from inside it). A filesystem holds only one of them, so the first in the report's order is
    placed and the other is counted as a path conflict; nothing is renamed or guessed."""
    counts = {"placed": 0, "bytes": 0, "not_verified": 0, "no_path": 0, "duplicate_path": 0, "path_conflict": 0}
    seen = set()
    os.makedirs(dest, exist_ok=True)
    for original_path, opener, verified in files:
        if not verified:
            counts["not_verified"] += 1
            continue
        rel = safe_relpath(original_path)
        if rel is None:
            counts["no_path"] += 1
            continue
        if rel in seen:
            counts["duplicate_path"] += 1
            continue
        seen.add(rel)
        target = os.path.join(dest, rel)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            out = open(target, "xb")
        except (NotADirectoryError, FileExistsError, IsADirectoryError):
            counts["path_conflict"] += 1
            continue
        with opener() as src, out:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                out.write(chunk)
                counts["bytes"] += len(chunk)
        counts["placed"] += 1
    return counts


def command(pin: dict, tree: str, out: str) -> list:
    return [pin["python"], "-I", "-c", _LAUNCH, pin["src"], pin["entry"], "-t", "fs", "-i", tree, "-o", out]


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ", "HOME")}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[k] = DEAD_PROXY
    env["NO_PROXY"] = env["no_proxy"] = ""
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def output_hashes(out: str) -> dict:
    files = []
    for root, _dirs, names in os.walk(out):
        for n in names:
            p = os.path.join(root, n)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            files.append({"path": os.path.relpath(p, out), "size": os.path.getsize(p), "sha256": h.hexdigest()})
    files.sort(key=lambda f: f["path"])
    whole = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"files": files, "manifest_sha256": whole}


def run(pin: dict, tree: str, out: str, wall_seconds: int = DEFAULT_WALL_SECONDS, nice: int = 15,
        cmd: list | None = None) -> dict:
    """Run the tool once. ``out`` must exist (the tools require it). Returns the run record."""
    os.makedirs(out, exist_ok=True)
    cmd = cmd or command(pin, tree, out)
    log = os.path.join(os.path.dirname(out.rstrip("/")) or ".", "tool.log")
    t0, started = time.monotonic(), time.time()
    with open(log, "wb") as lf:
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=child_env(), cwd=pin["src"],
                             preexec_fn=lambda: (os.nice(nice), os.setsid()))
        deadline, stopped = t0 + wall_seconds, None
        while True:  # wait4: this child's own peak memory, not every child the worker ever had
            pid, status, usage = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() > deadline:
                os.killpg(p.pid, signal.SIGKILL)
                pid, status, usage = os.wait4(p.pid, 0)
                stopped = "Stopped after %d s, the wall-clock limit." % wall_seconds
                break
            time.sleep(0.5)
        p.returncode = code = os.waitstatus_to_exitcode(status)
    seconds = round(time.monotonic() - t0, 1)
    peak_mb = round(usage.ru_maxrss / 1024, 1)  # Linux reports KiB
    hashes = output_hashes(out)
    with open(log, "rb") as lf:
        tail = lf.read()[-4000:].decode("utf-8", "replace")
    return {"tool": pin["tool"], "version": pin["version"], "commit": pin.get("installed_commit") or pin["commit"],
            "licence": pin["licence"], "command_line": cmd[:2] + ["-c", "<network guard + launcher>"] + cmd[4:],
            "exit_code": code, "stopped": stopped, "seconds": seconds, "peak_rss_mb": peak_mb,
            "started_at": started, "output": hashes, "log_tail": tail}


def lava_db(out: str) -> str | None:
    """The LAVA SQLite file the tool wrote (``*.lava`` or ``_lava_artifacts.db``), if any."""
    for root, _dirs, names in os.walk(out):
        for n in sorted(names):
            if n.endswith(".lava") or n == "_lava_artifacts.db":
                return os.path.join(root, n)
    return None


if __name__ == "__main__":  # operator check: python -m app.pipeline.reparse.leapp_runner <tool>
    print(json.dumps(pinned(sys.argv[1]), indent=1))
