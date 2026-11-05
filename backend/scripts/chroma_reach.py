#!/usr/bin/env python3
"""Can every stored passage be found by document search?

An approximate index can hold a record that no search reaches: nothing links to it (no depth finds it), or the links
to it are so thin that the search stops before it. The word fallback does not cover this, because it runs only when
the vector search fails. Each record is asked for with its own stored vector, inside its own case, at the depth the app
searches, so a record found here is a record the app can find.

    chroma_reach.py check  --url URL [--collection chunks] [--out FILE] [--known FILE]   exit 1 on an unreached record
    chroma_reach.py sweep  --url URL [--collection chunks] [--out FILE]     the same at any depth, one search per case
    chroma_reach.py relink --url URL --collection NAME --ids FILE [--keep FILE] [--apply]  re-add from the stored copy
    chroma_reach.py settings --url URL [--apply]                            exit 10 when the setting was changed

Standard library only: the restore drill runs it with the system python3 against a scratch server. Reads make no
embedding call. relink deletes and adds the same id, vector, text and metadata, because a new entry gets links again;
`settings` changes a setting the server reads when it loads an index, so its caller restarts the server on exit 10.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from array import array
from collections import Counter

API = "api/v2/tenants/default_tenant/databases/default_database"
PAGE = 500
QUERY_BATCH = 32
TIED = 1e-6
# search_chunks: max(top_k * 5, top_k + 20) for CHUNK_SEARCH_TOP_K 50; search_entities: ENTITY_SEARCH_TOP_K.
DEPTHS = {"chunks": 250, "entities": 50}
# Above the rows of the largest case, a case-filtered search walks the whole index, so it finds every linked record.
# 2,000 found 47 of 52 thinly linked passages and 12,000 all 52 (largest case 9,438 rows, 5 Nov 2026). The search cost
# follows the size of the index, not this number. A case outgrowing it shows as unreached records in `check`.
EF_SEARCH = {"chunks": 50000}
# Above any run of identical passages, so a twin cannot hide the record the repair just added (5 Nov 2026: twins of 2).
RELINK_DEPTH = 20
# A deleted entry stays in the index. Once reachable, it sits exactly where the next add of the same vector goes, and
# the link rule then keeps it alone, so adding a record again and again cuts it off for good (48 adds left one record
# unreached, 5 Nov 2026). Two rounds at most; what is left is reported.
RELINK_ATTEMPTS = 2
FOLLOW_PASSES = 2


class Chroma:
    def __init__(self, url, pause=0.0):
        self.url = url.rstrip("/")
        self.pause = pause

    def call(self, path, body=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self.url}/{API}/{path}", data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=900) as response:
            answer = json.load(response)
        if self.pause:
            time.sleep(self.pause)
        return answer

    def collection(self, name):
        for found in self.call("collections"):
            if found["name"] == name:
                return found
        raise SystemExit(f"no collection named {name}")


def searched(metadata):
    """search_chunks drops every state but these; anything else is out of search on purpose."""
    return (metadata or {}).get("ingestion_state") in (None, "", "active")


def read_records(chroma, cid, include=("embeddings", "metadatas")):
    total = chroma.call(f"collections/{cid}/count")
    records, offset = [], 0
    while offset < total:
        got = chroma.call(f"collections/{cid}/get", {"limit": PAGE, "offset": offset, "include": list(include)})
        if not got["ids"]:
            break
        # Packed: as Python floats the vectors of a 35,000-record collection take about 1.7 GB.
        records += [(i, array("f", v), m) for i, v, m in zip(got["ids"], got["embeddings"], got["metadatas"])]
        offset += len(got["ids"])
    if len(records) != total:
        raise SystemExit(f"read {len(records)} of {total} records: refused, a partial read is no measurement")
    return records


def check(chroma, name, depth):
    """Every record against its own vector. Returns {"rows": n, "unreached": [...], "cases": {...}}."""
    cid = chroma.collection(name)["id"]
    by_case = {}
    for rid, vector, metadata in read_records(chroma, cid):
        by_case.setdefault((metadata or {}).get("case_id") or None, []).append((rid, vector, metadata or {}))
    unreached, tied, rows = [], 0, 0
    for case, records in sorted(by_case.items(), key=lambda item: len(item[1])):
        rows += len(records)
        for start in range(0, len(records), QUERY_BATCH):
            batch = records[start:start + QUERY_BATCH]
            body = {"query_embeddings": [r[1].tolist() for r in batch], "n_results": min(depth, len(records)),
                    "include": ["distances"]}
            if case is not None:
                body["where"] = {"case_id": case}
            answer = chroma.call(f"collections/{cid}/query", body)
            for (rid, vector, metadata), ids, distances in zip(batch, answer["ids"], answer["distances"]):
                if rid in ids:
                    continue
                # A full page of identical passages hides a twin. The text is found; it is not a fault of the index.
                if len(ids) >= depth and distances and distances[-1] < TIED:
                    tied += 1
                    continue
                deep = chroma.call(f"collections/{cid}/query", {**{k: body[k] for k in body if k != "query_embeddings"},
                                                                "query_embeddings": [vector.tolist()],
                                                                "n_results": len(records)})
                unreached.append({"id": rid, "case": case, "case_rows": len(records),
                                  "document": metadata.get("doc_name") or metadata.get("filename") or metadata.get("doc_id"),
                                  "state": metadata.get("ingestion_state"), "searched": searched(metadata),
                                  "any_depth": rid in deep["ids"][0]})
    return {"collection": name, "rows": rows, "depth": depth, "tied": tied, "cases": len(by_case),
            "largest_case": max((len(v) for v in by_case.values()), default=0), "unreached": unreached}


def sweep(chroma, name):
    """One search per case at the depth of the whole case. It walks everything linked, so what it does not return no
    search can reach: the same list as `check` at any depth, in a few searches, so it can run against a live server."""
    cid = chroma.collection(name)["id"]
    total, offset, by_case = chroma.call(f"collections/{cid}/count"), 0, {}
    while offset < total:
        got = chroma.call(f"collections/{cid}/get", {"limit": PAGE, "offset": offset, "include": ["metadatas"]})
        if not got["ids"]:
            break
        offset += len(got["ids"])
        for rid, metadata in zip(got["ids"], got["metadatas"]):
            by_case.setdefault((metadata or {}).get("case_id") or None, {})[rid] = metadata or {}
    unreached = []
    for case, records in by_case.items():
        probe = chroma.call(f"collections/{cid}/get", {"ids": [next(iter(records))], "include": ["embeddings"]})
        body = {"query_embeddings": probe["embeddings"], "n_results": len(records), "include": []}
        if case is not None:
            body["where"] = {"case_id": case}
        found = set(chroma.call(f"collections/{cid}/query", body)["ids"][0])
        for rid in records.keys() - found:
            metadata = records[rid]
            unreached.append({"id": rid, "case": case, "case_rows": len(records), "state": metadata.get("ingestion_state"),
                              "document": metadata.get("doc_name") or metadata.get("filename") or metadata.get("doc_id"),
                              "searched": searched(metadata), "any_depth": False})
    return {"collection": name, "rows": offset, "depth": "whole case", "tied": 0, "cases": len(by_case),
            "largest_case": max((len(v) for v in by_case.values()), default=0), "unreached": unreached}


def relink(chroma, name, ids, apply, attempts=RELINK_ATTEMPTS, keep=None):
    """Delete and add each record from its stored copy, then ask for all of them. The count must end where it began.

    Asked for after the whole list, not one by one: a record added later can take the only link of one added earlier
    (5 Nov 2026: 1 of 50 lost its link that way within the same run). A list may be old: an id no longer stored is
    reported as gone. Each record is read just before it is replaced, and written to `keep` before it is deleted, so
    a server that dies between the delete and the add loses nothing.
    """
    cid = chroma.collection(name)["id"]
    before = chroma.call(f"collections/{cid}/count")
    report = {"before": before, "ids": len(ids), "applied": bool(apply), "found": 0, "not_found": [], "gone": []}
    include = ["embeddings", "metadatas", "documents"]
    questions, pending = {}, list(ids)
    for _ in range(attempts if apply else 1):
        for rid in list(pending):
            got = chroma.call(f"collections/{cid}/get", {"ids": [rid], "include": include})
            if not got["ids"]:
                report["gone"].append(rid)
                pending.remove(rid)
                continue
            if not apply:
                continue
            vector, metadata = got["embeddings"][0], got["metadatas"][0]
            questions[rid] = {"query_embeddings": [vector], "n_results": RELINK_DEPTH, "include": ["distances"]}
            if metadata and metadata.get("case_id"):
                questions[rid]["where"] = {"case_id": metadata["case_id"]}
            record = {"ids": [rid], "embeddings": [vector], "metadatas": [metadata], "documents": got["documents"]}
            if keep:
                with open(keep, "a") as kept:
                    kept.write(json.dumps(record) + "\n")
            chroma.call(f"collections/{cid}/delete", {"ids": [rid]})
            chroma.call(f"collections/{cid}/add", record)
        pending = [rid for rid, question in questions.items()
                   if rid not in chroma.call(f"collections/{cid}/query", question)["ids"][0]]
        if not pending:
            break
    report["found"], report["not_found"] = len(questions) - len(pending), pending
    report["after"] = chroma.call(f"collections/{cid}/count")
    return report


def follow(chroma, name, tried, report, keep):
    """A record added can take the only link of a neighbour, so sweep after a repair and repair what that cost."""
    tried = set(tried)
    for _ in range(FOLLOW_PASSES):
        fresh = [u["id"] for u in sweep(chroma, name)["unreached"] if u["searched"] and u["id"] not in tried]
        if not fresh:
            break
        tried.update(fresh)
        more = relink(chroma, name, fresh, True, keep=keep)
        report["found"] += more["found"]
        report["not_found"] += more["not_found"]
        report["followed"] = report.get("followed", 0) + len(fresh)
        report["after"] = more["after"]
    report["unreached_after"] = [u["id"] for u in sweep(chroma, name)["unreached"] if u["searched"]]


def settings(chroma, apply):
    """The search setting each collection should hold. True when a setting was changed."""
    changed = False
    for name, ef_search in EF_SEARCH.items():
        found = next((c for c in chroma.call("collections") if c["name"] == name), None)
        if found is None:
            print(f"{name}: no collection yet")
            continue
        now = ((found.get("configuration_json") or {}).get("hnsw") or {}).get("ef_search")
        print(f"{name}: ef_search {now}, wanted {ef_search}")
        if now != ef_search and apply:
            chroma.call(f"collections/{found['id']}", {"new_configuration": {"hnsw": {"ef_search": ef_search}}}, "PUT")
            changed = True
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "sweep", "relink", "settings"])
    parser.add_argument("--url", required=True)
    parser.add_argument("--collection", action="append")
    parser.add_argument("--ids")
    parser.add_argument("--out")
    parser.add_argument("--known", help="ids (first column) already listed with why: shown, and not a failure")
    parser.add_argument("--keep", help="relink: each record is appended here before it is deleted")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between calls, for a server people are using")
    args = parser.parse_args(argv)
    chroma = Chroma(args.url, args.pause)
    if args.action == "settings":
        return 10 if settings(chroma, args.apply) else 0
    if args.action == "relink":
        name = args.collection[0]
        ids = [line.strip() for line in open(args.ids) if line.strip()]
        report = relink(chroma, name, ids, args.apply, keep=args.keep)
        if args.apply:
            follow(chroma, name, ids, report, args.keep)
        print(json.dumps(report))
        # A record left unreached is reported and stays where it was; only a changed count means something was lost.
        return 1 if report.get("after", report["before"]) != report["before"] else 0
    names = args.collection or list(DEPTHS)
    if args.action == "sweep":
        reports = [sweep(chroma, name) for name in names]
    else:
        reports = [check(chroma, name, DEPTHS[name]) for name in names]
    if args.out:
        with open(args.out, "w") as out:
            json.dump(reports, out)
    known = set()
    if args.known and os.path.exists(args.known):
        with open(args.known) as listed:
            known = {line.split("\t")[0].strip() for line in listed if line.strip()}
    failed = 0
    for report in reports:
        missing = [u for u in report["unreached"] if u["searched"]]
        failed += sum(u["id"] not in known for u in missing)
        where = Counter(str(u["case"]) for u in missing).most_common(3)
        print(f"{report['collection']}: {report['rows'] - len(report['unreached'])} of {report['rows']} found at depth "
              f"{report['depth']}, {len(missing)} searched records unreached "
              f"({sum(not u['any_depth'] for u in missing)} at any depth, "
              f"{sum(u['id'] in known for u in missing)} already listed), largest case {report['largest_case']}"
              + (f", most in {where}" if where else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
