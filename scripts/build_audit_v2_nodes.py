#!/usr/bin/env python3
"""
Build v2 audited Transaction nodes in Neo4j from the JSON files written by the
manual re-extraction pass under ``ingestion/data/audit_results/<date>/``.

Each row in a JSON file becomes one Neo4j node:

    Label    : Transaction        (so it shows up in the existing financial table)
    Key      : audit-v2-{doc_slug}-{row_index_zero_padded}
    Flags    : audit_status='proposed'
               audit_run='2026-04-11'
               audit_doc=<doc_name>
               audit_verified=true
               has_manual_from=false   has_manual_to=false
    Source   : (n)-[:MENTIONED_IN]->(d:Document {name: doc_name})

Account-holder and counterparty are looked up against existing entities in the
case so that the financial UI's entity links keep working.  If a counterparty
cannot be matched, the name is stored verbatim and the entity_key is left null.

Run:
    python scripts/build_audit_v2_nodes.py                        # all JSONs, dry-run
    python scripts/build_audit_v2_nodes.py --apply                # actually create
    python scripts/build_audit_v2_nodes.py USA-ET-000388.pdf      # one document
    python scripts/build_audit_v2_nodes.py --date 2026-04-11
    python scripts/build_audit_v2_nodes.py --delete-all           # remove all v2 nodes for this case (rollback)

Safety:
  - Default mode is dry-run.  No writes happen unless ``--apply`` is passed.
  - Re-runs are idempotent: nodes are MERGE'd by key.
  - Legacy nodes are never touched.  Soft-delete of legacy is a separate step
    (see neo4j_service.bulk_soft_delete_financial_for_document) and the user
    has explicitly asked us NOT to run it until they've reviewed v1/v2 side by
    side.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase
from pypdf import PdfReader

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")
CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"  # ET-Fraud / Eric Tataw

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_ROOT = REPO_ROOT / "ingestion" / "data" / "audit_results"
EVIDENCE_ROOT = REPO_ROOT / "ingestion" / "data" / "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"

AUDIT_RUN_DEFAULT = "2026-04-11"


# Category-preservation rules for the audit v2 rebuild
# (see TRANSACTION_REPROCESS_PLAN.md §3.0.3).
#
# On reprocess we preserve a legacy row's category ONLY if it is one of the
# app's recognised 5-value taxonomy.  Anything else — channel-derived tags
# like "Cash App" or "Check Payment", junk like "Duplicate - Ignore" or
# "Zelle Transactions Need More Info", or empty/null — falls through to the
# channel_to_category mapping.  This "accept known-valid, reject everything
# else" approach is stricter than the original blocklist but much safer: we
# don't need to enumerate every possible junk string, we just need to know
# the 5 valid ones.  Case- and whitespace-insensitive.
CATEGORY_VALID = {
    "transfer": "Transfer",
    "personal": "Personal",
    "subscription": "Subscription",
    "payroll/salary": "Payroll/Salary",
    "other": "Other",
}


def _is_junk_category(cat: Optional[str]) -> bool:
    """Return True if `cat` is empty/null.  Preserves ALL non-null legacy
    categories including team-assigned ones like 'Check Card', 'Ignore', etc."""
    if cat is None:
        return True
    return cat.strip() == ""


def _canonical_category(cat: str) -> str:
    """Normalise a valid legacy category to its canonical casing.
    If it's one of the 5-value taxonomy, normalise; otherwise return as-is."""
    return CATEGORY_VALID.get(cat.strip().lower(), cat.strip())


