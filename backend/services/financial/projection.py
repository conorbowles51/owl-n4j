"""The ledger, rendered into the graph, deterministically.

Postgres holds the ledger and Neo4j does not.  The graph is a *view* of the
ledger the way a chart is a view of a table: useful, derived, and never the
thing that is cited.  Everything in this module follows from that one sentence,
so it is worth being exact about what it rules out.

It rules out writing anything into the graph that is not in the ledger.  It
rules out the graph and the ledger disagreeing after a re-run.  And it rules
out the graph being the place a fact goes to acquire authority it did not have
in Postgres: a quarantined row does not become admissible by being drawn.

Five properties, each of which is a decision that could have gone the other way.

*Deterministic.*  The same ledger state produces byte-identical Cypher, in the
same order, with the same parameters.  No clock, no ``datetime()``, no
randomness, no iteration over an unordered set.  This is not fastidiousness:
the projection is how a reader gets from an exhibit back to a row, and a view
that renders differently on Tuesday cannot be sworn to.

*Idempotent.*  Every write is a ``MERGE`` on a key derived from the content of
the ledger row rather than from its surrogate id, so re-ingesting the same file
reproduces the same nodes instead of a second copy of them.  Running the
projection twice is indistinguishable from running it once.

*Structurally faithful about direction.*  A debit leaves an account and a credit
arrives at one, and that difference is carried by the direction of the
relationship rather than by the sign of a number.  Getting this backwards is
the failure mode with no downstream detector: totals still foot, every period
still reconciles, and the graph quietly says that the money went the other way.

*Provenance-preserving.*  ``ref_id``, ``proof_class``, ``extraction_layer`` and
the source document travel onto the node.  A drawn transaction that cannot be
walked back to the page it was read from is decoration.

*Refusing.*  Only ``admitted`` rows are drawn.  Quarantined, superseded and
rejected rows are refused by name and counted, never skipped in silence.  A
projection that quietly drops six rows is worse than one that fails, because
the total it produces is wrong in a way nobody can see.

The module is pure.  It imports nothing from ``neo4j`` and touches no database:
it returns a :class:`ProjectionPlan` of statements and parameters, and the
caller applies them.  That keeps it testable without a driver, and it keeps the
decision about transaction boundaries with the code that owns the session.

On retraction.  A derived view has to be able to *unsay* things.  When a row is
superseded, the node it produced has to leave the graph, and the obvious way to
express that -- pass the full list of surviving keys and delete everything else
-- costs one parameter per row and falls over on a case with a hundred thousand
of them.  The way out is a digest.  Every node and relationship the projection
writes carries ``projection_digest``, a hash over the whole plan; retraction is
then ``WHERE projected_from_ledger = true AND projection_digest <> $digest``,
which is one parameter regardless of size.  An unchanged ledger yields the same
digest and retracts nothing.  Any change at all yields a new digest, every
surviving node is rewritten with it by the merge, and whatever the ledger no
longer contains is left holding a stale digest and is removed.  The statements
are applied in a single transaction, so there is no window in which the graph
carries two digests.

One consequence worth stating plainly, because it is a loaded gun: projecting
an empty transaction list retracts the entire projection for the case.  That is
the correct semantics -- an empty ledger draws an empty graph -- but it means a
caller whose query silently returned nothing will erase the view rather than
leave it stale.  :attr:`ProjectionPlan.transaction_count` is exposed so the
caller can refuse to apply a plan it did not expect to be empty.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import date
from typing import Iterable, Iterator, Mapping, Optional, Sequence

from postgres.models.enums import (
    DocumentStatus,
    ExtractionLayer,
    LedgerStatus,
    ProofClass,
    TransactionDirection,
)
from services.financial.money import Money

# Bumped whenever the shape of what is written changes: the key derivation, the
# property set, the relationship vocabulary.  It feeds the digest, so raising it
# forces every node in every case to be rewritten on the next run rather than
# leaving a graph half in the old shape and half in the new one.
PROJECTION_VERSION = "1"

# The tag the reader uses to decide whether a case is on the old model.  See
# ``FinancialService._get_dataset_metadata``: a case is treated as legacy the
# moment a single amount-bearing node lacks all three of the tags below, and in
# legacy mode the reader discards provenance for the whole case.  Everything the
# projection writes is tagged, so the projection can never itself cause it.
FINANCIAL_MODEL_VERSION = 2

LABEL_ACCOUNT = "FinancialAccount"
LABEL_DOCUMENT = "Document"
LABEL_PERIOD = "FinancialStatementPeriod"
LABEL_TRANSACTION = "FinancialTransaction"

# One label per node, deliberately.  ``FinancialService`` reads the type of a
# node as ``labels(n)[0]``, and Neo4j does not promise an order for labels, so a
# second label would make the rendered type depend on storage order.
PROJECTED_LABELS = (LABEL_ACCOUNT, LABEL_DOCUMENT, LABEL_PERIOD, LABEL_TRANSACTION)

# ``TRANSFERRED_TO`` is the existing vocabulary, not a new one.  The reader
# already resolves both ends of a transaction through
# ``TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO``, so projecting into it means the
# current UI renders projected data with no schema fork and no migration.
REL_TRANSFERRED_TO = "TRANSFERRED_TO"
REL_APPEARS_IN = "APPEARS_IN"
REL_COVERS = "COVERS"
REL_READ_FROM = "READ_FROM"

# Every relationship type the projection is allowed to write, which is also
# every type it is allowed to retract.  Naming them lets retraction match by
# type instead of scanning every relationship in the database, and -- more to
# the point -- it means the projection can never delete an edge of a type it
# does not itself create, whatever a stale digest might be attached to.
PROJECTED_RELATIONSHIPS = (REL_APPEARS_IN, REL_COVERS, REL_READ_FROM, REL_TRANSFERRED_TO)

PROJECTED_FLAG = "projected_from_ledger"
DIGEST_PROPERTY = "projection_digest"

_SEP = "\x1f"

# How many rows travel in one ``UNWIND``.  Chunking bounds the size of any one
# statement's parameters without making the plan non-deterministic, because the
# rows are sorted before they are cut.
DEFAULT_BATCH_SIZE = 500

# The closed set ``evidence_source_type`` is drawn from, defined in
# ``evidence-engine/app/ontology/prompt_builder.py``.  The projection may only
# write a value from this set.
EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "bank_statement",
        "invoice",
        "receipt",
        "wire",
        "card_statement",
        "ledger",
        "official_report",
        "email",
        "interview",
        "other",
    }
)

# Ledger ``document_type`` values that are account statements by definition, and
# so map to ``bank_statement`` without a judgement being made.  The list is
# short on purpose.  A NACHA file is not here: it is a payment origination file,
# not a statement, and calling it one would be a factual error rather than a
# rough edge.  Anything unrecognised becomes ``other``, which is the honest
# answer when the source vocabulary is open.
_SOURCE_TYPE_ALIASES = {
    "bai2": "bank_statement",
    "camt": "bank_statement",
    "camt053": "bank_statement",
    "camt_053": "bank_statement",
    "mt940": "bank_statement",
    "ofx": "bank_statement",
    "qfx": "bank_statement",
    "statement": "bank_statement",
}

# Not written, ever.  ``evidence_strength`` is the retired four-value vocabulary
# (see ``proof_class.from_legacy_strength``); ``proof_class`` carries the same
# information without the pretence that a strength was measured.  The rest are
# owned by the analyst through ``graph_edit_service`` and the
# ``update_transaction_*`` methods, and a projection that wrote them would
# silently undo a person's work on every run.
USER_OWNED_PROPERTIES = frozenset(
    {
        "amount_corrected",
        "correction_reason",
        "counterparty_details",
        "evidence_strength",
        "financial_category",
        "from_entity_key",
        "from_entity_name",
        "notes",
        "original_amount",
        "purpose",
        "to_entity_key",
        "to_entity_name",
    }
)

# Not emitted by the plan.  A uniqueness constraint on the merge key is the
# right guard, but ``CREATE CONSTRAINT`` fails outright if other code has
# already written duplicate keys, and a projection is not the place to discover
# that or to run a migration.  Applied deliberately, out of band.
RECOMMENDED_CONSTRAINTS = tuple(
    f"CREATE CONSTRAINT projected_{label.lower()}_key IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE (n.case_id, n.key) IS UNIQUE"
    for label in PROJECTED_LABELS
)

# Retraction looks for a stale digest, which without an index means reading
# every node and every relationship the projection has ever written.  These
# make it a seek.  Also applied out of band.
RECOMMENDED_INDEXES = tuple(
    f"CREATE INDEX projected_{label.lower()}_digest IF NOT EXISTS "
    f"FOR (n:{label}) ON (n.case_id, n.{DIGEST_PROPERTY})"
    for label in PROJECTED_LABELS
) + tuple(
    f"CREATE INDEX projected_{rel.lower()}_digest IF NOT EXISTS "
    f"FOR ()-[r:{rel}]-() ON (r.case_id, r.{DIGEST_PROPERTY})"
    for rel in PROJECTED_RELATIONSHIPS
)

# Counts amount-bearing nodes in a case and how many carry a provenance tag.
# This cannot be answered without the database, so it is exposed as text for the
# caller to run; :func:`interpret_preflight` reads the two numbers back.
PREFLIGHT_CYPHER = """
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
"""


class ProjectionError(Exception):
    """A projection could not be built from the rows it was given."""


# ---------------------------------------------------------------------------
# What the projection is given
# ---------------------------------------------------------------------------
#
# Explicit records rather than ORM rows.  Reading attributes straight off a
# model would work until a column was renamed, at which point the projection
# would write nulls and nobody would notice, because a missing property in Neo4j
# is indistinguishable from one that was never set.  An adapter fails loudly in
# one place instead.


@dataclass(frozen=True)
class ProjectedAccount:
    """One account, as the graph should hold it."""

    account_id: uuid.UUID
    identity_key: str
    institution_name: Optional[str] = None
    identifier_as_printed: Optional[str] = None
    identifier_normalised: Optional[str] = None
    account_type: Optional[str] = None
    holder_name: Optional[str] = None
    currency: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    routing_number: Optional[str] = None


@dataclass(frozen=True)
class ProjectedDocument:
    """One source document.

    ``original_filename`` is passed in rather than read from the ledger row
    because it lives on ``EvidenceFile``, not on ``FinancialSourceDocument``.
    """

    document_id: uuid.UUID
    sha256_at_ingestion: str
    document_type: str
    proof_class: str
    extraction_layer: int
    parser_name: str
    parser_version: str
    status: str
    original_filename: Optional[str] = None
    institution_name: Optional[str] = None
    page_count: Optional[int] = None
    currency: Optional[str] = None


@dataclass(frozen=True)
class ProjectedPeriod:
    """One statement period, with the arithmetic that was or was not closed."""

    period_id: uuid.UUID
    source_document_id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    period_start_source: Optional[str] = None
    period_end_source: Optional[str] = None
    opening_balance_minor: Optional[int] = None
    closing_balance_minor: Optional[int] = None
    opening_balance_source: Optional[str] = None
    closing_balance_source: Optional[str] = None
    reconciliation_status: Optional[str] = None
    computed_closing_minor: Optional[int] = None
    delta_minor: Optional[int] = None
    credit_total_minor: Optional[int] = None
    debit_total_minor: Optional[int] = None
    transaction_count: Optional[int] = None


@dataclass(frozen=True)
class ProjectedTransaction:
    """One ledger row.

    ``ref_id`` is the citable reference and, deliberately, also the node key:
    the thing a reader is asked to look up is the thing the graph is keyed on.
    """

    transaction_id: uuid.UUID
    ref_id: str
    account_id: uuid.UUID
    source_document_id: uuid.UUID
    amount_minor: int
    currency: str
    direction: str
    ordering_date: date
    ordering_date_source: str
    proof_class: str
    extraction_layer: int
    ledger_status: str
    content_hash: str
    row_index: int
    statement_period_id: Optional[uuid.UUID] = None
    running_balance_minor: Optional[int] = None
    transaction_date: Optional[date] = None
    posted_date: Optional[date] = None
    value_date: Optional[date] = None
    effective_date: Optional[date] = None
    description: Optional[str] = None
    counterparty_raw: Optional[str] = None
    transaction_type: Optional[str] = None
    bank_reference: Optional[str] = None


# ---------------------------------------------------------------------------
# What the projection produces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNode:
    label: str
    key: str
    properties: Mapping[str, object]


@dataclass(frozen=True)
class GraphEdge:
    type: str
    edge_key: str
    start_label: str
    start_key: str
    end_label: str
    end_key: str
    properties: Mapping[str, object]


@dataclass(frozen=True)
class CypherStatement:
    """One statement and its parameters, to be run as written.

    ``DriverManager.execute_cypher_batch`` takes bare strings and passes no
    parameters, so it cannot run these: interpolating projected values into
    Cypher text would be injection through a bank statement.  The caller runs
    ``session.run(statement.cypher, statement.parameters)`` for each statement,
    in order, inside one transaction.
    """

    cypher: str
    parameters: Mapping[str, object]
    purpose: str


@dataclass(frozen=True)
class Refusal:
    """A row that was not drawn, and why."""

    subject: str
    subject_id: str
    reason: str


@dataclass(frozen=True)
class PreflightFinding:
    """What :data:`PREFLIGHT_CYPHER` found, read back.

    ``uses_legacy`` reproduces the reader's own test exactly.  It matters
    because the reader applies it to the *case*, not to the node: a single
    untagged amount-bearing node anywhere in the case makes the reader return
    ``evidence_source_type: None`` and ``is_evidence_backed_transaction: False``
    for every transaction in it, projected ones included.  The projection cannot
    cause this and cannot fix it; it can only say so before it runs.
    """

    total_amount_nodes: int
    tagged_amount_nodes: int

    @property
    def untagged_amount_nodes(self) -> int:
        return self.total_amount_nodes - self.tagged_amount_nodes

    @property
    def uses_legacy(self) -> bool:
        return self.total_amount_nodes > 0 and self.tagged_amount_nodes < self.total_amount_nodes

    @property
    def provenance_will_survive_read(self) -> bool:
        return not self.uses_legacy


@dataclass(frozen=True)
class ProjectionPlan:
    """Everything needed to make the graph match the ledger, and nothing else."""

    case_id: str
    digest: str
    statements: tuple[CypherStatement, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    refusals: tuple[Refusal, ...]

    @property
    def transaction_count(self) -> int:
        return sum(1 for node in self.nodes if node.label == LABEL_TRANSACTION)

    @property
    def is_empty(self) -> bool:
        return not self.nodes


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------
#
# Derived from content, never from a surrogate id.  A ``uuid4`` primary key
# changes when a document is re-ingested, which would make the projection draw a
# second node for the same account and leave the first one behind.


def _digest(*parts: str) -> str:
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()


def account_key(identity_key: str) -> str:
    """Stable key for an account, from the identity the ledger resolved it to."""
    if not identity_key:
        raise ProjectionError("an account must have an identity_key to be projected")
    return "ACC-" + _digest("account", identity_key)[:32]


def document_key(sha256_at_ingestion: str) -> str:
    """Stable key for a document, from the bytes that were ingested."""
    if not sha256_at_ingestion:
        raise ProjectionError("a document must have a sha256 to be projected")
    return "DOC-" + _digest("document", sha256_at_ingestion)[:32]


def period_key(document_node_key: str, account_node_key: str,
               period_start: Optional[date], period_end: Optional[date]) -> str:
    """Stable key for a statement period.

    Keyed on the document and account node keys, which are themselves derived
    from content, so the period key is content-derived transitively.  The dates
    are included because one document can carry several periods for one account.
    """
    return "PER-" + _digest(
        "period",
        document_node_key,
        account_node_key,
        _iso(period_start) or "",
        _iso(period_end) or "",
    )[:32]


def transaction_key(ref_id: str) -> str:
    """The transaction's key is its citable reference, unchanged.

    ``ref_id`` already arrives grouped and prefixed (``TX-XXXX-XXXX-XXXX``) from
    ``references.ref_id``, and it is already a function of the document's bytes
    and the row's content hash.  Hashing it again would only make the key
    something a reader could not look up.
    """
    if not ref_id:
        raise ProjectionError("a transaction must have a ref_id to be projected")
    return ref_id


def _edge_key(rel_type: str, start_key: str, end_key: str) -> str:
    return _digest("edge", rel_type, start_key, end_key)[:32]


# ---------------------------------------------------------------------------
# Value rendering
# ---------------------------------------------------------------------------


def _iso(value: Optional[date]) -> Optional[str]:
    """A date as zero-padded ``YYYY-MM-DD``, or nothing.

    The format is not cosmetic.  ``get_financial_transactions`` compares
    ``n.date`` against its range filters as a *string* and sorts on it, so a
    date written in any other shape silently breaks both filtering and ordering
    while continuing to display correctly.
    """
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"


def _major_units(minor: Optional[int], currency: str) -> Optional[str]:
    """An exact decimal string in major units, ungrouped and unsigned-prefixed.

    Written for the existing reader, which coerces ``n.amount`` through
    ``toFloat`` and then ``round(f, 2)``.  The string itself is exact; the loss
    happens in the reader, and only for the three- and four-exponent currencies.
    ``amount_minor`` is the authoritative value on the node for that reason.
    """
    if minor is None:
        return None
    return Money.from_minor_units(minor, currency).format(with_currency=False, grouping=False)


def evidence_source_type_for(document_type: Optional[str]) -> str:
    """Map a ledger ``document_type`` into the graph's closed vocabulary.

    ``FinancialSourceDocument.document_type`` is free text with no enum behind
    it, so this normalises, accepts an exact match against the closed set,
    consults a short alias table for the format names whose mapping is not a
    judgement call, and otherwise answers ``other``.  Guessing would put a value
    on the node that reads as a finding and is not one.
    """
    if not document_type:
        return "other"
    normalised = document_type.strip().lower().replace("-", "_").replace(" ", "_").replace(".", "")
    if normalised in EVIDENCE_SOURCE_TYPES:
        return normalised
    return _SOURCE_TYPE_ALIASES.get(normalised, "other")


def _validate_enums(transaction: ProjectedTransaction) -> Optional[str]:
    """Reject a row whose coded fields are not in their vocabulary.

    Direction is the one that matters most: it decides which way the
    relationship points, and an unrecognised value would otherwise fall through
    to a default and draw the money flowing the wrong way.
    """
    try:
        TransactionDirection(transaction.direction)
    except ValueError:
        return f"direction {transaction.direction!r} is not a known direction"
    try:
        ProofClass(transaction.proof_class)
    except ValueError:
        return f"proof_class {transaction.proof_class!r} is not a known class"
    try:
        ExtractionLayer(transaction.extraction_layer)
    except ValueError:
        return f"extraction_layer {transaction.extraction_layer!r} is not a known layer"
    return None


# ---------------------------------------------------------------------------
# Node property sets
# ---------------------------------------------------------------------------
#
# Every ledger-owned key appears on every run, set to null when the ledger has
# no value.  Cypher removes a property assigned null and ``SET n += $props``
# touches only the keys it is given, so writing the full set both writes and
# clears deterministically while leaving anything an analyst added untouched.
# ``SET n = $props`` would destroy their work; omitting a null would leave a
# stale value behind after the ledger dropped it.


def _common(case_id: str, key: str) -> dict:
    return {
        "case_id": case_id,
        "key": key,
        PROJECTED_FLAG: True,
        "financial_model_version": FINANCIAL_MODEL_VERSION,
        "projection_version": PROJECTION_VERSION,
    }


def _account_display_name(account: ProjectedAccount) -> str:
    """A name for the account, because a node without one is invisible.

    ``get_financial_entities`` selects on ``n.name IS NOT NULL``, so an account
    with no name would be projected and then never appear in the entity picker.
    Falls back to the identity key, which is not pretty but is always present
    and is at least the thing the ledger actually resolved the account to.
    """
    for candidate in (account.holder_name, account.identifier_as_printed,
                      account.identifier_normalised, account.institution_name):
        if candidate and candidate.strip():
            return candidate.strip()
    return account.identity_key


def _account_properties(case_id: str, account: ProjectedAccount, key: str) -> dict:
    properties = _common(case_id, key)
    properties.update(
        {
            # No `amount` on this node, ever.  The reader treats any node in the
            # case carrying `amount` as a transaction, regardless of its label.
            "name": _account_display_name(account),
            "ledger_account_id": str(account.account_id),
            "ledger_identity_key": account.identity_key,
            "institution_name": account.institution_name,
            "identifier_as_printed": account.identifier_as_printed,
            "identifier_normalised": account.identifier_normalised,
            "account_type": account.account_type,
            "currency": account.currency,
            "iban": account.iban,
            "bic": account.bic,
            "routing_number": account.routing_number,
        }
    )
    return properties


def _document_properties(case_id: str, document: ProjectedDocument, key: str) -> dict:
    properties = _common(case_id, key)
    properties.update(
        {
            "name": document.original_filename or document.sha256_at_ingestion,
            "ledger_document_id": str(document.document_id),
            "sha256_at_ingestion": document.sha256_at_ingestion,
            "document_type": document.document_type,
            "proof_class": document.proof_class,
            "extraction_layer": document.extraction_layer,
            "parser_name": document.parser_name,
            "parser_version": document.parser_version,
            "institution_name": document.institution_name,
            "page_count": document.page_count,
            "currency": document.currency,
        }
    )
    return properties


def _period_properties(case_id: str, period: ProjectedPeriod, key: str) -> dict:
    properties = _common(case_id, key)
    properties.update(
        {
            # No `name`, so the period never surfaces in the entity picker, and
            # no `amount`, so it is never read as a transaction.  The balances
            # are named for what they are.
            "ledger_period_id": str(period.period_id),
            "currency": period.currency,
            "period_start": _iso(period.period_start),
            "period_end": _iso(period.period_end),
            "period_start_source": period.period_start_source,
            "period_end_source": period.period_end_source,
            "opening_balance_minor": period.opening_balance_minor,
            "closing_balance_minor": period.closing_balance_minor,
            "opening_balance": _major_units(period.opening_balance_minor, period.currency),
            "closing_balance": _major_units(period.closing_balance_minor, period.currency),
            "opening_balance_source": period.opening_balance_source,
            "closing_balance_source": period.closing_balance_source,
            "reconciliation_status": period.reconciliation_status,
            "computed_closing_minor": period.computed_closing_minor,
            "computed_closing": _major_units(period.computed_closing_minor, period.currency),
            "delta_minor": period.delta_minor,
            "delta": _major_units(period.delta_minor, period.currency),
            "credit_total_minor": period.credit_total_minor,
            "debit_total_minor": period.debit_total_minor,
            "ledger_transaction_count": period.transaction_count,
        }
    )
    return properties


def _transaction_properties(case_id: str, transaction: ProjectedTransaction,
                            key: str, document: ProjectedDocument) -> dict:
    description = (transaction.description or "").strip()
    properties = _common(case_id, key)
    properties.update(
        {
            # The three tags the reader checks for.  All three, on every node,
            # so a projected case can never be misread as legacy.
            "financial_view_mode": "transaction",
            "is_evidence_backed_transaction": True,
            "financial_record_kind": "transaction",
            "is_financial_event": True,
            # `name` is safe here: `get_financial_entities` excludes anything
            # with a non-null `amount`, so a named transaction cannot pollute
            # the entity list.  Without it the UI renders a blank row.
            "name": description or transaction.ref_id,
            "summary": description or None,
            "date": _iso(transaction.ordering_date),
            "amount": _major_units(transaction.amount_minor, transaction.currency),
            "amount_minor": transaction.amount_minor,
            "currency": transaction.currency,
            # Carried explicitly as well as structurally.  The relationship
            # direction is what the graph reasons over; this is what a person
            # reads when they open the node.
            "direction": transaction.direction,
            "ref_id": transaction.ref_id,
            "proof_class": transaction.proof_class,
            "extraction_layer": transaction.extraction_layer,
            "evidence_source_type": evidence_source_type_for(document.document_type),
            "source_document_id": str(transaction.source_document_id),
            "source_filename": document.original_filename,
            "ledger_transaction_id": str(transaction.transaction_id),
            "ledger_account_id": str(transaction.account_id),
            "ledger_content_hash": transaction.content_hash,
            "ledger_row_index": transaction.row_index,
            "ordering_date_source": transaction.ordering_date_source,
            "transaction_date": _iso(transaction.transaction_date),
            "posted_date": _iso(transaction.posted_date),
            "value_date": _iso(transaction.value_date),
            "effective_date": _iso(transaction.effective_date),
            "running_balance_minor": transaction.running_balance_minor,
            "bank_reference": transaction.bank_reference,
            "ledger_transaction_type": transaction.transaction_type,
            # Named `ledger_counterparty_raw` rather than `counterparty` because
            # it is the unresolved string off the statement.  Resolving it into
            # a node would be entity resolution by string equality, which is the
            # thing `linkage.py` exists to avoid; counterparty edges arrive with
            # the link table, not here.
            "ledger_counterparty_raw": transaction.counterparty_raw,
        }
    )
    return properties


# ---------------------------------------------------------------------------
# Building the plan
# ---------------------------------------------------------------------------


def _chunk(rows: Sequence[dict], size: int) -> Iterator[list]:
    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def _canonical(case: str, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]) -> str:
    """The plan, serialised so that the same plan always serialises the same way.

    ``sort_keys`` fixes the order within each property map; the node and edge
    lists are sorted by the caller before they arrive here.  Property values are
    only ever ``str``, ``int``, ``bool`` or ``None`` by construction, so any
    other type raises rather than being coerced to something that hashes
    differently on another interpreter.

    The case id is included even though every node already carries it, because
    an *empty* plan has no nodes to carry it and two different cases projecting
    nothing would otherwise share a digest.  Retraction is scoped by case so it
    would still be correct, but a digest that means "some case, empty" rather
    than "this case, empty" is a coincidence waiting to be relied upon.
    """
    return json.dumps(
        {
            "version": PROJECTION_VERSION,
            "case_id": case,
            "nodes": [
                {"label": n.label, "key": n.key, "properties": dict(n.properties)}
                for n in nodes
            ],
            "edges": [
                {
                    "type": e.type,
                    "edge_key": e.edge_key,
                    "start": [e.start_label, e.start_key],
                    "end": [e.end_label, e.end_key],
                    "properties": dict(e.properties),
                }
                for e in edges
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _fold_duplicate_keys(
    drawn: Sequence[tuple[GraphNode, str]],
) -> tuple[list[GraphNode], list[Refusal]]:
    """Keep one node per ``(label, key)`` and say which ledger rows folded in.

    Two ledger rows can legitimately reach the same node.  ``sha256`` is unique
    on a *document's bytes*, not on ``financial_source_documents``, whose only
    uniqueness is ``(ingestion_run_id, evidence_file_id)`` -- so the same file
    ingested by two runs is two admitted rows describing one document, until
    :func:`services.financial.duplicates.resolve_duplicates` is run, which is an
    explicit operation and not a constraint.  Statement periods inherit the
    collision, because a period's key is derived from its document's.

    Folding is right, because a content-addressed node *is* the document, and
    the transactions of both rows attach to it correctly.  Doing it silently is
    not: the second row's ledger id would vanish, and with it the only evidence
    in the graph that the file was ingested twice.  So the fold is recorded.

    ``MERGE`` would collapse these anyway, with the last write winning; the
    point of folding here is that the plan, the digest and the statements all
    agree on one node instead of the plan carrying a duplicate the database
    quietly resolves.
    """
    kept: list[GraphNode] = []
    first_by_key: dict[tuple[str, str], str] = {}
    refusals: list[Refusal] = []

    for node, ledger_id in drawn:
        identity = (node.label, node.key)
        if identity in first_by_key:
            refusals.append(
                Refusal(
                    node.label,
                    ledger_id,
                    f"folded into the {node.label} already drawn for key {node.key} "
                    f"from ledger row {first_by_key[identity]}; both rows describe "
                    "the same thing and rows referring to either still project",
                )
            )
            continue
        first_by_key[identity] = ledger_id
        kept.append(node)

    return kept, refusals


def project_case(
    case_id,
    *,
    accounts: Iterable[ProjectedAccount],
    documents: Iterable[ProjectedDocument],
    periods: Iterable[ProjectedPeriod] = (),
    transactions: Iterable[ProjectedTransaction] = (),
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ProjectionPlan:
    """Build the statements that make the graph match the ledger for one case.

    Nothing is written.  The returned plan is applied by the caller, in order,
    in a single transaction.

    Rows are drawn only if they are ``admitted`` and only if everything they
    depend on was drawn too: a transaction whose document was quarantined is an
    orphan and is refused rather than being attached to nothing.  Every refusal
    is named in :attr:`ProjectionPlan.refusals`, because a projection that
    quietly omits rows produces a total nobody can check.
    """
    if batch_size < 1:
        raise ProjectionError("batch_size must be at least 1")

    case = str(case_id)
    refusals: list[Refusal] = []

    # -- accounts ----------------------------------------------------------
    # No status column on FinancialAccount: an account exists because a
    # statement named it, and there is nothing to admit or quarantine.
    accounts_by_id: dict[uuid.UUID, ProjectedAccount] = {}
    for account in accounts:
        accounts_by_id[account.account_id] = account

    # -- documents ---------------------------------------------------------
    documents_by_id: dict[uuid.UUID, ProjectedDocument] = {}
    for document in documents:
        if document.status != DocumentStatus.admitted.value:
            refusals.append(
                Refusal("document", str(document.document_id),
                        f"document status is {document.status!r}, not admitted")
            )
            continue
        documents_by_id[document.document_id] = document

    # -- transactions ------------------------------------------------------
    # Two rows sharing a ref_id would MERGE onto one node and one of them would
    # vanish without trace.  It cannot happen legitimately -- the content hash
    # carries an occurrence counter precisely so that identical rows differ --
    # so a collision is a defect, and both rows are refused rather than one
    # being picked arbitrarily.
    seen_refs: dict[str, ProjectedTransaction] = {}
    collided: set[str] = set()
    admitted: list[ProjectedTransaction] = []

    for transaction in transactions:
        if transaction.ledger_status != LedgerStatus.admitted.value:
            refusals.append(
                Refusal("transaction", transaction.ref_id,
                        f"ledger status is {transaction.ledger_status!r}, not admitted")
            )
            continue
        problem = _validate_enums(transaction)
        if problem is not None:
            refusals.append(Refusal("transaction", transaction.ref_id, problem))
            continue
        if transaction.account_id not in accounts_by_id:
            refusals.append(
                Refusal("transaction", transaction.ref_id,
                        f"account {transaction.account_id} was not projected")
            )
            continue
        if transaction.source_document_id not in documents_by_id:
            refusals.append(
                Refusal("transaction", transaction.ref_id,
                        f"source document {transaction.source_document_id} was not projected")
            )
            continue
        if transaction.ref_id in seen_refs:
            collided.add(transaction.ref_id)
            refusals.append(
                Refusal("transaction", transaction.ref_id,
                        "ref_id is shared with another row in this batch")
            )
            continue
        seen_refs[transaction.ref_id] = transaction
        admitted.append(transaction)

    if collided:
        admitted = [t for t in admitted if t.ref_id not in collided]
        for ref in sorted(collided):
            refusals.append(
                Refusal("transaction", ref,
                        "ref_id is shared with another row in this batch")
            )

    # -- periods -----------------------------------------------------------
    kept_periods: list[tuple[ProjectedPeriod, str, str, str]] = []
    for period in periods:
        if period.account_id not in accounts_by_id:
            refusals.append(
                Refusal("period", str(period.period_id),
                        f"account {period.account_id} was not projected")
            )
            continue
        if period.source_document_id not in documents_by_id:
            refusals.append(
                Refusal("period", str(period.period_id),
                        f"source document {period.source_document_id} was not projected")
            )
            continue
        doc_key = document_key(documents_by_id[period.source_document_id].sha256_at_ingestion)
        acc_key = account_key(accounts_by_id[period.account_id].identity_key)
        kept_periods.append(
            (period, period_key(doc_key, acc_key, period.period_start, period.period_end),
             doc_key, acc_key)
        )

    period_key_by_id = {period.period_id: key for period, key, _, _ in kept_periods}

    # -- nodes -------------------------------------------------------------
    # Only accounts and documents a drawn row actually reaches.  Projecting an
    # account that no admitted transaction touches would put a node in the graph
    # that the ledger does not support.
    reachable_accounts = {t.account_id for t in admitted} | {p.account_id for p, _, _, _ in kept_periods}
    reachable_documents = {t.source_document_id for t in admitted} | {
        p.source_document_id for p, _, _, _ in kept_periods
    }

    drawn: list[tuple[GraphNode, str]] = []
    for account_id in sorted(reachable_accounts, key=str):
        account = accounts_by_id[account_id]
        key = account_key(account.identity_key)
        drawn.append(
            (GraphNode(LABEL_ACCOUNT, key, _account_properties(case, account, key)),
             str(account_id))
        )
    for document_id in sorted(reachable_documents, key=str):
        document = documents_by_id[document_id]
        key = document_key(document.sha256_at_ingestion)
        drawn.append(
            (GraphNode(LABEL_DOCUMENT, key, _document_properties(case, document, key)),
             str(document_id))
        )
    # Sorted by (key, ledger id) rather than by key alone: two periods can share
    # a key, and a stable sort would then fold whichever happened to arrive
    # first, making the plan depend on input order.
    for period, key, _, _ in sorted(kept_periods, key=lambda item: (item[1], str(item[0].period_id))):
        drawn.append(
            (GraphNode(LABEL_PERIOD, key, _period_properties(case, period, key)),
             str(period.period_id))
        )
    for transaction in sorted(admitted, key=lambda t: t.ref_id):
        key = transaction_key(transaction.ref_id)
        document = documents_by_id[transaction.source_document_id]
        drawn.append(
            (GraphNode(LABEL_TRANSACTION, key,
                       _transaction_properties(case, transaction, key, document)),
             str(transaction.transaction_id))
        )

    nodes, fold_refusals = _fold_duplicate_keys(drawn)
    refusals.extend(fold_refusals)

    # -- edges -------------------------------------------------------------
    edges: list[GraphEdge] = []

    def _edge(rel_type, start_label, start_key, end_label, end_key, **extra) -> None:
        key = _edge_key(rel_type, start_key, end_key)
        properties = {
            "case_id": case,
            "edge_key": key,
            PROJECTED_FLAG: True,
            "projection_version": PROJECTION_VERSION,
        }
        properties.update(extra)
        edges.append(GraphEdge(rel_type, key, start_label, start_key, end_label, end_key, properties))

    for transaction in sorted(admitted, key=lambda t: t.ref_id):
        tx_key = transaction_key(transaction.ref_id)
        acc_key = account_key(accounts_by_id[transaction.account_id].identity_key)
        doc_key = document_key(documents_by_id[transaction.source_document_id].sha256_at_ingestion)

        # The whole point of the module, in four lines.  A debit leaves the
        # account; a credit arrives at it.  The reader resolves `from_entity`
        # as (x)-[:TRANSFERRED_TO]->(n) and `to_entity` as
        # (n)-[:TRANSFERRED_TO]->(x), so this renders correctly with no change
        # to the reader at all.
        if transaction.direction == TransactionDirection.debit.value:
            _edge(REL_TRANSFERRED_TO, LABEL_ACCOUNT, acc_key, LABEL_TRANSACTION, tx_key,
                  direction=TransactionDirection.debit.value)
        else:
            _edge(REL_TRANSFERRED_TO, LABEL_TRANSACTION, tx_key, LABEL_ACCOUNT, acc_key,
                  direction=TransactionDirection.credit.value)

        _edge(REL_READ_FROM, LABEL_TRANSACTION, tx_key, LABEL_DOCUMENT, doc_key)

        if transaction.statement_period_id in period_key_by_id:
            _edge(REL_APPEARS_IN, LABEL_TRANSACTION, tx_key,
                  LABEL_PERIOD, period_key_by_id[transaction.statement_period_id])

    for period, key, doc_key, acc_key in sorted(kept_periods, key=lambda item: item[1]):
        _edge(REL_COVERS, LABEL_PERIOD, key, LABEL_ACCOUNT, acc_key)
        _edge(REL_READ_FROM, LABEL_PERIOD, key, LABEL_DOCUMENT, doc_key)

    edges.sort(key=lambda e: (e.type, e.start_label, e.end_label, e.edge_key))

    # A folded node's edges are drawn twice, once per ledger row that reached
    # it.  They are identical, and necessarily so: ``edge_key`` is a digest of
    # the relationship type and both endpoint keys, so two edges sharing one
    # carry the same endpoints, and the only non-constant property -- the
    # ``direction`` on TRANSFERRED_TO -- is a function of the transaction whose
    # key is already inside the digest.  Dropped silently rather than refused,
    # because the fold that caused it is already reported against the node.
    deduped: list[GraphEdge] = []
    seen_edges: dict[str, GraphEdge] = {}
    for edge in edges:
        previous = seen_edges.get(edge.edge_key)
        if previous is not None:
            if previous.properties != edge.properties:
                raise ProjectionError(
                    f"two edges share edge_key {edge.edge_key} but differ in properties"
                )
            continue
        seen_edges[edge.edge_key] = edge
        deduped.append(edge)
    edges = deduped

    refusals.sort(key=lambda r: (r.subject, r.subject_id, r.reason))

    # -- digest ------------------------------------------------------------
    # Computed over the plan without the digest in it, because a value cannot
    # be part of what it is a hash of.
    digest = hashlib.sha256(_canonical(case, nodes, edges).encode("utf-8")).hexdigest()

    nodes = [replace(n, properties={**n.properties, DIGEST_PROPERTY: digest}) for n in nodes]
    edges = [replace(e, properties={**e.properties, DIGEST_PROPERTY: digest}) for e in edges]

    statements = _statements(case, digest, nodes, edges, batch_size)

    return ProjectionPlan(
        case_id=case,
        digest=digest,
        statements=tuple(statements),
        nodes=tuple(nodes),
        edges=tuple(edges),
        refusals=tuple(refusals),
    )


def _statements(case: str, digest: str, nodes: Sequence[GraphNode],
                edges: Sequence[GraphEdge], batch_size: int) -> list[CypherStatement]:
    """Order matters, and it is total.

    Nodes before edges, so that a relationship ``MERGE`` never has to invent an
    endpoint.  Retraction last, and relationships before nodes, so that the
    final ``DETACH DELETE`` also sweeps any analyst-drawn edge that was left
    pointing at a node the ledger no longer supports.
    """
    statements: list[CypherStatement] = []

    by_label: dict[str, list[dict]] = {label: [] for label in PROJECTED_LABELS}
    for node in nodes:
        by_label[node.label].append({"key": node.key, "props": dict(node.properties)})

    for label in PROJECTED_LABELS:
        rows = by_label[label]
        if not rows:
            continue
        cypher = (
            "UNWIND $rows AS row\n"
            f"MERGE (n:{label} {{case_id: $case_id, key: row.key}})\n"
            "SET n += row.props"
        )
        for index, chunk in enumerate(_chunk(rows, batch_size)):
            statements.append(
                CypherStatement(cypher, {"case_id": case, "rows": chunk},
                                f"merge {label} nodes, batch {index}")
            )

    # Grouped by the shape of the pattern so that both endpoints carry a label
    # and the match is an index seek rather than a scan of every node.
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for edge in edges:
        grouped.setdefault((edge.start_label, edge.type, edge.end_label), []).append(
            {
                "start_key": edge.start_key,
                "end_key": edge.end_key,
                "edge_key": edge.edge_key,
                "props": dict(edge.properties),
            }
        )

    for (start_label, rel_type, end_label) in sorted(grouped):
        rows = grouped[(start_label, rel_type, end_label)]
        cypher = (
            "UNWIND $rows AS row\n"
            f"MATCH (a:{start_label} {{case_id: $case_id, key: row.start_key}})\n"
            f"MATCH (b:{end_label} {{case_id: $case_id, key: row.end_key}})\n"
            f"MERGE (a)-[r:{rel_type} {{edge_key: row.edge_key}}]->(b)\n"
            "SET r += row.props"
        )
        for index, chunk in enumerate(_chunk(rows, batch_size)):
            statements.append(
                CypherStatement(cypher, {"case_id": case, "rows": chunk},
                                f"merge ({start_label})-[:{rel_type}]->({end_label}), batch {index}")
            )

    for rel in PROJECTED_RELATIONSHIPS:
        statements.append(
            CypherStatement(
                f"MATCH ()-[r:{rel}]->()\n"
                f"WHERE r.{PROJECTED_FLAG} = true\n"
                "  AND r.case_id = $case_id\n"
                f"  AND r.{DIGEST_PROPERTY} <> $digest\n"
                "DELETE r",
                {"case_id": case, "digest": digest},
                f"retract {rel} relationships this projection no longer supports",
            )
        )

    for label in PROJECTED_LABELS:
        statements.append(
            CypherStatement(
                f"MATCH (n:{label} {{case_id: $case_id}})\n"
                f"WHERE n.{PROJECTED_FLAG} = true\n"
                f"  AND n.{DIGEST_PROPERTY} <> $digest\n"
                "DETACH DELETE n",
                {"case_id": case, "digest": digest},
                f"retract {label} nodes this projection no longer supports",
            )
        )

    return statements


def interpret_preflight(total_amount_nodes, tagged_amount_nodes) -> PreflightFinding:
    """Read back the two counts :data:`PREFLIGHT_CYPHER` returns.

    Kept separate from the query so the judgement is testable without a
    database, and so the caller can decide what to do about a legacy case rather
    than having the projection decide for it.
    """
    return PreflightFinding(
        total_amount_nodes=int(total_amount_nodes or 0),
        tagged_amount_nodes=int(tagged_amount_nodes or 0),
    )


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------
#
# One place where a schema change breaks loudly.


def account_from_row(row) -> ProjectedAccount:
    return ProjectedAccount(
        account_id=row.id,
        identity_key=row.identity_key,
        institution_name=row.institution_name,
        identifier_as_printed=row.identifier_as_printed,
        identifier_normalised=row.identifier_normalised,
        account_type=row.account_type,
        holder_name=row.holder_name,
        currency=row.currency,
        iban=row.iban,
        bic=row.bic,
        routing_number=row.routing_number,
    )


def document_from_row(row, *, original_filename: Optional[str] = None) -> ProjectedDocument:
    """``original_filename`` is joined in from ``EvidenceFile``; the ledger row
    carries only the reference to it."""
    return ProjectedDocument(
        document_id=row.id,
        sha256_at_ingestion=row.sha256_at_ingestion,
        document_type=row.document_type,
        proof_class=row.proof_class,
        extraction_layer=row.extraction_layer,
        parser_name=row.parser_name,
        parser_version=row.parser_version,
        status=row.status,
        original_filename=original_filename,
        institution_name=row.institution_name,
        page_count=row.page_count,
        currency=row.currency,
    )


def period_from_row(row) -> ProjectedPeriod:
    return ProjectedPeriod(
        period_id=row.id,
        source_document_id=row.source_document_id,
        account_id=row.account_id,
        currency=row.currency,
        period_start=row.period_start,
        period_end=row.period_end,
        period_start_source=row.period_start_source,
        period_end_source=row.period_end_source,
        opening_balance_minor=row.opening_balance_minor,
        closing_balance_minor=row.closing_balance_minor,
        opening_balance_source=row.opening_balance_source,
        closing_balance_source=row.closing_balance_source,
        reconciliation_status=row.reconciliation_status,
        computed_closing_minor=row.computed_closing_minor,
        delta_minor=row.delta_minor,
        credit_total_minor=row.credit_total_minor,
        debit_total_minor=row.debit_total_minor,
        transaction_count=row.transaction_count,
    )


def transaction_from_row(row) -> ProjectedTransaction:
    return ProjectedTransaction(
        transaction_id=row.id,
        ref_id=row.ref_id,
        account_id=row.account_id,
        source_document_id=row.source_document_id,
        amount_minor=row.amount_minor,
        currency=row.currency,
        direction=row.direction,
        ordering_date=row.ordering_date,
        ordering_date_source=row.ordering_date_source,
        proof_class=row.proof_class,
        extraction_layer=row.extraction_layer,
        ledger_status=row.ledger_status,
        content_hash=row.content_hash,
        row_index=row.row_index,
        statement_period_id=row.statement_period_id,
        running_balance_minor=row.running_balance_minor,
        transaction_date=row.transaction_date,
        posted_date=row.posted_date,
        value_date=row.value_date,
        effective_date=row.effective_date,
        description=row.description,
        counterparty_raw=row.counterparty_raw,
        transaction_type=row.transaction_type,
        bank_reference=row.bank_reference,
    )
