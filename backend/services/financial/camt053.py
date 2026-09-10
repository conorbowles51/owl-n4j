"""Layer 0 for camt.053: a specification-conformant parse, exact by construction.

Extraction divides into layers and this one runs first.  For P0 and P1 formats
there is no extraction problem: camt.053, BAI2, NACHA and MT940 are parsed with
a specification-conformant parser and the output is exact by
construction.  Everything else in the pipeline reads a document and forms an
opinion about what it says.  This module does not.  A camt.053 states its
figures in named elements with a declared currency, and the only way to get
them wrong is to misread the specification.

What the format guarantees is the reason camt.053 is
the first parser worth writing:

    OPBD + ΣCredits − ΣDebits = CLBD

That identity is *structural, not printed*.  A bank statement PDF prints its
control totals and we check them because the institution computed them; here
there is nothing to print, because the relationship is a property of a
conformant document.  The consequence is exact: if a parse
violates the identity, the parse is wrong.  This module therefore reports a violation as
evidence against its own reading first, and against the document second — which
is why a failure demotes the proof class rather than raising.

What this buys, and what it costs
---------------------------------

:attr:`~services.financial.proof_class.SourceShape.native_with_control_totals`
combined with :attr:`~postgres.models.enums.ReconciliationStatus.balanced`
is the only route to :attr:`~postgres.models.enums.ProofClass.p0`, which until
this module existed was unreachable — the shape's own comment in
``proof_class.py`` said so.  p0 auto-admits to the verified ledger with no
human act at all, so the bar is high and the safe direction is asymmetric:
``assign_proof_class`` will not name p0 on anything weaker than a passing
check, and neither will this module.  An unattempted check is not a passing
one, so a document whose balances are absent lands at ``unavailable`` and
therefore p3, not p0.

Three control totals, checked separately
----------------------------------------

A conformant document can carry three independent arithmetic guarantees, and
they are kept apart rather than merged into one verdict, because they fail for
different reasons and a reviewer needs to know which one moved.

1. **The balance identity**, above.  Always attempted.  Booked entries only,
   because ``OPBD`` and ``CLBD`` are *booked* balances by definition and
   including a pending entry breaks an identity that was never over it.
2. **The transaction summary** (``TxsSummry``): ``TtlCdtNtries/Sum``,
   ``TtlDbtNtries/Sum`` and the entry counts.  Optional in the schema.
   Attempted only when the entry population it covers is unambiguous — see
   :func:`_check_summary`.
3. **The batch totals** (``NtryDtls/Btch``): ``TtlAmt`` and ``NbOfTxs`` against
   the entry's own amount and its ``TxDtls`` count.  Per entry, when present.

The statement's status is the weakest outcome among the checks that ran, and
the document's is the weakest among its statements.  Weakest, not first, so a
second statement cannot mask a first that failed.

Decisions the specification leaves open
---------------------------------------

Each of these resolves toward *not* claiming p0, because the error is
asymmetric: a class assigned one step too low costs an adjudication a person will
resolve, and one step too high puts an unchecked row inside a total.

**Direction comes from ``CdtDbtInd``, never from the sign of ``Amt``.**  camt
amounts are non-negative by schema; the direction is a sibling element.  A
parser that inferred direction from a sign would read every debit as a credit
and still produce a ledger that looked entirely plausible, since every row
would carry a positive amount and a date.  The identity would then fail by
exactly twice the debit total, which is a large number that explains nothing.

**Only ``BOOK`` entries enter the balance identity.**  ``PDNG`` and ``INFO``
entries are parsed, retained and counted, but excluded from the arithmetic and
reported as excluded.  They are not booked, so ``CLBD`` does not contain them.

**Entry-level ``Amt`` only.**  Summing ``NtryDtls/TxDtls/Amt`` double-counts
every batched entry, because the entry amount already is their total.  The
``TxDtls`` amounts are read for the batch check and never added to the
identity.

**``PRCD`` may stand in for a missing ``OPBD``, and says so.**  The previous
statement's closing booked balance is this one's opening only if no production
gap separates them, which is a question for intake and cannot
be answered from inside one file.  The substitution is therefore recorded on
:attr:`Camt053BalanceIdentity.opening_substituted` rather than performed silently.

**``RvslInd`` is recorded; ``CdtDbtInd`` stays authoritative.**  Implementations
differ on whether a reversal's indicator describes the reversal or the entry it
reverses.  Guessing would flip a subset of rows invisibly.  Taking the
indicator at face value means that a document written under the other reading
fails its own identity and demotes to p3, which is a reviewable outcome rather
than a silent one.

**Anything that is not a conformant camt.053 raises.**  A missing mandatory
element, an amount outside the XSD decimal lexical space, a currency that
disagrees with the statement's, a DTD, an entity reference: these are not
unbalanced documents, they are documents this module cannot claim to have read,
and returning a proof class for them would be the error the taxonomy exists to
prevent.

Reading hostile XML
-------------------

Every document here arrives from outside — often from the party being
investigated.  The parser is configured against the standard attacks and the
configuration is asserted in the tests rather than trusted:

* ``resolve_entities=False`` leaves entity references unexpanded, so an
  external reference cannot read a local file.  lxml then represents them as
  entity nodes in the tree, which :func:`_reject_hostile_nodes` refuses
  outright, because a conformant camt.053 has no use for one.
* ``no_network=True`` refuses to fetch anything.
* ``load_dtd=False`` and ``dtd_validation=False``, plus an explicit rejection
  of a document that carries a doctype at all.  ISO 20022 is defined by XSD;
  a camt.053 with a DTD is either malformed or hostile, and it is unnecessary
  to decide which in order to refuse it.
* ``huge_tree=False`` keeps lxml's entity-amplification and depth limits in
  force, which is what stops the billion-laughs expansion.
* ``recover=False``, so a truncated document is an error rather than a
  partial statement — a silently truncated ledger is the worst possible
  output of a tool whose purpose is establishing that nothing is missing.

``defusedxml`` would also serve, and is deliberately not used: it is not in
``backend/requirements.txt``, so importing it would work in development and
fail on deployment.  ``lxml`` is declared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional, Sequence

from lxml import etree

from postgres.models.enums import (
    LocatorKind,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.locators import Locator
from services.financial.money import Money, MoneyError, get_currency, sum_money
from services.financial.proof_class import ProofClass, SourceShape, assign_proof_class


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class Camt053Error(Exception):
    """Base for every refusal in this module."""


class Camt053MalformedDocumentError(Camt053Error):
    """The bytes are not well-formed XML, or carry constructs a camt may not."""


class NotACamt053Error(Camt053Error):
    """Well-formed XML that is not a bank-to-customer statement message."""


class Camt053MissingElementError(Camt053Error):
    """A element the specification makes mandatory is absent."""


class Camt053AmountError(Camt053Error):
    """A figure is not a well-formed, exactly representable monetary amount."""


class Camt053StatementCurrencyError(Camt053Error):
    """A figure inside a statement disagrees with the statement's currency.

    Raised rather than reported as a discrepancy.  A camt.053 statement covers
    one account in one currency; a mixed-currency statement is not a statement
    whose totals fail to close, it is a document whose structure this module
    does not understand, and summing across it would produce a figure with no
    meaning at all.
    """


# ---------------------------------------------------------------------------
# Reading hostile XML
# ---------------------------------------------------------------------------

#: Hard ceiling on input size.  A camt.053 for a busy corporate account runs to
#: a few megabytes; anything past this is not a statement and reading it would
#: only be a way to spend memory on someone else's instruction.
CAMT053_MAX_DOCUMENT_BYTES: int = 64 * 1024 * 1024


def _hardened_parser() -> etree.XMLParser:
    """The only parser configuration this module uses.  See the module docstring."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=False,
        collect_ids=False,
    )