# Channel → default category mapping.  Uses the same VALID_CATEGORIES enum
# the rest of the app recognises (from backend/services/from_to_extraction_service.py).
# Better than "Uncategorized" for side-by-side viewing; final categorisation
# can still be refined later per row.
def channel_to_category(channel: Optional[str], direction: str) -> str:
    if not channel:
        return "Other"
    c = channel.lower()
    if "payroll" in c:
        return "Payroll/Salary"
    if "recurring" in c:
        return "Subscription"
    if "zelle" in c or "visa direct" in c or "transfer" in c or "counter credit" in c:
        return "Transfer"
    if "atm" in c:
        return "Transfer"
    if "paypal" in c:
        return "Transfer"
    if "service fee" in c or "bank fee" in c:
        return "Other"
    if "check " in c and "card" not in c:  # standalone 'Check' only, not 'Check Card'
        return "Other"
    if "check card" in c or "pos" in c or "purchase" in c:
        return "Personal"
    if "ach" in c:
        # ACH debits for specific vendors are usually utility/insurance/etc,
        # but without more signal default to 'Other'
        return "Payroll/Salary" if direction == "in" else "Other"
    return "Other"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalise_name(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Common noise words that can be safely dropped during token-set matching
_TOKEN_STOPWORDS = {
    "the", "and", "of", "for", "from", "to", "a", "an",
    "mr", "mrs", "ms", "dr", "jr", "sr",
    "llc", "ltd", "inc", "corp", "corporation", "company", "co",
}


def _tokens(s: str) -> List[str]:
    """Lowercased tokens of length >= 2, excluding stopwords and single letters."""
    if not s:
        return []
    raw = re.split(r"[^a-zA-Z0-9]+", s.lower())
    return [t for t in raw if len(t) >= 2 and t not in _TOKEN_STOPWORDS]


def _token_set(s: str) -> frozenset:
    return frozenset(_tokens(s))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def doc_slug(doc_name: str) -> str:
    return slug(doc_name.replace(".pdf", "").replace(".PDF", ""))


def fmt_amount(amount: float) -> str:
    """
    Format amount the way legacy nodes do: '$1,500.00' for positives and
    '-$1,500.00' for negatives (sign before the currency symbol, accounting
    standard — not Python's default '$-1,500.00').
    """
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def signed_amount(magnitude: float, direction: str) -> float:
    """
    Derive the signed amount used for storage from the JSON's positive
    magnitude + direction field.

    Convention (see TRANSACTION_REPROCESS_PLAN.md §3.0.1): direction encodes
    sign regardless of how the PDF rendered the transaction.
        direction == 'in'  →  positive  (receipt into account holder)
        direction == 'out' →  negative  (payment out of account holder)
    """
    m = abs(float(magnitude))
    if direction == "out":
        return -m
    if direction == "in":
        return m
    raise ValueError(f"unknown direction {direction!r}; expected 'in' or 'out'")


def build_txn_name(direction: str, counterparty: str, channel: str, amount: float) -> str:
    """Generate a readable transaction name."""
    arrow = "to" if direction == "out" else "from"
    chan = channel or "Transfer"
    return f"{chan} {arrow} {counterparty} ({fmt_amount(amount)})"


def build_summary(
    direction: str,
    counterparty: str,
    channel: str,
    amount: float,
    date: str,
    account_holder: str,
    reference: Optional[str],
    location: Optional[str],
    doc_name: str,
    source_page: Optional[int],
) -> str:
    """Generate a rich narrative summary sentence for the transaction."""
    amt = fmt_amount(amount)
    chan = channel or "transaction"
    if direction == "in":
        core = f"{amt} received from {counterparty} on {date} via {chan}, into {account_holder}."
    else:
        core = f"{amt} sent to {counterparty} on {date} via {chan}, from {account_holder}."
    extras = []
    if reference:
        extras.append(f"Reference: {reference}.")
    if location:
        extras.append(f"Location: {location}.")
    if source_page is not None:
        extras.append(f"Source: {doc_name}, page {source_page}.")
    else:
        extras.append(f"Source: {doc_name}.")
    return " ".join([core] + extras)


# ─────────────────────────────────────────────────────────────────────────────
# Physical page resolution via pypdf
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_for_page_match(s: str) -> str:
    """Lowercase and strip spaces for substring matching inside extracted PDF text."""
    return re.sub(r"\s+", "", s.lower())


def _amount_search_tokens(amount: float) -> List[str]:
    """
    Generate plausible string representations of an amount as it might appear
    in PDF text — banks print values in a few formats:
        $1,050.00    1,050.00    1050.00
    """
    tokens = [
        f"{amount:,.2f}",        # 1,050.00
        f"{amount:.2f}",         # 1050.00
    ]
    return list(dict.fromkeys(tokens))  # dedupe, keep order


def _date_search_tokens(iso_date: str) -> List[str]:
    """Convert 'YYYY-MM-DD' to common bank-statement forms: 'MM/DD/YY', 'MM/DD'."""
    try:
        y, m, d = iso_date.split("-")
        yy = y[-2:]
        return [
            f"{m}/{d}/{yy}",
            f"{m}/{d}",
        ]
    except Exception:
        return []


def _resolve_pdf_path(doc_name: str) -> Optional[Path]:
    """Locate the PDF on disk under the case evidence root (recursive)."""
    if not EVIDENCE_ROOT.exists():
        return None
    for p in EVIDENCE_ROOT.rglob(doc_name):
        if p.is_file():
            return p
    return None


class PageResolver:
    """
    Loads a PDF once, caches per-page normalised text, and lets callers look up
    the physical page for a given transaction by date + amount substring match.

    We search pages in order and return the first hit, so duplicates on the
    same page (e.g. two $50 transfers on the same day) share a page — which
    is correct.
    """

    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.page_texts: List[str] = []
        self.page_norms: List[str] = []
        try:
            reader = PdfReader(str(pdf_path))
            for page in reader.pages:
                txt = page.extract_text() or ""
                self.page_texts.append(txt)
                self.page_norms.append(_normalise_for_page_match(txt))
        except Exception as exc:
            print(f"  [warn] failed to read {pdf_path}: {exc}", file=sys.stderr)

    @property
    def num_pages(self) -> int:
        return len(self.page_texts)

    def page_for(
        self,
        date: str,
        amount: float,
        counterparty_hint: Optional[str] = None,
    ) -> Optional[int]:
        if not self.page_norms:
            return None
        date_tokens = _date_search_tokens(date)
        amount_tokens = _amount_search_tokens(amount)
        # Normalised counterparty hint helps disambiguate same-day same-amount rows
        cp_hint = _normalise_for_page_match(counterparty_hint or "")
        cp_hint_snippet = cp_hint[:12] if len(cp_hint) >= 4 else None

        best_page = None
        best_score = -1
        for i, page_norm in enumerate(self.page_norms):
            score = 0
            # Any date token present
            if any(_normalise_for_page_match(dt) in page_norm for dt in date_tokens):
                score += 2
            # Any amount token present
            if any(_normalise_for_page_match(at) in page_norm for at in amount_tokens):
                score += 2
            # Bonus if a hint of counterparty appears on the same page
            if cp_hint_snippet and cp_hint_snippet in page_norm:
                score += 1
            if score > best_score and score >= 4:
                # Need BOTH date and amount on the page to claim it
                best_score = score
                best_page = i + 1  # 1-indexed physical page

        return best_page


def build_verified_fact(
    txn: Dict,
    doc_name: str,
    account_holder: str,
    resolved_page: Optional[int],
) -> Dict:
    """
    Construct one verified_fact that satisfies the UI's CitationLink contract.

    The UI only needs ``source_doc`` + ``page`` to render a link that opens the
    source PDF at the right page, and ``text`` as the primary description.  The
    ``quote`` field is optional (rendered only if present) and we fall back to
    a synthesised string when the original JSON doesn't carry ``description_raw``
    (earlier docs preserved it; later ones dropped it to save context).

    ``resolved_page`` comes from PageResolver.page_for() — the authoritative
    physical page number derived by searching the PDF itself.  It supersedes
    any ``source_page`` previously written to the JSON.
    """
    direction = txn["direction"]
    amount_val = float(txn["amount"])
    date = txn["date"]
    channel = txn.get("channel") or "Transfer"
    source_page = resolved_page if resolved_page is not None else txn.get("source_page")
    reference = txn.get("reference")

    if direction == "in":
        counterparty = txn.get("from_party") or "Unknown sender"
        text = (
            f"{fmt_amount(amount_val)} received from {counterparty} "
            f"on {date} via {channel}"
            + (f" ({reference})" if reference else "")
            + f", into {account_holder}."
        )
    else:
        counterparty = txn.get("to_party") or "Unknown recipient"
        text = (
            f"{fmt_amount(amount_val)} sent to {counterparty} "
            f"on {date} via {channel}"
            + (f" ({reference})" if reference else "")
            + f", from {account_holder}."
        )

    # Prefer the exact PDF line if the extraction preserved it
    raw_quote = txn.get("description_raw")
    if raw_quote:
        quote = raw_quote
        quote_validated = True
    else:
        arrow = "to" if direction == "out" else "from"
        quote = (
            f"{date} {channel} {arrow} {counterparty} "
            f"{fmt_amount(amount_val)}"
            + (f"  {reference}" if reference else "")
        )
        quote_validated = False

    fact = {
        "text": text,
        "quote": quote,
        "page": source_page,
        "importance": 5,
        "source_doc": doc_name,
        "quote_validated": quote_validated,
        "audit_generated": True,
        "audit_run": AUDIT_RUN_DEFAULT,
    }
    if txn.get("source_section"):
        fact["source_section"] = txn["source_section"]
    return fact


# ─────────────────────────────────────────────────────────────────────────────
# Entity matching against existing case entities
# ─────────────────────────────────────────────────────────────────────────────

# Entity types we PREFER when matching counterparties / account holders.
# Document/form/tax types are explicitly de-prioritised because the AI created
# entities like "Form 1040 (2021) - Beltha B Mokube" that contain a person's
# name as a substring without actually being that person.
_PERSON_LIKE_TYPES = {
    "person", "company", "organisation", "organization", "bank", "merchant",
    "vendor", "account", "bankaccount", "creditaccount", "loanaccount",
}
_DOCUMENT_LIKE_TYPES = {
    "document", "taxreturn", "taxform", "form", "statement", "bankstatement",
    "loanapplication", "agreement", "contract", "addendum", "affidavit",
    "promissorynote", "deedoftrust", "insurancepolicy", "leaseagreement",
    "loanagreement", "notice", "report", "claim", "checksummary",
    "earningsstatement", "incomedeclaration", "payrollstatement",
    "billingstatement", "accountstatement",
}


def _type_score(entity_type: Optional[str]) -> int:
    """Higher score = more preferred match."""
    if not entity_type:
        return 1
    t = entity_type.lower()
    if t in _PERSON_LIKE_TYPES:
        return 3
    if t in _DOCUMENT_LIKE_TYPES:
        return 0
    return 1  # neutral


class EntityIndex:
    """Lightweight name → existing-entity lookup with type-aware ranking."""

    def __init__(self, entities: List[Dict]):
        # exact normalised match
        self.by_norm: Dict[str, Dict] = {}
        # token-set keyed: any entity whose token set CONTAINS this token
        # (used for token-overlap match)
        self.entries: List[Tuple[str, frozenset, Dict]] = []
        for e in entities:
            n = normalise_name(e.get("name", ""))
            tok = _token_set(e.get("name", ""))
            if not n and not tok:
                continue
            self.entries.append((n, tok, e))
            if n:
                existing = self.by_norm.get(n)
                if existing is None or _type_score(e.get("type")) > _type_score(existing.get("type")):
                    self.by_norm[n] = e
        # also key-form lookup
        for e in entities:
            k = normalise_name(e.get("key", ""))
            if k and k not in self.by_norm:
                self.by_norm[k] = e

    def lookup(self, name: Optional[str]) -> Tuple[Optional[str], str]:
        """Return (entity_key, canonical_name).  entity_key is None if no match."""
        if not name:
            return None, ""
        norm = normalise_name(name)
        if not norm:
            return None, name

        # 1. Exact normalised match — already type-ranked
        hit = self.by_norm.get(norm)
        if hit:
            return hit["key"], hit["name"]

        # 2. Token-set match — handles middle initials, name reordering,
        #    "Mokube, Beltha" vs "Beltha B Mokube", etc.  We require ALL of the
        #    input's tokens to appear in the candidate (or vice versa for short
        #    inputs), so e.g. "Beltha Mokube" matches "Beltha Bume Mokube".
        input_tokens = _token_set(name)
        if input_tokens:
            candidates: List[Dict] = []
            for _cand_norm, cand_tokens, cand in self.entries:
                if not cand_tokens:
                    continue
                # All input tokens present in candidate
                if input_tokens.issubset(cand_tokens):
                    candidates.append(cand)
                # OR all candidate tokens present in input (e.g. input is more
                # verbose like "Beltha B Mokube (Maryland)")
                elif len(cand_tokens) >= 2 and cand_tokens.issubset(input_tokens):
                    candidates.append(cand)
            if candidates:
                candidates.sort(
                    key=lambda c: (
                        -_type_score(c.get("type")),
                        # Prefer shorter (more specific) names — a person name
                        # is usually shorter than a document title containing it
                        len(c.get("name", "")),
                    )
                )
                best = candidates[0]
                if _type_score(best.get("type")) > 0:
                    return best["key"], best["name"]

        # 3. Substring fallback for single-token / short inputs
        if len(norm) < 4:
            return None, name

        substring_candidates: List[Dict] = []
        for cand_norm, _tok, cand in self.entries:
            if len(cand_norm) < 4:
                continue
            if norm in cand_norm or cand_norm in norm:
                substring_candidates.append(cand)

        if not substring_candidates:
            return None, name

        substring_candidates.sort(
            key=lambda c: (
                -_type_score(c.get("type")),
                abs(len(normalise_name(c.get("name", ""))) - len(norm)),
            )
        )
        best = substring_candidates[0]
        if _type_score(best.get("type")) == 0:
            return None, name
        return best["key"], best["name"]


def fetch_case_entities(driver, case_id: str) -> List[Dict]:
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n {case_id: $case_id})
            WHERE NOT n:Document AND NOT n:Case AND NOT n:RecycleBin
              AND n.amount IS NULL
              AND n.name IS NOT NULL
            RETURN DISTINCT n.key AS key, n.name AS name, labels(n)[0] AS type
            """,
            case_id=case_id,
        )
        return [dict(r) for r in result]


# ─────────────────────────────────────────────────────────────────────────────
# Legacy category lookup (for audit v2 category preservation)
# ─────────────────────────────────────────────────────────────────────────────

LegacyCatIndex = Dict[Tuple[str, float], List[Tuple[str, Optional[str]]]]


def fetch_legacy_category_index(session, doc_name: str, case_id: str) -> LegacyCatIndex:
    """
    Pre-fetch every legacy (non-audit-v2) transaction attached to one document,
    keyed by (date, round(magnitude, 2)) for O(1) lookup during the row loop.

    Excludes nodes with audit_status='proposed' (both the rows we are building
    right now and any prior audit pass) so the copied category always comes
    from the legacy row being replaced, not from another audit generation.

    Returns:
        {(date, rounded_magnitude): [(node_key, financial_category), ...]}
        Inner lists are sorted by node_key for deterministic selection when
        multiple legacy rows collide on (date, amount).
    """
    query = """
        MATCH (n)-[:MENTIONED_IN]->(d:Document {name: $doc_name, case_id: $case_id})
        WHERE n.amount IS NOT NULL
          AND n.case_id = $case_id
          AND coalesce(n.audit_status, '') <> 'proposed'
          AND NOT n:Document AND NOT n:Case
          AND NOT n:FinancialCategory AND NOT n:RecycleBin
        WITH n,
             toFloat(replace(replace(replace(replace(
               trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS amt
        WHERE amt IS NOT NULL AND amt = amt
        RETURN n.key AS key,
               n.date AS date,
               abs(amt) AS magnitude,
               n.financial_category AS category
    """
    result = session.run(query, doc_name=doc_name, case_id=case_id)
    index: LegacyCatIndex = {}
    for r in result:
        date = r["date"]
        mag = r["magnitude"]
        if date is None or mag is None:
            continue
        key = (str(date), round(float(mag), 2))
        index.setdefault(key, []).append((r["key"], r["category"]))
    for lst in index.values():
        lst.sort(key=lambda kv: kv[0])
    return index


def lookup_legacy_category(
    index: LegacyCatIndex,
    date: str,
    magnitude: float,
) -> Optional[str]:
    """
    Return the first non-junk legacy category matching (date, rounded
    magnitude), or None if no match exists or every match is in
    CATEGORY_JUNK. Sign-agnostic — matches on positive magnitude regardless
    of which side the legacy row's sign is on.
    """
    key = (date, round(float(magnitude), 2))
    matches = index.get(key, [])
    for _node_key, cat in matches:
        if _is_junk_category(cat):
            continue
        return _canonical_category(cat)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j writes
# ─────────────────────────────────────────────────────────────────────────────

CYPHER_MERGE_TXN = """
MERGE (n:Transaction {key: $key, case_id: $case_id})
SET n.name              = $name,
    n.date              = $date,
    n.amount            = $amount,
    n.currency          = $currency,
    n.summary            = $summary,
    n.financial_category = $financial_category,
    n.from_entity_key    = $from_key,
    n.from_entity_name   = $from_name,
    n.to_entity_key      = $to_key,
    n.to_entity_name     = $to_name,
    n.has_manual_from    = false,
    n.has_manual_to      = false,
    n.verified_facts     = $verified_facts,
    n.audit_status       = 'proposed',
    n.audit_run          = $audit_run,
    n.audit_doc          = $audit_doc,
    n.audit_verified     = true,
    n.audit_row_index    = $row_index,
    n.audit_source_page  = $source_page,
    n.audit_channel      = $channel,
    n.audit_reference    = $reference
WITH n
MATCH (d:Document {name: $audit_doc, case_id: $case_id})
MERGE (n)-[:MENTIONED_IN {case_id: $case_id}]->(d)
RETURN n.key AS key
"""

# Create graph edges so the entity graph view can see the transaction.
# Uses TRANSFERRED_TO both ways, matching what get_financial_transactions()
# already looks for in its phase-2 relationship fallback.
CYPHER_LINK_FROM_ENTITY = """
MATCH (n:Transaction {key: $tx_key, case_id: $case_id})
MATCH (fe {key: $from_key, case_id: $case_id})
WHERE NOT fe:Document AND NOT fe:Case AND NOT fe:RecycleBin
MERGE (fe)-[r:TRANSFERRED_TO {case_id: $case_id, audit_run: $audit_run}]->(n)
"""

CYPHER_LINK_TO_ENTITY = """
MATCH (n:Transaction {key: $tx_key, case_id: $case_id})
MATCH (te {key: $to_key, case_id: $case_id})
WHERE NOT te:Document AND NOT te:Case AND NOT te:RecycleBin
MERGE (n)-[r:TRANSFERRED_TO {case_id: $case_id, audit_run: $audit_run}]->(te)
"""

CYPHER_DELETE_ALL_AUDIT_NODES = """
MATCH (n:Transaction {case_id: $case_id})
WHERE n.audit_status = 'proposed' AND n.audit_run = $audit_run
DETACH DELETE n
"""


def upsert_v2_node(session, *, key, case_id, name, date, amount, currency,
                   summary, category, from_key, from_name, to_key, to_name,
                   verified_facts_json, audit_doc, audit_run, row_index,
                   source_page, channel, reference):
    session.run(
        CYPHER_MERGE_TXN,
        key=key,
        case_id=case_id,
        name=name,
        date=date,
        amount=amount,
        currency=currency,
        summary=summary,
        financial_category=category,
        from_key=from_key,
        from_name=from_name,
        to_key=to_key,
        to_name=to_name,
        verified_facts=verified_facts_json,
        audit_run=audit_run,
        audit_doc=audit_doc,
        row_index=row_index,
        source_page=source_page,
        channel=channel,
        reference=reference,
    ).consume()

    # Create graph edges only when we successfully matched the counterparty
    # to an existing entity (from_key / to_key is set).  Plain names without
    # a key can't be linked — the property fields carry them.
    if from_key:
        session.run(
            CYPHER_LINK_FROM_ENTITY,
            tx_key=key,
            case_id=case_id,
            from_key=from_key,
            audit_run=audit_run,
        ).consume()
    if to_key:
        session.run(
            CYPHER_LINK_TO_ENTITY,
            tx_key=key,
            case_id=case_id,
            to_key=to_key,
            audit_run=audit_run,
        ).consume()


# ─────────────────────────────────────────────────────────────────────────────
# Per-document processing
# ─────────────────────────────────────────────────────────────────────────────

def process_document(
    session,
    extracted: Dict,
    entity_index: EntityIndex,
    *,
    audit_run: str,
    apply: bool,
) -> Dict:
    doc_name = extracted["doc_name"]
    case_id = extracted["case_id"]
    holder_name = extracted["account_holder"]

    # Resolve account holder once per document
    holder_key, holder_canonical = entity_index.lookup(holder_name)
    if holder_canonical and holder_canonical.lower() != holder_name.lower():
        # Use the canonical name from the graph if we matched
        pass
    else:
        # No match — keep the holder name from the JSON (statement is ground truth)
        holder_canonical = holder_name

    # Load the PDF once so we can resolve the real physical page per row
    pdf_path = _resolve_pdf_path(doc_name)
    page_resolver: Optional[PageResolver] = None
    if pdf_path is not None:
        page_resolver = PageResolver(pdf_path)
    else:
        print(f"  [warn] PDF not found on disk for {doc_name} — pages will be null",
              file=sys.stderr)

    # Prefetch the legacy-row category index for this document once.
    # Used to preserve manually-curated categories on reprocess — see
    # TRANSACTION_REPROCESS_PLAN.md §3.0.3.  Single query per doc rather
    # than per-row.
    legacy_cat_index = fetch_legacy_category_index(session, doc_name, case_id)

    txns = extracted["transactions"]
    counterparty_matched = 0
    counterparty_unmatched = 0
    pages_resolved = 0
    pages_unresolved = 0
    category_copied = 0
    category_fallback = 0
    copied_category_dist: Dict[str, int] = {}
    written = 0
    skipped = []

    dslug = doc_slug(doc_name)

    for t in txns:
        row_idx = t["row_index"]
        direction = t["direction"]
        # amount_val is always positive magnitude — used for display, PDF-page
        # search, and narrative text. signed_val carries the stored sign
        # convention (see TRANSACTION_REPROCESS_PLAN.md §3.0.1) and is what
        # actually gets written to Neo4j's `amount` property.
        amount_val = abs(float(t["amount"]))
        signed_val = signed_amount(amount_val, direction)
        date = t["date"]
        channel = t.get("channel") or "Transaction"
        reference = t.get("reference")

        # Counterparty is the side opposite the account holder
        if direction == "in":
            cp_name = t.get("from_party") or "Unknown sender"
            from_key, from_name = entity_index.lookup(cp_name)
            if not from_key:
                from_name = cp_name
            to_key, to_name = (holder_key, holder_canonical)
        else:  # out
            cp_name = t.get("to_party") or "Unknown recipient"
            to_key, to_name = entity_index.lookup(cp_name)
            if not to_key:
                to_name = cp_name
            from_key, from_name = (holder_key, holder_canonical)

        # Track counterparty match status
        cp_matched = (from_key is not None) if direction == "in" else (to_key is not None)
        if cp_matched:
            counterparty_matched += 1
        else:
            counterparty_unmatched += 1

        # Resolve physical page from the PDF (authoritative over JSON)
        resolved_page: Optional[int] = None
        if page_resolver is not None:
            resolved_page = page_resolver.page_for(
                date=date,
                amount=amount_val,
                counterparty_hint=cp_name,
            )
        if resolved_page is None:
            resolved_page = t.get("source_page")  # fall back to JSON if PDF search missed
        if resolved_page is not None:
            pages_resolved += 1
        else:
            pages_unresolved += 1

        # Sanity: stored sign must agree with the direction we derived it from.
        # If this ever fails, the JSON's direction and our signed_amount helper
        # have diverged — abort rather than load bad data.
        if direction == "in" and signed_val < 0:
            raise RuntimeError(
                f"sign/direction mismatch for row {row_idx} in {doc_name}: "
                f"direction='in' but signed_val={signed_val}"
            )
        if direction == "out" and signed_val > 0:
            raise RuntimeError(
                f"sign/direction mismatch for row {row_idx} in {doc_name}: "
                f"direction='out' but signed_val={signed_val}"
            )

        key = f"audit-v2-{dslug}-{row_idx:04d}"
        name = build_txn_name(direction, cp_name, channel, amount_val)
        amount_str = fmt_amount(signed_val)

        # Category preservation (TRANSACTION_REPROCESS_PLAN.md §3.0.3):
        # copy the legacy row's category if one exists and isn't junk,
        # otherwise fall back to channel_to_category.
        legacy_cat = lookup_legacy_category(legacy_cat_index, date, amount_val)
        if legacy_cat is not None:
            category = legacy_cat
            category_copied += 1
            copied_category_dist[legacy_cat] = copied_category_dist.get(legacy_cat, 0) + 1
        else:
            category = channel_to_category(channel, direction)
            category_fallback += 1
        summary = build_summary(
            direction=direction,
            counterparty=cp_name,
            channel=channel,
            amount=amount_val,
            date=date,
            account_holder=holder_canonical,
            reference=reference,
            location=t.get("location"),
            doc_name=doc_name,
            source_page=resolved_page,
        )

        # Build verified_facts entry so the UI renders a source-document link
        fact = build_verified_fact(t, doc_name, holder_canonical, resolved_page)
        verified_facts_json = json.dumps([fact])

        if not apply:
            continue

        try:
            upsert_v2_node(
                session,
                key=key,
                case_id=case_id,
                name=name,
                date=date,
                amount=amount_str,
                currency="USD",
                summary=summary,
                category=category,
                from_key=from_key,
                from_name=from_name,
                to_key=to_key,
                to_name=to_name,
                verified_facts_json=verified_facts_json,
                audit_doc=doc_name,
                audit_run=audit_run,
                row_index=row_idx,
                source_page=resolved_page,
                channel=channel,
                reference=reference,
            )
            written += 1
        except Exception as exc:
            skipped.append({"key": key, "error": str(exc)})

    return {
        "doc_name": doc_name,
        "account_holder_input": holder_name,
        "account_holder_resolved_key": holder_key,
        "account_holder_resolved_name": holder_canonical,
        "account_holder_matched": holder_key is not None,
        "txn_total": len(txns),
        "txn_written": written if apply else 0,
        "txn_planned": len(txns) if not apply else 0,
        "counterparty_matched": counterparty_matched,
        "counterparty_unmatched": counterparty_unmatched,
        "pages_resolved": pages_resolved,
        "pages_unresolved": pages_unresolved,
        "category_copied": category_copied,
        "category_fallback": category_fallback,
        "copied_category_dist": copied_category_dist,
        "skipped": skipped,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("doc", nargs="?", help="Specific doc filename, or omit for all")
    parser.add_argument("--date", default=AUDIT_RUN_DEFAULT, help="Audit run subdir under audit_results/")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to Neo4j (default is dry-run preview)")
    parser.add_argument("--delete-all", action="store_true",
                        help="Roll back: delete every v2 node in this case for this audit run")
    args = parser.parse_args()

    audit_dir = AUDIT_ROOT / args.date
    if not audit_dir.exists():
        sys.exit(f"No audit dir at {audit_dir}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # Rollback path
        if args.delete_all:
            if not args.apply:
                print("--delete-all is destructive; pass --apply to actually run it.")
                with driver.session() as session:
                    res = session.run(
                        """
                        MATCH (n:Transaction {case_id: $case_id})
                        WHERE n.audit_status = 'proposed' AND n.audit_run = $audit_run
                        RETURN count(n) AS c
                        """,
                        case_id=CASE_ID, audit_run=args.date,
                    ).single()
                    print(f"Would delete {res['c']} v2 nodes (case={CASE_ID}, audit_run={args.date})")
                return
            with driver.session() as session:
                # Count first
                cnt = session.run(
                    """
                    MATCH (n:Transaction {case_id: $case_id})
                    WHERE n.audit_status = 'proposed' AND n.audit_run = $audit_run
                    RETURN count(n) AS c
                    """,
                    case_id=CASE_ID, audit_run=args.date,
                ).single()["c"]
                session.run(CYPHER_DELETE_ALL_AUDIT_NODES,
                            case_id=CASE_ID, audit_run=args.date)
                print(f"Deleted {cnt} v2 nodes (case={CASE_ID}, audit_run={args.date})")
            return

        # Build entity index once for the case
        print(f"Loading existing entities for case {CASE_ID} ...")
        entities = fetch_case_entities(driver, CASE_ID)
        index = EntityIndex(entities)
        print(f"  loaded {len(entities)} entities for fuzzy match")

        # Pick JSON files
        if args.doc:
            json_files = [audit_dir / (args.doc.replace(".pdf", "") + ".json")]
        else:
            json_files = sorted(p for p in audit_dir.glob("*.json")
                                if not p.name.startswith("_"))

        all_reports = []
        with driver.session() as session:
            for jf in json_files:
                if not jf.exists():
                    print(f"[skip] {jf} not found", file=sys.stderr)
                    continue
                extracted = json.loads(jf.read_text())
                report = process_document(
                    session, extracted, index,
                    audit_run=args.date, apply=args.apply,
                )
                all_reports.append(report)

                tag = "WRITE" if args.apply else "DRYRUN"
                holder_match = "✓" if report["account_holder_matched"] else "?"
                total_txns = report["counterparty_matched"] + report["counterparty_unmatched"]
                total_pages = report["pages_resolved"] + report["pages_unresolved"]
                total_cat = report["category_copied"] + report["category_fallback"]
                print(
                    f"[{tag}] {report['doc_name']:<24s} "
                    f"holder={holder_match} "
                    f"txns={report['txn_written'] if args.apply else report['txn_planned']:>3d} "
                    f"cp={report['counterparty_matched']:>3d}/{total_txns} "
                    f"pages={report['pages_resolved']:>3d}/{total_pages} "
                    f"cat_copied={report['category_copied']:>3d}/{total_cat}"
                )
                if report["copied_category_dist"]:
                    # Sort descending by count for quick eyeball
                    dist = sorted(
                        report["copied_category_dist"].items(),
                        key=lambda kv: (-kv[1], kv[0]),
                    )
                    dist_str = ", ".join(f"{k}={v}" for k, v in dist)
                    print(f"      copied categories: {dist_str}")
                if report["skipped"]:
                    for s in report["skipped"][:5]:
                        print(f"      [error] {s['key']}: {s['error']}")
                    if len(report["skipped"]) > 5:
                        print(f"      … and {len(report['skipped']) - 5} more")
    finally:
        driver.close()

    # Final tallies
    if all_reports:
        total_txns = sum(r["txn_written"] if args.apply else r["txn_planned"]
                         for r in all_reports)
        total_cp_matched = sum(r["counterparty_matched"] for r in all_reports)
        total_cp = sum(r["counterparty_matched"] + r["counterparty_unmatched"]
                       for r in all_reports)
        total_pages_resolved = sum(r["pages_resolved"] for r in all_reports)
        total_pages = sum(r["pages_resolved"] + r["pages_unresolved"]
                          for r in all_reports)
        holder_matched = sum(1 for r in all_reports if r["account_holder_matched"])

        total_cat_copied = sum(r["category_copied"] for r in all_reports)
        total_cat_fallback = sum(r["category_fallback"] for r in all_reports)
        total_cat = total_cat_copied + total_cat_fallback
        merged_copied_dist: Dict[str, int] = {}
        for r in all_reports:
            for cat, cnt in r["copied_category_dist"].items():
                merged_copied_dist[cat] = merged_copied_dist.get(cat, 0) + cnt

        print()
        print(f"== Totals across {len(all_reports)} documents ==")
        print(f"  account holders matched : {holder_matched}/{len(all_reports)}")
        print(f"  transactions {'written' if args.apply else 'planned'}    : {total_txns}")
        print(f"  counterparties matched  : {total_cp_matched}/{total_cp}")
        print(f"  source pages resolved   : {total_pages_resolved}/{total_pages}")
        print(f"  categories copied       : {total_cat_copied}/{total_cat}  "
              f"(fallback: {total_cat_fallback})")
        if merged_copied_dist:
            print("  copied category distribution:")
            for cat, cnt in sorted(merged_copied_dist.items(),
                                   key=lambda kv: (-kv[1], kv[0])):
                print(f"    {cat:<30s} {cnt}")
        if not args.apply:
            print()
            print("Dry-run only — pass --apply to actually create the v2 nodes.")


if __name__ == "__main__":
    main()
