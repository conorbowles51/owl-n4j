"""Investigator-facing graph edit operations."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from services.graph_edit_schema import (
    LOCATION_PROPERTY_KEYS,
    SYSTEM_PROPERTY_KEYS,
    get_graph_edit_schema,
    ontology_category_names,
)
from services.neo4j.driver import active_node_predicate, driver


SAFE_PROPERTY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DATE_PRECISIONS = {"day", "month", "year", "approximate"}


def _escape_label(label: str) -> str:
    return label.replace("`", "``")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _parse_history(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


class GraphEditService:
    """Validation, relabeling, audit metadata, and safe property updates."""

    def __init__(self) -> None:
        self._schema = get_graph_edit_schema

    @property
    def categories(self) -> set[str]:
        return ontology_category_names()

    @property
    def editable_schema(self) -> dict[str, Any]:
        return self._schema()

    def _current_category(self, labels: list[str]) -> str | None:
        categories = self.categories
        return next((label for label in labels if label in categories), None)

    def _validate_property_key(self, key: str) -> None:
        normalized = key.strip()
        if not normalized or not SAFE_PROPERTY_RE.match(normalized):
            raise ValueError(f"Property '{key}' is not a safe editable field")
        if normalized.lower() in SYSTEM_PROPERTY_KEYS:
            raise ValueError(f"Property '{key}' is a system field and cannot be edited")

    def _coerce_scalar(self, key: str, value: Any) -> Any:
        if value == "":
            return None
        if key == "date":
            if value is None:
                return None
            text = str(value).strip()
            if "T" in text:
                text = text.split("T", 1)[0]
            try:
                return datetime.fromisoformat(text).date().isoformat()
            except ValueError as exc:
                raise ValueError("date must be in YYYY-MM-DD format") from exc
        if key == "time":
            if value is None:
                return None
            text = str(value).strip()
            if not text:
                return None
            if len(text) >= 5:
                text = text[:5]
            if not TIME_RE.match(text):
                raise ValueError("time must be in HH:mm format")
            return text
        if key == "date_precision":
            if value is None or str(value).strip() == "":
                return None
            text = str(value).strip()
            if text not in DATE_PRECISIONS:
                raise ValueError("date_precision must be day, month, year, or approximate")
            return text
        if key in {"latitude", "longitude"}:
            if value is None or value == "":
                return None
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number") from exc
            if key == "latitude" and not -90 <= number <= 90:
                raise ValueError("latitude must be between -90 and 90")
            if key == "longitude" and not -180 <= number <= 180:
                raise ValueError("longitude must be between -180 and 180")
            return number
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        raise ValueError(f"Property '{key}' must be a scalar value")

    def _fetch_node(self, node_key: str, case_id: str) -> dict[str, Any] | None:
        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate("n")}
                RETURN labels(n) AS labels, properties(n) AS properties
                """,
                key=node_key,
                case_id=case_id,
            ).single()
        if not record:
            return None
        labels = list(record["labels"] or [])
        properties = dict(record["properties"] or {})
        return {
            "labels": labels,
            "category": self._current_category(labels),
            "properties": properties,
        }

    def update_node(
        self,
        node_key: str,
        *,
        case_id: str,
        name: str | None = None,
        summary: str | None = None,
        notes: str | None = None,
        category: str | None = None,
        specific_type: str | None = None,
        properties: dict[str, Any] | None = None,
        edited_by: str | None = None,
        source_view: str | None = None,
    ) -> dict[str, Any]:
        if not case_id:
            raise ValueError("case_id is required")

        current = self._fetch_node(node_key, case_id)
        if not current:
            raise LookupError(f"Node not found: {node_key}")

        current_props = current["properties"]
        if current_props.get("financial_identity_managed") and (category or specific_type or properties):
            raise ValueError("Edit account identity and ownership in Financial. You can add graph notes without changing its saved financial identity.")
        current_category = current["category"]
        updates: dict[str, Any] = {}
        changes: dict[str, dict[str, Any]] = {}
        manual_fields: list[str] = []

        def add_update(field: str, value: Any, before: Any | None = None) -> None:
            old_value = current_props.get(field) if before is None else before
            if old_value == value:
                return
            updates[field] = value
            changes[field] = {"before": _json_safe(old_value), "after": _json_safe(value)}
            manual_fields.append(field)

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("name cannot be empty")
            add_update("name", clean_name)
        if summary is not None:
            add_update("summary", summary if summary != "" else None)
        if notes is not None:
            add_update("notes", notes if notes != "" else None)
        if specific_type is not None:
            add_update("specific_type", specific_type.strip() or None)

        if properties:
            for key, value in properties.items():
                clean_key = key.strip()
                self._validate_property_key(clean_key)
                add_update(clean_key, self._coerce_scalar(clean_key, value))

        category_changed = False
        if category is not None:
            if category not in self.categories:
                raise ValueError(f"Unknown entity category: {category}")
            if category != current_category:
                category_changed = True
                changes["category"] = {"before": current_category, "after": category}
                manual_fields.append("category")

        if not updates and not category_changed:
            return {
                "success": True,
                "node_key": node_key,
                "updated_fields": [],
                "changes": {},
                "category": current_category,
            }

        edited_at = datetime.now(timezone.utc).isoformat()
        clauses = [
            f"MATCH (n {{key: $key, case_id: $case_id}})",
            f"WHERE {active_node_predicate('n')}",
        ]

        params: dict[str, Any] = {
            "key": node_key,
            "case_id": case_id,
            "updates": updates,
            "manual_fields": list(dict.fromkeys(manual_fields)),
            "edited_at": edited_at,
            "edited_by": edited_by,
            "source_view": source_view,
        }

        if category_changed and category:
            remove_labels = sorted(label for label in self.categories if label != category)
            for label in remove_labels:
                clauses.append(f"REMOVE n:`{_escape_label(label)}`")
            clauses.append(f"SET n:`{_escape_label(category)}`")

        if updates:
            clauses.append("SET n += $updates")

        clauses.append(
            """
            SET n.manual_fields = reduce(
                    acc = coalesce(n.manual_fields, []),
                    field IN $manual_fields |
                    CASE WHEN field IN acc THEN acc ELSE acc + field END
                ),
                n.last_edited_at = $edited_at,
                n.last_edited_by = $edited_by,
                n.last_edit_source = $source_view
            RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
            """
        )
        query = "\n".join(clauses)

        with driver.session() as session:
            record = session.run(query, **params).single()

        labels = list(record["labels"] or []) if record else []
        return {
            "success": True,
            "node_key": node_key,
            "updated_fields": list(dict.fromkeys(manual_fields)),
            "changes": changes,
            "category": self._current_category(labels),
            "properties": dict(record["properties"] or {}) if record else {},
        }

    def update_location(
        self,
        node_key: str,
        *,
        case_id: str,
        location_name: str,
        latitude: float,
        longitude: float,
        edited_by: str | None = None,
        source_view: str | None = "map",
    ) -> dict[str, Any]:
        location = location_name.strip()
        return self.update_node(
            node_key,
            case_id=case_id,
            properties={
                "location_name": location,
                "location_formatted": location,
                "location_raw": location,
                "latitude": latitude,
                "longitude": longitude,
            },
            edited_by=edited_by,
            source_view=source_view,
        )

    def update_geocoded_location(
        self,
        node_key: str,
        *,
        case_id: str,
        query: str,
        latitude: float,
        longitude: float,
        formatted_address: str,
        confidence: str | None,
        provider: str | None = None,
        location_granularity: str | None = None,
        edited_by: str | None = None,
        edited_by_name: str | None = None,
        source_view: str | None = "map",
    ) -> dict[str, Any]:
        if not case_id:
            raise ValueError("case_id is required")

        current = self._fetch_node(node_key, case_id)
        if not current:
            raise LookupError(f"Node not found: {node_key}")

        current_props = current["properties"]
        edited_at = datetime.now(timezone.utc).isoformat()
        clean_query = query.strip()
        clean_provider = provider or "nominatim"
        clean_formatted = formatted_address or clean_query

        history = _parse_history(current_props.get("manual_correction_history"))
        history.append(
            {
                "moved_by": edited_by or "unknown",
                "moved_by_name": edited_by_name,
                "moved_at": edited_at,
                "from_latitude": _json_safe(current_props.get("latitude")),
                "from_longitude": _json_safe(current_props.get("longitude")),
                "to_latitude": latitude,
                "to_longitude": longitude,
                "query": clean_query,
                "provider": clean_provider,
                "formatted_address": clean_formatted,
            }
        )

        updates: dict[str, Any] = {
            "latitude": self._coerce_scalar("latitude", latitude),
            "longitude": self._coerce_scalar("longitude", longitude),
            "location_raw": clean_query,
            "location_formatted": clean_formatted,
            "location_name": clean_formatted,
            "geocoding_status": "success",
            "geocoding_provider": clean_provider,
            "geocoding_query": clean_query,
            "geocoding_formatted_address": clean_formatted,
            "manual_correction_history": json.dumps(history),
        }
        if confidence:
            updates["geocoding_confidence"] = confidence
        if location_granularity:
            updates["location_granularity"] = location_granularity

        manual_fields = ["latitude", "longitude", "location_raw", "location_formatted", "location_name"]
        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                SET n += $updates
                SET n.manual_fields = reduce(
                        acc = coalesce(n.manual_fields, []),
                        field IN $manual_fields |
                        CASE WHEN field IN acc THEN acc ELSE acc + field END
                    ),
                    n.last_edited_at = $edited_at,
                    n.last_edited_by = $edited_by,
                    n.last_edit_source = $source_view
                RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
                """,
                key=node_key,
                case_id=case_id,
                updates=updates,
                manual_fields=manual_fields,
                edited_at=edited_at,
                edited_by=edited_by,
                source_view=source_view,
            ).single()

        labels = list(record["labels"] or []) if record else []
        return {
            "success": True,
            "node_key": node_key,
            "updated_fields": manual_fields,
            "changes": {
                "latitude": {"before": _json_safe(current_props.get("latitude")), "after": latitude},
                "longitude": {"before": _json_safe(current_props.get("longitude")), "after": longitude},
                "location_formatted": {
                    "before": _json_safe(current_props.get("location_formatted")),
                    "after": clean_formatted,
                },
            },
            "category": self._current_category(labels),
            "properties": dict(record["properties"] or {}) if record else {},
        }

    # A placement found by an address lookup a person asked for. It is a machine reading: the coordinates are set,
    # but no location field becomes a person's (manual_fields is untouched), the address from the evidence
    # (location_raw, location_formatted) stays as it was, and who asked and when is kept beside the result. It is
    # shown as "not confirmed" until a person confirms it or moves the pin.
    LOOKED_UP_STATUS = "looked_up"
    FLAGGED_STATUSES = ("ambiguous", "unverified", "failed", "not_run")

    def flagged_address(self, node_key: str, case_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """The node and its address when it is waiting for a lookup (flagged, no pin, not placed by a person);
        otherwise (node or None, why it cannot be looked up)."""
        current = self._fetch_node(node_key, case_id)
        if not current:
            return None, "Not found in this case."
        props = current["properties"]
        manual = set(props.get("manual_fields") or [])
        if manual & {"latitude", "longitude", "location_name", "location_formatted"}:
            return current, "Placed by a person; not looked up."
        if props.get("latitude") is not None and props.get("longitude") is not None:
            return current, "Already has a pin."
        if str(props.get("geocoding_status") or "") not in self.FLAGGED_STATUSES:
            return current, "Not flagged for an address lookup."
        if not self.lookup_address(props):
            return current, "No address recorded."
        return current, None

    @staticmethod
    def lookup_address(props: dict[str, Any]) -> str:
        """The address to send for a flagged entity: the address read from the evidence, else the query ingestion
        would have sent."""
        raw = str(props.get("location_raw") or "").strip()
        return raw or str(props.get("geocoding_query") or "").strip()

    def addresses_waiting(self, case_id: str, limit: int = 50) -> tuple[int, list[dict[str, Any]]]:
        """Entities of a case whose address was never looked up (status not_run, no pin, not placed by a person):
        how many, and the first ``limit`` of them (key and address)."""
        # The same entities the map's Needs review lists (services.neo4j.geo_service.get_locations_needing_review),
        # and the same address as lookup_address: the evidence address unless blank, else the ingestion query.
        address = (
            "trim(CASE WHEN trim(coalesce(n.location_raw, '')) <> '' THEN n.location_raw "
            "ELSE coalesce(n.geocoding_query, '') END)"
        )
        where = f"""
            WHERE n.case_id = $case_id
              AND {active_node_predicate('n')}
              AND n.geocoding_status = 'not_run'
              AND (n.latitude IS NULL OR n.longitude IS NULL)
              AND NONE(field IN coalesce(n.manual_fields, [])
                       WHERE field IN ['latitude', 'longitude', 'location_name', 'location_formatted'])
              AND NONE(label IN labels(n) WHERE label IN ['Document', 'RecycleBin', 'RecycleBinItem'])
              AND coalesce(n.system_node, false) <> true
              AND {address} <> ''
        """
        with driver.session() as session:
            total = session.run(f"MATCH (n) {where} RETURN count(n) AS c", case_id=case_id).single()["c"]
            rows = session.run(
                f"""MATCH (n) {where}
                RETURN n.key AS key, {address} AS address
                ORDER BY n.key LIMIT $limit""",
                case_id=case_id, limit=limit,
            ).data()
        return int(total or 0), rows

    def case_address_texts(self, case_id: str) -> list[str]:
        """Every address text of a case's entities (the evidence address unless blank, else the ingestion query):
        what the case's own state is read from (services.address_auto_rules.case_region)."""
        address = (
            "trim(CASE WHEN trim(coalesce(n.location_raw, '')) <> '' THEN n.location_raw "
            "ELSE coalesce(n.geocoding_query, '') END)"
        )
        with driver.session() as session:
            rows = session.run(
                f"""MATCH (n) WHERE n.case_id = $case_id AND {active_node_predicate('n')}
                      AND NONE(label IN labels(n) WHERE label IN ['Document', 'RecycleBin', 'RecycleBinItem'])
                      AND coalesce(n.system_node, false) <> true AND {address} <> ''
                    RETURN {address} AS address""",
                case_id=case_id,
            ).data()
        return [r["address"] for r in rows]

    def apply_looked_up_location(
        self,
        node_key: str,
        *,
        case_id: str,
        query: str,
        result: dict[str, Any],
        requested_by: str,
        requested_by_name: str | None,
        service: str,
        mode: str = "flag",
        region_added: str | None = None,
    ) -> dict[str, Any]:
        requested_at = datetime.now(timezone.utc).isoformat()
        updates: dict[str, Any] = {
            "latitude": self._coerce_scalar("latitude", result["latitude"]),
            "longitude": self._coerce_scalar("longitude", result["longitude"]),
            "geocoding_status": self.LOOKED_UP_STATUS,
            "geocoding_provider": result.get("provider") or "nominatim",
            "geocoding_query": query,
            "geocoding_formatted_address": result.get("formatted_address") or query,
            "geocoding_lookup_service": service,
            "geocoding_requested_by": requested_by,
            "geocoding_requested_by_name": requested_by_name,
            "geocoding_requested_at": requested_at,
            "geocoding_lookup_outcome": "placed",
            # 'flag': a person clicked Look up; 'auto': sent on its own because the case's lookup is automatic
            "geocoding_lookup_mode": mode,
        }
        if region_added:
            # the case's own state was added to the evidence text before it was sent (address_auto_rules)
            updates["geocoding_region_added"] = region_added
        if result.get("confidence"):
            updates["geocoding_confidence"] = result["confidence"]
        if result.get("location_granularity"):
            updates["location_granularity"] = result["location_granularity"]
        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                  AND (n.latitude IS NULL OR n.longitude IS NULL)
                  AND NONE(field IN coalesce(n.manual_fields, [])
                           WHERE field IN ['latitude', 'longitude', 'location_name', 'location_formatted'])
                SET n.geocoding_status_before_lookup = n.geocoding_status
                SET n += $updates
                RETURN n.key AS key
                """,
                key=node_key,
                case_id=case_id,
                updates=updates,
            ).single()
        if not record:
            raise LookupError(f"Node not found or no longer waiting for a lookup: {node_key}")
        return {"success": True, "node_key": node_key, **{k: updates[k] for k in (
            "latitude", "longitude", "geocoding_formatted_address", "geocoding_requested_at")}}

    def automatic_pins(self, case_id: str) -> list[dict[str, Any]]:
        """Pins an automatic lookup placed in a case that no person has confirmed or moved: key, the address text,
        and the service's address for the pin."""
        address = (
            "trim(CASE WHEN trim(coalesce(n.location_raw, '')) <> '' THEN n.location_raw "
            "ELSE coalesce(n.geocoding_query, '') END)"
        )
        with driver.session() as session:
            return session.run(
                f"""MATCH (n) WHERE n.case_id = $case_id AND {active_node_predicate('n')}
                      AND n.geocoding_status = $looked_up AND n.geocoding_lookup_mode = 'auto'
                      AND n.geocoding_requested_by = 'automatic'
                      AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                      AND NONE(field IN coalesce(n.manual_fields, [])
                               WHERE field IN ['latitude', 'longitude', 'location_name', 'location_formatted'])
                    RETURN n.key AS key, {address} AS address,
                           n.geocoding_formatted_address AS formatted_address
                    ORDER BY n.key""",
                case_id=case_id, looked_up=self.LOOKED_UP_STATUS,
            ).data()

    def withdraw_automatic_pin(self, node_key: str, *, case_id: str, outcome: str | None, status: str,
                               reason: str) -> bool:
        """Take an unconfirmed automatic pin off the map. The pin stays on the entity as withdrawn (where, the
        service's address, when and why); ``status`` 'not_run' sends it to the automatic lookup again, 'failed'
        leaves it for a person with ``outcome`` saying why."""
        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                  AND n.geocoding_status = $looked_up AND n.geocoding_lookup_mode = 'auto'
                  AND n.geocoding_requested_by = 'automatic'
                  AND NONE(field IN coalesce(n.manual_fields, [])
                           WHERE field IN ['latitude', 'longitude', 'location_name', 'location_formatted'])
                SET n.geocoding_withdrawn_latitude = n.latitude,
                    n.geocoding_withdrawn_longitude = n.longitude,
                    n.geocoding_withdrawn_formatted_address = n.geocoding_formatted_address,
                    n.geocoding_withdrawn_query = n.geocoding_query,
                    n.geocoding_withdrawn_at = $at,
                    n.geocoding_withdrawn_reason = $reason,
                    n.latitude = null, n.longitude = null,
                    n.geocoding_status = $status,
                    n.geocoding_lookup_outcome = $outcome
                RETURN n.key AS key
                """,
                key=node_key, case_id=case_id, looked_up=self.LOOKED_UP_STATUS, status=status, outcome=outcome,
                reason=reason, at=datetime.now(timezone.utc).isoformat(),
            ).single()
        return record is not None

    def record_lookup_outcome(
        self, node_key: str, *, case_id: str, outcome: str, requested_by: str, requested_by_name: str | None,
        status: str | None = None,
    ) -> None:
        """A lookup a person asked for found nothing (or the service did not answer): say so on the node; it stays
        flagged."""
        with driver.session() as session:
            session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                  AND (n.latitude IS NULL OR n.longitude IS NULL)
                SET n.geocoding_lookup_outcome = $outcome,
                    n.geocoding_requested_by = $requested_by,
                    n.geocoding_requested_by_name = $requested_by_name,
                    n.geocoding_requested_at = $requested_at,
                    n.geocoding_status = coalesce($status, n.geocoding_status)
                """,
                status=status,
                key=node_key,
                case_id=case_id,
                outcome=outcome,
                requested_by=requested_by,
                requested_by_name=requested_by_name,
                requested_at=datetime.now(timezone.utc).isoformat(),
            )

    def confirm_looked_up_location(
        self, node_key: str, *, case_id: str, confirmed_by: str, confirmed_by_name: str | None,
    ) -> dict[str, Any]:
        """A person confirms a looked-up pin: from now on it is their placement (Manual), with who and when kept."""
        confirmed_at = datetime.now(timezone.utc).isoformat()
        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                  AND n.geocoding_status = $looked_up
                  AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                SET n.manual_fields = reduce(
                        acc = coalesce(n.manual_fields, []),
                        field IN ['latitude', 'longitude'] |
                        CASE WHEN field IN acc THEN acc ELSE acc + field END
                    ),
                    n.geocoding_confirmed_by = $confirmed_by,
                    n.geocoding_confirmed_by_name = $confirmed_by_name,
                    n.geocoding_confirmed_at = $confirmed_at,
                    n.last_edited_at = $confirmed_at,
                    n.last_edited_by = $confirmed_by,
                    n.last_edit_source = 'map'
                RETURN n.key AS key, n.latitude AS latitude, n.longitude AS longitude
                """,
                key=node_key,
                case_id=case_id,
                looked_up=self.LOOKED_UP_STATUS,
                confirmed_by=confirmed_by,
                confirmed_by_name=confirmed_by_name,
                confirmed_at=confirmed_at,
            ).single()
        if not record:
            raise LookupError(f"No looked-up pin to confirm: {node_key}")
        return {"success": True, "node_key": node_key, "confirmed_at": confirmed_at,
                "latitude": record["latitude"], "longitude": record["longitude"]}

    def remove_location(
        self,
        node_key: str,
        *,
        case_id: str,
        edited_by: str | None = None,
    ) -> dict[str, Any]:
        result = self.update_node(
            node_key,
            case_id=case_id,
            properties={field: None for field in LOCATION_PROPERTY_KEYS},
            edited_by=edited_by,
            source_view="map",
        )
        # The values removed are kept in the manual-change record (one per field), so the location can be set
        # back (followups m11032229063349: they were nulled with no copy).
        changes = result.get("changes") or {}
        result["before"] = {field: change.get("before") for field, change in changes.items()}
        result["after"] = {field: change.get("after") for field, change in changes.items()}
        return result

    def batch_update_entities(
        self,
        updates: list[dict[str, Any]],
        case_id: str,
        *,
        edited_by: str | None = None,
    ) -> int:
        count = 0
        for update in updates[:500]:
            node_key = update.get("key")
            prop = update.get("property")
            if not node_key or not prop:
                continue
            value = update.get("value")
            kwargs: dict[str, Any] = {"case_id": case_id, "edited_by": edited_by, "source_view": "batch_update"}
            if prop == "name":
                kwargs["name"] = value
            elif prop == "summary":
                kwargs["summary"] = value
            elif prop == "notes":
                kwargs["notes"] = value
            elif prop in {"category", "type"}:
                kwargs["category"] = value
            elif prop == "specific_type":
                kwargs["specific_type"] = value
            else:
                kwargs["properties"] = {prop: value}
            self.update_node(str(node_key), **kwargs)
            count += 1
        return count


graph_edit_service = GraphEditService()
