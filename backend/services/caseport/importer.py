"""Load a verified package into a new case, never over an existing one.

Every id of the case is remapped in one pass over the JSON text of each line, so soft references (citations, links in
a stored answer, keys in a graph property, paths) move with the rows, and a reading's text, numbers and marks stay
byte for byte what the package holds: a label's author and status are copied, never rewritten, and nothing is upgraded.
A token is replaced only when it is an id this package listed, so a UUID inside a document's own text is left alone.

PostgreSQL loads in one transaction with triggers off (they would refuse or re-audit rows that already carry their own
history), then every foreign key of the new case is checked. The graph, the vectors and the files are written before
that transaction commits; any failure removes them all, so a refused import leaves nothing behind. No embedding is
made: vectors travel with the package.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path

from . import inventory as I
from . import package as P
from . import stores as S
from .export import psycopg_url, schema_revision

log = logging.getLogger(__name__)
BATCH_ROWS = 1000
BATCH_BYTES = 8 * 1024 * 1024
TOKEN = re.compile(r"(?<![0-9a-f-])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
                   r"|(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])|\bsnapshot_[0-9T-]+")
PHONE_NS = uuid.UUID("8fa2f9a7-e6b9-4809-a082-208cf14fa25c")      # services/phone/ids.py
IDENTITY_NS = uuid.UUID("5c1f0a7e-3d2b-4b8e-9f61-2a7d4c8e0b13")   # services/phone/identities.py
SUBJECT_NS = uuid.UUID("b4d7f1a2-6c3e-4e8b-9f05-1d2c3b4a5e6f")    # services/phone_analysis/framework.py


class ImportRefused(Exception):
    """The package will not be loaded, for the reason stated."""


def check_compatible(manifest: dict, *, target_revision: str, known_revisions, target_tables: dict) -> list:
    """Why this package cannot load here; empty when it can.

    ``known_revisions``: every schema revision this code knows, oldest to newest. A package from a schema this code has
    never heard of is from a newer version. One from an older schema loads when its columns still fit: added columns
    take their defaults, and a removed column or a new required one refuses, naming it."""
    reasons = []
    version = manifest.get("format_version")
    if version not in P.SUPPORTED_FORMAT_VERSIONS:
        reasons.append(f"The package is format {version}; this version of Loupe reads format "
                       f"{', '.join(map(str, P.SUPPORTED_FORMAT_VERSIONS))}. Update Loupe, or export again from it.")
    revision = manifest.get("schema_revision")
    known = list(known_revisions)
    if revision not in known:
        reasons.append(f"The package is from a newer database schema ({revision}) than this site has ({target_revision}). "
                       "Update this site first.")
        return reasons
    if known.index(revision) > known.index(target_revision):
        reasons.append(f"The package is from a newer database schema ({revision}) than this site has ({target_revision}). "
                       "Update this site first.")
        return reasons
    for name, meta in (manifest.get("tables") or {}).items():
        table = target_tables.get(name)
        if table is None:
            reasons.append(f"Table {name} no longer exists here, so its rows have nowhere to go.")
            continue
        columns = set(meta["columns"])
        for gone in sorted(columns - set(table.columns)):
            reasons.append(f"Column {name}.{gone} no longer exists here.")
        for needed in sorted(table.required - columns):
            reasons.append(f"Column {name}.{needed} is required here and the older package has no value for it.")
    return reasons


def known_revisions() -> list:
    """Every schema revision of this code, oldest first (the chain from the base to the head)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    backend = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(backend / "postgres" / "alembic"))
    return [s.revision for s in ScriptDirectory.from_config(config).walk_revisions()][::-1]