def _reject_hostile_nodes(root: etree._Element) -> None:
    """Refuse a tree carrying a doctype or an entity reference.

    Both are already defanged by the parser configuration — the entity is left
    unexpanded rather than resolved, so no file is read and no network call is
    made — but neither belongs in a conformant camt.053, and leaving an
    unexpanded entity in the tree would mean a figure could arrive as the
    literal text ``&x;`` and fail amount parsing with a confusing message
    instead of a true one.
    """
    doctype = root.getroottree().docinfo.doctype
    if doctype:
        raise Camt053MalformedDocumentError(
            "the document carries a document type declaration "
            f"({doctype!r}); ISO 20022 messages are defined by XML Schema and "
            "a camt.053 has no legitimate use for a DTD"
        )
    for node in root.iter():
        if node.tag is etree.Entity:
            raise Camt053MalformedDocumentError(
                f"the document references entity {node.text!r}; entity "
                "references are not expanded here and a camt.053 does not use "
                "them"
            )


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------

#: The XSD ``decimal`` lexical space, and nothing else.  ``Decimal`` on its own
#: is far more permissive: it accepts ``NaN``, ``Infinity`` and ``1E+2``, none
#: of which is a valid XSD decimal.  ``Money.from_decimal`` catches the first
#: two, but ``1E+2`` would pass as 100 — a figure this module would then report
#: as read exactly from a document that is not conformant.
_XSD_DECIMAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")

#: ISO 20022 codes are upper-case alphanumeric.  Matched loosely because the
#: value is recorded rather than interpreted, except where a specific code is
#: compared, and those comparisons are exact.
_BOOKED_STATUS = "BOOK"

#: Balance type codes this module gives meaning to.  Others are parsed and kept.
CAMT053_BALANCE_OPENING_BOOKED = "OPBD"
CAMT053_BALANCE_CLOSING_BOOKED = "CLBD"
CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED = "PRCD"

#: The camt.053 message root, whatever the version or the envelope around it.
_STATEMENT_MESSAGE = "BkToCstmrStmt"

#: ``Stmt/CpyDplctInd`` values.  ``CODU`` is a copy of a message that is also a
#: duplicate, ``COPY`` a copy sent to a party other than the original
#: recipient, ``DUPL`` a re-send of a message already delivered.
CAMT053_COPY_DUPLICATE_CODU = "CODU"
CAMT053_COPY_DUPLICATE_COPY = "COPY"
CAMT053_COPY_DUPLICATE_DUPL = "DUPL"

#: The two indicator values that say this statement's entries have been stated
#: before.  ``COPY`` is deliberately absent: a copy is the same message
#: delivered to an additional party, so it asserts money that moved, once.  A
#: duplicate asserts money that some earlier message already asserted, and
#: admitting both would count it twice.
CAMT053_RESTATING_INDICATORS: frozenset[str] = frozenset(
    {CAMT053_COPY_DUPLICATE_CODU, CAMT053_COPY_DUPLICATE_DUPL}
)

#: Every camt.053 entry is a row in a feed, not a rectangle on a page.  Stated
#: once here so that no caller has to decide, and so that the absence of a
#: click-through target reads as a property of the format rather than a defect
#: in a reader (see :class:`~postgres.models.enums.LocatorKind`).
CAMT053_LOCATOR: Locator = Locator(kind=LocatorKind.not_positional)


def _localname(element: etree._Element) -> str:
    """The tag without its namespace.

    Matching on local names is deliberate.  camt.053 ships as
    ``camt.053.001.02`` through ``.001.08``, each with its own namespace URI,
    and a document may arrive wrapped in a business envelope carrying others
    again.  Pinning the namespace would make the parser reject valid files for
    the version they were written in, which is not a property worth having.
    The element *names* are stable across those versions wherever this module
    reads them; where they are not — ``Sts``, below — the difference is handled
    explicitly.
    """
    return etree.QName(element).localname


def _children(parent: etree._Element, name: str) -> list[etree._Element]:
    """Direct children with the given local name, in document order."""
    return [
        child
        for child in parent
        if isinstance(child.tag, str) and _localname(child) == name
    ]


def _child(parent: etree._Element, name: str) -> Optional[etree._Element]:
    """The first direct child with the given local name, or ``None``."""
    found = _children(parent, name)
    return found[0] if found else None


def _path(parent: etree._Element, *names: str) -> Optional[etree._Element]:
    """Walk a chain of single children, stopping at the first absence."""
    node: Optional[etree._Element] = parent
    for name in names:
        if node is None:
            return None
        node = _child(node, name)
    return node


def _text(element: Optional[etree._Element]) -> Optional[str]:
    """Collapsed text of an element, or ``None`` when there is none.

    Whitespace is stripped because XSD collapses it for every simple type this
    module reads.  An element present but empty returns ``None`` rather than
    ``""``, since a present-and-empty element carries no more information than
    an absent one and treating them alike keeps every caller's check to one
    branch.
    """
    if element is None or element.text is None:
        return None
    stripped = element.text.strip()
    return stripped or None


def _required_text(parent: etree._Element, *names: str, context: str) -> str:
    """Text at a path, raising with the path spelled out when it is absent."""
    value = _text(_path(parent, *names))
    if value is None:
        raise Camt053MissingElementError(
            f"{context}: {'/'.join(names)} is mandatory and is absent or empty"
        )
    return value


