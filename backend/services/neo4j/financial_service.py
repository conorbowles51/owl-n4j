"""
Financial Analysis Service — transaction queries, categories, and sub-transaction management.

Extracted from the monolithic neo4j_service.py. Every method that was on
Neo4jService and dealt with financial transactions now lives here.
"""

import logging
import re
from typing import Dict, List, Optional

from services.neo4j.driver import driver, safe_float

logger = logging.getLogger(__name__)

LEGACY_FINANCIAL_EVENT_TYPES = [
    "Transaction",
    "transaction",
    "Transfer",
    "Payment",
    "Check",
    "Invoice",
    "RealEstatePurchase",
    "Event",
]


class FinancialService:
    """Neo4j-backed service for financial transaction analysis."""

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        return "intelligence" if mode == "intelligence" else "transactions"

    @staticmethod
    def _transaction_like_clause(alias: str = "n") -> str:
        return f"""
            (
                labels({alias})[0] IN $financial_types
                OR {alias}.date IS NOT NULL
                OR {alias}.time IS NOT NULL
                OR {alias}.from_entity_key IS NOT NULL
                OR {alias}.from_entity_name IS NOT NULL
                OR {alias}.to_entity_key IS NOT NULL
                OR {alias}.to_entity_name IS NOT NULL
                OR {alias}.sender IS NOT NULL
                OR {alias}.receiver IS NOT NULL
                OR {alias}.parent_transaction_key IS NOT NULL
                OR coalesce({alias}.is_parent, false) = true
            )
        """

    def _get_dataset_metadata(self, session, case_id: str, mode: str) -> Dict[str, bool | str]:
        record = session.run(
            """
            MATCH (n {case_id: $case_id})
            WHERE n.amount IS NOT NULL
            RETURN
                count(n) AS total_amount_nodes,
                sum(
                    CASE
                        WHEN n.financial_model_version = 2
                          OR n.financial_view_mode IS NOT NULL
                          OR n.is_evidence_backed_transaction IS NOT NULL
                        THEN 1
                        ELSE 0
                    END
                ) AS tagged_amount_nodes
            """,
            case_id=case_id,
        ).single()

        total_amount_nodes = int(record["total_amount_nodes"] or 0) if record else 0
        tagged_amount_nodes = int(record["tagged_amount_nodes"] or 0) if record else 0
        uses_legacy = total_amount_nodes > 0 and tagged_amount_nodes < total_amount_nodes
        return {
            "dataset_mode": mode,
            "uses_legacy_financial_model": uses_legacy,
        }

    def _mode_filter_clause(self, alias: str, *, uses_legacy: bool, mode: str) -> str:
        normalized_mode = self._normalize_mode(mode)
        if uses_legacy:
            tx_clause = self._transaction_like_clause(alias)
            return tx_clause if normalized_mode == "transactions" else f"NOT {tx_clause}"
        if normalized_mode == "transactions":
            return f"coalesce({alias}.is_evidence_backed_transaction, false) = true"
        return (
            f"coalesce({alias}.financial_view_mode, "
            f"CASE WHEN coalesce({alias}.is_evidence_backed_transaction, false) THEN 'transaction' ELSE 'intelligence' END"
            f") = 'intelligence'"
        )

    def _record_to_transaction(self, record, *, uses_legacy: bool, mode: str) -> Dict:
        from_key = record["from_entity_key"] or record["rel_from_key"] or record["initiator_key"]
        from_name = record["from_entity_name"] or record["rel_from_name"] or record["initiator_name"] or record["prop_sender"]
        to_key = record["to_entity_key"] or record["rel_to_key"] or record["rf_key"]
        to_name = record["to_entity_name"] or record["rel_to_name"] or record["rf_name"] or record["prop_receiver"]

        amount_val = safe_float(record["amount"])
        if amount_val == 0:
            raw = record.get("raw_amount")
            if raw is not None:
                cleaned = re.sub(r"[^\d.\-]", "", str(raw))
                amount_val = safe_float(cleaned)
                if amount_val != 0:
                    logger.warning(
                        "Amount fallback used for tx %s: raw=%r -> %s",
                        record["key"], raw, amount_val
                    )
                else:
                    logger.warning(
                        "Amount resolved to 0 for tx %s: raw=%r",
                        record["key"], raw
                    )

        requested_mode = self._normalize_mode(mode)
        record_mode = record.get("financial_view_mode") or ("intelligence" if requested_mode == "intelligence" else "transaction")
        if uses_legacy:
            record_mode = "intelligence" if requested_mode == "intelligence" else "transaction"

        return {
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
            "financial_record_kind": record.get("financial_record_kind") or ("transaction" if record_mode == "transaction" else "other"),
            "financial_view_mode": record_mode,
            "is_financial_event": bool(record.get("is_financial_event")) or True,
            "is_evidence_backed_transaction": bool(record.get("is_evidence_backed_transaction")) and not uses_legacy,
            "evidence_strength": None if uses_legacy else record.get("evidence_strength"),
            "evidence_source_type": None if uses_legacy else record.get("evidence_source_type"),
            "source_document_id": record.get("source_document_id"),
            "source_filename": record.get("source_filename"),
            "source_page": record.get("source_page"),
            "source_excerpt": record.get("source_excerpt"),
            "extraction_confidence": (
                safe_float(record["extraction_confidence"])
                if record.get("extraction_confidence") is not None
                else None
            ),
        }

    def get_financial_transactions(
        self,
        case_id: str,
        types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        categories: Optional[List[str]] = None,
        mode: str = "transactions",
    ) -> Dict:
        """Get financial records with strict provenance mode and legacy fallback."""
        with driver.session() as session:
            normalized_mode = self._normalize_mode(mode)
            metadata = self._get_dataset_metadata(session, case_id, normalized_mode)
            uses_legacy = bool(metadata["uses_legacy_financial_model"])
            params = {"case_id": case_id, "financial_types": LEGACY_FINANCIAL_EVENT_TYPES}
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
                AND {self._mode_filter_clause("n", uses_legacy=uses_legacy, mode=normalized_mode)}
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
                    n.correction_reason AS correction_reason,
                    n.financial_record_kind AS financial_record_kind,
                    coalesce(
                        n.financial_view_mode,
                        CASE WHEN coalesce(n.is_evidence_backed_transaction, false) THEN 'transaction' ELSE 'intelligence' END
                    ) AS financial_view_mode,
                    coalesce(n.is_financial_event, false) AS is_financial_event,
                    coalesce(n.is_evidence_backed_transaction, false) AS is_evidence_backed_transaction,
                    n.evidence_strength AS evidence_strength,
                    n.evidence_source_type AS evidence_source_type,
                    n.source_document_id AS source_document_id,
                    n.source_filename AS source_filename,
                    n.source_page AS source_page,
                    n.source_excerpt AS source_excerpt,
                    n.extraction_confidence AS extraction_confidence
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(query, **params)
            transactions = [
                self._record_to_transaction(record, uses_legacy=uses_legacy, mode=normalized_mode)
                for record in result
            ]
            return {"transactions": transactions, "total": len(transactions), **metadata}

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

    def get_financial_summary(self, case_id: str, entity_key: str = None, mode: str = "transactions") -> Dict:
        """Get aggregated financial summary stats for a case."""
        with driver.session() as session:
            normalized_mode = self._normalize_mode(mode)
            metadata = self._get_dataset_metadata(session, case_id, normalized_mode)
            uses_legacy = bool(metadata["uses_legacy_financial_model"])
            filter_clause = self._mode_filter_clause("n", uses_legacy=uses_legacy, mode=normalized_mode)
            if entity_key:
                query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                      AND {filter_clause}
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
                record = session.run(
                    query,
                    case_id=case_id,
                    entity_key=entity_key,
                    financial_types=LEGACY_FINANCIAL_EVENT_TYPES,
                ).single()
                if not record or record["transaction_count"] == 0:
                    return {"transaction_count": 0, "total_inflows": 0, "total_outflows": 0, "net_flow": 0, **metadata}
                inflows = safe_float(record["total_inflows"])
                outflows = safe_float(record["total_outflows"])
                return {
                    "transaction_count": record["transaction_count"],
                    "total_inflows": inflows,
                    "total_outflows": outflows,
                    "net_flow": round(inflows - outflows, 2),
                    **metadata,
                }

            query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                  AND {filter_clause}
                WITH n, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                RETURN
                    count(n) AS transaction_count,
                    sum(abs(amt)) AS total_volume,
                    avg(abs(amt)) AS avg_amount,
                    max(abs(amt)) AS max_amount
            """
            record = session.run(
                query,
                case_id=case_id,
                financial_types=LEGACY_FINANCIAL_EVENT_TYPES,
            ).single()
            if not record or record["transaction_count"] == 0:
                return {"transaction_count": 0, "total_volume": 0, "avg_amount": 0, "max_amount": 0, **metadata}
            return {
                "transaction_count": record["transaction_count"],
                "total_volume": safe_float(record["total_volume"]),
                "avg_amount": safe_float(record["avg_amount"]),
                "max_amount": safe_float(record["max_amount"]),
                **metadata,
            }

    def get_financial_volume_over_time(self, case_id: str, mode: str = "transactions") -> Dict:
        """Get transaction volume grouped by date and category for chart data."""
        with driver.session() as session:
            normalized_mode = self._normalize_mode(mode)
            metadata = self._get_dataset_metadata(session, case_id, normalized_mode)
            uses_legacy = bool(metadata["uses_legacy_financial_model"])
            filter_clause = self._mode_filter_clause("n", uses_legacy=uses_legacy, mode=normalized_mode)
            query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.date IS NOT NULL
                  AND {filter_clause}
                WITH n.date AS date, coalesce(n.financial_category, 'Uncategorized') AS category, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                RETURN
                    date,
                    category,
                    sum(abs(amt)) AS total_amount,
                    count(*) AS count
                ORDER BY date ASC, category ASC
            """
            result = session.run(
                query,
                case_id=case_id,
                financial_types=LEGACY_FINANCIAL_EVENT_TYPES,
            )
            return {
                "data": [
                    {
                        "date": record["date"],
                        "category": record["category"],
                        "total_amount": safe_float(record["total_amount"]),
                        "count": record["count"],
                    }
                    for record in result
                ],
                **metadata,
            }

    def update_transaction_category(self, node_key: str, category: str, case_id: str) -> Dict:
        """Set the financial_category on a transaction node."""
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
        """Set manual from/to entity overrides on a transaction node."""
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

    def get_financial_categories(self, case_id: str, mode: str = "transactions") -> List[Dict]:
        """Get all financial categories for a case: predefined + persisted custom + orphaned from transactions."""
        predefined = {
            "Utility": "#3b82f6",
            "Payroll/Salary": "#22c55e",
            "Rent/Lease": "#8b5cf6",
            "Reimbursement": "#06b6d4",
            "Loan Payment": "#ef4444",
            "Insurance": "#f59e0b",
            "Subscription": "#ec4899",
            "Transfer": "#14b8a6",
            "Income": "#10b981",
            "Personal": "#f97316",
            "Legal/Professional": "#6366f1",
            "Other": "#6b7280",
        }
        result_categories = [
            {"name": name, "color": color, "builtin": True}
            for name, color in predefined.items()
        ]
        seen_names = set(predefined.keys())

        with driver.session() as session:
            normalized_mode = self._normalize_mode(mode)
            metadata = self._get_dataset_metadata(session, case_id, normalized_mode)
            uses_legacy = bool(metadata["uses_legacy_financial_model"])
            filter_clause = self._mode_filter_clause("n", uses_legacy=uses_legacy, mode=normalized_mode)
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

            orphan_query = """
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.financial_category IS NOT NULL
                  AND __FILTER__
                RETURN DISTINCT n.financial_category AS category
            """
            orphan_result = session.run(
                orphan_query.replace("__FILTER__", filter_clause),
                case_id=case_id,
                financial_types=LEGACY_FINANCIAL_EVENT_TYPES,
            )
            for record in orphan_result:
                name = record["category"]
                if name not in seen_names:
                    result_categories.append({"name": name, "color": "#6b7280", "builtin": False})
                    seen_names.add(name)

        return result_categories

    def create_financial_category(self, name: str, color: str, case_id: str) -> Dict:
        """Create or update a custom FinancialCategory node for a case."""
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
        """Set purpose, counterparty_details, and/or notes on a transaction node."""
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
        """Set from/to entity on multiple transaction nodes at once."""
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
