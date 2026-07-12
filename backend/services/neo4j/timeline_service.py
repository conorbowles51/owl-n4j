"""
Timeline Service - chronological event retrieval from the graph.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Dict, List, Optional

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


class TimelineService:
    SORT_DATE_CYPHER = """
        CASE
            WHEN n.date IS NOT NULL AND toString(n.date) CONTAINS 'T' THEN split(toString(n.date), 'T')[0]
            WHEN n.date IS NOT NULL THEN substring(toString(n.date), 0, 10)
            WHEN 'date' IN coalesce(n.manual_fields, []) THEN NULL
            WHEN n.timestamp IS NOT NULL THEN substring(toString(n.timestamp), 0, 10)
            WHEN n.start_time IS NOT NULL THEN substring(toString(n.start_time), 0, 10)
            WHEN n.capture_time IS NOT NULL THEN substring(toString(n.capture_time), 0, 10)
            WHEN n.creation_time IS NOT NULL THEN substring(toString(n.creation_time), 0, 10)
            WHEN n.date_time IS NOT NULL THEN substring(toString(n.date_time), 0, 10)
            WHEN n.datetime IS NOT NULL THEN substring(toString(n.datetime), 0, 10)
            ELSE NULL
        END
    """
    SORT_TIME_CYPHER = """
        CASE
            WHEN n.time IS NOT NULL AND trim(toString(n.time)) <> ''
                THEN substring(toString(n.time), 0, 5)
            WHEN 'time' IN coalesce(n.manual_fields, []) THEN NULL
            WHEN n.date IS NOT NULL AND toString(n.date) CONTAINS 'T'
                THEN substring(split(toString(n.date), 'T')[1], 0, 5)
            WHEN n.date IS NOT NULL AND toString(n.date) =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(toString(n.date), 11, 5)
            WHEN n.timestamp IS NOT NULL AND replace(toString(n.timestamp), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.timestamp), 'T', ' '), 11, 5)
            WHEN n.start_time IS NOT NULL AND replace(toString(n.start_time), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.start_time), 'T', ' '), 11, 5)
            WHEN n.capture_time IS NOT NULL AND replace(toString(n.capture_time), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.capture_time), 'T', ' '), 11, 5)
            WHEN n.creation_time IS NOT NULL AND replace(toString(n.creation_time), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.creation_time), 'T', ' '), 11, 5)
            WHEN n.date_time IS NOT NULL AND replace(toString(n.date_time), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.date_time), 'T', ' '), 11, 5)
            WHEN n.datetime IS NOT NULL AND replace(toString(n.datetime), 'T', ' ') =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}.*'
                THEN substring(replace(toString(n.datetime), 'T', ' '), 11, 5)
            ELSE NULL
        END
    """

    @staticmethod
    def _normalise_date_time(date_value, time_value) -> tuple[str | None, str | None]:
        date_text = str(date_value) if date_value is not None else ""
        time_text = str(time_value) if time_value is not None else ""

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        if date_match:
            date_text = date_match.group(1)

        if not time_text:
            time_match = re.search(r"(?:T| )(\d{2}:\d{2})", str(date_value or ""))
            if time_match:
                time_text = time_match.group(1)

        if time_text:
            match = re.search(r"(\d{2}:\d{2})", time_text)
            time_text = match.group(1) if match else time_text

        return (date_text or None, time_text or None)

    @staticmethod
    def _encode_cursor(event: Dict) -> str:
        payload = {
            "date": event.get("date") or "",
            "time": event.get("time") or "99:99",
            "key": event.get("key") or "",
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> Dict | None:
        if not cursor:
            return None
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            payload = json.loads(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return {
            "date": str(payload.get("date") or ""),
            "time": str(payload.get("time") or ""),
            "key": str(payload.get("key") or ""),
        }

    @staticmethod
    def _build_filters(
        event_types: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        case_id: str,
    ) -> tuple[str, Dict]:
        conditions = [
            "sort_date IS NOT NULL",
            "NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])",
            "coalesce(properties(n)['system_node'], false) <> true",
            "n.case_id = $case_id",
        ]
        params: Dict = {"case_id": case_id}

        if event_types:
            conditions.append("labels(n)[0] IN $types")
            params["types"] = event_types
        if start_date:
            conditions.append("sort_date >= $start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append("sort_date <= $end_date")
            params["end_date"] = end_date

        return " AND ".join(conditions), params

    @staticmethod
    def _event_from_record(record) -> Dict:
        date_value, time_value = TimelineService._normalise_date_time(
            record["date"], record["time"]
        )
        event = {
            "key": record["key"],
            "name": record["name"],
            "type": record["type"],
            "date": date_value,
            "time": time_value,
            "amount": record["amount"],
            "summary": record["summary"],
            "notes": record["notes"],
            "connections": [c for c in record["connections"] if c["key"]],
        }
        record_keys = record.keys() if hasattr(record, "keys") else record
        for field in (
            "location",
            "location_raw",
            "location_formatted",
            "location_name",
            "latitude",
            "longitude",
            "source_files",
            "source_quotes",
            "source_references",
            "source_pages",
        ):
            if field in record_keys:
                event[field] = record[field]
        return event

    def get_timeline_events(
        self,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        case_id: str = None,
    ) -> List[Dict]:
        """Backward-compatible full timeline fetch."""
        page = self.get_timeline_page(
            event_types=event_types,
            start_date=start_date,
            end_date=end_date,
            case_id=case_id,
            limit=10000,
            cursor=None,
        )
        return page["events"]

    def get_timeline_page(
        self,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        case_id: str = None,
        limit: int = 500,
        cursor: str | None = None,
    ) -> Dict:
        """Get timeline events using stable keyset pagination."""
        limit = max(1, min(int(limit or 500), 2000))
        where_clause, params = self._build_filters(event_types, start_date, end_date, case_id)

        cursor_payload = self._decode_cursor(cursor)
        if cursor_payload:
            where_clause += """
                AND (
                    sort_date > $cursor_date
                    OR (
                        sort_date = $cursor_date
                        AND coalesce(sort_time, '99:99') > $cursor_time
                    )
                    OR (
                        sort_date = $cursor_date
                        AND coalesce(sort_time, '99:99') = $cursor_time
                        AND n.key > $cursor_key
                    )
                )
            """
            params.update(
                {
                    "cursor_date": cursor_payload["date"],
                    "cursor_time": cursor_payload["time"],
                    "cursor_key": cursor_payload["key"],
                }
            )

        page_params = dict(params)
        page_params["limit"] = limit + 1

        query = f"""
            MATCH (n)
            WITH
                n,
                {self.SORT_DATE_CYPHER} AS sort_date,
                {self.SORT_TIME_CYPHER} AS sort_time
            WHERE {where_clause}
            OPTIONAL MATCH (n)-[r]-(connected)
            WHERE connected IS NULL OR (
              NONE(label IN labels(connected) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
              AND coalesce(properties(connected)['system_node'], false) <> true
              AND connected.case_id = $case_id
            )
            WITH n, sort_date, sort_time, collect(DISTINCT {{
                key: connected.key,
                name: connected.name,
                type: labels(connected)[0],
                relationship: type(r),
                direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
            }}) AS connections
            RETURN
                n.key AS key,
                n.name AS name,
                labels(n)[0] AS type,
                sort_date AS date,
                sort_time AS time,
                n.amount AS amount,
                n.summary AS summary,
                n.notes AS notes,
                connections
            ORDER BY sort_date ASC, coalesce(sort_time, '99:99') ASC, n.key ASC
            LIMIT $limit
        """

        count_where, count_params = self._build_filters(event_types, start_date, end_date, case_id)
        count_query = f"""
            MATCH (n)
            WITH
                n,
                {self.SORT_DATE_CYPHER} AS sort_date,
                {self.SORT_TIME_CYPHER} AS sort_time
            WHERE {count_where}
            RETURN count(n) AS total
        """

        with driver.session() as session:
            rows = [self._event_from_record(record) for record in session.run(query, **page_params)]
            total_record = session.run(count_query, **count_params).single()

        has_more = len(rows) > limit
        events = rows[:limit]
        next_cursor = self._encode_cursor(events[-1]) if has_more and events else None
        return {
            "events": events,
            "count": len(events),
            "total": int(total_record["total"] or 0) if total_record else 0,
            "next_cursor": next_cursor,
        }

    def get_timeline_events_by_keys(
        self,
        *,
        case_id: str,
        event_keys: List[str],
        include_export_fields: bool = False,
    ) -> List[Dict]:
        """Fetch a case-scoped set of timeline events by key."""
        ordered_keys = []
        seen = set()
        for key in event_keys or []:
            key_text = str(key or "").strip()
            if key_text and key_text not in seen:
                seen.add(key_text)
                ordered_keys.append(key_text)
        if not ordered_keys:
            return []

        export_returns = ""
        if include_export_fields:
            export_returns = """
                n.location AS location,
                n.location_raw AS location_raw,
                n.location_formatted AS location_formatted,
                n.location_name AS location_name,
                n.latitude AS latitude,
                n.longitude AS longitude,
                n.source_files AS source_files,
                n.source_quotes AS source_quotes,
                n.source_references AS source_references,
                n.source_pages AS source_pages,
            """

        query = f"""
            MATCH (n)
            WITH
                n,
                {self.SORT_DATE_CYPHER} AS sort_date,
                {self.SORT_TIME_CYPHER} AS sort_time
            WHERE
                n.case_id = $case_id
                AND n.key IN $event_keys
                AND sort_date IS NOT NULL
                AND NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])
                AND coalesce(properties(n)['system_node'], false) <> true
            OPTIONAL MATCH (n)-[r]-(connected)
            WHERE connected IS NULL OR (
              NONE(label IN labels(connected) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
              AND coalesce(properties(connected)['system_node'], false) <> true
              AND connected.case_id = $case_id
            )
            WITH n, sort_date, sort_time, collect(DISTINCT {{
                key: connected.key,
                name: connected.name,
                type: labels(connected)[0],
                relationship: type(r),
                direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
            }}) AS connections
            RETURN
                n.key AS key,
                n.name AS name,
                labels(n)[0] AS type,
                sort_date AS date,
                sort_time AS time,
                n.amount AS amount,
                n.summary AS summary,
                n.notes AS notes,
                connections,
                {export_returns}
                n.key AS key_echo
            ORDER BY sort_date ASC, coalesce(sort_time, '99:99') ASC, n.key ASC
        """

        with driver.session() as session:
            return [
                self._event_from_record(record)
                for record in session.run(
                    query,
                    case_id=case_id,
                    event_keys=ordered_keys,
                )
            ]


timeline_service = TimelineService()