def _decimal_from_xsd(text: str, *, context: str) -> Decimal:
    """Parse an XSD ``decimal``, refusing anything outside its lexical space."""
    if not _XSD_DECIMAL_RE.match(text):
        raise Camt053AmountError(
            f"{context}: {text!r} is not a well-formed XSD decimal; a camt.053 "
            "amount is a plain signed decimal with no exponent, grouping or "
            "special value"
        )
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex precludes this
        raise Camt053AmountError(f"{context}: {text!r} could not be read") from exc


def _money_from_amount(
    element: etree._Element,
    *,
    expected_currency: Optional[str],
    context: str,
) -> Money:
    """Read an ``Amt`` element: its text is the figure, its ``Ccy`` the currency.

    The currency is an attribute of the figure rather than of the document, so
    it is read from the figure every time.  A statement-level currency, once
    known, is enforced here rather than downstream, so that a mismatch is
    reported against the element that carries it instead of surfacing later as
    a :class:`~services.financial.money.CurrencyMismatchError` from inside a
    summation, where the offending element is no longer identifiable.
    """
    raw = _text(element)
    if raw is None:
        raise Camt053MissingElementError(f"{context}: the amount element is empty")
    currency = element.get("Ccy")
    if not currency:
        raise Camt053MissingElementError(
            f"{context}: the amount {raw!r} carries no Ccy attribute; a "
            "figure without a currency is not money"
        )
    currency = currency.strip()
    try:
        code = get_currency(currency).code
    except MoneyError as exc:
        raise Camt053AmountError(f"{context}: {exc}") from exc
    if expected_currency is not None and code != expected_currency:
        raise Camt053StatementCurrencyError(
            f"{context}: the figure is in {code} and the statement is in "
            f"{expected_currency}; a camt.053 statement covers one account in "
            "one currency"
        )
    value = _decimal_from_xsd(raw, context=context)
    try:
        return Money.from_decimal(value, code)
    except MoneyError as exc:
        raise Camt053AmountError(f"{context}: {exc}") from exc


def _direction(parent: etree._Element, *, context: str) -> TransactionDirection:
    """Read ``CdtDbtInd``.  The single source of direction in this format."""
    raw = _required_text(parent, "CdtDbtInd", context=context)
    if raw == "CRDT":
        return TransactionDirection.credit
    if raw == "DBIT":
        return TransactionDirection.debit
    raise Camt053MalformedDocumentError(
        f"{context}: CdtDbtInd is {raw!r}; the only values the specification "
        "permits are CRDT and DBIT, and direction is not inferable from "
        "anything else in the message"
    )


def _signed(amount: Money, direction: TransactionDirection) -> Money:
    """A balance as a signed quantity: debit means the account is overdrawn."""
    return amount if direction is TransactionDirection.credit else -amount


def _date_text(parent: Optional[etree._Element]) -> Optional[str]:
    """A camt date choice — ``Dt`` (a date) or ``DtTm`` (a timestamp) — as written.

    Kept as the lexical string rather than converted to a ``date``.  A ``DtTm``
    carries an offset, and reducing it to a calendar day requires choosing a
    zone; the choice would be invisible and would move entries across a period
    boundary at the two ends of a statement, which is where a reconciliation is
    most likely to be contested.  The raw value is unambiguous and the choice
    belongs to whoever has the account's jurisdiction to hand.
    """
    if parent is None:
        return None
    return _text(_child(parent, "Dt")) or _text(_child(parent, "DtTm"))


def _status_code(entry: etree._Element) -> Optional[str]:
    """Entry status across message versions.

    ``Ntry/Sts`` holds a code directly up to camt.053.001.05 and becomes a
    choice of ``Cd`` or ``Prtry`` from .06 onward.  Both forms are read; a
    proprietary status is returned as written and will not compare equal to
    ``BOOK``, which is the conservative outcome — an entry whose booked-ness is
    stated in a private vocabulary is not one to feed into a booked identity.
    """
    node = _child(entry, "Sts")
    if node is None:
        return None
    direct = _text(node)
    if direct is not None:
        return direct
    return _text(_child(node, "Cd")) or _text(_child(node, "Prtry"))


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Camt053Balance:
    """One ``Bal`` block: a typed balance at a stated moment.

    ``amount`` is the magnitude exactly as printed and ``direction`` is its
    ``CdtDbtInd``; :attr:`signed` combines them.  The pair is kept rather than
    collapsed because ``DBIT`` on a balance means the account is overdrawn,
    which is a fact worth being able to read back out of the parse without
    inferring it from a minus sign.
    """

    code: str
    amount: Money
    direction: TransactionDirection
    date: Optional[str]
    is_proprietary: bool = False

    @property
    def signed(self) -> Money:
        return _signed(self.amount, self.direction)


@dataclass(frozen=True, slots=True)
class Camt053BatchTotals:
    """``NtryDtls/Btch``: what a batched entry says it contains."""

    number_of_transactions: Optional[int]
    total_amount: Optional[Money]
    payment_information_id: Optional[str]


@dataclass(frozen=True, slots=True)
class Camt053TransactionDetail:
    """One ``TxDtls`` inside an entry.

    Amounts here are read but never summed into the balance identity; the
    entry's own ``Amt`` is already their total and adding both would count a
    batched entry twice.  What these carry that the entry does not is the
    reference set a reconciliation joins on.
    """

    amount: Optional[Money]
    direction: Optional[TransactionDirection]
    end_to_end_id: Optional[str]
    instruction_id: Optional[str]
    transaction_id: Optional[str]
    mandate_id: Optional[str]
    remittance_information: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Camt053Entry:
    """One ``Ntry``: a movement the bank has recorded against the account.

    ``amount`` is an unsigned magnitude and ``direction`` carries the sign,
    matching the ledger's discipline
    (:class:`~postgres.models.enums.TransactionDirection`) rather than the
    document's.  They are the same discipline: camt states magnitude and
    direction separately too, which is why this format needs no convention
    inference at all.
    """

    amount: Money
    direction: TransactionDirection
    status: Optional[str]
    booking_date: Optional[str]
    value_date: Optional[str]
    entry_reference: Optional[str]
    account_servicer_reference: Optional[str]
    is_reversal: bool
    bank_transaction_code: Optional[str]
    additional_information: Optional[str]
    batch: Optional[Camt053BatchTotals]
    details: tuple[Camt053TransactionDetail, ...]
    index: int

    @property
    def is_booked(self) -> bool:
        """Whether this entry participates in the booked balance identity."""
        return self.status == _BOOKED_STATUS

    @property
    def signed(self) -> Money:
        return _signed(self.amount, self.direction)

    @property
    def locator(self) -> Locator:
        return CAMT053_LOCATOR