class Remap:
    """Old value to new, for the ids a package lists."""

    def __init__(self, new_case: str):
        self.new_case = new_case
        self.namespace = uuid.UUID(new_case)
        self.table: dict = {}

    def add(self, old: str):
        if old in self.table:
            return
        if len(old) == 36:
            self.table[old] = str(uuid.uuid5(self.namespace, old))
        elif len(old) == 64:
            self.table[old] = hashlib.sha256(f"{self.new_case}|{old}".encode()).hexdigest()
        else:
            self.table[old] = f"{old}-{self.new_case[:8]}"

    def set(self, old: str, new: str):
        self.table[old] = new

    def text(self, line: str) -> str:
        table = self.table
        return TOKEN.sub(lambda m: table.get(m.group(0), m.group(0)), line)


def build_remap(reader, manifest, new_case: str, people: dict) -> Remap:
    """The whole id table: every listed id, the people, and the ids this application computes rather than stores
    (a later run looks those up by computing them, so they follow the same formula with the new ids)."""
    remap = Remap(new_case)
    for line in reader.lines("ids.txt.gz"):
        remap.add(line.strip())
    old_case = manifest["source_case"]["id"]
    remap.set(old_case, new_case)
    for old, new in people.items():
        remap.set(old, new)
    for line in reader.lines("pg/phone_records.jsonl.gz"):
        row = json.loads(line)
        ext, doc, ordinal = row["extraction_id"], row["document_index"], row["ordinal"]
        remap.set(str(uuid.uuid5(PHONE_NS, f"{ext}/{doc}/r{ordinal}")),
                  str(uuid.uuid5(PHONE_NS, f"{remap.table.get(ext, ext)}/{doc}/r{ordinal}")))
    for line in reader.lines("pg/phone_files.jsonl.gz"):
        row = json.loads(line)
        ext, doc, ordinal = row["extraction_id"], row["document_index"], row["ordinal"]
        remap.set(str(uuid.uuid5(PHONE_NS, f"{ext}/{doc}/f{ordinal}")),
                  str(uuid.uuid5(PHONE_NS, f"{remap.table.get(ext, ext)}/{doc}/f{ordinal}")))
    for line in reader.lines("pg/phone_identities.jsonl.gz"):
        row = json.loads(line)
        remap.set(row["id"], str(uuid.uuid5(IDENTITY_NS, f"{new_case}|{row['identity_key']}")))
    for line in reader.lines("pg/phone_analysis_result_subjects.jsonl.gz"):
        row = json.loads(line)
        remap.set(row["id"], str(uuid.uuid5(SUBJECT_NS, f"{new_case}|{row['approach']}|{row['result_key']}")))
    for line in reader.lines("pg/timeline_entries.jsonl.gz"):
        row = json.loads(line)
        kind, source = row["source_kind"], row["source_id"]
        remap.set(str(uuid.uuid5(uuid.NAMESPACE_URL, f"loupe:{old_case}:{kind}:{source}")),
                  str(uuid.uuid5(uuid.NAMESPACE_URL, f"loupe:{new_case}:{kind}:{remap.table.get(source, source)}")))
    return remap


def _insert(cur, name, columns, offsets, lines):
    if not lines:
        return
    quoted = I._quote(name)
    targets = ", ".join(I._quote(c) for c in columns)
    values = ", ".join(f"{I._quote(c)} + {offsets[c]}" if c in offsets else I._quote(c) for c in columns)
    # OVERRIDING SYSTEM VALUE: the ids were reserved from the sequence (offsets), and a GENERATED ALWAYS identity
    # column (the pol_* tables) refuses any explicit value without it.
    cur.execute(f"INSERT INTO {quoted} ({targets}) OVERRIDING SYSTEM VALUE SELECT {values} "
                f"FROM json_populate_recordset(NULL::{quoted}, %s::json)", ("[" + ",".join(lines) + "]",))


