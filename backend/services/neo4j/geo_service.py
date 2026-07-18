"""
Geo Service — location-related operations: geocoded entity retrieval,
location updates, location node creation, and relationship management.
"""

import logging
from typing import Any, Dict, List, Optional

from services.location_validation import GeocodeProvenance, validate_location
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
                    n.geocoding_provider AS geocoding_provider,
                    n.geocoding_query AS geocoding_query,
                    n.geocoding_precision AS geocoding_precision,
                    n.geocoding_confidence AS geocoding_confidence,
                    n.geocoding_candidates AS geocoding_candidates,
                    n.geocoding_status AS geocoding_status,
                    n.geocoding_rejection_reason AS geocoding_rejection_reason,
                    n.geocoding_provider_error AS geocoding_provider_error,
                    n.summary AS summary,
                    n.date AS date,
                    connections
            """

            result = session.run(query, **params)

            entities = []
            for record in result:
                validated = validate_location(
                    latitude=record["latitude"],
                    longitude=record["longitude"],
                    entity_type=record["type"],
                    provenance=GeocodeProvenance(
                        geocoder=record["geocoding_provider"],
                        query=record["geocoding_query"] or record["location_raw"],
                        formatted_address=record["location_formatted"],
                        precision=record["geocoding_precision"],
                        confidence=record["geocoding_confidence"],
                        provider_status=record["geocoding_status"],
                        failure_reason=record["geocoding_provider_error"],
                    ),
                )
                if not validated.is_valid:
                    logger.warning(
                        "Rejected map-visible coordinates",
                        extra={
                            "node_key": record["key"],
                            "entity_type": record["type"],
                            "reason": validated.rejection_reason.value if validated.rejection_reason else None,
                        },
                    )
                    continue

                entity = {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "latitude": validated.latitude,
                    "longitude": validated.longitude,
                    "location_raw": record["location_raw"],
                    "location_formatted": record["location_formatted"],
                    "geocoding_provider": record["geocoding_provider"],
                    "geocoding_query": record["geocoding_query"],
                    "geocoding_precision": record["geocoding_precision"],
                    "geocoding_confidence": record["geocoding_confidence"],
                    "geocoding_candidates": record["geocoding_candidates"],
                    "geocoding_status": record["geocoding_status"],
                    "geocoding_rejection_reason": record["geocoding_rejection_reason"],
                    "geocoding_provider_error": record["geocoding_provider_error"],
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
                       n.location_raw, n.geocoding_confidence, n.geocoding_provider,
                       n.geocoding_query, n.geocoding_precision, n.geocoding_candidates,
                       n.geocoding_status, n.geocoding_rejection_reason,
                       n.geocoding_provider_error
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
                       n.location_raw AS location_raw
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
        geocoding_provider: str | None = None,
        geocoding_query: str | None = None,
        geocoding_precision: str | None = None,
        geocoding_candidates: str | None = None,
        geocoding_status: str | None = None,
        geocoding_rejection_reason: str | None = None,
        geocoding_provider_error: str | None = None,
        edited_by: str | None = None,
        source_view: str | None = None,
    ) -> Dict:
        """Set all location properties on an entity node."""
        with driver.session() as session:
            current = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
            ).single()
            if not current:
                return {}
            provenance = GeocodeProvenance(
                geocoder=geocoding_provider,
                query=geocoding_query or location_raw,
                formatted_address=location_formatted,
                precision=geocoding_precision,
                confidence=geocoding_confidence,
                provider_status=geocoding_status,
                failure_reason=geocoding_provider_error,
            )
            validated = validate_location(
                latitude=latitude,
                longitude=longitude,
                entity_type=current["type"],
                provenance=provenance,
            )
            provenance_props = validated.provenance.as_node_properties(
                status=validated.status,
                rejection_reason=validated.rejection_reason.value if validated.rejection_reason else geocoding_rejection_reason,
            )
            if geocoding_candidates:
                provenance_props["geocoding_candidates"] = geocoding_candidates
            if validated.is_valid:
                coordinate_clause = "SET n.latitude = $latitude, n.longitude = $longitude"
            else:
                coordinate_clause = "REMOVE n.latitude, n.longitude"
                logger.warning(
                    "Rejected location update before graph write",
                    extra={
                        "node_key": node_key,
                        "entity_type": current["type"],
                        "reason": validated.rejection_reason.value if validated.rejection_reason else None,
                    },
                )
            audit_clause = ""
            if edited_by:
                audit_clause = """
                SET n.manual_fields = reduce(
                        acc = coalesce(n.manual_fields, []),
                        field IN $manual_fields |
                        CASE WHEN field IN acc THEN acc ELSE acc + field END
                    ),
                    n.last_edited_at = datetime(),
                    n.last_edited_by = $edited_by,
                    n.last_edit_source = $source_view
                """
            result = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                SET n.location_raw = $location_raw,
                    n.location_formatted = $location_formatted,
                    n.location_name = $location_formatted,
                    n += $provenance_props
                {coordinate_clause}
                {audit_clause}
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
                location_raw=location_raw,
                latitude=latitude,
                longitude=longitude,
                location_formatted=location_formatted,
                provenance_props=provenance_props,
                manual_fields=[
                    "latitude",
                    "longitude",
                    "location_raw",
                    "location_formatted",
                    "location_name",
                ],
                edited_by=edited_by,
                source_view=source_view,
            )
            record = result.single()
            response = dict(record) if record else {}
            response["geocoding_status"] = validated.status
            response["geocoding_rejection_reason"] = (
                validated.rejection_reason.value if validated.rejection_reason else None
            )
            return response

    def create_location_node(
        self,
        case_id: str,
        name: str,
        latitude: float,
        longitude: float,
        location_formatted: str,
        geocoding_confidence: str,
        geocoding_provider: str | None = None,
        geocoding_query: str | None = None,
        geocoding_precision: str | None = None,
        geocoding_candidates: str | None = None,
        context: str = "",
    ) -> Optional[str]:
        """Create a new Location node in the graph and return its key."""
        import uuid
        node_key = f"loc_{uuid.uuid4().hex[:12]}"
        provenance = GeocodeProvenance(
            geocoder=geocoding_provider,
            query=geocoding_query or name,
            formatted_address=location_formatted,
            precision=geocoding_precision,
            confidence=geocoding_confidence,
        )
        validated = validate_location(
            latitude=latitude,
            longitude=longitude,
            entity_type="Location",
            provenance=provenance,
        )
        if not validated.is_valid:
            logger.warning(
                "Rejected location node before graph write",
                extra={
                    "name": name,
                    "reason": validated.rejection_reason.value if validated.rejection_reason else None,
                },
            )
            return None
        provenance_props = validated.provenance.as_node_properties(status=validated.status)
        if geocoding_candidates:
            provenance_props["geocoding_candidates"] = geocoding_candidates
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
                    summary: $context,
                    source: 'geo_rescan'
                })
                SET n += $provenance_props
                RETURN n.key AS key
                """,
                key=node_key,
                name=name,
                case_id=case_id,
                latitude=validated.latitude,
                longitude=validated.longitude,
                location_formatted=location_formatted,
                geocoding_confidence=geocoding_confidence,
                context=context,
                provenance_props=provenance_props,
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
