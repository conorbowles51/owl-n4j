"""
Financial Analysis Service — transaction queries, categories, and sub-transaction management.

Extracted from the monolithic neo4j_service.py.  Every method that was on
Neo4jService and dealt with financial transactions now lives here.
"""

import logging
import re
from typing import Dict, List, Optional

from services.neo4j.driver import driver, safe_float

logger = logging.getLogger(__name__)


class FinancialService:
    """Neo4j-backed service for financial transaction analysis."""

    # ── Queries ───────────────────────────────────────────────────────────

    def get_financial_transactions(
        self,
        case_id: str,
        types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        categories: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Get all nodes that have amount properties, with from/to entity resolution.

        Args:
            case_id: REQUIRED - Filter to only include nodes belonging to this case
            types: Filter by specific node types (e.g., ['Transaction', 'Payment'])
            start_date: Filter on or after this date (YYYY-MM-DD)
            end_date: Filter on or before this date (YYYY-MM-DD)
            categories: Filter by financial_category values

        Returns:
            List of transaction dicts with from/to entity resolution
        """
        with driver.session() as session:
            params = {"case_id": case_id}
            conditions = []

            if types:
                conditions.append("labels(n)[0] IN $types")
                params["types"] = types
            if start_date:
                conditions.append("n.date >= $start_date")
                params["start_date"] = start_date
            if end_date:
                conditions.append("n.date <= $end_date")
                params["end_date"] = end_date
            if categories:
                conditions.append("coalesce(n.financial_category, 'Unknown') IN $categories")
                params["categories"] = categories

            extra_filter = (" AND " + " AND ".join(conditions)) if conditions else ""

            query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL
                AND n.case_id = $case_id
                {extra_filter}
                OPTIONAL MATCH (n)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(to_entity)
                WHERE to_entity.case_id = $case_id AND NOT to_entity:Document AND NOT to_entity:Case
                OPTIONAL MATCH (from_entity)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(n)
                WHERE from_entity.case_id = $case_id AND NOT from_entity:Document AND NOT from_entity:Case
                OPTIONAL MATCH (n)-[:RECEIVED_FROM]->(rf_entity)
                WHERE rf_entity.case_id = $case_id AND NOT rf_entity:Document AND NOT rf_entity:Case
                OPTIONAL MATCH (n)<-[:MADE_PAYMENT|INITIATED]-(initiator)
                WHERE initiator.case_id = $case_id AND NOT initiator:Document AND NOT initiator:Case
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.date AS date,
                    n.time AS time,
                    toFloat(replace(replace(replace(replace(
                      trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS amount,
                    n.amount AS raw_amount,
                    n.currency AS currency,
                    n.summary AS summary,
                    n.financial_category AS financial_category,
                    n.purpose AS purpose,
                    n.counterparty_details AS counterparty_details,
                    n.notes AS notes,
                    n.from_entity_key AS from_entity_key,
                    n.from_entity_name AS from_entity_name,
                    n.to_entity_key AS to_entity_key,
                    n.to_entity_name AS to_entity_name,
                    n.sender AS prop_sender,
                    n.receiver AS prop_receiver,
                    collect(DISTINCT to_entity.key)[0] AS rel_to_key,
                    collect(DISTINCT to_entity.name)[0] AS rel_to_name,
                    collect(DISTINCT from_entity.key)[0] AS rel_from_key,
                    collect(DISTINCT from_entity.name)[0] AS rel_from_name,
                    collect(DISTINCT rf_entity.key)[0] AS rf_key,
                    collect(DISTINCT rf_entity.name)[0] AS rf_name,
                    collect(DISTINCT initiator.key)[0] AS initiator_key,
                    collect(DISTINCT initiator.name)[0] AS initiator_name,
                    n.is_parent AS is_parent,
                    n.parent_transaction_key AS parent_transaction_key,
                    n.amount_corrected AS amount_corrected,
                    n.original_amount AS original_amount,
                    n.correction_reason AS correction_reason
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(query, **params)
            transactions = []
            for record in result:
                # Resolve from entity: manual override > relationship-derived > property fallback
                from_key = record["from_entity_key"] or record["rel_from_key"] or record["initiator_key"]
                from_name = record["from_entity_name"] or record["rel_from_name"] or record["initiator_name"] or record["prop_sender"]
                # Resolve to entity: manual override > relationship-derived > property fallback
                to_key = record["to_entity_key"] or record["rel_to_key"] or record["rf_key"]
                to_name = record["to_entity_name"] or record["rel_to_name"] or record["rf_name"] or record["prop_receiver"]

                amount_val = safe_float(record["amount"])
                if amount_val == 0:
                    raw = record.get("raw_amount")
                    if raw is not None:
                        cleaned = re.sub(r'[^\d.\-]', '', str(raw))
                        amount_val = safe_float(cleaned)
                        if amount_val != 0:
                            logger.warning(
                                "Amount fallback used for tx %s: raw=%r → %s",
                                record["key"], raw, amount_val
                            )
                        else:
                            logger.warning(
                                "Amount resolved to 0 for tx %s: raw=%r",
                                record["key"], raw
                            )

                transactions.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "date": record["date"],
                    "time": record["time"],
                    "amount": amount_val,
                    "currency": record["currency"],
                    "summary": record["summary"],
                    "category": record["financial_category"] or "Uncategorized",
                    "purpose": record["purpose"],
                    "counterparty_details": record["counterparty_details"],
                    "notes": record["notes"],
                    "from_entity": {"key": from_key, "name": from_name} if (from_key or from_name) else None,
                    "to_entity": {"key": to_key, "name": to_name} if (to_key or to_name) else None,
                    "has_manual_from": record["from_entity_key"] is not None,
                    "has_manual_to": record["to_entity_key"] is not None,
                    "is_parent": record["is_parent"] or False,
                    "parent_transaction_key": record["parent_transaction_key"],
                    "amount_corrected": record["amount_corrected"] or False,
                    "original_amount": record["original_amount"],
                    "correction_reason": record["correction_reason"],
                })
            return transactions

    def get_financial_entities(self, case_id: str) -> List[Dict]:
        """Return all non-transaction entities in a case for from/to entity pickers."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE NOT n:Document AND NOT n:Case
                  AND n.amount IS NULL
                  AND n.name IS NOT NULL
                RETURN DISTINCT n.key AS key, n.name AS name, labels(n)[0] AS type
                ORDER BY n.name
                """,
                case_id=case_id,
            )
            return [{"key": r["key"], "name": r["name"], "type": r["type"]} for r in result]

    def get_financial_summary(self, case_id: str, entity_key: str = None) -> Dict:
        """
        Get aggregated financial summary stats for a case.

        Args:
            case_id: REQUIRED - Case ID
            entity_key: Optional - If provided, compute inflows/outflows relative to this entity

        Returns:
            Dict with overview metrics (no entity) or entity-relative inflow/outflow metrics
        """
        with driver.session() as session:
            if entity_key:
                # Entity-relative mode: classify by relationship direction
                query = """
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    WITH n, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                    OPTIONAL MATCH (n)-[:FROM_ENTITY]->(fe) WHERE fe.case_id = $case_id
                    OPTIONAL MATCH (n)-[:TO_ENTITY]->(te) WHERE te.case_id = $case_id
                    OPTIONAL MATCH (n)<-[:MANUAL_FROM]-(mf) WHERE mf.case_id = $case_id
                    OPTIONAL MATCH (n)<-[:MANUAL_TO]-(mt) WHERE mt.case_id = $case_id
                    WITH n, amt,
                         coalesce(mf.key, fe.key) AS from_key,
                         coalesce(mt.key, te.key) AS to_key
                    WHERE from_key = $entity_key OR to_key = $entity_key
                    RETURN
                        count(n) AS transaction_count,
                        sum(CASE WHEN to_key = $entity_key THEN abs(amt) ELSE 0 END) AS total_inflows,
                        sum(CASE WHEN from_key = $entity_key THEN abs(amt) ELSE 0 END) AS total_outflows
                """
                record = session.run(query, case_id=case_id, entity_key=entity_key).single()
                if not record or record["transaction_count"] == 0:
                    return {"transaction_count": 0, "total_inflows": 0, "total_outflows": 0, "net_flow": 0}
                inflows = safe_float(record["total_inflows"])
                outflows = safe_float(record["total_outflows"])
                return {
                    "transaction_count": record["transaction_count"],
                    "total_inflows": inflows,
                    "total_outflows": outflows,
                    "net_flow": round(inflows - outflows, 2),
                }
            else:
                # Overview mode: total volume without directional classification
                query = """
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    WITH n, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                    RETURN
                        count(n) AS transaction_count,
                        sum(abs(amt)) AS total_volume,
                        avg(abs(amt)) AS avg_amount,
                        max(abs(amt)) AS max_amount
                """
                record = session.run(query, case_id=case_id).single()
                if not record or record["transaction_count"] == 0:
                    return {"transaction_count": 0, "total_volume": 0, "avg_amount": 0, "max_amount": 0}
                return {
                    "transaction_count": record["transaction_count"],
                    "total_volume": safe_float(record["total_volume"]),
                    "avg_amount": safe_float(record["avg_amount"]),
                    "max_amount": safe_float(record["max_amount"]),
                }

    def get_financial_volume_over_time(self, case_id: str) -> List[Dict]:
        """
        Get transaction volume grouped by date and category for chart data.

        Args:
            case_id: REQUIRED - Case ID

        Returns:
            List of {date, category, total_amount, count}
        """
        with driver.session() as session:
            query = """
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.date IS NOT NULL
                WITH n.date AS date, coalesce(n.financial_category, 'Uncategorized') AS category, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                RETURN
                    date,
                    category,
                    sum(abs(amt)) AS total_amount,
                    count(*) AS count
                ORDER BY date ASC, category ASC
            """
            result = session.run(query, case_id=case_id)
            return [
                {
                    "date": record["date"],
                    "category": record["category"],
                    "total_amount": safe_float(record["total_amount"]),
                    "count": record["count"],
                }
                for record in result
            ]

    def update_transaction_category(self, node_key: str, category: str, case_id: str) -> Dict:
        """
        Set the financial_category on a transaction node.

        Args:
            node_key: The node key
            category: Category string to set
            case_id: REQUIRED - Case ID

        Returns:
            Dict with success status
        """
        with driver.session() as session:
            query = """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.financial_category = $category
                RETURN n.key AS key
            """
            record = session.run(query, key=node_key, case_id=case_id, category=category).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"], "category": category}

    def update_transaction_from_to(
        self,
        node_key: str,
        case_id: str,
        from_key: Optional[str] = None,
        from_name: Optional[str] = None,
        to_key: Optional[str] = None,
        to_name: Optional[str] = None,
    ) -> Dict:
        """
        Set manual from/to entity overrides on a transaction node.

        Args:
            node_key: The node key
            case_id: REQUIRED - Case ID
            from_key: Key of the from entity (or None to clear)
            from_name: Display name of the from entity
            to_key: Key of the to entity (or None to clear)
            to_name: Display name of the to entity

        Returns:
            Dict with success status
        """
        with driver.session() as session:
            set_clauses = []
            params = {"key": node_key, "case_id": case_id}

            if from_key is not None:
                set_clauses.append("n.from_entity_key = $from_key")
                set_clauses.append("n.from_entity_name = $from_name")
                params["from_key"] = from_key
                params["from_name"] = from_name
            if to_key is not None:
                set_clauses.append("n.to_entity_key = $to_key")
                set_clauses.append("n.to_entity_name = $to_name")
                params["to_key"] = to_key
                params["to_name"] = to_name

            if not set_clauses:
                return {"success": False, "error": "No from/to data provided"}

            query = f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                SET {', '.join(set_clauses)}
                RETURN n.key AS key
            """
            record = session.run(query, **params).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"]}

    def get_financial_categories(self, case_id: str) -> List[Dict]:
        """
        Get all financial categories for a case: predefined + persisted custom + orphaned from transactions.

        Args:
            case_id: REQUIRED - Case ID

        Returns:
            List of dicts with name, color, builtin keys
        """
        predefined = {
            "Utility":            "#3b82f6",
            "Payroll/Salary":     "#22c55e",
            "Rent/Lease":         "#8b5cf6",
            "Reimbursement":      "#06b6d4",
            "Loan Payment":       "#ef4444",
            "Insurance":          "#f59e0b",
            "Subscription":       "#ec4899",
            "Transfer":           "#14b8a6",
            "Income":             "#10b981",
            "Personal":           "#f97316",
            "Legal/Professional": "#6366f1",
            "Other":              "#6b7280",
        }
        result_categories = [
            {"name": name, "color": color, "builtin": True}
            for name, color in predefined.items()
        ]
        seen_names = set(predefined.keys())

        with driver.session() as session:
            # Persisted custom FinancialCategory nodes for this case
            custom_query = """
                MATCH (c:FinancialCategory {case_id: $case_id})
                RETURN c.name AS name, c.color AS color
                ORDER BY c.name
            """
            custom_result = session.run(custom_query, case_id=case_id)
            for record in custom_result:
                name = record["name"]
                if name not in seen_names:
                    result_categories.append({"name": name, "color": record["color"] or "#6b7280", "builtin": False})
                    seen_names.add(name)

            # Orphaned categories on transaction nodes (no FinancialCategory node)
            orphan_query = """
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.financial_category IS NOT NULL
                RETURN DISTINCT n.financial_category AS category
            """
            orphan_result = session.run(orphan_query, case_id=case_id)
            for record in orphan_result:
                name = record["category"]
                if name not in seen_names:
                    result_categories.append({"name": name, "color": "#6b7280", "builtin": False})
                    seen_names.add(name)

        return result_categories

    def create_financial_category(self, name: str, color: str, case_id: str) -> Dict:
        """
        Create or update a custom FinancialCategory node for a case.

        Args:
            name: Category name
            color: Hex color string
            case_id: REQUIRED - Case ID

        Returns:
            Dict with success, name, color
        """
        with driver.session() as session:
            query = """
                MERGE (c:FinancialCategory {name: $name, case_id: $case_id})
                ON CREATE SET c.color = $color, c.created_at = datetime()
                ON MATCH SET c.color = $color
                RETURN c.name AS name, c.color AS color
            """
            record = session.run(query, name=name, color=color, case_id=case_id).single()
            if not record:
                return {"success": False, "error": "Failed to create category"}
            return {"success": True, "name": record["name"], "color": record["color"]}

    def update_transaction_details(
        self,
        node_key: str,
        case_id: str,
        purpose: Optional[str] = None,
        counterparty_details: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict:
        """
        Set purpose, counterparty_details, and/or notes on a transaction node.

        Args:
            node_key: The node key
            case_id: REQUIRED - Case ID
            purpose: Optional purpose text
            counterparty_details: Optional counterparty details text
            notes: Optional investigation notes

        Returns:
            Dict with success status
        """
        with driver.session() as session:
            set_clauses = []
            params = {"key": node_key, "case_id": case_id}

            if purpose is not None:
                set_clauses.append("n.purpose = $purpose")
                params["purpose"] = purpose
            if counterparty_details is not None:
                set_clauses.append("n.counterparty_details = $counterparty_details")
                params["counterparty_details"] = counterparty_details
            if notes is not None:
                set_clauses.append("n.notes = $notes")
                params["notes"] = notes

            if not set_clauses:
                return {"success": False, "error": "No details provided"}

            query = f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                SET {', '.join(set_clauses)}
                RETURN n.key AS key
            """
            record = session.run(query, **params).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"]}

    def batch_update_from_to(
        self,
        node_keys: List[str],
        case_id: str,
        from_key: Optional[str] = None,
        from_name: Optional[str] = None,
        to_key: Optional[str] = None,
        to_name: Optional[str] = None,
    ) -> Dict:
        """
        Set from/to entity on multiple transaction nodes at once.

        Args:
            node_keys: List of node keys to update
            case_id: REQUIRED - Case ID
            from_key: Key of the from entity
            from_name: Display name of the from entity
            to_key: Key of the to entity
            to_name: Display name of the to entity

        Returns:
            Dict with success count
        """
        results = []
        for key in node_keys:
            result = self.update_transaction_from_to(
                node_key=key,
                case_id=case_id,
                from_key=from_key,
                from_name=from_name,
                to_key=to_key,
                to_name=to_name,
            )
            results.append(result)
        success_count = sum(1 for r in results if r.get("success"))
        return {"success": True, "updated": success_count, "total": len(node_keys)}

    def update_transaction_amount(self, node_key: str, case_id: str, new_amount: float, correction_reason: str) -> Dict:
        """Update a transaction amount, preserving the original value for audit trail."""
        with driver.session() as session:
            # Single query: conditionally preserve original_amount on first correction
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.original_amount = CASE WHEN n.original_amount IS NULL THEN n.amount ELSE n.original_amount END,
                    n.amount = $new_amount,
                    n.amount_corrected = true,
                    n.correction_reason = $correction_reason
                RETURN n.key AS key, n.amount AS amount, n.original_amount AS original_amount
                """,
                key=node_key,
                case_id=case_id,
                new_amount=new_amount,
                correction_reason=correction_reason,
            ).single()
            if not result:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "key": result["key"],
                "amount": result["amount"],
                "original_amount": result["original_amount"],
            }


    def link_sub_transaction(self, parent_key: str, child_key: str, case_id: str) -> Dict:
        """Link a child transaction to a parent transaction."""
        with driver.session() as session:
            check = session.run(
                """
                MATCH (parent {key: $parent_key, case_id: $case_id})
                MATCH (child {key: $child_key, case_id: $case_id})
                RETURN parent.key AS pk, child.key AS ck
                """,
                parent_key=parent_key, child_key=child_key, case_id=case_id,
            ).single()
            if not check:
                raise ValueError(f"One or both nodes not found in case {case_id}")

            session.run(
                """
                MATCH (parent {key: $parent_key, case_id: $case_id})
                MATCH (child {key: $child_key, case_id: $case_id})
                MERGE (child)-[:PART_OF]->(parent)
                SET child.parent_transaction_key = $parent_key,
                    parent.is_parent = true
                """,
                parent_key=parent_key, child_key=child_key, case_id=case_id,
            )
            return {"success": True, "parent_key": parent_key, "child_key": child_key}

    def unlink_sub_transaction(self, child_key: str, case_id: str) -> Dict:
        """Remove a child transaction from its parent group."""
        with driver.session() as session:
            parent_result = session.run(
                """
                MATCH (child {key: $child_key, case_id: $case_id})-[:PART_OF]->(parent)
                RETURN parent.key AS parent_key
                """,
                child_key=child_key, case_id=case_id,
            ).single()

            if not parent_result:
                raise ValueError(f"Child node {child_key} has no parent relationship")

            parent_key = parent_result["parent_key"]

            session.run(
                """
                MATCH (child {key: $child_key, case_id: $case_id})-[r:PART_OF]->(parent)
                DELETE r
                REMOVE child.parent_transaction_key
                """,
                child_key=child_key, case_id=case_id,
            )

            remaining = session.run(
                """
                MATCH (child)-[:PART_OF]->(parent {key: $parent_key, case_id: $case_id})
                RETURN count(child) AS count
                """,
                parent_key=parent_key, case_id=case_id,
            ).single()

            if remaining and remaining["count"] == 0:
                session.run(
                    "MATCH (n {key: $key, case_id: $case_id}) SET n.is_parent = false",
                    key=parent_key, case_id=case_id,
                )

            return {"success": True, "child_key": child_key, "parent_key": parent_key}

    def get_transaction_children(self, parent_key: str, case_id: str) -> list:
        """Get all child sub-transactions for a parent."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (child)-[:PART_OF]->(parent {key: $parent_key, case_id: $case_id})
                RETURN child.key AS key, child.name AS name, child.date AS date,
                       child.time AS time, child.amount AS amount, child.type AS type,
                       child.financial_category AS financial_category,
                       child.from_entity_name AS from_name, child.to_entity_name AS to_name,
                       child.purpose AS purpose, child.notes AS notes,
                       child.amount_corrected AS amount_corrected,
                       child.original_amount AS original_amount,
                       child.correction_reason AS correction_reason
                ORDER BY child.date
                """,
                parent_key=parent_key, case_id=case_id,
            )
            children = []
            for record in result:
                children.append({k: record[k] for k in record.keys()})
            return children


financial_service = FinancialService()
