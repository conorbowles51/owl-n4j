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
        # max_neighbors 32: already built with enough links, so `rebuild` leaves them; a test sets 16 to rebuild.
        self.collections = {"chunks": {"id": "c1", "name": "chunks", "metadata": {"description": "chunks"},
                                       "configuration_json": {"hnsw": {"ef_search": 100, "max_neighbors": 32}}},
                            "entities": {"id": "e1", "name": "entities", "metadata": None,
                                         "configuration_json": {"hnsw": {"ef_search": 100, "max_neighbors": 32}}}}
        self.records = {"c1": {}, "e1": {}}
        self.lossy = {"c1", "e1"}  # collections whose index loses the orphans; one made by a rebuild links them all
        self.drop_next_upsert = False
        self.skip_in_next_page = False  # a page read by offset misses a record (one deleted ahead of it meanwhile)
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

        def do_DELETE(self):
            found = store.collections.pop(self.path.split("/")[-1])
            store.records.pop(found["id"])
            store.writes.append("drop")
            self._send({})

        def do_PUT(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            for c in list(store.collections.values()):
                if c["id"] == self.path.split("/")[-1]:
                    if "new_name" in body:
                        if body["new_name"] in store.collections:
                            return self._send({"error": "exists"}, 409)
                        store.collections[body["new_name"]] = store.collections.pop(c["name"])
                        c["name"] = body["new_name"]
                        store.writes.append("rename")
                    else:
                        c["configuration_json"]["hnsw"].update(body["new_configuration"]["hnsw"])
                        store.writes.append("settings")
            self._send({})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.endswith("/collections"):
                made = {"id": f"n{len(store.records)}", "name": body["name"], "metadata": body.get("metadata"),
                        "configuration_json": json.loads(json.dumps(body["configuration"]))}
                store.collections[body["name"]] = made
                store.records[made["id"]] = {}
                store.writes.append("create")
                return self._send(made)
            cid, action = self.path.split("/")[-2:]
            records = store.records[cid]
            if action == "get":
                ids = body.get("ids") or list(records)[body["offset"]:body["offset"] + body["limit"]]
                if store.skip_in_next_page and not body.get("ids") and len(ids) > 1:
                    store.skip_in_next_page = False
                    ids = ids[1:]
                ids = [i for i in ids if i in records]
                return self._send({"ids": ids, "embeddings": [records[i]["vector"] for i in ids],
                                   "metadatas": [records[i]["metadata"] for i in ids],
                                   "documents": [records[i]["document"] for i in ids]})
            if action == "query":
                ids_out, dist_out = [], []
                case = (body.get("where") or {}).get("case_id")
                for q in body["query_embeddings"]:
                    pool = [i for i in records if not case or records[i]["metadata"]["case_id"] == case]
                    lossy = cid in store.lossy
                    pool = [i for i in pool if not (lossy and i in store.orphans)
                            and (not lossy or i not in store.thin or body["n_results"] >= len(pool))]
                    pool.sort(key=lambda i: abs(records[i]["vector"][0] - q[0]))
                    pool = pool[:body["n_results"]]
                    ids_out.append(pool)
                    dist_out.append([abs(records[i]["vector"][0] - q[0]) for i in pool])
                return self._send({"ids": ids_out, "distances": dist_out})
            store.writes.append(action)
            if action == "delete":
                for i in body["ids"]:
                    records.pop(i, None)
            if action == "upsert":
                ids = body["ids"][:-1] if store.drop_next_upsert and len(body["ids"]) > 1 else body["ids"]
                store.drop_next_upsert = False
                for n, rid in enumerate(ids):
                    records[rid] = {"vector": body["embeddings"][n], "metadata": body["metadatas"][n],
                                    "document": body["documents"][n]}
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


def few_links(store):
    for c in store.collections.values():
        c["configuration_json"]["hnsw"].update({"max_neighbors": 16, "space": "l2", "ef_construction": 100})
        c["configuration_json"]["embedding_function"] = {"type": "known", "name": "default", "config": {}}


def test_rebuild_dry_run_changes_nothing(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    store.add("c1", "a0", "case-a")
    done = run("rebuild", "--url", url, "--state", str(tmp_path))
    assert done.returncode == 0 and store.writes == [], done.stdout + done.stderr
    assert '"links": [16, 32]' in done.stdout


def test_rebuild_links_every_record_and_keeps_each_one_as_it_was(chroma, tmp_path):
    """10 Nov 2026: 5 of 47,531 chunks no search could reach at 16 links, one of them past any re-add."""
    store, url = chroma
    few_links(store)
    for i in range(5):
        store.add("c1", f"a{i}", "case-a")
    store.add("c1", "b0", "case-b")
    store.add("e1", "e0", "case-a")
    store.orphans.update({"a1", "b0"})
    before = json.loads(json.dumps(store.records["c1"]))
    assert run("sweep", "--url", url, "--collection", "chunks").returncode == 1
    done = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply")
    assert done.returncode == 0, done.stdout + done.stderr
    chunks = store.collections["chunks"]
    assert chunks["id"] != "c1" and chunks["configuration_json"]["hnsw"]["max_neighbors"] == 32
    assert chunks["configuration_json"]["hnsw"]["space"] == "l2"
    assert chunks["configuration_json"]["hnsw"]["ef_search"] == 50000
    assert chunks["configuration_json"]["embedding_function"]["name"] == "default"
    assert chunks["metadata"] == {"description": "chunks"}
    assert store.records[chunks["id"]] == before
    assert store.collections["chunks__before_rebuild"]["id"] == "c1"
    assert "chunks__rebuild" not in store.collections
    assert run("sweep", "--url", url, "--known", "/none").returncode == 0
    assert '"unreached": [2, 0]' in done.stdout
    again = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply")
    assert "chunks: null" in again.stdout and "entities: null" in again.stdout


def test_catch_up_carries_over_what_the_old_one_took_after_the_swap(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    assert run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks").returncode == 0
    new = store.collections["chunks"]["id"]
    # The old backend, holding c1 by its id until it restarts: one add, one delete, one metadata change.
    store.add("c1", "late", "case-a")
    store.records["c1"].pop("a0")
    store.records["c1"]["a1"]["metadata"] = {**store.records["c1"]["a1"]["metadata"], "folder": "moved"}
    # The new backend meanwhile changes a record only in the new collection: left alone.
    store.records[new]["a2"]["metadata"] = {**store.records[new]["a2"]["metadata"], "folder": "new side"}
    done = run("catch-up", "--url", url, "--state", str(tmp_path), "--collection", "chunks")
    assert done.returncode == 0, done.stdout + done.stderr
    assert '"written": 2, "deleted": 1' in done.stdout
    assert set(store.records[new]) == {"a1", "a2", "late"}
    assert store.records[new]["a1"]["metadata"]["folder"] == "moved"
    assert store.records[new]["a2"]["metadata"]["folder"] == "new side"
    writes = list(store.writes)
    assert run("catch-up", "--url", url, "--state", str(tmp_path), "--collection", "chunks").returncode == 0
    assert store.writes == writes, "a second catch-up writes nothing"
    assert run("clean-up", "--url", url, "--state", str(tmp_path), "--collection", "chunks").returncode == 0
    assert "chunks__before_rebuild" not in store.collections and (tmp_path / "chunks.rebuild.json.done").exists()


def test_a_copy_made_ahead_is_swapped_in_by_the_release_with_what_changed_since(chroma, tmp_path):
    """The copy takes about an hour on live; made while the app runs, the release only carries over and swaps."""
    store, url = chroma
    few_links(store)
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    ahead = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--build-only", "--collection", "chunks")
    assert ahead.returncode == 0, ahead.stdout + ahead.stderr
    assert store.collections["chunks"]["id"] == "c1" and "chunks__rebuild" in store.collections
    build = store.collections["chunks__rebuild"]["id"]
    for step in ("catch-up", "clean-up"):
        left = run(step, "--url", url, "--state", str(tmp_path), "--collection", "chunks")
        assert "copy made, not swapped in yet" in left.stdout and "chunks__rebuild" in store.collections
    store.add("c1", "later", "case-a")          # the app goes on writing before the release
    store.records["c1"].pop("a0")
    release = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks")
    assert release.returncode == 0, release.stdout + release.stderr
    assert '"copied_before": 3' in release.stdout and '"since_copy": {"written": 1, "deleted": 1' in release.stdout
    assert store.collections["chunks"]["id"] == build
    assert set(store.records[build]) == {"a1", "a2", "later"}


def test_clean_up_waits_for_the_catch_up(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    store.add("c1", "a0", "case-a")
    assert run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks").returncode == 0
    done = run("clean-up", "--url", url, "--state", str(tmp_path), "--collection", "chunks")
    assert "waiting for catch-up" in done.stdout and "chunks__before_rebuild" in store.collections


def test_a_record_the_copy_missed_is_carried_over_before_the_swap(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.skip_in_next_page = True
    done = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks")
    assert done.returncode == 0, done.stdout + done.stderr
    assert '"copied": 2, "since_copy": {"written": 1, "deleted": 0, "old": 3, "new": 3}' in done.stdout
    assert set(store.records[store.collections["chunks"]["id"]]) == {"a0", "a1", "a2"}


def test_a_write_the_copy_lost_is_refused(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.drop_next_upsert = True
    done = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks")
    assert '"refused": "counts differ"' in done.stdout, done.stdout + done.stderr
    assert store.collections["chunks"]["id"] == "c1"


def test_a_copy_whose_count_differs_is_refused_and_the_old_one_keeps_serving(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.records["c1"] = CountsLie(store.records["c1"])
    done = run("rebuild", "--url", url, "--state", str(tmp_path), "--apply", "--collection", "chunks")
    assert done.returncode == 0, done.stdout + done.stderr
    assert '"refused": "counts differ"' in done.stdout
    assert store.collections["chunks"]["id"] == "c1" and "chunks__rebuild" not in store.collections
    assert not (tmp_path / "chunks.rebuild.json").exists()


class CountsLie(dict):
    """The old collection says it holds one more record than any read returns."""
    def __len__(self):
        return dict.__len__(self) + 1


def release_step(url, tmp_path):
    docker = tmp_path / "docker"
    docker.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/docker.calls\n')
    docker.chmod(0o755)
    return subprocess.run(["bash", str(SETTINGS)], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "CHROMA_URL": url, "DOCKER": str(docker), "READY_TRIES": "3",
                               "CHROMA_RELINK_LISTS": str(tmp_path), "CHROMA_REBUILD_STATE": str(tmp_path / "rebuild")})


def test_release_step_rebuilds_once_catches_up_after_the_restart_then_removes_the_old_one(chroma, tmp_path):
    store, url = chroma
    few_links(store)
    store.add("c1", "a0", "case-a")
    store.orphans.add("a0")
    first = release_step(url, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "chroma: rebuild chunks:" in first.stdout and "chunks__before_rebuild" in store.collections
    store.add("c1", "late", "case-a")   # the old backend writes before it stops
    docker = tmp_path / "docker"
    after = subprocess.run(["bash", str(SETTINGS), "catch-up"], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "CHROMA_URL": url, "DOCKER": str(docker),
                                "CHROMA_REBUILD_STATE": str(tmp_path / "rebuild")})
    assert after.returncode == 0, after.stdout + after.stderr
    assert "late" in store.records[store.collections["chunks"]["id"]]
    second = release_step(url, tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "chunks__before_rebuild" not in store.collections and "entities__before_rebuild" not in store.collections
    assert run("sweep", "--url", url).returncode == 0


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


def test_sweep_queues_what_it_cannot_reach_and_the_release_repairs_it(chroma, tmp_path):
    """11 Nov: the daily sweep listed 18 unreached chunks and alerted, and nothing repaired them."""
    store, url = chroma
    for i in range(3):
        store.add("c1", f"a{i}", "case-a")
    store.orphans.update({"a1", "a2"})
    known = tmp_path / "known.ids"
    known.write_text("a2\tan outlier its neighbours prune\n")
    for _ in range(2):   # a second sweep before the release lists nothing twice
        done = run("sweep", "--url", url, "--collection", "chunks", "--known", str(known), "--queue", str(tmp_path))
        assert done.returncode == 1, done.stdout + done.stderr
    assert (tmp_path / "chunks.ids").read_text() == "a1\n"
    released = release_step(url, tmp_path)
    assert released.returncode == 0, released.stdout + released.stderr
    assert "a1" not in store.orphans and (tmp_path / "chunks.ids.done").exists()


def test_a_clean_sweep_queues_nothing(chroma, tmp_path):
    store, url = chroma
    store.add("c1", "a0", "case-a")
    assert run("sweep", "--url", url, "--queue", str(tmp_path)).returncode == 0
    assert not list(tmp_path.glob("*.ids"))
