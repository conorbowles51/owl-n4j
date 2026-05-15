"""
Timeline Service - chronological event retrieval from the graph.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Dict, List, Optional

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


class TimelineService:
    @staticmethod
    def _encode_cursor(event: Dict) -> str:
        payload = {
            "date": event.get("date") or "",
            "time": event.get("time") or "",
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
            "n.date IS NOT NULL",
            "NONE(label IN labels(n) WHERE label IN ['RecycleBin', 'RecycleBinItem'])",
            "coalesce(properties(n)['system_node'], false) <> true",
            "n.case_id = $case_id",
        ]
        params: Dict = {"case_id": case_id}

        if event_types:
            conditions.append("labels(n)[0] IN $types")
            params["types"] = event_types
        if start_date:
            conditions.append("n.date >= $start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append("n.date <= $end_date")
            params["end_date"] = end_date

        return " AND ".join(conditions), params

    @staticmethod
    def _event_from_record(record) -> Dict:
        return {
            "key": record["key"],
            "name": record["name"],
            "type": record["type"],
            "date": record["date"],
            "time": record["time"],
            "amount": record["amount"],
            "summary": record["summary"],
            "notes": record["notes"],
            "connections": [c for c in record["connections"] if c["key"]],
        }

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
                    n.date > $cursor_date
                    OR (
                        n.date = $cursor_date
                        AND coalesce(n.time, '') > $cursor_time
                    )
                    OR (
                        n.date = $cursor_date
                        AND coalesce(n.time, '') = $cursor_time
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
            WHERE {where_clause}
            OPTIONAL MATCH (n)-[r]-(connected)
            WHERE connected IS NULL OR (
              NONE(label IN labels(connected) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
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
                n.key AS key,
                n.name AS name,
                labels(n)[0] AS type,
                n.date AS date,
                n.time AS time,
                n.amount AS amount,
                n.summary AS summary,
                n.notes AS notes,
                connections
            ORDER BY n.date ASC, coalesce(n.time, '') ASC, n.key ASC
            LIMIT $limit
        """

        count_where, count_params = self._build_filters(event_types, start_date, end_date, case_id)
        count_query = f"""
            MATCH (n)
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


timeline_service = TimelineService()
