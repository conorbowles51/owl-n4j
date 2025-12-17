"""
Neo4j Client module - handles all database interactions.

Provides functions for:
- Connection management
- Entity CRUD operations
- Relationship management
- Search (exact and fuzzy)
"""

import uuid
from typing import Dict, List, Optional, Any

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class Neo4jClient:
    """
    Client for Neo4j database operations.
    """

    def __init__(self):
        if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
            raise RuntimeError("Neo4j configuration missing. Check .env values.")

        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )

    def close(self):
        """Close the database connection."""
        self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -------------------------------------------------------------------------
    # Entity Operations
    # -------------------------------------------------------------------------

    def get_all_entity_keys(self) -> List[str]:
        """
        Get all entity keys currently in the database.

        Returns:
            List of entity key strings
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e)
                WHERE e.key IS NOT NULL
                  AND NOT e:Document
                RETURN e.key AS key
                """
            )
            return [record["key"] for record in result]

    def find_entity_by_key(self, key: str) -> Optional[Dict]:
        """
        Find an entity by exact key match.

        Args:
            key: The normalised entity key

        Returns:
            Entity dict if found, None otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e {key: $key})
                WHERE NOT e:Document
                RETURN e.id AS id,
                       e.key AS key,
                       e.name AS name,
                       labels(e)[0] AS type,
                       e.notes AS notes,
                       e.summary AS summary,
                       e.latitude AS latitude,
                       e.longitude AS longitude,
                       e.location_raw AS location_raw
                """,
                key=key,
            )
            record = result.single()
            if record:
                return dict(record)
            return None

    def fuzzy_search_entities(
        self,
        name: str,
        entity_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict]:
        """
        Search for entities with similar names (fuzzy match).

        Uses case-insensitive CONTAINS matching on name.

        Args:
            name: The name to search for
            entity_type: Optional type filter
            limit: Maximum results to return

        Returns:
            List of matching entity dicts
        """
        # Extract meaningful parts of the name for searching
        search_terms = name.lower().split()

        with self.driver.session() as session:
            if entity_type:
                query = f"""
                MATCH (e:{entity_type})
                WHERE e.name IS NOT NULL
                  AND any(term IN $terms WHERE toLower(e.name) CONTAINS term)
                RETURN e.id AS id,
                       e.key AS key,
                       e.name AS name,
                       labels(e)[0] AS type,
                       e.notes AS notes,
                       e.summary AS summary
                LIMIT $limit
                """
            else:
                query = """
                MATCH (e)
                WHERE e.name IS NOT NULL
                  AND NOT e:Document
                  AND any(term IN $terms WHERE toLower(e.name) CONTAINS term)
                RETURN e.id AS id,
                       e.key AS key,
                       e.name AS name,
                       labels(e)[0] AS type,
                       e.notes AS notes,
                       e.summary AS summary
                LIMIT $limit
                """

            result = session.run(query, terms=search_terms, limit=limit)
            return [dict(record) for record in result]

    def get_entity_neighbours(
        self,
        key: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get entities related to a given entity.

        Args:
            key: The entity key
            limit: Maximum neighbours to return

        Returns:
            List of neighbour entity dicts with relationship info
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e {key: $key})-[r]-(neighbour)
                WHERE NOT neighbour:Document
                RETURN neighbour.key AS key,
                       neighbour.name AS name,
                       labels(neighbour)[0] AS type,
                       type(r) AS relationship
                LIMIT $limit
                """,
                key=key,
                limit=limit,
            )
            return [dict(record) for record in result]

    def create_entity(
        self,
        key: str,
        entity_type: str,
        name: str,
        notes: str,
        summary: Optional[str] = None,
        date: Optional[str] = None,
        time: Optional[str] = None,
        amount: Optional[str] = None,
        extra_props: Optional[Dict] = None,
    ) -> str:
        """
        Create a new entity node.

        Args:
            key: Normalised key for deduplication
            entity_type: The entity type (used as label)
            name: Human-readable name
            notes: Initial notes text
            summary: Initial summary
            date: Event date (YYYY-MM-DD) for event-type entities
            time: Event time (HH:MM) for event-type entities
            amount: Transaction amount for financial entities
            extra_props: Additional properties to set

        Returns:
            The generated UUID for the entity
        """
        entity_id = str(uuid.uuid4())

        props = {
            "id": entity_id,
            "key": key,
            "name": name,
            "notes": notes,
        }

        # Add optional properties if provided
        if summary:
            props["summary"] = summary
        if date:
            props["date"] = date
        if time:
            props["time"] = time
        if amount:
            props["amount"] = amount

        if extra_props:
            props.update(extra_props)

        with self.driver.session() as session:
            session.run(
                f"""
                CREATE (e:{entity_type} $props)
                """,
                props=props,
            )

        return entity_id

    def update_entity(
        self,
        key: str,
        notes: Optional[str] = None,
        summary: Optional[str] = None,
        extra_props: Optional[Dict] = None,
    ):
        """
        Update an existing entity's properties.

        Args:
            key: The entity key
            notes: New notes text (replaces existing)
            summary: New summary text
            extra_props: Additional properties to update
        """
        updates = []
        params = {"key": key}

        if notes is not None:
            updates.append("e.notes = $notes")
            params["notes"] = notes

        if summary is not None:
            updates.append("e.summary = $summary")
            params["summary"] = summary

        if extra_props:
            for prop_key, prop_val in extra_props.items():
                param_name = f"prop_{prop_key}"
                updates.append(f"e.{prop_key} = ${param_name}")
                params[param_name] = prop_val

        if not updates:
            return

        set_clause = ", ".join(updates)

        with self.driver.session() as session:
            session.run(
                f"""
                MATCH (e {{key: $key}})
                SET {set_clause}
                """,
                **params,
            )

    # -------------------------------------------------------------------------
    # Document Operations
    # -------------------------------------------------------------------------

    def ensure_document(
        self,
        doc_key: str,
        doc_name: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Ensure a Document node exists (create or update).

        Args:
            doc_key: Normalised document key
            doc_name: Document filename/name
            metadata: Additional document properties

        Returns:
            The document's UUID
        """
        doc_id = str(uuid.uuid4())

        props = {
            "id": doc_id,
            "key": doc_key,
            "name": doc_name,
        }

        if metadata:
            props.update(metadata)

        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (d:Document {key: $key})
                ON CREATE SET d = $props
                ON MATCH SET d.name = $name
                RETURN d.id AS id
                """,
                key=doc_key,
                props=props,
                name=doc_name,
            )
            record = result.single()
            return record["id"] if record else doc_id

    # -------------------------------------------------------------------------
    # Relationship Operations
    # -------------------------------------------------------------------------

    def create_relationship(
        self,
        from_key: str,
        to_key: str,
        rel_type: str,
        doc_name: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """
        Create or update a relationship between two entities.

        Args:
            from_key: Source entity key
            to_key: Target entity key
            rel_type: Relationship type
            doc_name: Document where this relationship was found
            notes: Notes about this relationship
        """
        with self.driver.session() as session:
            # First, create/merge the relationship
            session.run(
                f"""
                MATCH (from {{key: $from_key}})
                MATCH (to {{key: $to_key}})
                MERGE (from)-[r:{rel_type}]->(to)
                """,
                from_key=from_key,
                to_key=to_key,
            )

            # If we have doc_refs to add, update them
            if doc_name and notes:
                doc_ref_entry = f"\n\n[{doc_name}]\n{notes}"
                session.run(
                    f"""
                    MATCH (from {{key: $from_key}})-[r:{rel_type}]->(to {{key: $to_key}})
                    SET r.doc_refs = COALESCE(r.doc_refs, '') + $doc_ref
                    """,
                    from_key=from_key,
                    to_key=to_key,
                    doc_ref=doc_ref_entry,
                )

    def link_entity_to_document(self, entity_key: str, doc_key: str):
        """
        Create MENTIONED_IN relationship between entity and document.

        Args:
            entity_key: The entity key
            doc_key: The document key
        """
        with self.driver.session() as session:
            session.run(
                """
                MATCH (e {key: $entity_key})
                MATCH (d:Document {key: $doc_key})
                MERGE (e)-[:MENTIONED_IN]->(d)
                """,
                entity_key=entity_key,
                doc_key=doc_key,
            )

    # -------------------------------------------------------------------------
    # Utility Operations
    # -------------------------------------------------------------------------

    def run_query(self, query: str, **params) -> List[Dict]:
        """
        Run an arbitrary Cypher query.

        Args:
            query: Cypher query string
            **params: Query parameters

        Returns:
            List of result records as dicts
        """
        with self.driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def clear_database(self):
        """
        Delete all nodes and relationships. Use with caution!
        """
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
