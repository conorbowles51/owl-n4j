"""
Financial from/to and category extraction.

This service ports Neil's auto-extraction behavior onto the current modular
financial service. It does not persist any local JSON files; JSON handling here
is limited to parsing structured LLM responses.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from services.llm_service import LLMService
from services.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {
    "Utility",
    "Payroll/Salary",
    "Rent/Lease",
    "Reimbursement",
    "Loan Payment",
    "Insurance",
    "Subscription",
    "Transfer",
    "Income",
    "Personal",
    "Legal/Professional",
    "Other",
}

BATCH_SIZE = 50
MAX_LLM_TRANSACTIONS = 2000
LLM_CONCURRENCY = 4

_HEURISTIC_PATTERNS = [
    re.compile(
        r"(?:transfer|wire|sent?)\s+from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:payment|deposit|remittance)\s+from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:payment|transfer|wire|sent?|disbursement|remittance)\s+to\s+(?P<to>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:payment|transfer|wire|receipt|deposit|remittance)\s+from\s+(?P<from>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"received\s+from\s+(?P<from>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"invoice\s+to\s+(?P<to>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<from>.+?)\s+paid\s+(?:to\s+)?(?P<to>.+?)(?:\s*[-\u2013\u2014]\s*|\s*$)",
        re.IGNORECASE,
    ),
]


def _clean_extracted_name(name: str | None) -> Optional[str]:
    if not name:
        return None
    cleaned = re.sub(
        r"\s*[-\u2013\u2014]\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b.*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*[-\u2013\u2014]\s*\d{1,2}/\d{1,2}.*$", "", cleaned)
    cleaned = re.sub(r"\s*[-\u2013\u2014]\s*\d{4}.*$", "", cleaned)
    cleaned = re.sub(r"\s*[\u20ac\u00a3$][\d,.]+.*$", "", cleaned)
    cleaned = cleaned.strip(" -\u2013\u2014,.")
    if len(cleaned) < 2 or cleaned.lower() in {"n/a", "unknown", "none", "null", "various"}:
        return None
    return cleaned


def extract_heuristic(name: str | None) -> Dict[str, Optional[str]]:
    if not name:
        return {"from_name": None, "to_name": None}
    for pattern in _HEURISTIC_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        groups = match.groupdict()
        from_name = _clean_extracted_name(groups.get("from"))
        to_name = _clean_extracted_name(groups.get("to"))
        if from_name or to_name:
            return {"from_name": from_name, "to_name": to_name}
    return {"from_name": None, "to_name": None}


def _format_transaction_for_llm(idx: int, txn: Dict) -> str:
    parts = [f"[{idx}]"]
    for label, key in [
        ("Name", "name"),
        ("Summary", "summary"),
        ("Counterparty", "counterparty_details"),
        ("Purpose", "purpose"),
    ]:
        value = txn.get(key)
        if value:
            parts.append(f"{label}: {value}")
    category = txn.get("category")
    if category and category != "Uncategorized":
        parts.append(f"Category: {category}")
    return " | ".join(parts)


def _build_llm_prompt(transactions: List[Dict]) -> str:
    category_list = ", ".join(sorted(VALID_CATEGORIES))
    rows = "\n".join(
        _format_transaction_for_llm(index, transaction)
        for index, transaction in enumerate(transactions)
    )
    return f"""You are a financial transaction analyst. Given a batch of financial transactions, extract the sender, beneficiary, and financial category for each transaction.

For each transaction, determine:
- from: who sent or paid the money.
- to: who received the money.
- category: the best category from ONLY this list: {category_list}

Rules:
1. Use the transaction name and summary as primary sources.
2. Use null when a party cannot be determined.
3. Return proper person or organization names, not descriptions.
4. If no category fits, use "Other". Never return "Uncategorized".

Return ONLY JSON in this shape:
{{
  "extractions": [
    {{"index": 0, "from": "Entity Name or null", "to": "Entity Name or null", "category": "Category Name"}}
  ]
}}

