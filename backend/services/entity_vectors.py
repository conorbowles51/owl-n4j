"""Entity meaning-search vectors kept in step with the graph (followups m11040658479405).

The evidence engine embeds each entity once, at ingestion (``evidence-engine/app/pipeline/write_graph.py``
``_embed_entities``). Before this module nothing refreshed that vector afterwards: an entity renamed or re-described
by an investigator (``PUT /api/graph/node/{key}``, batch update) or by a later merge was meaning-searched by its old
words. Measured on live 2026-11-04 07:40 UTC: 64 of 31,398 entity vectors held an older name or description than the
graph (4 of them renamed by a person).

- ``embedding_text`` builds the text the engine builds (``Category: name — description (aliases: …) Facts: …``), so a
  vector written here reads like one written at ingestion, plus the investigator's notes when there are any.
- ``refresh_entities`` re-embeds the given keys from the graph as it is now. It runs after every edit (in a thread,
  so the edit answers at once) and after a recycle-bin restore.
- ``stale_keys`` finds the vectors whose stored text no longer holds the entity's current name, description or notes.
  The meaning-search gap backfill (``meaning_search.run_gap_backfill``) runs it for every case when the embedding
  service answers again, so an edit whose re-embed was refused (no credits, an outage) is retried then.

Phone graph nodes are never embedded here (docs/cellebrite/02 section 9.8), as before.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from typing import Any, Callable, Iterable

from postgres.models.cost_record import CostJobType
from services.ai_costs_service import ai_cost_context

logger = logging.getLogger(__name__)

MATCH_PREFIX = 150  # characters of description / notes that must appear in the stored text
MAX_FACTS = 5  # the engine embeds the first five verified facts
# Fields whose change changes the text an entity is searched by.
SEARCH_FIELDS = frozenset({"name", "description", "notes", "aliases", "verified_facts", "category", "type"})
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _aliases(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            value = [part.strip() for part in value.split(",")]
    return [str(a).strip() for a in (value or []) if str(a or "").strip()]


def _facts(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    out = []
    for fact in (value or [])[:MAX_FACTS]:
        text = (fact.get("text") if isinstance(fact, dict) else fact) or ""
        if str(text).strip():
            out.append(str(text).strip())
    return out


def is_phone(category: str | None) -> bool:
    return str(category or "").startswith("Phone")


def embedding_text(category: str, props: dict[str, Any]) -> str:
    """The text an entity is meaning-searched by: the engine's format, then the investigator's notes."""
    name = str(props.get("name") or props.get("key") or "").strip()
    text = f"{category}: {name}"
    description = str(props.get("description") or "").strip()
    if description:
        text += f" — {description}"
    aliases = _aliases(props.get("aliases"))
    if aliases:
        text += f" (aliases: {', '.join(aliases)})"
    facts = _facts(props.get("verified_facts"))
    if facts:
        text += f" Facts: {'; '.join(facts)}"
    notes = str(props.get("notes") or "").strip()
    if notes:
        text += f" Notes: {notes}"
    return text


def is_stale(document: str | None, props: dict[str, Any]) -> bool:
    """True when the stored text no longer holds the entity's current name, description or notes."""
    stored = (document or "").casefold()
    for field in ("name", "description", "notes"):
        value = str(props.get(field) or "").strip()
        if value and value[:MATCH_PREFIX].casefold() not in stored:
            return True
    return False


# ------------------------------------------------------------------------------------------------- graph reads

def _case_uuid(case_id):
    try:
        return uuid.UUID(str(case_id))
    except ValueError:
        return None


def _category(labels: Iterable[str], props: dict[str, Any]) -> str:
    labels = [label for label in labels or [] if label not in ("Entity", "RecycleBin", "RecycleBinItem")]
    return str(props.get("category") or (labels[0] if labels else "") or "Other")