def _load_table(cur, reader, name, columns, remap, paths, offsets) -> int:
    rows = 0
    batch: list = []
    size = 0
    for line in reader.lines(f"pg/{name}.jsonl.gz"):
        text = paths(remap.text(line))
        batch.append(text)
        size += len(text)
        rows += 1
        if len(batch) >= BATCH_ROWS or size >= BATCH_BYTES:
            _insert(cur, name, columns, offsets, batch)
            batch, size = [], 0
    _insert(cur, name, columns, offsets, batch)
    return rows


def _load_audit_chain(cur, reader, columns, remap, paths) -> int:
    """Financial audit events are a hash chain over their payloads, and a payload names its case. The payloads move to
    the new ids, so the chain is computed again over them, by the rule of guard_financial_audit_insert. The original
    chain's head is kept in the import's trail entry; the package itself keeps every original link."""
    previous = "0" * 64
    rows = 0
    batch: list = []
    for line in reader.lines("pg/financial_audit_events.jsonl.gz"):
        row = json.loads(paths(remap.text(line)))
        digest = hashlib.sha256(bytes.fromhex(previous) + row["payload_text"].encode("utf-8")).hexdigest()
        row["previous_sha256"], row["entry_sha256"] = previous, digest
        previous = digest
        batch.append(json.dumps(row, ensure_ascii=False))
        rows += 1
        if len(batch) >= BATCH_ROWS:
            _insert(cur, "financial_audit_events", columns, {}, batch)
            batch = []
    _insert(cur, "financial_audit_events", columns, {}, batch)
    return rows


def resolve_people(cur, reader) -> tuple:
    """Each person named in the package, as a user of this site: the same email is the same person; anyone else gets
    an account that cannot sign in, so their name stays on what they did and they gain no access."""
    people, added = {}, 0
    for line in reader.lines("people.jsonl.gz"):
        row = json.loads(line)
        found = cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (row["email"],)).fetchone()
        if found:
            people[row["id"]] = str(found[0])
            continue
        new_id = str(uuid.uuid4())
        cur.execute("INSERT INTO users (id, email, name, password_hash, global_role, is_active) "
                    "VALUES (%s, %s, %s, %s, 'user', false)", (new_id, row["email"], row["name"], "!imported-no-sign-in"))
        people[row["id"]] = new_id
        added += 1
    return people, added


def _load_references(cur, reader, inv) -> dict:
    """Installation rows the case points at, added when this site lacks them. A row already here is not changed."""
    counts = {}
    for name in I.REFERENCE_TABLES + ("phone_mapping_rows",):
        if name not in inv.tables:
            continue
        table = inv.tables[name]
        quoted = I._quote(name)
        columns = [c for c in table.columns if c not in table.generated]
        targets = ", ".join(I._quote(c) for c in columns)
        before = cur.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
        batch = []
        for line in reader.lines(f"reference/{name}.jsonl.gz"):
            batch.append(line)
            if len(batch) >= BATCH_ROWS:
                cur.execute(f"INSERT INTO {quoted} ({targets}) SELECT {targets} FROM "
                            f"json_populate_recordset(NULL::{quoted}, %s::json) ON CONFLICT DO NOTHING",
                            ("[" + ",".join(batch) + "]",))
                batch = []
        if batch:
            cur.execute(f"INSERT INTO {quoted} ({targets}) SELECT {targets} FROM "
                        f"json_populate_recordset(NULL::{quoted}, %s::json) ON CONFLICT DO NOTHING",
                        ("[" + ",".join(batch) + "]",))
        counts[name] = cur.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0] - before
    return counts


