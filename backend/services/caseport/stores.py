"""The graph and the vectors, behind two small classes so that the export and import never hold them in memory.

Graph values that JSON cannot carry (dates, times, points) are written as {"$neo4j": kind, "value": text} and rebuilt on
import. Vectors travel as stored: an import makes no embedding call.
"""
from __future__ import annotations

import json

LOCK_LABEL = "IngestionCaseWriteLock"  # a lock, recreated on demand; never carried
PAGE = 500


def encode_graph_value(value):
    from neo4j.time import Date, DateTime, Duration, Time
    from neo4j.spatial import Point
    if isinstance(value, (DateTime, Date, Time)):
        return {"$neo4j": type(value).__name__, "value": value.iso_format()}
    if isinstance(value, Duration):
        return {"$neo4j": "Duration", "value": value.iso_format()}
    if isinstance(value, Point):
        return {"$neo4j": "Point", "srid": value.srid, "value": list(value)}
    raise TypeError(f"Graph value of type {type(value).__name__} cannot be carried")


def decode_graph_props(props: dict) -> dict:
    return {k: _decode(v) for k, v in props.items()}


def _decode(value):
    from neo4j.time import Date, DateTime, Time
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, dict) and "$neo4j" in value:
        kind = value["$neo4j"]
        if kind == "DateTime":
            return DateTime.from_iso_format(value["value"])
        if kind == "Date":
            return Date.from_iso_format(value["value"])
        if kind == "Time":
            return Time.from_iso_format(value["value"])
        if kind == "Point":
            from neo4j.spatial import CartesianPoint, WGS84Point
            cls = WGS84Point if value["srid"] in (4326, 4979) else CartesianPoint
            return cls(tuple(value["value"]))
        raise ValueError(f"Unknown graph value kind {kind}")
    return value


def _label(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


class GraphStore:
    def __init__(self, driver, database=None):
        self.driver = driver
        self.database = database

    @classmethod
    def from_config(cls):
        from neo4j import GraphDatabase
        import config
        return cls(GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)))

    def _session(self):
        return self.driver.session(database=self.database) if self.database else self.driver.session()

    def close(self):
        self.driver.close()

    def nodes(self, case_id):
        """(element id, labels, properties) of every node of the case, streamed."""
        with self._session() as s:
            for r in s.run("MATCH (n) WHERE n.case_id = $c AND NOT n:" + LOCK_LABEL +
                           " RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props", c=case_id):
                yield r["id"], r["labels"], r["props"]

    def relationships(self, case_id):
        with self._session() as s:
            for r in s.run("MATCH (a)-[x]->(b) WHERE a.case_id = $c AND b.case_id = $c AND NOT a:" + LOCK_LABEL +
                           " AND NOT b:" + LOCK_LABEL +
                           " RETURN elementId(a) AS a, elementId(b) AS b, type(x) AS t, properties(x) AS p", c=case_id):
                yield r["a"], r["b"], r["t"], r["p"]

    def crossing(self, case_id) -> int:
        """Relationships from this case to another: not carried (0 on live, 6 Nov)."""
        with self._session() as s:
            return s.run("MATCH (a)-[x]-(b) WHERE a.case_id = $c AND b.case_id <> $c RETURN count(x) AS n",
                         c=case_id).single()["n"]

    def create_nodes(self, labels, rows):
        """Create nodes of one label set. rows: [{"i": old element id, "p": props}]. Returns {old id: new element id}."""
        label_text = ":".join(_label(x) for x in labels)
        query = (f"UNWIND $rows AS r CREATE (n:{label_text}) SET n = r.p RETURN r.i AS i, elementId(n) AS id"
                 if labels else "UNWIND $rows AS r CREATE (n) SET n = r.p RETURN r.i AS i, elementId(n) AS id")
        with self._session() as s:
            return {r["i"]: r["id"] for r in s.run(query, rows=rows)}

    def create_relationships(self, rel_type, rows):
        """rows: [{"a": element id, "b": element id, "p": props}]. Returns how many were made."""
        with self._session() as s:
            return s.run("UNWIND $rows AS r MATCH (a) WHERE elementId(a) = r.a MATCH (b) WHERE elementId(b) = r.b "
                         f"CREATE (a)-[x:{_label(rel_type)}]->(b) SET x = r.p RETURN count(x) AS n",
                         rows=rows).single()["n"]

    def counts(self, case_id) -> dict:
        with self._session() as s:
            nodes = s.run("MATCH (n) WHERE n.case_id = $c AND NOT n:" + LOCK_LABEL + " RETURN count(n) AS n",
                          c=case_id).single()["n"]
            rels = s.run("MATCH (a)-[x]->(b) WHERE a.case_id = $c AND b.case_id = $c RETURN count(x) AS n",
                         c=case_id).single()["n"]
        return {"nodes": nodes, "relationships": rels}

    def delete_case(self, case_id):
        with self._session() as s:
            s.run("MATCH (n) WHERE n.case_id = $c CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS",
                  c=case_id).consume()


COLLECTIONS = ("chunks", "entities")


class VectorStore:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_config(cls):
        import chromadb
        from chromadb.config import Settings
        import config
        return cls(chromadb.HttpClient(host=config.CHROMADB_HOST, port=config.CHROMADB_PORT,
                                       settings=Settings(anonymized_telemetry=False)))

    def _collection(self, name):
        return self.client.get_or_create_collection(name=name)

    def rows(self, collection, case_id):
        """Every vector of the case in one collection, a page at a time."""
        col = self._collection(collection)
        offset = 0
        while True:
            page = col.get(where={"case_id": case_id}, include=["embeddings", "documents", "metadatas"],
                           limit=PAGE, offset=offset)
            ids = page["ids"]
            if not ids:
                return
            for i, row_id in enumerate(ids):
                embedding = page["embeddings"][i]
                yield {"id": row_id, "document": page["documents"][i], "metadata": page["metadatas"][i],
                       "embedding": [float(x) for x in embedding]}
            offset += len(ids)

    def existing(self, collection, ids) -> set:
        return set(self._collection(collection).get(ids=list(ids), include=[])["ids"])

    def dimension(self, collection):
        col = self._collection(collection)
        if col.count() == 0:
            return None
        sample = col.peek(1)
        return len(sample["embeddings"][0])

    def add(self, collection, rows):
        self._collection(collection).add(ids=[r["id"] for r in rows], documents=[r["document"] for r in rows],
                                         metadatas=[r["metadata"] for r in rows],
                                         embeddings=[r["embedding"] for r in rows])

    def count(self, collection, case_id) -> int:
        return len(self._collection(collection).get(where={"case_id": case_id}, include=[])["ids"])

    def delete_case(self, case_id):
        for name in COLLECTIONS:
            col = self._collection(name)
            ids = col.get(where={"case_id": case_id}, include=[])["ids"]
            for i in range(0, len(ids), PAGE):
                col.delete(ids=ids[i:i + PAGE])


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=encode_graph_value, separators=(",", ":"))
