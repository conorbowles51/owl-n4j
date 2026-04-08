"""
Financial Router - endpoints for financial analysis and transaction visualization.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from services import neo4j_service
from services.financial_export_service import render_financial_export

router = APIRouter(prefix="/api/financial", tags=["financial"])


def _parse_csv_param(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _entity_value(entity) -> Optional[str]:
    if isinstance(entity, dict):
        return entity.get("key") or entity.get("name")
    if isinstance(entity, str):
        return entity
    return None


def _entity_name(entity) -> Optional[str]:
    if isinstance(entity, dict):
        return entity.get("name") or entity.get("key")
    if isinstance(entity, str):
        return entity
    return None


def _matches_text_search(transaction: dict, query: str) -> bool:
    q = query.lower()
    fields = [
        transaction.get("name"),
        transaction.get("purpose"),
        transaction.get("notes"),
        transaction.get("counterparty_details"),
        transaction.get("summary"),
        transaction.get("category"),
        _entity_name(transaction.get("from_entity")),
        _entity_name(transaction.get("to_entity")),
    ]
    return any(q in (field or "").lower() for field in fields)


def _apply_directional_filters(
    transactions: list[dict],
    from_entities: set[str],
    to_entities: set[str],
) -> list[dict]:
    if not from_entities and not to_entities:
        return transactions

    filtered = []
    for transaction in transactions:
        from_value = _entity_value(transaction.get("from_entity"))
        to_value = _entity_value(transaction.get("to_entity"))
        if from_entities and (not from_value or from_value not in from_entities):
            continue
        if to_entities and (not to_value or to_value not in to_entities):
            continue
        filtered.append(transaction)
    return filtered


def _build_entity_flow_rows(
    transactions: list[dict],
    side: str,
    counterpart_selections: set[str],
) -> list[dict]:
    grouped: dict[str, dict] = {}
    counter_side = "to_entity" if side == "from_entity" else "from_entity"

    for transaction in transactions:
        counterpart = _entity_value(transaction.get(counter_side))
        if counterpart_selections and (not counterpart or counterpart not in counterpart_selections):
            continue

        entity = transaction.get(side)
        entity_value = _entity_value(entity)
        entity_name = _entity_name(entity)
        if not entity_value or not entity_name:
            continue

        current = grouped.get(entity_value)
        if current:
            current["count"] += 1
            current["totalAmount"] += abs(float(transaction.get("amount") or 0))
            continue

        grouped[entity_value] = {
            "key": entity_value,
            "name": entity_name,
            "count": 1,
            "totalAmount": abs(float(transaction.get("amount") or 0)),
        }

    return sorted(
        grouped.values(),
        key=lambda row: (-row["totalAmount"], row["name"].lower()),
    )


def _collect_entity_notes(case_id: str, transactions: list[dict]) -> list[dict]:
    entity_keys = set()
    for transaction in transactions:
        from_entity = transaction.get("from_entity")
        to_entity = transaction.get("to_entity")
        if isinstance(from_entity, dict) and from_entity.get("key"):
            entity_keys.add(from_entity["key"])
        if isinstance(to_entity, dict) and to_entity.get("key"):
            entity_keys.add(to_entity["key"])

    if not entity_keys:
        return []

    notes = []
    with neo4j_service._driver.session() as session:
        result = session.run(
            """
            MATCH (n {case_id: $case_id})
            WHERE n.key IN $keys AND NOT n:Document
            RETURN n.key AS key, n.name AS name,
                   labels(n)[0] AS type,
                   n.notes AS notes, n.summary AS summary
            """,
            case_id=case_id,
            keys=list(entity_keys),
        )
        for record in result:
            value = dict(record)
            if value.get("notes") or value.get("summary"):
                notes.append(value)

    notes.sort(key=lambda entry: (entry.get("name") or "").lower())
    return notes


class CategorizeRequest(BaseModel):
    category: str
    case_id: str


class FromToRequest(BaseModel):
    case_id: str
    from_key: Optional[str] = None
    from_name: Optional[str] = None
    to_key: Optional[str] = None
    to_name: Optional[str] = None


class BatchCategorizeRequest(BaseModel):
    node_keys: List[str]
    category: str
    case_id: str


class DetailsRequest(BaseModel):
    case_id: str
    purpose: Optional[str] = None
    counterparty_details: Optional[str] = None
    notes: Optional[str] = None


class BatchFromToRequest(BaseModel):
    node_keys: List[str]
    case_id: str
    from_key: Optional[str] = None
    from_name: Optional[str] = None
    to_key: Optional[str] = None
    to_name: Optional[str] = None


class CreateCategoryRequest(BaseModel):
    name: str
    color: str
    case_id: str


@router.get("")
async def get_financial_transactions(
    case_id: str = Query(..., description="REQUIRED: Filter to transactions in this case"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
    types: Optional[str] = Query(None, description="Comma-separated transaction types to include"),
    start_date: Optional[str] = Query(None, description="Filter on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter on or before this date (YYYY-MM-DD)"),
    categories: Optional[str] = Query(None, description="Comma-separated financial categories to include"),
):
    """
    Get financial transactions with from/to entity resolution for a specific case.
    """
    try:
        parsed_types = [t.strip() for t in types.split(",") if t.strip()] if types else None
        parsed_categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

        transactions = neo4j_service.get_financial_transactions(
            case_id=case_id,
            mode=mode,
            types=parsed_types,
            start_date=start_date,
            end_date=end_date,
            categories=parsed_categories,
        )
        return transactions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities")
async def get_financial_entities(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Return all non-transaction entities in a case for from/to pickers."""
    try:
        entities = neo4j_service.get_financial_entities(case_id)
        return {"entities": entities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_financial_summary(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
    entity_key: Optional[str] = Query(None, description="Optional entity key for entity-relative inflow/outflow"),
):
    """
    Get aggregated financial summary statistics for a case.
    Without entity_key: returns overview metrics (total_volume, avg_amount, etc.)
    With entity_key: returns entity-relative inflows/outflows.
    """
    try:
        return neo4j_service.get_financial_summary(case_id=case_id, entity_key=entity_key, mode=mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/volume")
async def get_financial_volume(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
):
    """
    Get transaction volume over time grouped by date and type for chart data.
    """
    try:
        return neo4j_service.get_financial_volume_over_time(case_id=case_id, mode=mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/categorize/{node_key}")
async def categorize_transaction(node_key: str, body: CategorizeRequest):
    """
    Set the financial category on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_category(
            node_key=node_key,
            category=body.category,
            case_id=body.case_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/batch-categorize")
async def batch_categorize_transactions(body: BatchCategorizeRequest):
    """
    Set the financial category on multiple transaction nodes at once.
    """
    try:
        results = []
        for key in body.node_keys:
            result = neo4j_service.update_transaction_category(
                node_key=key,
                category=body.category,
                case_id=body.case_id,
            )
            results.append(result)
        success_count = sum(1 for r in results if r.get("success"))
        return {"success": True, "updated": success_count, "total": len(body.node_keys)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/from-to/{node_key}")
async def update_from_to(node_key: str, body: FromToRequest):
    """
    Set manual from/to entity override on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_from_to(
            node_key=node_key,
            case_id=body.case_id,
            from_key=body.from_key,
            from_name=body.from_name,
            to_key=body.to_key,
            to_name=body.to_name,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/details/{node_key}")
async def update_transaction_details(node_key: str, body: DetailsRequest):
    """
    Set purpose, counterparty_details, and/or notes on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_details(
            node_key=node_key,
            case_id=body.case_id,
            purpose=body.purpose,
            counterparty_details=body.counterparty_details,
            notes=body.notes,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/batch-from-to")
async def batch_update_from_to(body: BatchFromToRequest):
    """
    Set from/to entity on multiple transaction nodes at once.
    """
    try:
        result = neo4j_service.batch_update_from_to(
            node_keys=body.node_keys,
            case_id=body.case_id,
            from_key=body.from_key,
            from_name=body.from_name,
            to_key=body.to_key,
            to_name=body.to_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_categories(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
):
    """
    Get predefined + custom financial categories found in a case.
    """
    try:
        categories = neo4j_service.get_financial_categories(case_id=case_id, mode=mode)
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


PREDEFINED_CATEGORY_NAMES = {
    "Utility", "Payroll/Salary", "Rent/Lease", "Reimbursement",
    "Loan Payment", "Insurance", "Subscription", "Transfer",
    "Income", "Personal", "Legal/Professional", "Other",
}


@router.post("/categories")
async def create_category(body: CreateCategoryRequest):
    """
    Create a custom financial category for a case (persisted as a FinancialCategory node).
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    if name in PREDEFINED_CATEGORY_NAMES:
        raise HTTPException(status_code=400, detail=f"'{name}' is a predefined category and cannot be overridden")
    try:
        result = neo4j_service.create_financial_category(
            name=name,
            color=body.color,
            case_id=body.case_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to create category"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BulkCorrectionItem(BaseModel):
    name: str
    new_amount: float
    correction_reason: str


class BulkCorrectRequest(BaseModel):
    case_id: str
    corrections: List[BulkCorrectionItem]


class UpdateAmountRequest(BaseModel):
    case_id: str
    new_amount: float
    correction_reason: str


@router.put("/transactions/{node_key}/amount")
async def update_transaction_amount(node_key: str, body: UpdateAmountRequest):
    """Update a transaction amount with audit trail."""
    if body.new_amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")
    try:
        result = neo4j_service.update_transaction_amount(
            node_key=node_key,
            case_id=body.case_id,
            new_amount=body.new_amount,
            correction_reason=body.correction_reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions/bulk-correct")
async def bulk_correct_transactions(body: BulkCorrectRequest):
    """Apply amount corrections in bulk, matching by transaction name."""
    if not body.corrections:
        raise HTTPException(status_code=400, detail="No corrections provided")
    try:
        # Fetch all transactions for this case to match by name
        all_txns_result = neo4j_service.get_financial_transactions(case_id=body.case_id)
        all_txns = (
            all_txns_result.get("transactions", [])
            if isinstance(all_txns_result, dict)
            else all_txns_result
        )

        # Build a lookup: lowercase name -> list of transaction dicts
        name_lookup: dict = {}
        for t in all_txns:
            name = (t.get("name") or "").strip().lower()
            if name:
                name_lookup.setdefault(name, []).append(t)

        results = []
        for correction in body.corrections:
            search_name = correction.name.strip().lower()
            if not search_name:
                results.append({"name": correction.name, "status": "skipped", "reason": "Empty name"})
                continue

            matches = name_lookup.get(search_name)
            if not matches:
                results.append({"name": correction.name, "status": "not_found", "reason": "No matching transaction"})
                continue

            if correction.new_amount == 0:
                results.append({"name": correction.name, "status": "skipped", "reason": "Amount cannot be zero"})
                continue

            for match in matches:
                try:
                    neo4j_service.update_transaction_amount(
                        node_key=match["key"],
                        case_id=body.case_id,
                        new_amount=correction.new_amount,
                        correction_reason=correction.correction_reason,
                    )
                    results.append({
                        "name": correction.name,
                        "key": match["key"],
                        "status": "corrected",
                        "old_amount": match.get("amount"),
                        "new_amount": correction.new_amount,
                    })
                except Exception as exc:
                    results.append({
                        "name": correction.name,
                        "key": match["key"],
                        "status": "error",
                        "reason": str(exc),
                    })

        corrected = sum(1 for r in results if r["status"] == "corrected")
        not_found = sum(1 for r in results if r["status"] == "not_found")
        errors = sum(1 for r in results if r["status"] == "error")
        return {
            "success": True,
            "corrected": corrected,
            "not_found": not_found,
            "errors": errors,
            "total": len(body.corrections),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LinkSubTransactionRequest(BaseModel):
    case_id: str
    child_key: str


@router.post("/transactions/{parent_key}/sub-transactions")
async def link_sub_transaction(parent_key: str, body: LinkSubTransactionRequest):
    """Link a child transaction to a parent."""
    if parent_key == body.child_key:
        raise HTTPException(status_code=400, detail="Cannot link a transaction to itself")
    try:
        result = neo4j_service.link_sub_transaction(parent_key, body.child_key, body.case_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/transactions/{child_key}/parent")
async def unlink_sub_transaction(
    child_key: str,
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Remove a child transaction from its parent group."""
    try:
        result = neo4j_service.unlink_sub_transaction(child_key, case_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions/{parent_key}/sub-transactions")
async def get_transaction_children(
    parent_key: str,
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Get all child sub-transactions for a parent."""
    try:
        children = neo4j_service.get_transaction_children(parent_key, case_id)
        return {"children": children, "count": len(children)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/pdf")
async def export_financial_pdf(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
    case_name: str = Query("Case", description="Case name for the header"),
    categories: Optional[str] = Query(None, description="Comma-separated categories to filter"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    entity_key: Optional[str] = Query(None, description="Filter by entity key (from/to)"),
    entity_name: Optional[str] = Query(None, description="Entity name for filter display"),
    entity: Optional[str] = Query(None, description="Entity name to filter by from/to (legacy)"),
    search: Optional[str] = Query(None, description="Free-text search term"),
    search_header: Optional[str] = Query(None, description="Optional header search term"),
    from_entities: Optional[str] = Query(None, description="Comma-separated sender entity keys"),
    to_entities: Optional[str] = Query(None, description="Comma-separated beneficiary entity keys"),
    include_entity_notes: bool = Query(True, description="Include entity notes appendix"),
):
    """Export filtered financial transactions as a PDF report.

    Designed for print-friendly output suitable for attorney-client meetings
    where laptops and internet are unavailable (e.g., jail visits).
    Includes transaction names, AI summaries, and entity notes appendix.
    """
    try:
        result = neo4j_service.get_financial_transactions(case_id=case_id, mode=mode)
        transactions = result.get("transactions", []) if isinstance(result, dict) else result
        filters = []
        category_list = _parse_csv_param(categories)
        from_entity_values = set(_parse_csv_param(from_entities))
        to_entity_values = set(_parse_csv_param(to_entities))

        if category_list:
            transactions = [
                t
                for t in transactions
                if (t.get("category") or "Uncategorized") in category_list
            ]
            filters.append(f"Categories: {', '.join(category_list)}")
        if start_date:
            transactions = [t for t in transactions if t.get("date") and t["date"] >= start_date]
            filters.append(f"From: {start_date}")
        if end_date:
            transactions = [t for t in transactions if t.get("date") and t["date"] <= end_date]
            filters.append(f"To: {end_date}")
        if entity_key:
            display_name = entity_name or entity_key
            transactions = [
                t for t in transactions
                if (isinstance(t.get("from_entity"), dict) and t["from_entity"].get("key") == entity_key)
                or (isinstance(t.get("to_entity"), dict) and t["to_entity"].get("key") == entity_key)
                or t.get("from_entity") == entity_key
                or t.get("to_entity") == entity_key
            ]
            filters.append(f"Entity: {display_name}")
        elif entity:
            # Legacy: filter by entity name
            transactions = [
                t for t in transactions
                if (isinstance(t.get("from_entity"), dict) and t["from_entity"].get("name") == entity)
                or (isinstance(t.get("to_entity"), dict) and t["to_entity"].get("name") == entity)
            ]
            filters.append(f"Entity: {entity}")
        if search_header:
            transactions = [t for t in transactions if _matches_text_search(t, search_header)]
            filters.append(f'Search: "{search_header}"')
        elif search:
            transactions = [t for t in transactions if _matches_text_search(t, search)]
            filters.append(f'Search: "{search}"')

        base_filtered_transactions = transactions

        entity_flow = None
        if mode == "transactions":
            entity_flow = {
                "senders": _build_entity_flow_rows(
                    base_filtered_transactions, "from_entity", to_entity_values
                ),
                "beneficiaries": _build_entity_flow_rows(
                    base_filtered_transactions, "to_entity", from_entity_values
                ),
            }

        transactions = _apply_directional_filters(
            base_filtered_transactions, from_entity_values, to_entity_values
        )
        if from_entity_values:
            filters.append(f"Senders: {len(from_entity_values)} selected")
        if to_entity_values:
            filters.append(f"Beneficiaries: {len(to_entity_values)} selected")

        filters_description = " | ".join(filters) if filters else ""

        # Collect entity notes for appendix
        entity_notes = []
        if include_entity_notes:
            try:
                entity_notes = _collect_entity_notes(case_id, transactions)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to fetch entity notes: {e}")

        rendered = render_financial_export(
            transactions,
            case_name,
            filters_description,
            entity_notes=entity_notes,
            entity_flow=entity_flow,
        )

        safe_name = case_name.replace(" ", "_").replace("/", "-")[:50]
        mode_label = "Transactions" if mode != "intelligence" else "Financial_Intelligence"
        filename = (
            f"Financial_Report_{mode_label}_{safe_name}_{datetime.now().strftime('%Y%m%d')}."
            f"{rendered['extension']}"
        )

        return Response(
            content=rendered["content"],
            media_type=rendered["media_type"],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