def _read_nodes(case_id: str, keys: list[str], *, labels_by_key: dict[str, str] | None = None,
                session_factory: Callable | None = None) -> dict[str, tuple[str, dict[str, Any]]]:
    """{key: (category, properties)} for the case's live nodes. Keys whose label is known are read through the
    label's key index; the rest by key and case."""
    if not keys:
        return {}
    if session_factory is None:
        from services.neo4j.driver import driver
        session_factory = driver.session
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    by_label: dict[str, list[str]] = {}
    for key in keys:
        label = (labels_by_key or {}).get(key) or ""
        by_label.setdefault(label if _LABEL_RE.match(label) else "", []).append(key)
    with session_factory() as session:
        for label, chunk_keys in by_label.items():
            match = f"(n:`{label}` {{key: k}})" if label else "(n {key: k})"
            for i in range(0, len(chunk_keys), 2000):
                rows = session.run(
                    f"UNWIND $keys AS k MATCH {match} WHERE n.case_id = $case_id "
                    "AND NONE(l IN labels(n) WHERE l IN ['RecycleBin', 'RecycleBinItem']) "
                    "RETURN n.key AS key, labels(n) AS labels, properties(n) AS props",
                    keys=chunk_keys[i:i + 2000], case_id=case_id)
                for row in rows:
                    props = dict(row["props"] or {})
                    out[row["key"]] = (_category(row["labels"], props), props)
        missing = [k for k in keys if k not in out and (labels_by_key or {}).get(k)]
        if missing:  # the stored category is not the node's label any more: read those by key
            for row in session.run(
                    "UNWIND $keys AS k MATCH (n {key: k}) WHERE n.case_id = $case_id "
                    "AND NONE(l IN labels(n) WHERE l IN ['RecycleBin', 'RecycleBinItem']) "
                    "RETURN n.key AS key, labels(n) AS labels, properties(n) AS props",
                    keys=missing, case_id=case_id):
                props = dict(row["props"] or {})
                out[row["key"]] = (_category(row["labels"], props), props)
    return out


