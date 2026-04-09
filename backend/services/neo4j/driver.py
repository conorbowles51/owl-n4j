"""
Neo4j Driver — shared singleton connection and low-level query helpers.

Every domain service (graph, entity, financial, …) imports `driver` from here
and calls `driver.session()` to run Cypher queries.
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)


def active_node_predicate(alias: str, case_scoped: bool = True) -> str:
    """Cypher predicate for nodes that belong to the active investigation graph."""
    clauses = [
        f"NOT {alias}:RecycleBin",
        f"NOT {alias}:RecycleBinItem",
        f"coalesce({alias}.system_node, false) <> true",
    ]
    if case_scoped:
        clauses.insert(0, f"{alias}.case_id = $case_id")
    return " AND ".join(clauses)


# ── Utility helpers ────────────────────────────────────────────────────────


def parse_json_field(value: Optional[str]) -> Optional[List]:
    """Parse a JSON string field into a Python list."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def safe_float(value, default=0) -> float:
    """Convert a value to float, returning default if it's None, NaN, or invalid."""
    if value is None:
        return default
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else round(f, 2)
    except (TypeError, ValueError):
        return default


# ── Driver singleton ───────────────────────────────────────────────────────


class Neo4jDriver:
    """Thin wrapper around the Neo4j Python driver (singleton)."""

    _instance = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
            )
            self._ensure_case_id_index()

    def _ensure_case_id_index(self):
        try:
            with self._driver.session() as session:
                session.run(
                    "CREATE INDEX node_case_id IF NOT EXISTS FOR (n) ON (n.case_id)"
                )
        except Exception:
            pass

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def session(self, **kwargs):
        """Return a Neo4j session (use as context manager)."""
        return self._driver.session(**kwargs)

    # ── Low-level query execution ──────────────────────────────────────

    def run_cypher(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Run a Cypher query and return results as list of dicts."""
        with self._driver.session() as session:
            def work(tx):
                result = tx.run(query, params or {})
                return [dict(r) for r in result]
            return session.execute_write(work)

    def validate_cypher_batch(self, queries: List[str]) -> List[str]:
        """Dry-run a batch of Cypher queries (always rolls back). Returns error list."""
        errors: List[str] = []
        if not queries:
            return errors
        with self._driver.session() as session:
            tx = session.begin_transaction()
            try:
                for idx, query in enumerate(queries):
                    q = (query or "").strip()
                    if not q:
                        continue
                    try:
                        tx.run(q)
                    except Exception as e:
                        errors.append(f"Query {idx + 1} failed sanity check: {e}")
                tx.rollback()
            except Exception:
                tx.rollback()
                raise
        return errors

    def execute_cypher_batch(self, queries: List[str]) -> int:
        """Execute a batch of Cypher queries in a single transaction."""
        if not queries:
            return 0
        executed = 0
        with self._driver.session() as session:
            tx = session.begin_transaction()
            try:
                for query in queries:
                    q = (query or "").strip()
                    if not q:
                        continue
                    tx.run(q)
                    executed += 1
                tx.commit()
            except Exception:
                tx.rollback()
                raise
        return executed

    def clear_graph(self) -> None:
        """Delete all nodes and relationships from the graph."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def delete_case_data(self, case_id: str) -> Dict[str, Any]:
        """Delete all nodes and relationships belonging to a specific case."""
        with self._driver.session() as session:
            node_count_result = session.run(
                "MATCH (n {case_id: $case_id}) RETURN count(n) AS count",
                case_id=case_id,
            )
            node_count = node_count_result.single()["count"]

            rel_count_result = session.run(
                "MATCH ()-[r {case_id: $case_id}]-() RETURN count(r) AS count",
                case_id=case_id,
            )
            rel_count = rel_count_result.single()["count"]

            session.run(
                "MATCH ()-[r {case_id: $case_id}]-() DELETE r",
                case_id=case_id,
            )
            session.run(
                "MATCH (n {case_id: $case_id}) DELETE n",
                case_id=case_id,
            )

            return {
                "success": True,
                "case_id": case_id,
                "nodes_deleted": node_count,
                "relationships_deleted": rel_count,
            }


# Module-level singleton
driver = Neo4jDriver()