@dataclass(frozen=True, slots=True)
class Camt053TransactionsSummary:
    """``TxsSummry``: the statement's own count and totals of its entries."""

    total_entries: Optional[int]
    total_net_amount: Optional[Money]
    total_net_direction: Optional[TransactionDirection]
    credit_entries: Optional[int]
    credit_sum: Optional[Money]
    debit_entries: Optional[int]
    debit_sum: Optional[Money]


@dataclass(frozen=True, slots=True)
class Camt053Account:
    """Who the statement is about, to the extent the message says."""

    iban: Optional[str]
    other_id: Optional[str]
    other_scheme: Optional[str]
    currency: Optional[str]
    owner_name: Optional[str]
    servicer_bic: Optional[str]

    @property
    def identifier(self) -> Optional[str]:
        """The strongest account identifier present."""
        return self.iban or self.other_id


@dataclass(frozen=True, slots=True)
class Camt053BalanceIdentity:
    """Outcome of ``OPBD + ΣCredits − ΣDebits = CLBD`` over booked entries.

    ``delta`` is ``computed_closing - printed_closing``, the sign convention
    used across the package: positive means the entries produce more money than
    the statement says it ended with.
    """

    status: ReconciliationStatus
    opening: Optional[Money]
    opening_code: Optional[str]
    opening_substituted: bool
    printed_closing: Optional[Money]
    computed_closing: Optional[Money]
    delta: Optional[Money]
    booked_credits: Optional[Money]
    booked_debits: Optional[Money]
    booked_entry_count: int
    excluded_entry_count: int
    unavailable_reason: Optional[str]

    @property
    def is_balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced


@dataclass(frozen=True, slots=True)
class Camt053SummaryIdentity:
    """Outcome of checking ``TxsSummry`` against the entries actually present."""

    status: ReconciliationStatus
    credit_delta: Optional[Money]
    debit_delta: Optional[Money]
    net_delta: Optional[Money]
    count_delta: Optional[int]
    unavailable_reason: Optional[str]
    credit_count_delta: Optional[int] = None
    debit_count_delta: Optional[int] = None

    @property
    def is_balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced


@dataclass(frozen=True, slots=True)
class Camt053BatchIdentity:
    """Outcome of checking one entry's ``Btch`` block against its own contents."""

    status: ReconciliationStatus
    entry_index: int
    amount_delta: Optional[Money]
    count_delta: Optional[int]
    unavailable_reason: Optional[str]

    @property
    def is_balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced


def _weakest(statuses: Iterable[ReconciliationStatus]) -> ReconciliationStatus:
    """The least favourable outcome in a run of them.

    Order: ``unbalanced`` beats everything, then ``unavailable``, then
    ``not_attempted``, and ``balanced`` only when every check balanced.  A
    single failure anywhere therefore governs, which is what stops a document
    with one clean statement and one broken one from presenting as clean.
    """
    seen = list(statuses)
    if not seen:
        return ReconciliationStatus.not_attempted
    for candidate in (
        ReconciliationStatus.unbalanced,
        ReconciliationStatus.unavailable,
        ReconciliationStatus.not_attempted,
    ):
        if candidate in seen:
            return candidate
    return ReconciliationStatus.balanced


@dataclass(frozen=True, slots=True)
class Camt053Statement:
    """One ``Stmt``: a period on one account, with its entries and its checks."""

    identification: str
    currency: str
    account: Camt053Account
    creation_date_time: Optional[str]
    electronic_sequence_number: Optional[str]
    legal_sequence_number: Optional[str]
    period_from: Optional[str]
    period_to: Optional[str]
    balances: tuple[Camt053Balance, ...]
    entries: tuple[Camt053Entry, ...]
    summary: Optional[Camt053TransactionsSummary]
    balance_identity: Camt053BalanceIdentity
    summary_identity: Camt053SummaryIdentity
    batch_identities: tuple[Camt053BatchIdentity, ...]
    copy_duplicate_indicator: Optional[str] = None

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Reasons this statement must not auto-admit, whatever its arithmetic says.

        Kept out of the arithmetic for the reason
        :attr:`~services.financial.bai2.Bai2Group.admissibility_reservations`
        gives: a duplicate's totals are not merely sound, they are *identical*
        to the original's, because it is the same message. Folding the
        reservation into the reconciliation status would report an arithmetic
        failure that did not happen and send a reviewer hunting for a
        discrepancy in a file that has none. The statement adds up; the
        question is whether admitting it counts the same money twice.

        ``COPY`` draws no reservation. A copy is one message delivered to a
        second party — the same assertion, made once. Only ``DUPL`` and
        ``CODU`` say the entries beneath them have been stated before, and only
        those two put a total at risk of being doubled.
        """
        indicator = self.copy_duplicate_indicator
        if indicator is None or indicator not in CAMT053_RESTATING_INDICATORS:
            return ()
        return (
            f"statement {self.identification!r} carries CpyDplctInd "
            f"{indicator}; its entries have been stated in an earlier message, "
            "and admitting both would count the same money twice",
        )

    def balance(self, code: str) -> Optional[Camt053Balance]:
        """The first balance carrying a given ISO type code."""
        for item in self.balances:
            if item.code == code and not item.is_proprietary:
                return item
        return None

    @property
    def booked_entries(self) -> tuple[Camt053Entry, ...]:
        return tuple(entry for entry in self.entries if entry.is_booked)

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The balance identity, weakened by any corroboration that failed.

        The three checks are not peers and are not combined as though they
        were.  The balance identity is the statement's proof: ``CLBD`` is
        mandatory and its population is not in doubt, so whatever that check
        concluded is what the statement has established, and it governs
        unconditionally.

        ``TxsSummry`` and ``Btch`` are optional corroborations, and an optional
        corroboration can only ever weaken the outcome by *failing*.  It cannot
        weaken it by being absent, because nothing was claimed; nor by
        declining, because a decline is a statement about what this parser can
        interpret and not about the document's arithmetic.  Folding either into
        the roll-up would demote every camt.053 that simply omits the optional
        block — which is a great many real ones — and the format's whole
        advantage would be lost to files that are not defective in any way.

        A corroboration that ran and disagreed is a different matter entirely.
        If the entries close against the balances but contradict the file's own
        printed summary of those same entries, then one of the two readings is
        wrong and there is no ground for claiming P0 while it is unclear which.
        """
        failures = [
            check.status
            for check in (self.summary_identity, *self.batch_identities)
            if check.status is ReconciliationStatus.unbalanced
        ]
        return _weakest([self.balance_identity.status, *failures])


