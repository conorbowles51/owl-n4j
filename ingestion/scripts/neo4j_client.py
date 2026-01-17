"""
Neo4j Client module - handles all database interactions.

Provides functions for:
- Connection management
- Entity CRUD operations
- Relationship management
- Search (exact and fuzzy)
"""

import uuid
import time
from typing import Dict, List, Optional, Any

from neo4j import GraphDatabase
from neo4j.exceptions import TransientError, ServiceUnavailable

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
    
    def _execute_with_retry(self, func, max_retries=3, initial_delay=1.0):
        """
        Execute a Neo4j operation with retry logic for transient errors.
        
        Args:
            func: Function to execute (should be a lambda or callable that takes session)
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before retry (exponential backoff)
        
        Returns:
            Result from the function
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries + 1):
            try:
                return func()
            except (TransientError, ServiceUnavailable) as e:
                last_exception = e
                error_code = getattr(e, 'code', '')
                error_message = str(e)
                
                # Check if it's a transaction log error
                if 'TransactionLogError' in error_message or 'Transaction' in error_code:
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        wait_time = delay * (2 ** attempt) + (time.time() % 1)
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f"Neo4j transaction log error after {max_retries + 1} attempts. "
                            f"This may indicate:\n"
                            f"1. Disk space issues on the Neo4j server\n"
                            f"2. Transaction log corruption\n"
                            f"3. Too many concurrent transactions\n"
                            f"4. Neo4j configuration issues\n\n"
                            f"Original error: {error_message}\n"
                            f"Error code: {error_code}\n\n"
                            f"Please check Neo4j server logs and ensure:\n"
                            f"- Sufficient disk space is available\n"
                            f"- Neo4j transaction log is not corrupted\n"
                            f"- Neo4j server is properly configured"
                        ) from e
                else:
                    # For other transient errors, retry with backoff
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt) + (time.time() % 1)
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception

    # -------------------------------------------------------------------------
    # Entity Operations
    # -------------------------------------------------------------------------

    def get_all_entity_keys(self, case_id: str) -> List[str]:
        """
        Get all entity keys for a specific case.

        Args:
            case_id: The case ID to filter by

        Returns:
            List of entity key strings
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e)
                WHERE e.key IS NOT NULL
                  AND NOT e:Document
                  AND e.case_id = $case_id
                RETURN e.key AS key
                """,
                case_id=case_id,
            )
            return [record["key"] for record in result]

    def find_entity_by_key(self, key: str, case_id: str) -> Optional[Dict]:
        """
        Find an entity by exact key match within a specific case.

        Args:
            key: The normalised entity key
            case_id: The case ID to filter by

        Returns:
            Entity dict if found, None otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e {key: $key, case_id: $case_id})
                WHERE NOT e:Document
                RETURN e.id AS id,
                       e.key AS key,
                       e.name AS name,
                       labels(e)[0] AS type,
                       e.notes AS notes,
                       e.summary AS summary,
                       e.latitude AS latitude,
                       e.longitude AS longitude,
                       e.location_raw AS location_raw,
                       e.verified_facts AS verified_facts,
                       e.ai_insights AS ai_insights
                """,
                key=key,
                case_id=case_id,
            )
            record = result.single()
            if record:
                return dict(record)
            return None

    def fuzzy_search_entities(
        self,
        name: str,
        case_id: str,
        entity_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict]:
        """
        Search for entities with similar names (fuzzy match) within a specific case.

        Uses case-insensitive CONTAINS matching on name.

        Args:
            name: The name to search for
            case_id: The case ID to filter by
            entity_type: Optional type filter
            limit: Maximum results to return

        Returns:
            List of matching entity dicts
        """
        # Extract meaningful parts of the name for searching
        search_terms = name.lower().split()

        # Sanitize entity_type if provided
        sanitized_type = None
        if entity_type:
            import re
            sanitized_type = entity_type.strip()
            sanitized_type = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized_type)
            sanitized_type = re.sub(r'_+', '_', sanitized_type)
            sanitized_type = sanitized_type.strip('_')
            if not sanitized_type:
                sanitized_type = None

        with self.driver.session() as session:
            if sanitized_type:
                query = f"""
                MATCH (e:`{sanitized_type}`)
                WHERE e.name IS NOT NULL
                  AND e.case_id = $case_id
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
                  AND e.case_id = $case_id
                  AND any(term IN $terms WHERE toLower(e.name) CONTAINS term)
                RETURN e.id AS id,
                       e.key AS key,
                       e.name AS name,
                       labels(e)[0] AS type,
                       e.notes AS notes,
                       e.summary AS summary
                LIMIT $limit
                """

            result = session.run(query, terms=search_terms, case_id=case_id, limit=limit)
            return [dict(record) for record in result]

    def get_entity_neighbours(
        self,
        key: str,
        case_id: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Get entities related to a given entity within a specific case.

        Args:
            key: The entity key
            case_id: The case ID to filter by
            limit: Maximum neighbours to return

        Returns:
            List of neighbour entity dicts with relationship info
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e {key: $key, case_id: $case_id})-[r]-(neighbour)
                WHERE NOT neighbour:Document
                  AND neighbour.case_id = $case_id
                RETURN neighbour.key AS key,
                       neighbour.name AS name,
                       labels(neighbour)[0] AS type,
                       type(r) AS relationship
                LIMIT $limit
                """,
                key=key,
                case_id=case_id,
                limit=limit,
            )
            return [dict(record) for record in result]

    def create_entity(
        self,
        key: str,
        entity_type: str,
        name: str,
        notes: str,
        case_id: str,
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
            case_id: REQUIRED - The case ID to associate with this entity
            summary: Initial summary
            date: Event date (YYYY-MM-DD) for event-type entities
            time: Event time (HH:MM) for event-type entities
            amount: Transaction amount for financial entities
            extra_props: Additional properties to set

        Returns:
            The generated UUID for the entity

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for creating entities")

        entity_id = str(uuid.uuid4())

        props = {
            "id": entity_id,
            "key": key,
            "name": name,
            "notes": notes,
            "case_id": case_id,  # MANDATORY: Associate entity with case
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

        # Sanitize entity_type for use as Cypher label
        # Remove or replace characters that aren't valid in Cypher labels
        # Labels can contain alphanumeric and underscore, but we'll allow common patterns
        sanitized_type = entity_type.strip()
        # Replace spaces and special chars with underscores, but keep alphanumeric
        import re
        sanitized_type = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized_type)
        # Remove multiple consecutive underscores
        sanitized_type = re.sub(r'_+', '_', sanitized_type)
        # Remove leading/trailing underscores
        sanitized_type = sanitized_type.strip('_')
        # Fallback to "Other" if empty after sanitization
        if not sanitized_type:
            sanitized_type = "Other"

        def _create():
            with self.driver.session() as session:
                session.run(
                    f"""
                    CREATE (e:`{sanitized_type}` $props)
                    """,
                    props=props,
                )
        
        self._execute_with_retry(_create)
        return entity_id

    def update_entity(
        self,
        key: str,
        case_id: str,
        notes: Optional[str] = None,
        summary: Optional[str] = None,
        extra_props: Optional[Dict] = None,
    ):
        """
        Update an existing entity's properties.

        Args:
            key: The entity key
            case_id: REQUIRED - The case ID (used to verify entity belongs to case)
            notes: New notes text (replaces existing)
            summary: New summary text
            extra_props: Additional properties to update

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for updating entities")

        updates = []
        params = {"key": key, "case_id": case_id}

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

        def _update():
            with self.driver.session() as session:
                session.run(
                    f"""
                    MATCH (e {{key: $key, case_id: $case_id}})
                    SET {set_clause}
                    """,
                    **params,
                )

        self._execute_with_retry(_update)

    # -------------------------------------------------------------------------
    # Document Operations
    # -------------------------------------------------------------------------

    def ensure_document(
        self,
        doc_key: str,
        doc_name: str,
        case_id: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Ensure a Document node exists (create or update).

        Args:
            doc_key: Normalised document key
            doc_name: Document filename/name
            case_id: REQUIRED - The case ID to associate with this document
            metadata: Additional document properties

        Returns:
            The document's UUID

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for creating documents")

        doc_id = str(uuid.uuid4())

        props = {
            "id": doc_id,
            "key": doc_key,
            "name": doc_name,
            "case_id": case_id,  # MANDATORY: Associate document with case
        }

        if metadata:
            props.update(metadata)

        def _ensure():
            with self.driver.session() as session:
                result = session.run(
                    """
                    MERGE (d:Document {key: $key, case_id: $case_id})
                    ON CREATE SET d = $props
                    ON MATCH SET d.name = $name
                    RETURN d.id AS id
                    """,
                    key=doc_key,
                    case_id=case_id,
                    props=props,
                    name=doc_name,
                )
                record = result.single()
                return record["id"] if record else doc_id

        return self._execute_with_retry(_ensure)

    def update_document(
        self,
        doc_key: str,
        case_id: str,
        updates: Dict,
    ) -> None:
        """
        Update a Document node with additional properties.

        Args:
            doc_key: Normalised document key
            case_id: REQUIRED - The case ID (used to verify document belongs to case)
            updates: Dictionary of properties to update

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for updating documents")

        def _update_doc():
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (d:Document {key: $key, case_id: $case_id})
                    SET d += $updates
                    """,
                    key=doc_key,
                    case_id=case_id,
                    updates=updates,
                )

        self._execute_with_retry(_update_doc)

    # -------------------------------------------------------------------------
    # Relationship Operations
    # -------------------------------------------------------------------------

    def create_relationship(
        self,
        from_key: str,
        to_key: str,
        rel_type: str,
        case_id: str,
        doc_name: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """
        Create or update a relationship between two entities.

        Args:
            from_key: Source entity key
            to_key: Target entity key
            rel_type: Relationship type (will be sanitized for Cypher)
            case_id: REQUIRED - The case ID to associate with this relationship
            doc_name: Document where this relationship was found
            notes: Notes about this relationship

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for creating relationships")

        # Sanitize relationship type for use as Cypher relationship type
        # Relationship types can contain alphanumeric and underscores, but we'll sanitize special chars
        import re
        sanitized_rel_type = rel_type.strip()
        # Replace spaces and special chars with underscores, but keep alphanumeric
        sanitized_rel_type = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized_rel_type)
        # Remove multiple consecutive underscores
        sanitized_rel_type = re.sub(r'_+', '_', sanitized_rel_type)
        # Remove leading/trailing underscores
        sanitized_rel_type = sanitized_rel_type.strip('_')
        # Fallback to "RELATED_TO" if empty after sanitization
        if not sanitized_rel_type:
            sanitized_rel_type = "RELATED_TO"

        def _create_rel():
            with self.driver.session() as session:
                # First, create/merge the relationship with case_id
                session.run(
                    f"""
                    MATCH (from {{key: $from_key, case_id: $case_id}})
                    MATCH (to {{key: $to_key, case_id: $case_id}})
                    MERGE (from)-[r:`{sanitized_rel_type}` {{case_id: $case_id}}]->(to)
                    """,
                    from_key=from_key,
                    to_key=to_key,
                    case_id=case_id,
                )

                # If we have doc_refs to add, update them
                if doc_name and notes:
                    doc_ref_entry = f"\n\n[{doc_name}]\n{notes}"
                    session.run(
                        f"""
                        MATCH (from {{key: $from_key, case_id: $case_id}})-[r:`{sanitized_rel_type}` {{case_id: $case_id}}]->(to {{key: $to_key, case_id: $case_id}})
                        SET r.doc_refs = COALESCE(r.doc_refs, '') + $doc_ref
                        """,
                        from_key=from_key,
                        to_key=to_key,
                        case_id=case_id,
                        doc_ref=doc_ref_entry,
                    )

        self._execute_with_retry(_create_rel)

    def link_entity_to_document(self, entity_key: str, doc_key: str, case_id: str):
        """
        Create MENTIONED_IN relationship between entity and document.

        Args:
            entity_key: The entity key
            doc_key: The document key
            case_id: REQUIRED - The case ID to associate with this relationship

        Raises:
            ValueError: If case_id is not provided
        """
        if not case_id:
            raise ValueError("case_id is required for linking entities to documents")

        def _link():
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (e {key: $entity_key, case_id: $case_id})
                    MATCH (d:Document {key: $doc_key, case_id: $case_id})
                    MERGE (e)-[r:MENTIONED_IN {case_id: $case_id}]->(d)
                    """,
                    entity_key=entity_key,
                    doc_key=doc_key,
                    case_id=case_id,
                )

        self._execute_with_retry(_link)

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
