"""
Timeline Service — chronological event retrieval from the graph.
"""

import logging
from typing import Dict, List, Optional

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


class TimelineService:

    def get_timeline_events(
        self,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        case_id: str = None,
    ) -> List[Dict]:
        """
        Get all nodes that have dates, sorted chronologically.

        Args:
            event_types: Filter by specific types (e.g., ['Transaction', 'Payment']).
                        If None, returns ALL entities with dates (not just event types).
            start_date: Filter events on or after this date (YYYY-MM-DD)
            end_date: Filter events on or before this date (YYYY-MM-DD)
            case_id: REQUIRED - Filter to only include nodes belonging to this case

        Returns:
            List of nodes with their connected entities, sorted by date
        """
        with driver.session() as session:
            # Build date filter conditions
            date_conditions = []
            # case_id is always required
            params = {"case_id": case_id}

            if start_date:
                date_conditions.append("n.date >= $start_date")
                params["start_date"] = start_date
            if end_date:
                date_conditions.append("n.date <= $end_date")
                params["end_date"] = end_date

            date_filter = " AND " + " AND ".join(date_conditions) if date_conditions else ""

            # Build type filter condition
            type_filter = ""
            if event_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = event_types

            # Always filter by case_id
            query = f"""
                MATCH (n)
                WHERE n.date IS NOT NULL
                AND NOT n:RecycleBin
                AND NOT n:RecycleBinItem
                AND coalesce(n.system_node, false) <> true
                {type_filter}
                {date_filter}
                AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE NOT connected:Document AND NOT connected:Case
                  AND NOT connected:RecycleBin AND NOT connected:RecycleBinItem
                  AND coalesce(connected.system_node, false) <> true
                  AND connected.case_id = $case_id
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
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(query, **params)

            events = []
            for record in result:
                event = {
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
                events.append(event)

            return events


timeline_service = TimelineService()
