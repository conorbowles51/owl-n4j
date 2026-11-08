"""chroma_reach against a small stand-in for the server: the same HTTP paths, an index that can lose a record."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "backend" / "scripts" / "chroma_reach.py"
SETTINGS = REPO / "deploy" / "chroma-settings.sh"


class Store:
    def __init__(self):
        self.collections = {"chunks": {"id": "c1", "name": "chunks", "configuration_json": {"hnsw": {"ef_search": 100}}},
                            "entities": {"id": "e1", "name": "entities", "configuration_json": {"hnsw": {"ef_search": 100}}}}
        self.records = {"c1": {}, "e1": {}}
        self.orphans = set()      # no query finds them
        self.thin = set()         # only a query deeper than the app's finds them
        self.writes = []
        self.steals = {}          # adding the key takes the only link of the value

    def add(self, cid, rid, case, state="active", vector=None):
        self.records[cid][rid] = {"vector": vector or [float(len(self.records[cid]) + 1), 0.0], "document": f"text {rid}",
                                  "metadata": {"case_id": case, "doc_name": "file.pdf", "ingestion_state": state}}


def serve(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.endswith("/heartbeat"):
                return self._send({})
            if self.path.endswith("/collections"):
                return self._send(list(store.collections.values()))
            return self._send(len(store.records[self.path.split("/")[-2]]))

        def do_PUT(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            for c in store.collections.values():
                if c["id"] == self.path.split("/")[-1]:
                    c["configuration_json"]["hnsw"].update(body["new_configuration"]["hnsw"])
            store.writes.append("settings")
            self._send({})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            cid, action = self.path.split("/")[-2:]
            records = store.records[cid]
            if action == "get":
                ids = body.get("ids") or list(records)[body["offset"]:body["offset"] + body["limit"]]
                ids = [i for i in ids if i in records]
                return self._send({"ids": ids, "embeddings": [records[i]["vector"] for i in ids],
                                   "metadatas": [records[i]["metadata"] for i in ids],
                                   "documents": [records[i]["document"] for i in ids]})
            if action == "query":
                ids_out, dist_out = [], []
                case = (body.get("where") or {}).get("case_id")
                for q in body["query_embeddings"]:
                    pool = [i for i in records if not case or records[i]["metadata"]["case_id"] == case]
                    pool = [i for i in pool if i not in store.orphans
                            and (i not in store.thin or body["n_results"] >= len(pool))]
                    pool.sort(key=lambda i: abs(records[i]["vector"][0] - q[0]))
                    pool = pool[:body["n_results"]]
                    ids_out.append(pool)
                    dist_out.append([abs(records[i]["vector"][0] - q[0]) for i in pool])
                return self._send({"ids": ids_out, "distances": dist_out})
            store.writes.append(action)
            if action == "delete":
                for i in body["ids"]:
                    records.pop(i, None)
            if action == "add":
                records[body["ids"][0]] = {"vector": body["embeddings"][0], "metadata": body["metadatas"][0],
                                           "document": body["documents"][0]}
                store.orphans.discard(body["ids"][0])
                if body["ids"][0] in store.steals:
                    store.orphans.add(store.steals.pop(body["ids"][0]))
            self._send({})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def chroma():
    store = Store()
    server, url = serve(store)
    yield store, url
    server.shutdown()


def run(*args, env=None):
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, timeout=60,
                          env={**os.environ, **(env or {})})


def test_every_record_found_passes(chroma):
    store, url = chroma
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.add("c1", "b0", "case-b")
    store.add("e1", "e0", "case-a")
    done = run("check", "--url", url)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 of 4 found at depth 250" in done.stdout and "1 of 1 found at depth 50" in done.stdout


def test_record_nothing_links_to_fails_and_is_named(chroma, tmp_path):
    store, url = chroma
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.orphans.add("a1")
    out = tmp_path / "reach.json"
    done = run("check", "--url", url, "--collection", "chunks", "--out", str(out))
    assert done.returncode == 1
    assert "1 searched records unreached (1 at any depth, 0 already listed)" in done.stdout
    report = json.loads(out.read_text())[0]
    assert [(u["id"], u["case"], u["document"], u["any_depth"]) for u in report["unreached"]] == [
        ("a1", "case-a", "file.pdf", False)]


def test_record_only_a_deeper_search_finds_fails_as_reachable(chroma, tmp_path):
    store, url = chroma
    for i in range(300):
        store.add("c1", f"a{i}", "case-a")
    store.thin.add("a7")
    out = tmp_path / "reach.json"
    assert run("check", "--url", url, "--collection", "chunks", "--out", str(out)).returncode == 1
    assert [u["any_depth"] for u in json.loads(out.read_text())[0]["unreached"]] == [True]


def test_retired_revision_does_not_fail_the_check(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.add("c1", "a1", "case-a", state="inactive")
    store.orphans.add("a1")
    out = tmp_path / "reach.json"
    assert run("check", "--url", url, "--collection", "chunks", "--out", str(out)).returncode == 0
    assert json.loads(out.read_text())[0]["unreached"][0]["searched"] is False


def test_page_of_identical_passages_is_a_tie_not_a_fault(chroma):
    store, url = chroma
    for i in range(251):
        store.add("c1", f"a{i}", "case-a", vector=[1.0, 0.0])
    done = run("check", "--url", url, "--collection", "chunks")
    assert done.returncode == 0, done.stdout


def test_relink_dry_run_changes_nothing(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.orphans.add("a0")
    ids = tmp_path / "ids"
    ids.write_text("a0\n")
    done = run("relink", "--url", url, "--collection", "chunks", "--ids", str(ids))
    assert done.returncode == 0 and store.writes == []


def test_relink_keeps_the_stored_copy_and_the_count(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.add("c1", "a1", "case-a")
    store.orphans.add("a1")
    before = json.loads(json.dumps(store.records["c1"]["a1"]))
    ids = tmp_path / "ids"
    ids.write_text("a1\ngone-since\n")
    kept = tmp_path / "kept"
    done = run("relink", "--url", url, "--collection", "chunks", "--ids", str(ids), "--keep", str(kept), "--apply")
    assert done.returncode == 0, done.stdout + done.stderr
    copy = json.loads(kept.read_text().splitlines()[0])
    assert copy["documents"] == ["text a1"] and copy["metadatas"] == [before["metadata"]]
    report = json.loads(done.stdout)
    assert (report["before"], report["after"], report["found"], report["gone"]) == (2, 2, 1, ["gone-since"])
    assert store.records["c1"]["a1"] == before
    assert run("check", "--url", url, "--collection", "chunks").returncode == 0


def test_relink_repairs_a_record_a_later_add_took_the_link_from(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.add("c1", "a1", "case-a")
    store.orphans.update({"a0", "a1"})
    store.steals["a1"] = "a0"
    ids = tmp_path / "ids"
    ids.write_text("a0\na1\n")
    done = run("relink", "--url", url, "--collection", "chunks", "--ids", str(ids), "--apply")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not store.orphans and json.loads(done.stdout)["found"] == 2


def test_relink_says_so_when_a_record_stays_unreached(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.add("c1", "a1", "case-a")

    class Stubborn(set):
        def discard(self, value):
            pass

    store.orphans = Stubborn({"a0"})
    ids = tmp_path / "ids"
    ids.write_text("a0\n")
    done = run("relink", "--url", url, "--collection", "chunks", "--ids", str(ids), "--apply")
    assert done.returncode == 0, "a stubborn record is reported, it does not stop a release"
    report = json.loads(done.stdout)
    assert report["not_found"] == ["a0"] and report["unreached_after"] == ["a0"]


def test_relink_follows_a_neighbour_it_cost_a_link(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.add("c1", "a1", "case-a")
    store.orphans.add("a0")
    store.steals["a0"] = "a1"
    ids = tmp_path / "ids"
    ids.write_text("a0\n")
    done = run("relink", "--url", url, "--collection", "chunks", "--ids", str(ids), "--apply")
    report = json.loads(done.stdout)
    assert report["followed"] == 1 and report["unreached_after"] == [] and not store.orphans


def test_sweep_names_the_unlinked_in_one_search_per_case(chroma):
    store, url = chroma
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.add("c1", "b0", "case-b")
    store.orphans.add("a2")
    done = run("sweep", "--url", url, "--collection", "chunks")
    assert done.returncode == 1 and "3 of 4 found at depth whole case" in done.stdout


def test_a_listed_record_is_shown_and_a_new_one_still_fails(chroma, tmp_path):
    store, url = chroma
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.orphans.add("a2")
    known = tmp_path / "known"
    known.write_text("a2\tan outlier its neighbours prune\n")
    done = run("sweep", "--url", url, "--collection", "chunks", "--known", str(known))
    assert done.returncode == 0 and "1 already listed" in done.stdout
    store.orphans.add("a1")
    assert run("sweep", "--url", url, "--collection", "chunks", "--known", str(known)).returncode == 1


def test_settings_change_once_and_only_on_chunks(chroma):
    store, url = chroma
    assert run("settings", "--url", url).returncode == 0
    assert store.writes == []
    assert run("settings", "--url", url, "--apply").returncode == 10
    assert store.collections["chunks"]["configuration_json"]["hnsw"]["ef_search"] == 50000
    assert store.collections["entities"]["configuration_json"]["hnsw"]["ef_search"] == 100
    assert run("settings", "--url", url, "--apply").returncode == 0


def release_step(url, tmp_path):
    docker = tmp_path / "docker"
    docker.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/docker.calls\n')
    docker.chmod(0o755)
    return subprocess.run(["bash", str(SETTINGS)], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "CHROMA_URL": url, "DOCKER": str(docker), "READY_TRIES": "3",
                               "CHROMA_RELINK_LISTS": str(tmp_path)})


def test_release_step_restarts_only_on_a_change_and_uses_a_list_once(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    store.orphans.add("a0")
    (tmp_path / "chunks.ids").write_text("a0\n")
    first = release_step(url, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert (tmp_path / "docker.calls").read_text().split() == ["restart", "owl-v2-chromadb"]
    assert not store.orphans and (tmp_path / "chunks.ids.done").exists() and not (tmp_path / "chunks.ids").exists()
    writes = list(store.writes)
    second = release_step(url, tmp_path)
    assert second.returncode == 0 and store.writes == writes
    assert (tmp_path / "docker.calls").read_text().count("restart") == 1


def test_release_step_leaves_the_sweeps_known_list_alone(chroma, tmp_path):
    """8 Nov: known.ids (backup-check.sh REACH_KNOWN) sits beside the relink lists; read as one it named a
    collection 'known' and stopped every release."""
    store, url = chroma
    (tmp_path / "known.ids").write_text("a2\tan outlier its neighbours prune\n")
    done = release_step(url, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (tmp_path / "known.ids").exists() and not (tmp_path / "known.ids.done").exists()


def test_release_step_stops_when_chroma_does_not_answer(tmp_path):
    done = release_step("http://127.0.0.1:9", tmp_path)
    assert done.returncode != 0
