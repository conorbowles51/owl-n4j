"""Graph entity summaries: cite each page by its evidence file id instead of its file name.

The engine wrote summary links as doc://<file name>/<page> (evidence-engine generate_summaries._document_citation);
a link by name opens only when the case holds exactly one live file of that name. On 17 Nov 2026, 5,166 of the 37,140
such links named a file the case holds more than once and 21 named none. The engine now writes doc://<file id>/<page>
from the fact's source location; this rewrites the links already stored, by the same rule:

- the file id the entity's own sources (verified_facts[].source_location, source_locations[]) give for that file
  name, when they give exactly one;
- else the one live file of that name in the case;
- else the link stays as written and is counted.

Only the link target changes; the words of the summary and the link's label stay as they were. Each node is written
only if its summary is still the one read (a summary regenerated meanwhile is left alone).

    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/summary_citations_by_id.py [--case <uuid>] [--apply]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import unquote

_LINK = re.compile(r"\]\(\s*doc://([^)/\s]+)(?:/(\d+))?\s*\)")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _locations(raw) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [item for item in raw or [] if isinstance(item, dict)]


def entity_file_ids(verified_facts, source_locations) -> dict[str, set[str]]:
    """{file name: {evidence file ids}} from the entity's own stored sources."""
    found: dict[str, set[str]] = defaultdict(set)
    places = [fact.get("source_location") for fact in _locations(verified_facts)] + _locations(source_locations)
    for place in places:
        if not isinstance(place, dict):
            continue
        name = str(place.get("source_file") or "").strip()
        file_id = str(place.get("source_document_id") or "").strip().lower()
        if name and _UUID.match(file_id):
            found[name].add(file_id)
    return found


def rewrite(summary: str, own: dict[str, set[str]], case_files: dict[str, list[str]], live_ids: set[str]):
    """(new summary, Counter of outcomes). ``case_files``: {file name: [live file ids]}; ``live_ids``: the case's
    live file ids (an id is used only when it is one of them)."""
    counts: Counter = Counter()

    def replace(match):
        target, page = match.group(1), match.group(2)
        name = unquote(target)
        if _UUID.match(name):
            counts["already_by_id"] += 1
            return match.group(0)
        mine = sorted(i for i in own.get(name, ()) if i in live_ids)
        theirs = case_files.get(name) or []
        file_id = mine[0] if len(mine) == 1 else (theirs[0] if len(theirs) == 1 else None)
        if file_id is None:
            counts["left_no_file" if not theirs and not mine else "left_ambiguous"] += 1
            return match.group(0)
        counts["by_entity_source" if len(mine) == 1 else "by_only_file"] += 1
        return f"](doc://{file_id}/{page})" if page else f"](doc://{file_id})"

    return _LINK.sub(replace, summary or ""), counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    from sqlalchemy import text
    from postgres.session import _get_session_local
    from services.neo4j.driver import open_driver

    driver = open_driver()
    with driver.session() as session:
        rows = list(session.run(
            "MATCH (n) WHERE n.summary CONTAINS '](doc://' AND ($case IS NULL OR n.case_id = $case) "
            "RETURN elementId(n) AS node, n.case_id AS case_id, n.summary AS summary, "
            "n.verified_facts AS facts, n.source_locations AS locations", case=args.case))
    files: dict[str, tuple[dict, set]] = {}
    with _get_session_local()() as db:
        for case_id in sorted({str(r["case_id"]) for r in rows if r["case_id"]}):
            by_name: dict[str, list[str]] = defaultdict(list)
            for file_id, name in db.execute(text(
                    "SELECT id::text, original_filename FROM evidence_files WHERE case_id = CAST(:c AS uuid) "
                    "AND deleted_at IS NULL"), {"c": case_id}):
                by_name[name].append(file_id)
            files[case_id] = (by_name, {i for ids in by_name.values() for i in ids})
        db.rollback()
    totals: dict[str, Counter] = defaultdict(Counter)
    changes = []
    for r in rows:
        case_id = str(r["case_id"] or "")
        if case_id not in files:
            continue
        by_name, live = files[case_id]
        new, counts = rewrite(r["summary"], entity_file_ids(r["facts"], r["locations"]), by_name, live)
        totals[case_id].update(counts)
        if new != r["summary"]:
            totals[case_id]["nodes_changed"] += 1
            changes.append((r["node"], r["summary"], new))
    for case_id, counts in sorted(totals.items()):
        print(case_id, dict(sorted(counts.items())))
    grand = sum(totals.values(), Counter())
    print("all cases", dict(sorted(grand.items())))
    if not args.apply:
        print(f"dry run: {len(changes)} summaries would change; --apply writes them")
        driver.close()
        return 0
    written = 0
    with driver.session() as session:
        for node, old, new in changes:
            result = session.run("MATCH (n) WHERE elementId(n) = $node AND n.summary = $old SET n.summary = $new "
                                 "RETURN count(n) AS n", node=node, old=old, new=new).single()
            written += result["n"]
    driver.close()
    print(f"written: {written} of {len(changes)} (a summary changed since it was read is left alone)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