@dataclass(frozen=True, slots=True)
class Camt053Document:
    """A parsed camt.053 message: its group header and one or more statements."""

    message_identification: str
    creation_date_time: Optional[str]
    statements: tuple[Camt053Statement, ...]
    namespace: Optional[str]

    #: Fixed.  A camt.053 is a structured file whose format mandates control
    #: totals, which is the whole of what the shape asserts.
    source_shape: SourceShape = field(
        default=SourceShape.native_with_control_totals, init=False
    )

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The weakest outcome across every statement in the message."""
        return _weakest([stmt.reconciliation_status for stmt in self.statements])

    @property
    def proof_class(self) -> ProofClass:
        """The class this message earns, computed rather than asserted.

        Delegated to :func:`~services.financial.proof_class.assign_proof_class`
        so that the rule lives in one place: this module supplies the shape and
        the outcome and has no vote on what they add up to.  In practice the
        answer is p0 when every check balanced and p3 otherwise, which is the
        asymmetry the classes require.

        The one thing decided here is the reservation, on the reasoning
        :attr:`~services.financial.bai2.Bai2File.proof_class` sets out.  A
        duplicate message's arithmetic is not merely sound but identical to the
        original's, so ``assign_proof_class`` would rightly call it p0 on the
        evidence it is given.  But p0 auto-admits with no human act at
        all, and auto-admitting a re-send alongside the message it repeats
        double-counts every figure in it.  The promotion is withheld and the
        message lands at p3, where a person decides which copy is the exhibit.
        """
        earned = assign_proof_class(self.source_shape, self.reconciliation_status)
        if earned is ProofClass.p0 and self.admissibility_reservations:
            return ProofClass.p3
        return earned

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Every statement's reservations, gathered so a caller reads one list.

        Present on all four native parsers for the reason
        :attr:`~services.financial.mt940.Mt940File.admissibility_reservations`
        states: the caller that wires Layer 0 into extraction reads
        this from every one of them, and a caller that has to remember which
        parsers have reservations is a caller that will eventually forget.
        """
        return tuple(
            reason
            for statement in self.statements
            for reason in statement.admissibility_reservations
        )

    @property
    def entries(self) -> tuple[Camt053Entry, ...]:
        """Every entry in the message, in document order."""
        return tuple(
            entry for statement in self.statements for entry in statement.entries
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_int(text: Optional[str], *, context: str) -> Optional[int]:
    """Read a count.  Absent stays absent; malformed raises."""
    if text is None:
        return None
    if not re.match(r"^\d+$", text):
        raise Camt053MalformedDocumentError(
            f"{context}: {text!r} is not a non-negative integer"
        )
    return int(text)


def _parse_account(node: Optional[etree._Element]) -> Camt053Account:
    if node is None:
        return Camt053Account(None, None, None, None, None, None)
    other = _path(node, "Id", "Othr")
    servicer = _path(node, "Svcr", "FinInstnId")
    bic = None
    if servicer is not None:
        bic = _text(_child(servicer, "BICFI")) or _text(_child(servicer, "BIC"))
    return Camt053Account(
        iban=_text(_path(node, "Id", "IBAN")),
        other_id=_text(_child(other, "Id")) if other is not None else None,
        other_scheme=(
            _text(_path(other, "SchmeNm", "Cd")) or _text(_path(other, "SchmeNm", "Prtry"))
            if other is not None
            else None
        ),
        currency=_text(_child(node, "Ccy")),
        owner_name=_text(_path(node, "Ownr", "Nm")),
        servicer_bic=bic,
    )


def _resolve_currency(statement: etree._Element, account: Camt053Account, *, context: str) -> str:
    """Fix the statement's currency, from the account or from its balances.

    ``Acct/Ccy`` is optional, and a statement that omits it still states its
    currency on every ``Amt`` it carries.  Taking it from the balances is
    therefore sound, but only if they agree: two balances in different
    currencies mean this is not one account's statement, and choosing the first
    would produce totals that silently mix them.
    """
    if account.currency:
        try:
            return get_currency(account.currency).code
        except MoneyError as exc:
            raise Camt053AmountError(f"{context}: Acct/Ccy is unusable: {exc}") from exc

    found: list[str] = []
    for balance in _children(statement, "Bal"):
        amount = _child(balance, "Amt")
        if amount is None:
            continue
        code = (amount.get("Ccy") or "").strip()
        if code and code not in found:
            found.append(code)
    if not found:
        raise Camt053MissingElementError(
            f"{context}: the statement declares no Acct/Ccy and carries no "
            "balance from which a currency could be read"
        )
    if len(found) > 1:
        raise Camt053StatementCurrencyError(
            f"{context}: the balances are stated in {', '.join(sorted(found))}; "
            "a camt.053 statement covers one account in one currency and this "
            "message cannot be read as one"
        )
    try:
        return get_currency(found[0]).code
    except MoneyError as exc:
        raise Camt053AmountError(f"{context}: {exc}") from exc


def _parse_balance(
    node: etree._Element, *, currency: str, context: str
) -> Camt053Balance:
    type_node = _path(node, "Tp", "CdOrPrtry")
    if type_node is None:
        raise Camt053MissingElementError(f"{context}: Bal/Tp/CdOrPrtry is mandatory")
    code = _text(_child(type_node, "Cd"))
    proprietary = False
    if code is None:
        code = _text(_child(type_node, "Prtry"))
        proprietary = True
    if code is None:
        raise Camt053MissingElementError(
            f"{context}: Bal/Tp/CdOrPrtry carries neither Cd nor Prtry"
        )
    amount_node = _child(node, "Amt")
    if amount_node is None:
        raise Camt053MissingElementError(f"{context}: Bal/Amt is mandatory")
    return Camt053Balance(
        code=code,
        amount=_money_from_amount(
            amount_node, expected_currency=currency, context=f"{context} Bal/Amt"
        ),
        direction=_direction(node, context=f"{context} Bal"),
        date=_date_text(_child(node, "Dt")),
        is_proprietary=proprietary,
    )


def _parse_detail(
    node: etree._Element, *, currency: str, context: str
) -> Camt053TransactionDetail:
    refs = _child(node, "Refs")
    # Written as an explicit ``is None`` test rather than ``a or b``.  An lxml
    # element with no children is falsy, so ``or`` silently discards exactly the
    # leaf elements this module reads -- an ``<Amt>`` holding a figure and
    # nothing else -- and falls through to the alternative, which is usually
    # absent.  The amount then arrives as ``None`` from a document that stated
    # it plainly.
    amount_node = _child(node, "Amt")
    if amount_node is None:
        amount_node = _path(node, "AmtDtls", "TxAmt", "Amt")
    direction = None
    if _child(node, "CdtDbtInd") is not None:
        direction = _direction(node, context=context)
    remittance: list[str] = []
    rmt = _child(node, "RmtInf")
    if rmt is not None:
        for line in _children(rmt, "Ustrd"):
            value = _text(line)
            if value:
                remittance.append(value)
    return Camt053TransactionDetail(
        amount=(
            _money_from_amount(
                amount_node, expected_currency=currency, context=f"{context} Amt"
            )
            if amount_node is not None
            else None
        ),
        direction=direction,
        end_to_end_id=_text(_child(refs, "EndToEndId")) if refs is not None else None,
        instruction_id=_text(_child(refs, "InstrId")) if refs is not None else None,
        transaction_id=_text(_child(refs, "TxId")) if refs is not None else None,
        mandate_id=_text(_child(refs, "MndtId")) if refs is not None else None,
        remittance_information=tuple(remittance),
    )


def _parse_batch(
    node: etree._Element, *, currency: str, context: str
) -> Optional[Camt053BatchTotals]:
    batch = _child(node, "Btch")
    if batch is None:
        return None
    total_node = _child(batch, "TtlAmt")
    return Camt053BatchTotals(
        number_of_transactions=_parse_int(
            _text(_child(batch, "NbOfTxs")), context=f"{context} Btch/NbOfTxs"
        ),
        total_amount=(
            _money_from_amount(
                total_node,
                expected_currency=currency,
                context=f"{context} Btch/TtlAmt",
            )
            if total_node is not None
            else None
        ),
        payment_information_id=_text(_child(batch, "PmtInfId")),
    )


def _parse_entry(
    node: etree._Element, *, currency: str, index: int, context: str
) -> Camt053Entry:
    amount_node = _child(node, "Amt")
    if amount_node is None:
        raise Camt053MissingElementError(f"{context}: Ntry/Amt is mandatory")
    details_node = _child(node, "NtryDtls")
    details: list[Camt053TransactionDetail] = []
    batch: Optional[Camt053BatchTotals] = None
    if details_node is not None:
        batch = _parse_batch(details_node, currency=currency, context=context)
        for position, detail in enumerate(_children(details_node, "TxDtls")):
            details.append(
                _parse_detail(
                    detail,
                    currency=currency,
                    context=f"{context} TxDtls[{position}]",
                )
            )
    code_node = _path(node, "BkTxCd", "Domn")
    bank_code = None
    if code_node is not None:
        family = _child(code_node, "Fmly")
        bank_code = "/".join(
            part
            for part in (
                _text(_child(code_node, "Cd")),
                _text(_child(family, "Cd")) if family is not None else None,
                _text(_child(family, "SubFmlyCd")) if family is not None else None,
            )
            if part
        ) or None
    if bank_code is None:
        bank_code = _text(_path(node, "BkTxCd", "Prtry", "Cd"))

    return Camt053Entry(
        amount=_money_from_amount(
            amount_node, expected_currency=currency, context=f"{context} Ntry/Amt"
        ),
        direction=_direction(node, context=f"{context} Ntry"),
        status=_status_code(node),
        booking_date=_date_text(_child(node, "BookgDt")),
        value_date=_date_text(_child(node, "ValDt")),
        entry_reference=_text(_child(node, "NtryRef")),
        account_servicer_reference=_text(_child(node, "AcctSvcrRef")),
        is_reversal=(_text(_child(node, "RvslInd")) or "").lower() == "true",
        bank_transaction_code=bank_code,
        additional_information=_text(_child(node, "AddtlNtryInf")),
        batch=batch,
        details=tuple(details),
        index=index,
    )


def _parse_summary(
    node: Optional[etree._Element], *, currency: str, context: str
) -> Optional[Camt053TransactionsSummary]:
    if node is None:
        return None

    def block(name: str) -> tuple[Optional[int], Optional[Money]]:
        child = _child(node, name)
        if child is None:
            return None, None
        sum_node = _child(child, "Sum")
        total = None
        if sum_node is not None:
            raw = _text(sum_node)
            if raw is not None:
                value = _decimal_from_xsd(raw, context=f"{context} {name}/Sum")
                try:
                    total = Money.from_decimal(value, currency)
                except MoneyError as exc:
                    raise Camt053AmountError(f"{context} {name}/Sum: {exc}") from exc
        return (
            _parse_int(
                _text(_child(child, "NbOfNtries")),
                context=f"{context} {name}/NbOfNtries",
            ),
            total,
        )

    total_entries, _ = block("TtlNtries")
    credit_entries, credit_sum = block("TtlCdtNtries")
    debit_entries, debit_sum = block("TtlDbtNtries")

    net_node = _child(node, "TtlNtries")
    net_amount = None
    net_direction = None
    if net_node is not None:
        net_raw = _text(_child(net_node, "TtlNetNtryAmt"))
        if net_raw is not None:
            value = _decimal_from_xsd(
                net_raw, context=f"{context} TtlNtries/TtlNetNtryAmt"
            )
            try:
                net_amount = Money.from_decimal(value, currency)
            except MoneyError as exc:
                raise Camt053AmountError(
                    f"{context} TtlNtries/TtlNetNtryAmt: {exc}"
                ) from exc
            if _child(net_node, "CdtDbtInd") is not None:
                net_direction = _direction(
                    net_node, context=f"{context} TtlNtries"
                )

    return Camt053TransactionsSummary(
        total_entries=total_entries,
        total_net_amount=net_amount,
        total_net_direction=net_direction,
        credit_entries=credit_entries,
        credit_sum=credit_sum,
        debit_entries=debit_entries,
        debit_sum=debit_sum,
    )


# ---------------------------------------------------------------------------
# The three checks
# ---------------------------------------------------------------------------


def _sum_direction(
    entries: Sequence[Camt053Entry], direction: TransactionDirection, currency: str
) -> Money:
    return sum_money(
        (entry.amount for entry in entries if entry.direction is direction), currency
    )


def _check_balances(
    balances: Sequence[Camt053Balance], entries: Sequence[Camt053Entry], currency: str
) -> Camt053BalanceIdentity:
    """``OPBD + ΣCredits − ΣDebits = CLBD``, over booked entries only.

    Declines rather than assumes when an endpoint balance is absent, for the
    reason :func:`~services.financial.statement_totals.check_header_identity`
    gives: substituting zero for a missing opening manufactures a delta exactly
    equal to the real opening balance, which reads as a large unexplained
    discrepancy and sends a reviewer hunting for fraud in a document whose only
    defect is an incomplete balance block.
    """
    booked = [entry for entry in entries if entry.is_booked]
    excluded = len(entries) - len(booked)

    def find(code: str) -> Optional[Camt053Balance]:
        for item in balances:
            if item.code == code and not item.is_proprietary:
                return item
        return None

    opening_balance = find(CAMT053_BALANCE_OPENING_BOOKED)
    opening_code = CAMT053_BALANCE_OPENING_BOOKED
    substituted = False
    if opening_balance is None:
        opening_balance = find(CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED)
        if opening_balance is not None:
            opening_code = CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED
            substituted = True
    closing_balance = find(CAMT053_BALANCE_CLOSING_BOOKED)

    credits = _sum_direction(booked, TransactionDirection.credit, currency)
    debits = _sum_direction(booked, TransactionDirection.debit, currency)

    if opening_balance is None or closing_balance is None:
        missing = [
            name
            for name, present in (
                (f"opening ({CAMT053_BALANCE_OPENING_BOOKED} or "
                 f"{CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED})", opening_balance),
                (f"closing ({CAMT053_BALANCE_CLOSING_BOOKED})", closing_balance),
            )
            if present is None
        ]
        return Camt053BalanceIdentity(
            status=ReconciliationStatus.unavailable,
            opening=opening_balance.signed if opening_balance else None,
            opening_code=opening_code if opening_balance else None,
            opening_substituted=substituted,
            printed_closing=closing_balance.signed if closing_balance else None,
            computed_closing=None,
            delta=None,
            booked_credits=credits,
            booked_debits=debits,
            booked_entry_count=len(booked),
            excluded_entry_count=excluded,
            unavailable_reason=(
                f"the statement carries no {' and no '.join(missing)} balance, "
                "and substituting zero would manufacture a delta equal to the "
                "real figure"
            ),
        )

    opening = opening_balance.signed
    printed = closing_balance.signed
    computed = opening + credits - debits
    delta = computed - printed

    return Camt053BalanceIdentity(
        status=(
            ReconciliationStatus.balanced
            if delta.is_zero
            else ReconciliationStatus.unbalanced
        ),
        opening=opening,
        opening_code=opening_code,
        opening_substituted=substituted,
        printed_closing=printed,
        computed_closing=computed,
        delta=delta,
        booked_credits=credits,
        booked_debits=debits,
        booked_entry_count=len(booked),
        excluded_entry_count=excluded,
        unavailable_reason=None,
    )


def _check_summary(
    summary: Optional[Camt053TransactionsSummary],
    entries: Sequence[Camt053Entry],
    currency: str,
) -> Camt053SummaryIdentity:
    """``TxsSummry`` against the entries present, when the population is certain.

    ``TxsSummry`` is optional, so its absence is ``not_attempted`` rather than
    a failure: nothing was claimed and nothing is contradicted.

    When entries carry a status other than ``BOOK``, the check is declined.
    The specification names the block "total entries" without saying whether a
    pending entry is one, and the two readings give different totals.  Trying
    both and reporting whichever closed is the failure mode
    ``statement_totals`` was built to avoid — there is nearly always some
    population that closes, so such a check would pass on documents that are
    genuinely wrong.  Declining says what is true: the block cannot be
    interpreted without a rule the document does not supply.  The balance
    identity is unaffected, because ``OPBD`` and ``CLBD`` are booked balances
    by definition and their population is not in doubt.
    """
    if summary is None:
        return Camt053SummaryIdentity(
            status=ReconciliationStatus.not_attempted,
            credit_delta=None,
            debit_delta=None,
            net_delta=None,
            count_delta=None,
            unavailable_reason=None,
        )

    if any(not entry.is_booked for entry in entries):
        return Camt053SummaryIdentity(
            status=ReconciliationStatus.unavailable,
            credit_delta=None,
            debit_delta=None,
            net_delta=None,
            count_delta=None,
            unavailable_reason=(
                "the statement mixes booked and unbooked entries, and the "
                "specification does not say which of them TxsSummry counts; "
                "checking under either reading would be choosing one"
            ),
        )

    credits = _sum_direction(entries, TransactionDirection.credit, currency)
    debits = _sum_direction(entries, TransactionDirection.debit, currency)

    credit_delta = (
        credits - summary.credit_sum if summary.credit_sum is not None else None
    )
    debit_delta = (
        debits - summary.debit_sum if summary.debit_sum is not None else None
    )
    count_delta = (
        len(entries) - summary.total_entries
        if summary.total_entries is not None
        else None
    )

    credit_count_delta = (sum(entry.direction == TransactionDirection.credit for entry in entries) - summary.credit_entries
                          if summary.credit_entries is not None else None)
    debit_count_delta = (sum(entry.direction == TransactionDirection.debit for entry in entries) - summary.debit_entries
                         if summary.debit_entries is not None else None)
    net_delta = None
    if summary.total_net_amount is not None:
        stated = summary.total_net_amount
        if summary.total_net_direction is not None:
            stated = _signed(stated, summary.total_net_direction)
        net_delta = (credits - debits) - stated

    checked = [
        value
        for value in (credit_delta, debit_delta, net_delta)
        if value is not None
    ]
    counts = [value for value in (count_delta, credit_count_delta, debit_count_delta) if value is not None]
    if not checked and not counts:
        return Camt053SummaryIdentity(
            status=ReconciliationStatus.unavailable,
            credit_delta=None,
            debit_delta=None,
            net_delta=None,
            count_delta=None,
            unavailable_reason=(
                "TxsSummry is present but states neither a total nor a count, "
                "so there is nothing in it to check"
            ),
        )

    agrees = all(value.is_zero for value in checked) and all(value == 0 for value in counts)
    return Camt053SummaryIdentity(
        status=(
            ReconciliationStatus.balanced
            if agrees
            else ReconciliationStatus.unbalanced
        ),
        credit_delta=credit_delta,
        debit_delta=debit_delta,
        net_delta=net_delta,
        count_delta=count_delta,
        credit_count_delta=credit_count_delta,
        debit_count_delta=debit_count_delta,
        unavailable_reason=None,
    )


def _check_batches(entries: Sequence[Camt053Entry]) -> tuple[Camt053BatchIdentity, ...]:
    """Each batched entry's ``Btch`` block against its own amount and details.

    A third guarantee, free where it is stated: a batch's ``TtlAmt`` is the
    entry's amount by definition, and its ``NbOfTxs`` is the count of
    ``TxDtls`` the entry carries — but only when the entry carries them at all.
    Many institutions send a batch total with no per-transaction detail, and a
    count check against zero details would report every such entry as broken.
    """
    outcomes: list[Camt053BatchIdentity] = []
    for entry in entries:
        batch = entry.batch
        if batch is None:
            continue
        amount_delta = (
            batch.total_amount - entry.amount
            if batch.total_amount is not None
            else None
        )
        count_delta = (
            len(entry.details) - batch.number_of_transactions
            if batch.number_of_transactions is not None and entry.details
            else None
        )
        if amount_delta is None and count_delta is None:
            outcomes.append(
                Camt053BatchIdentity(
                    status=ReconciliationStatus.unavailable,
                    entry_index=entry.index,
                    amount_delta=None,
                    count_delta=None,
                    unavailable_reason=(
                        "the batch block states no total amount, and no "
                        "transaction detail is present to count"
                    ),
                )
            )
            continue
        agrees = (amount_delta is None or amount_delta.is_zero) and (
            count_delta is None or count_delta == 0
        )
        outcomes.append(
            Camt053BatchIdentity(
                status=(
                    ReconciliationStatus.balanced
                    if agrees
                    else ReconciliationStatus.unbalanced
                ),
                entry_index=entry.index,
                amount_delta=amount_delta,
                count_delta=count_delta,
                unavailable_reason=None,
            )
        )
    return tuple(outcomes)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_statement(node: etree._Element, *, position: int) -> Camt053Statement:
    context = f"Stmt[{position}]"
    identification = _required_text(node, "Id", context=context)
    context = f"Stmt[{position}] {identification!r}"
    account = _parse_account(_child(node, "Acct"))
    currency = _resolve_currency(node, account, context=context)

    balances = tuple(
        _parse_balance(item, currency=currency, context=f"{context} Bal[{index}]")
        for index, item in enumerate(_children(node, "Bal"))
    )
    entries = tuple(
        _parse_entry(
            item, currency=currency, index=index, context=f"{context} Ntry[{index}]"
        )
        for index, item in enumerate(_children(node, "Ntry"))
    )
    summary = _parse_summary(
        _child(node, "TxsSummry"), currency=currency, context=f"{context} TxsSummry"
    )
    period = _child(node, "FrToDt")

    return Camt053Statement(
        identification=identification,
        currency=currency,
        account=account,
        creation_date_time=_text(_child(node, "CreDtTm")),
        electronic_sequence_number=_text(_child(node, "ElctrncSeqNb")),
        legal_sequence_number=_text(_child(node, "LglSeqNb")),
        period_from=_text(_child(period, "FrDtTm")) if period is not None else None,
        period_to=_text(_child(period, "ToDtTm")) if period is not None else None,
        balances=balances,
        entries=entries,
        summary=summary,
        balance_identity=_check_balances(balances, entries, currency),
        summary_identity=_check_summary(summary, entries, currency),
        batch_identities=_check_batches(entries),
        copy_duplicate_indicator=_text(_child(node, "CpyDplctInd")),
    )


def _find_message(root: etree._Element) -> etree._Element:
    """Locate ``BkToCstmrStmt``, wherever the envelope has put it.

    A camt.053 may arrive bare under ``Document``, or wrapped in a business
    message envelope alongside an ``AppHdr``, or inside a vendor's own
    container.  Searching for the message element by local name reads all
    three, and finding exactly one is required: a file carrying two statement
    messages is a batch, and treating it as one message would merge two banks'
    statements into a single set of totals.
    """
    found = [
        node
        for node in root.iter()
        if isinstance(node.tag, str) and _localname(node) == _STATEMENT_MESSAGE
    ]
    if not found:
        raise NotACamt053Error(
            f"no {_STATEMENT_MESSAGE} element is present; the document root is "
            f"{_localname(root)!r}, which is not a bank-to-customer statement "
            "message"
        )
    if len(found) > 1:
        raise NotACamt053Error(
            f"the document carries {len(found)} {_STATEMENT_MESSAGE} messages; "
            "each is a separate statement message and they must be parsed "
            "separately rather than merged into one set of totals"
        )
    return found[0]


def parse_camt053(data: bytes) -> Camt053Document:
    """Parse a camt.053 message.  Pure: no database, no network, no clock.

    ``data`` is bytes, not text, and deliberately so.  An XML document declares
    its own encoding inside itself, so decoding it before parsing means
    guessing the thing the file states — and a wrong guess corrupts exactly the
    non-ASCII characters that appear in payee names, which is where a forensic
    reader most needs the bytes to survive intact.

    :raises Camt053MalformedDocumentError: not well-formed, or carrying a DTD or an
        entity reference.
    :raises NotACamt053Error: well-formed XML that is not this message type.
    :raises Camt053MissingElementError: a mandatory element is absent.
    :raises Camt053AmountError: a figure is not exactly representable as money.
    :raises Camt053StatementCurrencyError: a statement mixes currencies.
    """
    if isinstance(data, str):
        raise Camt053MalformedDocumentError(
            "parse_camt053 takes bytes, not str; an XML document declares its "
            "own encoding, so decoding it beforehand means guessing what the "
            "file already says"
        )
    if not isinstance(data, (bytes, bytearray)):
        raise Camt053MalformedDocumentError(
            f"parse_camt053 takes bytes, got {type(data).__name__}"
        )
    if not data.strip():
        raise Camt053MalformedDocumentError("the document is empty")
    if len(data) > CAMT053_MAX_DOCUMENT_BYTES:
        raise Camt053MalformedDocumentError(
            f"the document is {len(data)} bytes, over the "
            f"{CAMT053_MAX_DOCUMENT_BYTES}-byte ceiling for a statement message"
        )

    try:
        root = etree.fromstring(bytes(data), _hardened_parser())
    except etree.XMLSyntaxError as exc:
        raise Camt053MalformedDocumentError(f"the document is not well-formed XML: {exc}") from exc

    _reject_hostile_nodes(root)
    message = _find_message(root)

    header = _child(message, "GrpHdr")
    if header is None:
        raise Camt053MissingElementError(
            f"{_STATEMENT_MESSAGE}/GrpHdr is mandatory and is absent"
        )
    message_id = _required_text(header, "MsgId", context="GrpHdr")

    statement_nodes = _children(message, "Stmt")
    if not statement_nodes:
        raise Camt053MissingElementError(
            f"{_STATEMENT_MESSAGE} carries no Stmt; the specification requires "
            "at least one, and a message with none states nothing about any "
            "account"
        )

    statements = tuple(
        _parse_statement(node, position=index)
        for index, node in enumerate(statement_nodes)
    )

    qname = etree.QName(message)
    return Camt053Document(
        message_identification=message_id,
        creation_date_time=_text(_child(header, "CreDtTm")),
        statements=statements,
        namespace=qname.namespace,
    )