def _stored(collection, case_id: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """{key: (document, metadata)} of every entity vector of the case."""
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    offset = 0
    while True:
        page = collection.get(where={"case_id": case_id}, include=["documents", "metadatas"], limit=5000,
                              offset=offset)
        ids = page.get("ids") or []
        for key, doc, meta in zip(ids, page.get("documents") or [], page.get("metadatas") or []):
            out[key] = (doc or "", meta or {})
        if len(ids) < 5000:
            return out
        offset += len(ids)


# ------------------------------------------------------------------------------------------------- refresh

def stale_keys(case_id: str, *, vector_db=None, read_nodes: Callable | None = None) -> list[str]:
    """Keys of the case's entity vectors whose stored text no longer matches the graph."""
    if vector_db is None:
        from services.vector_db_service import get_vector_db_service
        vector_db = get_vector_db_service()
    if not vector_db:
        return []
    stored = _stored(vector_db.entity_collection, case_id)
    labels = {k: str(m.get("category") or m.get("entity_type") or "") for k, (_, m) in stored.items()}
    nodes = (read_nodes or _read_nodes)(case_id, list(stored), labels_by_key=labels)
    return [key for key, (doc, _) in stored.items()
            if key in nodes and not is_phone(nodes[key][0]) and is_stale(doc, nodes[key][1])]


def refresh_entities(case_id: str, keys: Iterable[str], *, vector_db=None, embed: Callable | None = None,
                     read_nodes: Callable | None = None, stop_on_failure: bool = True) -> dict[str, Any]:
    """Re-embed these entities from the graph as it is now. Stops at the first refused embedding call (the
    failure is recorded by the embedding service; the gap backfill retries when the service answers again)."""
    keys = [k for k in dict.fromkeys(keys or []) if k]
    summary: dict[str, Any] = {"requested": len(keys), "embedded": 0, "skipped": 0, "stopped": None}
    if not keys:
        return summary
    if vector_db is None:
        from services.vector_db_service import get_vector_db_service
        vector_db = get_vector_db_service()
    if not vector_db:
        summary["stopped"] = "vector database unavailable"
        return summary
    if embed is None:
        from services.embedding_service import EmbeddingService
        embed = EmbeddingService().generate_embedding
    nodes = (read_nodes or _read_nodes)(case_id, keys)
    for key in keys:
        if key not in nodes:
            summary["skipped"] += 1
            continue
        category, props = nodes[key]
        if is_phone(category):
            summary["skipped"] += 1
            continue
        text = embedding_text(category, props)
        try:
            with ai_cost_context(job_type=CostJobType.INGESTION, case_id=_case_uuid(case_id),
                                 description="Entity search index"):
                vector = embed(text)
            vector_db.add_entity(entity_key=key, text=text, embedding=vector, metadata={
                "category": category, "specific_type": props.get("specific_type") or "",
                "name": props.get("name") or "", "case_id": case_id,
                "aliases": ",".join(_aliases(props.get("aliases"))),
            })
            summary["embedded"] += 1
        except Exception as exc:  # refused or unreachable: the next recovery backfill finds it stale
            logger.warning("Entity meaning-search vector not refreshed for %s: %s", key, exc)
            summary["stopped"] = str(exc)[:300]
            if stop_on_failure:
                break
    return summary


def keys_to_refresh(updates: Iterable[Any]) -> list[str]:
    """Keys of a batch update whose change touches the searched text."""
    keys = []
    for update in updates or []:
        if isinstance(update, dict) and update.get("key") and update.get("property") in SEARCH_FIELDS:
            keys.append(str(update["key"]))
    return list(dict.fromkeys(keys))


def refresh_after_edit(case_id: str | None, keys: Iterable[str], *, run: Callable | None = None) -> threading.Thread | None:
    """Re-embed edited entities without holding up the edit's answer."""
    keys = [k for k in (keys or []) if k]
    if not case_id or not keys:
        return None

    def work():
        try:
            (run or refresh_entities)(case_id, keys)
        except Exception as exc:
            logger.warning("Entity meaning-search refresh after edit failed for %s: %s", keys[:5], exc)

    thread = threading.Thread(target=work, name="entity-vector-refresh", daemon=True)
    thread.start()
    return thread


def pending_keys(case_id: str, *, session_factory: Callable | None = None) -> list[str]:
    """Keys of the case's entities with no vector yet: a merge kept while embedding was refused (the engine's
    ``vector_pending`` mark)."""
    if session_factory is None:
        from services.neo4j.driver import driver
        session_factory = driver.session
    with session_factory() as session:
        return [row["key"] for row in session.run(
            "MATCH (n) WHERE n.case_id = $case_id AND n.vector_pending = true RETURN n.key AS key", case_id=case_id)]


def clear_pending(case_id: str, keys: list[str], *, session_factory: Callable | None = None) -> None:
    if session_factory is None:
        from services.neo4j.driver import driver
        session_factory = driver.session
    with session_factory() as session:
        session.run("UNWIND $keys AS k MATCH (n {key: k}) WHERE n.case_id = $case_id REMOVE n.vector_pending",
                    keys=keys, case_id=case_id)


def backfill_case(case_id: str, *, stale: Callable | None = None, refresh: Callable | None = None,
                  log: Callable[[str, str], None] | None = None, pending: Callable | None = None,
                  clear: Callable | None = None) -> dict[str, Any]:
    """The gap backfill's entity pass for one case: re-embed every stale entity vector and embed every entity still
    waiting for its first one. The mark goes only when the whole pass finished; a pass that stopped embeds them again."""
    waiting = (pending or pending_keys)(case_id)
    keys = list(dict.fromkeys(list((stale or stale_keys)(case_id)) + waiting))
    if not keys:
        return {"requested": 0, "embedded": 0, "skipped": 0, "stopped": None}
    if log:
        log("info", "Case %s: %d entity vector(s) older than the graph, %d waiting for a first one" % (
            case_id, len(keys) - len(waiting), len(waiting)))
    result = (refresh or refresh_entities)(case_id, keys)
    if waiting and not result.get("stopped"):
        (clear or clear_pending)(case_id, waiting)
    return result
