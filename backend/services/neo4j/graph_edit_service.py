"""Investigator-facing graph edit operations."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from postgres.models.graph_recycle_bin import GraphRecycleBinItem
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
LOCATION_AUDIT_KEYS = frozenset(
    {
        "geocoding_status",
        "geocoding_confidence",
        "location_source",
        "location_corrected_at",
        "location_corrected_by",
        "location_correction_source",
        "location_correction_address",
        "last_location_relocation_key",
    }
)


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
        if normalized.lower() in LOCATION_PROPERTY_KEYS:
            raise ValueError(
                f"Property '{key}' is a location field and must be edited through the geocode flow"
            )
        if normalized.lower() in SYSTEM_PROPERTY_KEYS:
            raise ValueError(f"Property '{key}' is a system field and cannot be edited")

    @staticmethod
    def _case_uuid(case_id: str) -> uuid.UUID:
        return uuid.UUID(str(case_id))

    @staticmethod
    def _recycle_key(node_key: str) -> str:
        return f"location_relocation_{node_key}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

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
        lat = self._coerce_scalar("latitude", latitude)
        lng = self._coerce_scalar("longitude", longitude)
        edited_at = datetime.now(timezone.utc).isoformat()

        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                SET n.location_name = $location_name,
                    n.location_formatted = $location_name,
                    n.location_raw = $location_name,
                    n.latitude = $latitude,
                    n.longitude = $longitude,
                    n.last_edited_at = $edited_at,
                    n.last_edited_by = $edited_by,
                    n.last_edit_source = $source_view
                SET n.manual_fields = reduce(
                    acc = coalesce(n.manual_fields, []),
                    field IN $manual_fields |
                    CASE WHEN field IN acc THEN acc ELSE acc + field END
                )
                RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
                """,
                key=node_key,
                case_id=case_id,
                location_name=location,
                latitude=lat,
                longitude=lng,
                edited_at=edited_at,
                edited_by=edited_by,
                source_view=source_view,
                manual_fields=sorted(LOCATION_PROPERTY_KEYS),
            ).single()

        if not record:
            raise LookupError(f"Node not found: {node_key}")

        return {
            "success": True,
            "node_key": node_key,
            "updated_fields": sorted(LOCATION_PROPERTY_KEYS),
            "category": self._current_category(list(record["labels"] or [])),
            "properties": dict(record["properties"] or {}),
        }

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

    def remove_location(
        self,
        node_key: str,
        *,
        case_id: str,
        edited_by: str | None = None,
    ) -> dict[str, Any]:
        edited_at = datetime.now(timezone.utc).isoformat()

        with driver.session() as session:
            record = session.run(
                f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                WHERE {active_node_predicate('n')}
                SET n.latitude = null,
                    n.longitude = null,
                    n.location_name = null,
                    n.location_formatted = null,
                    n.location_raw = null,
                    n.geocoding_status = null,
                    n.geocoding_confidence = null,
                    n.last_edited_at = $edited_at,
                    n.last_edited_by = $edited_by,
                    n.last_edit_source = 'map'
                RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
                """,
                key=node_key,
                case_id=case_id,
                edited_at=edited_at,
                edited_by=edited_by,
            ).single()

        if not record:
            raise LookupError(f"Node not found: {node_key}")

        return {
            "success": True,
            "node_key": node_key,
            "updated_fields": sorted(LOCATION_PROPERTY_KEYS),
            "category": self._current_category(list(record["labels"] or [])),
            "properties": dict(record["properties"] or {}),
        }

    def _location_snapshot(self, properties: dict[str, Any]) -> dict[str, Any]:
        keys = set(LOCATION_PROPERTY_KEYS) | set(LOCATION_AUDIT_KEYS)
        return {key: _json_safe(properties.get(key)) for key in sorted(keys)}

    def _record_location_relocation(
        self,
        node_key: str,
        *,
        case_id: str,
        node: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        corrected_at: datetime,
        corrected_by: str | None,
        source_view: str | None,
        db: Session,
    ) -> GraphRecycleBinItem:
        properties = node["properties"]
        labels = list(node["labels"] or [])
        category = self._current_category(labels) or (labels[0] if labels else None)
        snapshot = {
            "schema_version": 1,
            "case_id": case_id,
            "node_key": node_key,
            "node_name": properties.get("name"),
            "labels": labels,
            "before_location": before,
            "after_location": after,
            "before_manual_fields": _json_safe(properties.get("manual_fields") or []),
            "relocated_at": corrected_at.isoformat(),
            "relocated_by": corrected_by,
            "source_view": source_view,
        }

        item = GraphRecycleBinItem(
            case_id=self._case_uuid(case_id),
            recycle_key=self._recycle_key(node_key),
            item_type="location_relocation",
            original_key=node_key,
            original_name=properties.get("name"),
            original_type=category,
            reason="location_relocation",
            deleted_by=corrected_by,
            deleted_at=corrected_at,
            relationship_count=0,
            status="pending_delete",
            snapshot=snapshot,
        )
        db.add(item)
        return item

    def apply_geocoded_location(
        self,
        node_key: str,
        *,
        case_id: str,
        address: str,
        latitude: float,
        longitude: float,
        formatted_address: str,
        geocoder_confidence: str | None = None,
        provider: str | None = None,
        location_granularity: str | None = None,
        edited_by: str | None = None,
        edited_by_name: str | None = None,
        source_view: str | None = "map",
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Apply a geocode result and save the previous location for one-step undo."""
        if db is None:
            raise ValueError("db session is required for location corrections")
        if not case_id:
            raise ValueError("case_id is required")

        location_raw = address.strip()
        if not location_raw:
            raise ValueError("address cannot be empty")
        formatted = formatted_address.strip() if formatted_address else location_raw
        lat = self._coerce_scalar("latitude", latitude)
        lng = self._coerce_scalar("longitude", longitude)
        if lat is None or lng is None:
            raise ValueError("latitude and longitude are required")

        node = self._fetch_node(node_key, case_id)
        if not node:
            raise LookupError(f"Node not found: {node_key}")

        corrected_at = datetime.now(timezone.utc)
        corrected_at_iso = corrected_at.isoformat()
        clean_provider = provider or "nominatim"
        before = self._location_snapshot(node["properties"])
        after = {
            "geocoding_status": "success",
            "geocoding_confidence": "manual",
            "location_source": "manual",
            "latitude": lat,
            "longitude": lng,
            "location_raw": location_raw,
            "location_formatted": formatted,
            "location_name": formatted,
            "geocoding_provider": clean_provider,
            "geocoding_query": location_raw,
            "geocoding_formatted_address": formatted,
            "location_corrected_at": corrected_at_iso,
            "location_corrected_by": edited_by,
            "location_correction_source": source_view,
            "location_correction_address": location_raw,
        }
        if location_granularity:
            after["location_granularity"] = location_granularity

        history = _parse_history(node["properties"].get("manual_correction_history"))
        history.append(
            {
                "moved_by": edited_by or "unknown",
                "moved_by_name": edited_by_name,
                "moved_at": corrected_at_iso,
                "from_latitude": _json_safe(node["properties"].get("latitude")),
                "from_longitude": _json_safe(node["properties"].get("longitude")),
                "to_latitude": lat,
                "to_longitude": lng,
                "query": location_raw,
                "provider": clean_provider,
                "formatted_address": formatted,
            }
        )
        item = self._record_location_relocation(
            node_key,
            case_id=case_id,
            node=node,
            before=before,
            after=after,
            corrected_at=corrected_at,
            corrected_by=edited_by,
            source_view=source_view,
            db=db,
        )
        after["last_location_relocation_key"] = item.recycle_key
        item.snapshot["after_location"] = after

        updates = {
            **after,
            "manual_correction_history": json.dumps(history),
            "last_edited_at": corrected_at_iso,
            "last_edited_by": edited_by,
            "last_edit_source": source_view,
        }
        manual_fields = sorted(set(LOCATION_PROPERTY_KEYS) | {"geocoding_confidence", "location_source"})

        try:
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
                    )
                    RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
                    """,
                    key=node_key,
                    case_id=case_id,
                    updates=updates,
                    manual_fields=manual_fields,
                ).single()

            if not record:
                raise LookupError(f"Node not found: {node_key}")

            item.status = "active"
            db.commit()
            db.refresh(item)
        except Exception:
            db.rollback()
            raise

        return {
            "success": True,
            "node_key": node_key,
            "latitude": lat,
            "longitude": lng,
            "formatted_address": formatted,
            "confidence": "manual",
            "geocoder_confidence": geocoder_confidence,
            "applied": True,
            "undo_key": item.recycle_key,
            "corrected_at": corrected_at_iso,
            "corrected_by": edited_by,
            "previous_location": before,
            "properties": dict(record["properties"] or {}),
        }

    def undo_last_location_relocation(
        self,
        node_key: str,
        *,
        case_id: str,
        edited_by: str | None = None,
        source_view: str | None = "map",
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Undo the latest active location relocation for a node in this case."""
        if db is None:
            raise ValueError("db session is required for location correction undo")

        item = (
            db.query(GraphRecycleBinItem)
            .filter(
                GraphRecycleBinItem.case_id == self._case_uuid(case_id),
                GraphRecycleBinItem.original_key == node_key,
                GraphRecycleBinItem.item_type == "location_relocation",
                GraphRecycleBinItem.status == "active",
            )
            .order_by(GraphRecycleBinItem.deleted_at.desc())
            .with_for_update()
            .first()
        )
        if not item:
            raise LookupError(f"No location relocation to undo for node: {node_key}")

        snapshot = item.snapshot or {}
        before = snapshot.get("before_location") or {}
        manual_fields = snapshot.get("before_manual_fields")
        if not isinstance(manual_fields, list):
            manual_fields = []

        undo_at = datetime.now(timezone.utc).isoformat()
        restore_updates = {
            key: before.get(key)
            for key in sorted(set(LOCATION_PROPERTY_KEYS) | set(LOCATION_AUDIT_KEYS))
        }
        audit_updates = {
            "last_edited_at": undo_at,
            "last_edited_by": edited_by,
            "last_edit_source": source_view,
            "location_correction_undone_at": undo_at,
            "location_correction_undone_by": edited_by,
        }

        try:
            with driver.session() as session:
                record = session.run(
                    f"""
                    MATCH (n {{key: $key, case_id: $case_id}})
                    WHERE {active_node_predicate('n')}
                    SET n += $restore_updates
                    SET n += $audit_updates
                    SET n.manual_fields = $manual_fields
                    RETURN n.key AS key, labels(n) AS labels, properties(n) AS properties
                    """,
                    key=node_key,
                    case_id=case_id,
                    restore_updates=restore_updates,
                    audit_updates=audit_updates,
                    manual_fields=manual_fields,
                ).single()

            if not record:
                raise LookupError(f"Node not found: {node_key}")

            item.status = "restored"
            db.commit()
            db.refresh(item)
        except Exception:
            db.rollback()
            raise

        properties = dict(record["properties"] or {})
        return {
            "success": True,
            "node_key": node_key,
            "undone": True,
            "undo_key": item.recycle_key,
            "latitude": properties.get("latitude"),
            "longitude": properties.get("longitude"),
            "formatted_address": properties.get("location_formatted"),
            "confidence": properties.get("geocoding_confidence"),
            "properties": properties,
        }

    apply_location_correction = apply_geocoded_location
    undo_last_location_correction = undo_last_location_relocation

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