def _check_foreign_keys(cur, inv, loaded, new_case) -> list:
    """Every foreign key of every loaded table, over the new case's rows only."""
    broken = []
    for name in loaded:
        table = inv.tables[name]
        for cols, target, target_cols, _ in table.foreign_keys:
            if target == "cases":
                continue
            joined = " AND ".join(f"p.{I._quote(tc)} = t.{I._quote(c)}" for c, tc in zip(cols, target_cols))
            present = " AND ".join(f"t.{I._quote(c)} IS NOT NULL" for c in cols)
            where = I.scope_where(inv, name, "t").replace("%(case)s", "%s")
            n = cur.execute(f"SELECT count(*) FROM {I._quote(name)} t WHERE {where} AND {present} AND NOT EXISTS "
                            f"(SELECT 1 FROM {I._quote(target)} p WHERE {joined})",
                            (new_case,) * where.count("%s")).fetchone()[0]
            if n:
                broken.append(f"{name}.{','.join(cols)}: {n} rows point at nothing in {target}")
    return broken


def _sequence_offsets(cur, inv, reader, manifest) -> dict:
    """{table: {column: offset}}: integer ids move past this site's sequence, keeping their order and references."""
    offsets: dict = {}
    for name, meta in (manifest.get("tables") or {}).items():
        table = inv.tables[name]
        column = table.sequence_column
        if not column or column not in meta["columns"]:
            continue
        low = high = None
        for line in reader.lines(f"pg/{name}.jsonl.gz"):
            value = json.loads(line)[column]
            low = value if low is None else min(low, value)
            high = value if high is None else max(high, value)
        if low is None:
            continue
        start = cur.execute("SELECT nextval(%s)", (table.sequence_name,)).fetchone()[0]
        offset = start - low
        cur.execute("SELECT setval(%s, %s)", (table.sequence_name, high + offset))
        offsets.setdefault(name, {})[column] = offset
        for ref_table, ref_column in I.SEQUENCE_REFERENCES.get(name, (None, ()))[1]:
            offsets.setdefault(ref_table, {})[ref_column] = offset
    return offsets


def _load_graph(graph, reader, remap, new_case) -> dict:
    mapping: dict = {}
    groups: dict = {}

    def flush(labels):
        rows = groups.pop(labels, [])
        if rows:
            mapping.update(graph.create_nodes(list(labels), rows))

    nodes = 0
    for line in reader.lines("neo4j/nodes.jsonl.gz"):
        row = json.loads(remap.text(line))
        labels = tuple(row["l"])
        groups.setdefault(labels, []).append({"i": row["i"], "p": S.decode_graph_props(row["p"])})
        nodes += 1
        if len(groups[labels]) >= 1000:
            flush(labels)
    for labels in list(groups):
        flush(labels)
    rels = 0
    by_type: dict = {}

    def flush_rels(rel_type):
        nonlocal rels
        rows = by_type.pop(rel_type, [])
        if rows:
            rels += graph.create_relationships(rel_type, rows)

    for line in reader.lines("neo4j/relationships.jsonl.gz"):
        row = json.loads(remap.text(line))
        by_type.setdefault(row["t"], []).append(
            {"a": mapping[row["a"]], "b": mapping[row["b"]], "p": S.decode_graph_props(row["p"])})
        if len(by_type[row["t"]]) >= 1000:
            flush_rels(row["t"])
    for rel_type in list(by_type):
        flush_rels(rel_type)
    return {"nodes": nodes, "relationships": rels}


def _load_vectors(vectors, reader, remap) -> dict:
    counts, clashes = {}, {}
    for collection in S.COLLECTIONS:
        batch: list = []
        loaded = 0

        def flush():
            nonlocal batch, loaded
            if not batch:
                return
            held = vectors.existing(collection, [r["id"] for r in batch])
            fresh = [r for r in batch if r["id"] not in held]
            if held:
                # An id with no UUID in it (an old hand-made entity key) is shared with the case it came from; adding
                # it would replace that case's vector. It stays out and the import says so.
                clashes[collection] = clashes.get(collection, 0) + len(held)
            if fresh:
                vectors.add(collection, fresh)
                loaded += len(fresh)
            batch = []

        for line in reader.lines(f"vectors/{collection}.jsonl.gz"):
            batch.append(json.loads(remap.text(line)))
            if len(batch) >= S.PAGE:
                flush()
        flush()
        counts[collection] = loaded
    return {"loaded": counts, "not_loaded_id_in_use": clashes}