TRANSACTIONS:
{rows}
"""


def _process_single_batch(batch_start: int, batch: List[Dict]) -> List[Dict]:
    llm = LLMService()
    prompt = _build_llm_prompt(batch)
    try:
        raw = llm.call(prompt, temperature=0.1, json_mode=True, timeout=120)
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("from/to LLM batch at %s failed: %s", batch_start, exc)
        return []

    results = []
    for item in parsed.get("extractions", []):
        try:
            index = int(item.get("index", 0))
        except (TypeError, ValueError):
            continue
        results.append(
            {
                "index": batch_start + index,
                "from": item.get("from"),
                "to": item.get("to"),
                "category": item.get("category"),
            }
        )
    return results


def extract_from_to_llm(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return []

    batches = [
        (batch_start, transactions[batch_start : batch_start + BATCH_SIZE])
        for batch_start in range(0, len(transactions), BATCH_SIZE)
    ]
    all_results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as executor:
        futures = {
            executor.submit(_process_single_batch, batch_start, batch): batch_start
            for batch_start, batch in batches
        }
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as exc:
                logger.warning("from/to LLM worker failed: %s", exc)
    return all_results


def _normalize_for_match(name: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def match_to_entity(
    extracted_name: Optional[str],
    entity_index: Dict[str, Dict],
    entity_key_index: Dict[str, Dict],
) -> Dict:
    if not extracted_name:
        return {"key": None, "name": None, "matched": False}

    normalized = _normalize_for_match(extracted_name)
    if not normalized:
        return {"key": None, "name": extracted_name, "matched": False}

    if normalized in entity_index:
        entity = entity_index[normalized]
        return {"key": entity["key"], "name": entity["name"], "matched": True}

    key_form = normalized.replace(" ", "-")
    if key_form in entity_key_index:
        entity = entity_key_index[key_form]
        return {"key": entity["key"], "name": entity["name"], "matched": True}

    for entity_normalized, entity in entity_index.items():
        if len(normalized) >= 3 and (normalized in entity_normalized or entity_normalized in normalized):
            return {"key": entity["key"], "name": entity["name"], "matched": True}

    return {"key": None, "name": extracted_name, "matched": False}


def _transactions_for_case(case_id: str) -> List[Dict]:
    result = neo4j_service.get_financial_transactions(case_id=case_id)
    if isinstance(result, dict):
        return list(result.get("transactions", []))
    return list(result or [])


def extract_from_to_for_case(case_id: str, dry_run: bool = True) -> Dict:
    transactions = _transactions_for_case(case_id)
    if not transactions:
        return {"success": True, "message": "No transactions found", "total": 0, "proposals": []}

    eligible = []
    for transaction in transactions:
        needs_from_to = not (transaction.get("has_manual_from") and transaction.get("has_manual_to"))
        needs_category = (transaction.get("category") or "Uncategorized") == "Uncategorized"
        if needs_from_to or needs_category:
            transaction["_needs_from_to"] = needs_from_to
            transaction["_needs_category"] = needs_category
            eligible.append(transaction)

    if not eligible:
        return {
            "success": True,
            "message": "All transactions already have manual from/to and categories",
            "total": len(transactions),
            "eligible": 0,
            "proposals": [],
        }

    entities = neo4j_service.get_financial_entities(case_id)
    entity_name_index: Dict[str, Dict] = {}
    entity_key_index: Dict[str, Dict] = {}
    for entity in entities:
        if entity.get("name"):
            entity_name_index[_normalize_for_match(entity["name"])] = entity
        if entity.get("key"):
            entity_key_index[str(entity["key"]).lower()] = entity

    proposals: List[Dict] = []
    needs_llm: List[Dict] = []
    heuristic_by_key: Dict[str, Dict] = {}

    for transaction in eligible:
        has_from = bool(transaction.get("has_manual_from"))
        has_to = bool(transaction.get("has_manual_to"))
        heuristic = extract_heuristic(transaction.get("name"))

        proposed_from = heuristic["from_name"] if transaction["_needs_from_to"] and not has_from else None
        proposed_to = heuristic["to_name"] if transaction["_needs_from_to"] and not has_to else None
        heuristic_hit = proposed_from or proposed_to

        if heuristic_hit:
            heuristic_by_key[transaction["key"]] = {"from": proposed_from, "to": proposed_to}

        if transaction["_needs_category"] or (transaction["_needs_from_to"] and not heuristic_hit):
            needs_llm.append(transaction)
        elif heuristic_hit:
            proposals.append(
                {
                    "txn_key": transaction["key"],
                    "txn_name": transaction.get("name", ""),
                    "source": "heuristic",
                    "proposed_from": proposed_from,
                    "proposed_to": proposed_to,
                    "proposed_category": None,
                    "needs_from": not has_from,
                    "needs_to": not has_to,
                    "needs_category": False,
                }
            )

    capped_llm_transactions = needs_llm[:MAX_LLM_TRANSACTIONS]
    for extraction in extract_from_to_llm(capped_llm_transactions):
        index = extraction["index"]
        if index >= len(capped_llm_transactions):
            continue
        transaction = capped_llm_transactions[index]
        has_from = bool(transaction.get("has_manual_from"))
        has_to = bool(transaction.get("has_manual_to"))
        heuristic = heuristic_by_key.get(transaction["key"])

        if heuristic and transaction["_needs_from_to"]:
            proposed_from = heuristic["from"] if not has_from else None
            proposed_to = heuristic["to"] if not has_to else None
            source = "heuristic"
        elif transaction["_needs_from_to"]:
            proposed_from = extraction.get("from") if not has_from else None
            proposed_to = extraction.get("to") if not has_to else None
            source = "llm"
        else:
            proposed_from = None
            proposed_to = None
            source = "llm"

        proposed_category = extraction.get("category") if transaction["_needs_category"] else None
        if proposed_category and proposed_category not in VALID_CATEGORIES:
            proposed_category = None

        if proposed_from or proposed_to or proposed_category:
            proposals.append(
                {
                    "txn_key": transaction["key"],
                    "txn_name": transaction.get("name", ""),
                    "source": source if (proposed_from or proposed_to) else "llm",
                    "proposed_from": proposed_from,
                    "proposed_to": proposed_to,
                    "proposed_category": proposed_category,
                    "needs_from": not has_from,
                    "needs_to": not has_to,
                    "needs_category": transaction["_needs_category"],
                }
            )

    entity_matches = 0
    custom_names = 0
    for proposal in proposals:
        if proposal.get("proposed_from"):
            match = match_to_entity(proposal["proposed_from"], entity_name_index, entity_key_index)
            proposal["from_entity"] = match
            entity_matches += 1 if match["matched"] else 0
            custom_names += 1 if match["name"] and not match["matched"] else 0
        if proposal.get("proposed_to"):
            match = match_to_entity(proposal["proposed_to"], entity_name_index, entity_key_index)
            proposal["to_entity"] = match
            entity_matches += 1 if match["matched"] else 0
            custom_names += 1 if match["name"] and not match["matched"] else 0

    applied = 0
    categories_applied = 0
    if not dry_run:
        for proposal in proposals:
            from_entity = proposal.get("from_entity") or {}
            to_entity = proposal.get("to_entity") or {}
            from_name = from_entity.get("name") if proposal.get("needs_from") else None
            to_name = to_entity.get("name") if proposal.get("needs_to") else None

            if from_name or to_name:
                result = neo4j_service.update_transaction_from_to(
                    node_key=proposal["txn_key"],
                    case_id=case_id,
                    from_key=from_entity.get("key"),
                    from_name=from_name,
                    to_key=to_entity.get("key"),
                    to_name=to_name,
                )
                if result.get("success"):
                    applied += 1

            if proposal.get("proposed_category") and proposal.get("needs_category"):
                result = neo4j_service.update_transaction_category(
                    node_key=proposal["txn_key"],
                    category=proposal["proposed_category"],
                    case_id=case_id,
                )
                if result.get("success"):
                    categories_applied += 1

    return {
        "success": True,
        "total": len(transactions),
        "eligible": len(eligible),
        "proposals_count": len(proposals),
        "heuristic_count": sum(1 for item in proposals if item["source"] == "heuristic"),
        "llm_count": sum(1 for item in proposals if item["source"] == "llm"),
        "entity_matches": entity_matches,
        "custom_names": custom_names,
        "category_proposals_count": sum(1 for item in proposals if item.get("proposed_category")),
        "applied": applied if not dry_run else 0,
        "categories_applied": categories_applied if not dry_run else 0,
        "dry_run": dry_run,
        "proposals": [
            {
                "txn_key": proposal["txn_key"],
                "txn_name": proposal["txn_name"],
                "source": proposal["source"],
                "from": (proposal.get("from_entity") or {}).get("name"),
                "from_key": (proposal.get("from_entity") or {}).get("key"),
                "from_matched": (proposal.get("from_entity") or {}).get("matched", False),
                "to": (proposal.get("to_entity") or {}).get("name"),
                "to_key": (proposal.get("to_entity") or {}).get("key"),
                "to_matched": (proposal.get("to_entity") or {}).get("matched", False),
                "proposed_category": proposal.get("proposed_category"),
            }
            for proposal in proposals
        ],
    }
