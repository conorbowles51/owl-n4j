"""
Financial Router - endpoints for financial analysis and transaction visualization.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from decimal import Decimal
from pydantic import BaseModel, Field, FiniteFloat, field_validator, model_validator
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import attach_transaction_locators
from services.neo4j_service import neo4j_service
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access
from services.financial_export_service import render_financial_export

import re
import logging

logger = logging.getLogger(__name__)


def _financial_case_permission(request, payload: dict) -> tuple[str, str] | None:
    if request.url.path == "/api/financial/auto-extract-from-to":
        # This route already distinguishes a view-only dry run from mutation.
        return None
    if request.method == "GET":
        return ("case", "view")
    return ("case", "edit")


_require_financial_case_access = case_access_dependency(_financial_case_permission)


router = APIRouter(
    prefix="/api/financial",
    tags=["financial"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_financial_case_access),
    ],
)


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
    grouped: dict[tuple[str, str | None], dict] = {}
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

        currency = str(transaction.get('currency') or '').strip().upper() or None
        group_key = (entity_value, currency)
        current = grouped.get(group_key)
        if current:
            current["count"] += 1
            current["totalAmount"] += abs(float(transaction.get("amount") or 0))
            continue

        grouped[group_key] = {
            "currency": currency,
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
    category: str = Field(min_length=1, max_length=120)
    case_id: str

    @field_validator('category')
    @classmethod
    def nonblank_category(cls, value):
        if not value.strip():
            raise ValueError('Choose a category name.')
        return value.strip()


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
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    case_id: str


class AutoExtractFromToRequest(BaseModel):
    case_id: str
    dry_run: bool = True


@router.get("")
async def get_financial_transactions(
    case_id: str = Query(..., description="REQUIRED: Filter to transactions in this case"),
    mode: str = Query("transactions", description="Dataset mode: transactions or intelligence"),
    types: Optional[str] = Query(None, description="Comma-separated transaction types to include"),
    start_date: Optional[str] = Query(None, description="Filter on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter on or before this date (YYYY-MM-DD)"),
    categories: Optional[str] = Query(None, description="Comma-separated financial categories to include"),
    db: Session = Depends(get_db),
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
        rows = (
            transactions.get("transactions")
            if isinstance(transactions, dict)
            else transactions
        )
        if isinstance(rows, list):
            # A locator is auxiliary to the row it decorates: a failure here
            # costs the click-through highlight, never the transaction list.
            try:
                attach_transaction_locators(db, rows)
            except Exception:
                logger.exception("Attaching transaction locators failed for case %s", case_id)
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


@router.post("/auto-extract-from-to")
async def auto_extract_from_to(
    body: AutoExtractFromToRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Propose or apply sender/beneficiary/category extraction for financial records.

    With dry_run=true, returns proposals only. With dry_run=false, applies the
    proposed from/to/category updates to Neo4j.
    """
    try:
        required_permission = ("case", "view") if body.dry_run else ("case", "edit")
        check_case_access(db, UUID(body.case_id), current_user, required_permission=required_permission)

        from services.from_to_extraction_service import extract_from_to_for_case

        result = extract_from_to_for_case(case_id=body.case_id, dry_run=body.dry_run)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "Extraction failed"))
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case_id")
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CaseAccessDenied:
        detail = "Access denied - case.edit permission required" if not body.dry_run else "Access denied - case.view permission required"
        raise HTTPException(status_code=403, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BulkCorrectionItem(BaseModel):
    node_key: Optional[str] = Field(default=None, min_length=1, max_length=512)
    name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    new_amount: FiniteFloat
    expected_amount: Optional[FiniteFloat] = None
    correction_reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def validate_correction(self):
        if bool(self.node_key) == bool(self.name):
            raise ValueError('Supply one record key or one transaction name.')
        if Decimal(str(self.new_amount)).normalize().as_tuple().exponent < -2:
            raise ValueError('Use no more than two decimal places for a correction.')
        if self.new_amount == 0:
            raise ValueError('Correction amount cannot be zero.')
        if not self.correction_reason.strip():
            raise ValueError('Explain why the amount is being corrected.')
        return self


class BulkCorrectRequest(BaseModel):
    case_id: str
    corrections: List[BulkCorrectionItem] = Field(min_length=1, max_length=1000)


class UpdateAmountRequest(BaseModel):
    case_id: str
    new_amount: FiniteFloat
    expected_amount: Optional[FiniteFloat] = None
    correction_reason: str = Field(min_length=1, max_length=4000)

    @field_validator('new_amount')
    @classmethod
    def amount_precision(cls, value):
        if Decimal(str(value)).normalize().as_tuple().exponent < -2:
            raise ValueError('Use no more than two decimal places for a correction.')
        return value

    @field_validator('correction_reason')
    @classmethod
    def reason_is_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Explain why the amount is being corrected.')
        return value


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
            expected_amount=body.expected_amount,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=409 if body.expected_amount is not None else 404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions/bulk-correct")
async def bulk_correct_transactions(body: BulkCorrectRequest):
    """Correct exact record keys; older name-based requests must identify one record."""
    try:
        by_key = {}
        for mode in ('transactions', 'intelligence'):
            response = neo4j_service.get_financial_transactions(case_id=body.case_id, mode=mode)
            rows = response.get('transactions', []) if isinstance(response, dict) else response
            by_key.update((row['key'], row) for row in rows)
        names = {}
        for row in by_key.values():
            name = (row.get('name') or '').strip().lower()
            if name:
                names.setdefault(name, []).append(row)

        selected = []
        seen = set()
        for correction in body.corrections:
            if correction.node_key:
                match = by_key.get(correction.node_key)
                if match is None:
                    raise HTTPException(status_code=404, detail=f'Record {correction.node_key} is not in this case. No corrections were applied.')
            else:
                matches = names.get(correction.name.strip().lower(), [])
                if len(matches) != 1:
                    raise HTTPException(status_code=409, detail=f'Name {correction.name!r} must identify exactly one record. Use record keys instead. No corrections were applied.')
                match = matches[0]
            if match['key'] in seen:
                raise HTTPException(status_code=400, detail=f'Record {match["key"]} is repeated. No corrections were applied.')
            seen.add(match['key'])
            if correction.expected_amount is not None and match.get('amount') != correction.expected_amount:
                raise HTTPException(status_code=409, detail=f'Record {match["key"]} changed after the preview. Reload its amount. No corrections were applied.')
            selected.append((correction, match))

        results = []
        for correction, match in selected:
            try:
                answer = neo4j_service.update_transaction_amount(
                    node_key=match['key'], case_id=body.case_id,
                    new_amount=correction.new_amount,
                    correction_reason=correction.correction_reason,
                    expected_amount=correction.expected_amount,
                )
                if not answer.get('success') or answer.get('key') != match['key'] or answer.get('amount') != correction.new_amount:
                    raise ValueError('The response did not confirm this correction.')
                results.append(dict(key=match['key'], name=correction.name, status='corrected',
                                    old_amount=match.get('amount'), new_amount=correction.new_amount))
            except Exception as exc:
                results.append(dict(key=match['key'], name=correction.name, status='error', reason=str(exc)))
        corrected = sum(row['status'] == 'corrected' for row in results)
        return dict(success=corrected == len(results), corrected=corrected, not_found=0,
                    errors=len(results) - corrected, total=len(results), results=results)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Bulk financial correction failed for case %s', body.case_id)
        raise HTTPException(status_code=500, detail='Corrections could not be confirmed. Reload the records before retrying.')


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
    category_names: Optional[List[str]] = Query(None),
    sender_values: Optional[List[str]] = Query(None),
    beneficiary_values: Optional[List[str]] = Query(None),
    min_amount: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    max_amount: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
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
        category_list = category_names if category_names is not None else _parse_csv_param(categories)
        from_entity_values = set(sender_values if sender_values is not None else _parse_csv_param(from_entities))
        to_entity_values = set(beneficiary_values if beneficiary_values is not None else _parse_csv_param(to_entities))

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

        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise HTTPException(status_code=422, detail='Minimum amount must not exceed maximum amount.')
        if min_amount is not None:
            transactions = [t for t in transactions if abs(float(t.get('amount') or 0)) >= min_amount]
            filters.append(f'Minimum amount (absolute value): {min_amount}')
        if max_amount is not None:
            transactions = [t for t in transactions if abs(float(t.get('amount') or 0)) <= max_amount]
            filters.append(f'Maximum amount (absolute value): {max_amount}')
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
            dataset_mode=mode,
        )

        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", case_name)[:50] or "Case"
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