def _copy_evidence(reader, remap, evidence_root: Path, source_root: str, done: list) -> dict:
    files = size = 0
    bad = []
    for line in reader.lines("evidence-index.jsonl.gz"):
        entry = json.loads(line)
        target = evidence_root / remap.text(entry["path"])
        if target.exists():
            raise ImportRefused(f"{target} already exists: an import never writes over a file.")
        done.append(target)
        sha = reader.copy_evidence(entry["path"], target)
        if sha != entry["sha256"]:
            bad.append(entry["path"])
        files += 1
        size += entry["size"]
    if bad:
        raise ImportRefused(f"{len(bad)} evidence files changed while being copied, first {bad[0]}.")
    return {"files": files, "bytes": size}


def run_import(url, package_path, *, by_email, evidence_root, graph=None, vectors=None, title=None,
               revisions=None) -> dict:
    """Verify the package and load it into a new case owned by ``by_email``, who must have an active account here.
    Returns the report; raises ImportRefused with the reason, leaving nothing behind."""
    import psycopg
    package_path = Path(package_path)
    result = P.verify(package_path)
    if not result["ok"]:
        raise ImportRefused("The package failed verification: " + "; ".join(result["problems"][:10]))
    manifest = result["manifest"]
    new_case = str(uuid.uuid4())
    evidence_root = Path(evidence_root)
    reader = P.PackageReader(package_path)
    written: list = []
    graph_touched = vectors_touched = False
    try:
        with psycopg.connect(psycopg_url(url), application_name="loupe-case-import", autocommit=False) as conn:
            cur = conn.cursor()
            inv = I.classify(I.read_catalog(conn))
            revision = schema_revision(conn)
            reasons = check_compatible(manifest, target_revision=revision,
                                       known_revisions=revisions or known_revisions(), target_tables=inv.tables)
            if reasons:
                raise ImportRefused(" ".join(reasons))
            owner = cur.execute("SELECT id, email, name, is_active FROM users WHERE lower(email) = lower(%s)",
                                (by_email,)).fetchone()
            if owner is None or not owner[3]:
                raise ImportRefused(f"{by_email} has no active account on this site; the imported case needs an owner.")
            if vectors is not None:
                for collection in S.COLLECTIONS:
                    if manifest.get("vectors", {}).get(collection):
                        here = vectors.dimension(collection)
                        sample = next(reader.lines(f"vectors/{collection}.jsonl.gz"), None)
                        if here is not None and sample and len(json.loads(sample)["embedding"]) != here:
                            raise ImportRefused(f"The package's {collection} vectors have a different size from this "
                                                "site's, so they cannot be searched here.")
            try:
                cur.execute("SET LOCAL session_replication_role = replica")
            except psycopg.Error as exc:
                raise ImportRefused("The database account may not load rows with their history intact "
                                    f"(session_replication_role): {exc}") from exc
            people, people_added = resolve_people(cur, reader)
            remap = build_remap(reader, manifest, new_case, people)
            source_root = manifest["evidence_root"].rstrip("/") + "/"
            target_root = str(evidence_root).rstrip("/") + "/"
            paths = (lambda s: s.replace(source_root, target_root)) if source_root != target_root else (lambda s: s)
            references = _load_references(cur, reader, inv)
            offsets = _sequence_offsets(cur, inv, reader, manifest)

            case_row = json.loads(remap.text(next(reader.lines("pg/cases.jsonl.gz"))))
            case_row.update(owner_user_id=str(owner[0]), deleted_at=None, deleted_by_user_id=None)
            if title:
                case_row["title"] = title
            case_columns = [c for c in case_row if c in inv.tables["cases"].columns]
            _insert(cur, "cases", case_columns, {}, [json.dumps(case_row, ensure_ascii=False)])
            cur.execute("INSERT INTO case_memberships (case_id, user_id, membership_role, permissions, added_by_user_id) "
                        "VALUES (%s, %s, 'owner', %s::jsonb, %s)",
                        (new_case, owner[0], json.dumps(_owner_permissions()), owner[0]))

            loaded = {}
            for name, meta in manifest["tables"].items():
                if name in I.RECORD_ONLY:
                    continue
                if name == "financial_audit_events":
                    loaded[name] = _load_audit_chain(cur, reader, meta["columns"], remap, paths)
                else:
                    loaded[name] = _load_table(cur, reader, name, meta["columns"], remap, paths, offsets.get(name, {}))
            broken = _check_foreign_keys(cur, inv, list(loaded), new_case)
            if broken:
                raise ImportRefused("The loaded rows do not hold together: " + "; ".join(broken[:10]))
            mismatch = [f"{name}: {n} loaded, {manifest['parts'][f'pg/{name}.jsonl.gz']['rows']} in the package"
                        for name, n in loaded.items() if n != manifest["parts"][f"pg/{name}.jsonl.gz"]["rows"]]
            if mismatch:
                raise ImportRefused("Row counts differ: " + "; ".join(mismatch[:10]))
            files = _copy_evidence(reader, remap, evidence_root, source_root, written)
            graph_result = None
            if graph is not None and manifest.get("graph"):
                graph_touched = True
                graph_result = _load_graph(graph, reader, remap, new_case)
                if graph_result["nodes"] != manifest["graph"]["nodes"] or \
                        graph_result["relationships"] != manifest["graph"]["relationships"]:
                    raise ImportRefused(f"The graph loaded {graph_result}; the package holds {manifest['graph']}.")
            vector_result = None
            if vectors is not None and manifest.get("vectors"):
                vectors_touched = True
                vector_result = _load_vectors(vectors, reader, remap)
            report = {
                "case_id": new_case, "title": case_row["title"], "owner": owner[1], "tables": len(loaded),
                "rows": sum(loaded.values()), "rows_per_table": loaded, "evidence": files, "graph": graph_result,
                "vectors": vector_result, "people_added_without_sign_in": people_added, "reference_rows_added": references,
                "not_loaded": {t: f"{manifest['parts'][f'pg/{t}.jsonl.gz']['rows']} rows, kept in the package as a "
                               "record; access to the new case is given by its owner" for t in I.RECORD_ONLY},
                "package_sha256": result["sha256"], "source_case": manifest["source_case"],
                "source_app_sha": manifest.get("app_sha"), "source_schema": manifest.get("schema_revision"),
                "exported_by": manifest.get("exported_by"), "exported_at": manifest.get("created_at"),
                "source_host": manifest.get("host"),
                "source_financial_audit_head_sha256": manifest.get("financial_audit_head_sha256"),
            }
            trail = {k: v for k, v in report.items() if k != "rows_per_table"}
            cur.execute("INSERT INTO activity_events (action, user_id, user_name, user_email, case_id, source_address, "
                        "details) VALUES ('case_imported', %s, %s, %s, %s, 'system', %s::jsonb)",
                        (owner[0], owner[2], owner[1], new_case, json.dumps(trail, ensure_ascii=False, default=str)))
            conn.commit()
            return report
    except BaseException:
        for path in written:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        _remove_empty(evidence_root / new_case)
        if graph_touched:
            graph.delete_case(new_case)
        if vectors_touched:
            vectors.delete_case(new_case)
        raise
    finally:
        reader.close()


def _owner_permissions() -> dict:
    from postgres.permissions import OWNER_PERMISSIONS, clone_permissions
    return clone_permissions(OWNER_PERMISSIONS)


def _remove_empty(folder: Path):
    if not folder.exists():
        return
    for here, _, _ in os.walk(folder, topdown=False):
        try:
            os.rmdir(here)
        except OSError:
            pass
