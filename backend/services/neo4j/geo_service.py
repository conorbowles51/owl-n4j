"""
Geo Service — location-related operations: geocoded entity retrieval,
location updates, location node creation, and relationship management.
"""

import logging
from typing import Any, Dict, List, Optional

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


class GeoService:

    def get_entities_with_locations(
        self,
        entity_types: Optional[List[str]] = None,
        case_id: str = None,
    ) -> List[Dict]:
        """
        Get all entities that have geocoded locations.

        Args:
            entity_types: Optional filter for specific entity types
            case_id: REQUIRED - Filter to only include nodes belonging to this case

        Returns:
            List of entities with lat/lng coordinates
        """
        with driver.session() as session:
            type_filter = ""
            # case_id is always required
            params = {"case_id": case_id}

            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Always filter by case_id
            query = f"""
                MATCH (n)
                WHERE n.latitude IS NOT NULL
                  AND n.longitude IS NOT NULL
                  AND NONE(label IN labels(n) WHERE label IN ['Document', 'RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(n)['system_node'], false) <> true
                  {type_filter}
                  AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE connected IS NULL OR (
                  NONE(label IN labels(connected) WHERE label IN ['Document', 'RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(connected)['system_node'], false) <> true
                  AND connected.case_id = $case_id
                )
                WITH n, collect(DISTINCT {{
                    key: connected.key,
                    name: connected.name,
                    type: labels(connected)[0],
                    relationship: type(r),
                    direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                }}) AS connections
                RETURN
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.latitude AS latitude,
                    n.longitude AS longitude,
                    n.location_raw AS location_raw,
                    n.location_formatted AS location_formatted,
                    n.geocoding_confidence AS geocoding_confidence,
                    n.location_source AS location_source,
                    n.location_corrected_at AS location_corrected_at,
                    n.location_corrected_by AS location_corrected_by,
                    n.location_correction_source AS location_correction_source,
                    n.location_correction_address AS location_correction_address,
                    n.last_location_relocation_key AS last_location_relocation_key,
                    n.summary AS summary,
                    n.date AS date,
                    connections
            """

            result = session.run(query, **params)

            entities = []
            for record in result:
                entity = {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "location_raw": record["location_raw"],
                    "location_formatted": record["location_formatted"],
                    "geocoding_confidence": record["geocoding_confidence"],
                    "location_source": record["location_source"],
                    "location_corrected_at": record["location_corrected_at"],
                    "location_corrected_by": record["location_corrected_by"],
                    "location_correction_source": record["location_correction_source"],
                    "location_correction_address": record["location_correction_address"],
                    "last_location_relocation_key": record["last_location_relocation_key"],
                    "summary": record["summary"],
                    "date": record["date"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
                entities.append(entity)

            return entities

    def update_entity_location(self, node_key: str, case_id: str, location_name: str, latitude: float, longitude: float) -> Dict:
        """Update the location properties of an entity node."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.location_name = $location_name,
                    n.location_formatted = $location_name,
                    n.latitude = $latitude,
                    n.longitude = $longitude
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
                location_name=location_name,
                latitude=latitude,
                longitude=longitude,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "node": {"key": record["key"], "name": record["name"], "type": record["type"]},
                "location": {"location_name": location_name, "latitude": latitude, "longitude": longitude},
            }

    def remove_entity_location(self, node_key: str, case_id: str) -> Dict:
        """Remove location properties from an entity node (node stays in graph)."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                REMOVE n.latitude, n.longitude, n.location_name, n.location_formatted,
                       n.location_raw, n.geocoding_confidence
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "node": {"key": record["key"], "name": record["name"], "type": record["type"]},
            }

    def get_all_nodes(self, case_id: str) -> List[Dict]:
        """Return every non-Document node for a case with key properties."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE NOT n:Document
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.latitude AS latitude, n.longitude AS longitude,
                       n.location_raw AS location_raw,
                       n.location_source AS location_source,
                       n.geocoding_confidence AS geocoding_confidence
                """,
                case_id=case_id,
            )
            return [dict(r) for r in result]

    def update_entity_location_full(
        self,
        node_key: str,
        case_id: str,
        location_raw: str,
        latitude: float,
        longitude: float,
        location_formatted: str,
        geocoding_confidence: str,
    ) -> Dict:
        """Set all location properties on an entity node."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                WHERE coalesce(n.location_source, '') <> 'manual'
                  AND coalesce(n.geocoding_confidence, '') <> 'manual'
                SET n.location_raw = $location_raw,
                    n.latitude = $latitude,
                    n.longitude = $longitude,
                    n.location_formatted = $location_formatted,
                    n.location_name = $location_formatted,
                    n.geocoding_status = 'success',
                    n.geocoding_confidence = $geocoding_confidence,
                    n.location_source = coalesce(n.location_source, 'auto')
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
                location_raw=location_raw,
                latitude=latitude,
                longitude=longitude,
                location_formatted=location_formatted,
                geocoding_confidence=geocoding_confidence,
            )
            record = result.single()
            return dict(record) if record else {}

    def create_location_node(
        self,
        case_id: str,
        name: str,
        latitude: float,
        longitude: float,
        location_formatted: str,
        geocoding_confidence: str,
        context: str = "",
    ) -> Optional[str]:
        """Create a new Location node in the graph and return its key."""
        import uuid
        node_key = f"loc_{uuid.uuid4().hex[:12]}"
        with driver.session() as session:
            result = session.run(
                """
                CREATE (n:Location {
                    key: $key,
                    name: $name,
                    case_id: $case_id,
                    latitude: $latitude,
                    longitude: $longitude,
                    location_raw: $name,
                    location_formatted: $location_formatted,
                    location_name: $location_formatted,
                    geocoding_status: 'success',
                    geocoding_confidence: $geocoding_confidence,
                    location_source: 'auto',
                    summary: $context,
                    source: 'geo_rescan'
                })
                RETURN n.key AS key
                """,
                key=node_key,
                name=name,
                case_id=case_id,
                latitude=latitude,
                longitude=longitude,
                location_formatted=location_formatted,
                geocoding_confidence=geocoding_confidence,
                context=context,
            )
            record = result.single()
            return record["key"] if record else None

    def ensure_located_at_relationship(
        self,
        source_key: str,
        target_key: str,
        case_id: str,
        context: str = "",
    ) -> bool:
        """Create a LOCATED_AT relationship if it doesn't exist. Returns True if created."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a {key: $source_key, case_id: $case_id})
                MATCH (b {key: $target_key, case_id: $case_id})
                WHERE NOT (a)-[:LOCATED_AT]->(b)
                CREATE (a)-[r:LOCATED_AT {context: $context, source: 'geo_rescan'}]->(b)
                RETURN type(r) AS rel_type
                """,
                source_key=source_key,
                target_key=target_key,
                case_id=case_id,
                context=context,
            )
            return result.single() is not None


geo_service = GeoService()
