"""One payment, seen from more than one vantage point, joined at a stated strength.

The word for this is normally *reconciliation*.  This package already spends
that word on
:mod:`services.financial.reconcile`, which checks that one period's arithmetic
closes, and the two answer questions that must not be confused.  The identity
asks *do these rows add up*.  This module asks *are these two rows the same
payment*.  A period can balance perfectly while the same wire is counted twice
across two accounts, and a set of rows can be joined flawlessly while every
period is short a transaction.  Neither check implies the other, so neither
name should be readable as the other.

What is being joined
--------------------

A payment leaves a trail in more than one place.  The payer's statement shows
a debit.  The payer's ACH file shows the same debit again, from a different
system, days earlier.  The payee's statement shows a credit.  Three documents,
three rows, and *one* payment -- but not three redundant rows, and this is the
distinction the module is built around.

The payer's two rows are the same movement of the payer's money.  Adding them
together counts the payment twice.  They are :attr:`~postgres.models.enums.
LinkRelation.same_side`.

The payer's debit and the payee's credit are *different* movements in
*different* accounts, and both are real.  Each belongs in its own account's
totals; each is needed for its own period's balance identity to close.
Merging them, or dropping either, breaks :mod:`services.financial.reconcile`
for two periods at once.  They are
:attr:`~postgres.models.enums.LinkRelation.counterparty`, and the link exists
so that a tracing engine can walk from one account to the other -- not so that
anything can be collapsed.

Getting these two backwards is the failure mode with no downstream detector.
Treating a counterparty pair as redundant silently deletes one leg of every
transfer; treating a same-side pair as two payments silently doubles a total.
In both cases every period still reconciles, because the identity is computed
per account and neither error moves a single account's arithmetic.

Nothing here collapses anything
-------------------------------

*A reconciled transaction retains all its sources.*  This module
writes no status, supersedes no row and deletes nothing.  It emits claims about
pairs and groups of rows, and the rows stay exactly as they were.  That is a
deliberate contrast with :mod:`services.financial.duplicates`, which does
supersede -- because a second copy of one document is not additional evidence,
whereas a second *sighting* of one payment very much is.  Two independent
sources agreeing is the strongest thing this corpus can say about a figure, and
it would be destroyed by merging them into one row.

The tiers
---------

:class:`~postgres.models.enums.JoinTier` is recorded on every link.

Tier 0, *exact identifier*, is equality of an identifier inside a scope both
rows share.  Certain, and only as certain as the scope.  See
:class:`ScopedReference`.

Tier 1, *deterministic composite*, is agreement on currency, amount, direction
and date, the last within a stated tolerance.  Reproducible from the ledger
alone, by anybody, which is what makes it assertable without a person.

Tier 2, *probabilistic*, adds a fuzzy counterparty name and widens the date
window.  It is a proposal, and nothing may be merged on it automatically.
Nothing in this module merges on anything, so what tier 2 really marks is a
link that must not be treated as established.

The tiers are **not nested**, and this is the difference from
:class:`~postgres.models.enums.DuplicateMatchRung`, whose rungs are.  A pair
sharing a UETR has not thereby been shown to agree on amount: the tiers read
different fields.  So a link records the single tier it was made at, and the
list of components that actually agreed travels with it in
:attr:`Link.components`.

Three things that are easy to get wrong
---------------------------------------

**Tolerance is not transitive.**  If A and B are three days apart and B and C
are three days apart, A and C are six days apart, and a four-day window admits
both pairs and not the third.  Building a same-side group by following the
chain would assert a link the rule rejects.  So tier-1 same-side groups are
required to be *cliques*: every pair inside the group within tolerance, not
merely every consecutive pair.  Tier 0 needs no such rule, because equality
really is transitive.

**A payment has two ends, so one debit may answer to exactly one credit.**
When it answers to three, the useful output is not the first of the three -- it
is the fact that there are three.  A greedy match would pick one by iteration
order and write down a path through the money that nothing chose.  Counterparty
matching therefore requires mutual uniqueness, and everything else is
:attr:`~postgres.models.enums.LinkOutcome.ambiguous`.

**A counterparty name means the opposite thing on each side of a pair.**  On
the payer's row ``counterparty_raw`` names the payee; on the payee's row it
names the payer.  Comparing the two directly compares a payee's name to a
payer's name, which for a genuine pair should *not* match -- so a tier-2
counterparty rule written the obvious way rejects exactly the pairs it exists
to find.  The comparison is crossed: each row's counterparty is matched against
the *other* row's account holder.  For a same-side pair the naive comparison is
the right one, because both rows are describing the same third party.

Deliberate limits
-----------------

**Same currency only.**  Amounts are integer minor units and are compared for
equality.  A cross-currency payment leaves GBP one side and EUR the other, and
joining those needs an FX rate on a date, which is a substantially weaker and
differently-sourced claim than anything here.  Such a pair is not matched, and
is not reported as a conflict either; it is simply out of scope.

**Admitted rows only.**  Quarantined, superseded and rejected rows are not
candidates, matching :func:`services.financial.reconcile.total_transactions`.
Linking a superseded row would attach evidence to a reading that has already
been replaced.

**No persistence.**  There is no link table in the schema and inventing one
here would be a migration smuggled into a service module.  Every function is
pure: observations in, claims out, no session, no writes.  Persisting the
claims is its own unit of work with its own migration.
"""

from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Mapping, Optional, Sequence

from postgres.models.enums import (
    DateSource,
    JoinTier,
    LinkOutcome,
    LinkRelation,
    ReferenceScope,
    TransactionDirection,
)
from services.financial.money import Money


class LinkageError(Exception):
    """A caller-side mistake that makes a join meaningless rather than absent."""


# ---------------------------------------------------------------------------
# What agreed
# ---------------------------------------------------------------------------

# Recorded on each link so that a link can be read without re-deriving it.
# Named rather than positional because these strings reach an exhibit, where
# "amount, currency and value date agreed within 2 days" is the sentence, and a
# tuple of booleans is not.

#: A scoped identifier was equal on both sides.  Tier 0 only.
MATCH_IDENTIFIER = "identifier"
#: Both rows are denominated in the same currency.
MATCH_CURRENCY = "currency"
#: Equal integer minor units.  Never a tolerance; see the module docstring.
MATCH_AMOUNT = "amount"
#: Directions stand in the relationship the relation requires -- equal for
#: ``same_side``, opposite for ``counterparty``.
MATCH_DIRECTION = "direction"
#: A date field present on both rows agreed within the tolerance in force.
MATCH_DATE = "date"
#: The two rows name the same account.  Required by ``same_side``.
MATCH_ACCOUNT = "account"
#: The two rows name different accounts.  Required by ``counterparty``.
MATCH_ACCOUNTS_DIFFER = "accounts_differ"
#: Counterparty names were compared and were similar enough.  Tier 2 only.
MATCH_COUNTERPARTY_NAME = "counterparty_name"


# ---------------------------------------------------------------------------
# Date tolerance
# ---------------------------------------------------------------------------

#: Rails, and how far apart two sightings of one payment may sit.
#:
#: These are **configuration, not standards**.  No rulebook states a matching
#: window; what the rulebooks state is a settlement window, and the numbers
#: below are settlement windows rounded outward to absorb a weekend.  ACH under
#: the NACHA rules settles same-day, next-day or in two banking days, and two
#: banking days across a weekend is four calendar days.  Fedwire and CHAPS
#: settle the same day, so a wire pair should differ by at most a cutoff
#: crossing.  Cheques clear over a longer and much less predictable interval,
#: and card authorisation precedes settlement by a few days.
#:
#: They are exposed as a mapping, and every function that uses one takes it as
#: an argument, so that a matter with a known rail can narrow the window and a
#: link can record which window it was made under.
RAIL_WIRE = "wire"
RAIL_ACH = "ach"
RAIL_CHEQUE = "cheque"
RAIL_CARD = "card"
RAIL_UNKNOWN = "unknown"

RAIL_TOLERANCE_DAYS: Mapping[str, int] = {
    RAIL_WIRE: 1,
    RAIL_ACH: 4,
    RAIL_CHEQUE: 10,
    RAIL_CARD: 5,
    RAIL_UNKNOWN: 2,
}

#: Used when the rail is not known, which for rows read out of a PDF statement
#: is most of the time.  Narrow on purpose: tier 1 is asserted without a human,
#: so its errors are the expensive ones, and a payment that falls outside the
#: window is still reachable at tier 2 where a person sees it.
DEFAULT_TOLERANCE_DAYS = RAIL_TOLERANCE_DAYS[RAIL_UNKNOWN]

#: Tier 2 widens the window, because a proposal that is wrong costs a person a
#: glance while a proposal never made costs the finding.
PROBABILISTIC_TOLERANCE_DAYS = 14

#: How alike two counterparty strings must be before tier 2 will pair them.
#: An operating point rather than a fact.  ``difflib`` ratios on normalised
#: company names sit near 1.0 for spelling variants and abbreviations of the
#: same name and fall away quickly for different names; 0.85 keeps "ACME
#: HOLDINGS LTD" against "ACME HOLDINGS LIMITED" and rejects "ACME" against
#: "APEX".  Nothing downstream may treat a pair that clears it as established.
NAME_SIMILARITY_THRESHOLD = 0.85

#: Date fields tried, in order, when deciding which two dates to compare.
#:
#: Like must be compared with like: a booking date against an effective date is
#: two different events, and their difference is not evidence of anything.  So
#: the comparison uses the strongest field *both* rows carry.  Value date leads
#: because every rail defines it the same way -- when funds are available.
#: Posting is bank-internal and consistent within an institution.  Transaction
#: date is the least reliably populated.  Effective date is NACHA's own and
#: therefore only common when both sides came from ACH files, which is exactly
#: when the earlier three are all absent.
DATE_FIELD_PREFERENCE: tuple[str, ...] = (
    "value_date",
    "posted_date",
    "transaction_date",
    "effective_date",
)

#: The fallback when no preferred field is present on both rows.  Always
#: populated -- the ledger orders by it -- but it is whichever date the source
#: happened to supply, so two rows can hold ordering dates of different kinds.
ORDERING_DATE_FIELD = "ordering_date"


_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^0-9A-Z ]+")


# ---------------------------------------------------------------------------
# Scoped references
# ---------------------------------------------------------------------------

#: A UUID sitting in a payment reference field.  Not claimed to be a UETR --
#: an end-to-end id can be a UUID too -- but a version-4 UUID is globally
#: unique by construction whatever field it arrived in, so two rows carrying
#: the same one are related by something, and the collision probability is the
#: only false-positive risk.
REFERENCE_UUID = "uuid"
#: A NACHA trace number.  Fifteen digits whose leading eight are the ODFI's
#: routing prefix, so the string carries its own scope and full-string
#: equality is already scoped equality.
REFERENCE_NACHA_TRACE = "nacha_trace"
#: Anything else a native parser left in ``bank_reference``: a camt.053
#: account-servicer reference, a BAI2 bank reference, an MT940 institution
#: reference.  Unique to the institution that minted it and to nothing wider,
#: which is why it needs an explicit scope key.
REFERENCE_BANK_REFERENCE = "bank_reference"
#: A cheque number.  Unique within one account and reused when the book runs
#: out.  No extractor populates this today; the machinery carries it because
#: it is the case that makes :class:`ReferenceScope` necessary, and a caller
#: holding cheque numbers can supply them.
REFERENCE_CHEQUE_NUMBER = "cheque_number"

_NACHA_TRACE_RE = re.compile(r"^[0-9]{15}$")


@dataclass(frozen=True)
class ScopedReference:
    """An identifier and the universe it is unique in.

    ``scope_key`` names that universe: an institution for
    :attr:`~postgres.models.enums.ReferenceScope.institution`, an account for
    :attr:`~postgres.models.enums.ReferenceScope.account`, and nothing at all
    for :attr:`~postgres.models.enums.ReferenceScope.global_`.  Two references
    are equal for joining purposes only when kind, scope, scope key *and*
    value all agree, which is what stops cheque 1001 in one account from
    joining cheque 1001 in another.

    A non-global reference with no scope key is refused rather than treated as
    global.  Silently widening the scope is how a bare bank reference from two
    different banks becomes one payment.
    """

    kind: str
    scope: ReferenceScope
    value: str
    scope_key: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.value:
            raise LinkageError("a scoped reference must carry a value")
        if not self.kind:
            raise LinkageError("a scoped reference must carry a kind")
        if self.scope is ReferenceScope.global_:
            if self.scope_key is not None:
                raise LinkageError(
                    "a global reference has no scope key; supplying one "
                    "implies a narrower scope than the value claims"
                )
        elif not self.scope_key:
            raise LinkageError(
                f"a {self.scope.value}-scoped reference needs a scope key; "
                "without one the comparison silently becomes global, which is "
                "how two banks' internal references become one payment"
            )

    @property
    def join_key(self) -> tuple[str, str, str, str]:
        """The tuple two references must share to be the same reference."""
        return (self.kind, self.scope.value, self.scope_key or "", self.value)


def _looks_like_uuid(value: str) -> Optional[str]:
    """The canonical form of ``value`` if it is a UUID, else ``None``.

    Canonicalised rather than compared as written, because the same UETR
    travels through a payment chain in upper case in one system and lower in
    another, and with or without braces.  :class:`uuid.UUID` accepts all of
    those and prints one form.
    """
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def references_from_bank_reference(
    bank_reference: Optional[str],
    *,
    parser_name: Optional[str] = None,
    institution_key: Optional[str] = None,
) -> tuple[ScopedReference, ...]:
    """Read the one reference column the ledger has, and scope it honestly.

    ``bank_reference`` is a single column holding four different things
    depending on which parser filled it, and the scope differs with the thing.
    ``parser_name`` -- the value
    :func:`services.financial.native.parser_name` writes onto the source
    document -- is what says which.

    A NACHA trace is recognised by shape as well as by parser, because the
    shape is diagnostic and because a row can reach here with its parser
    unrecorded.  Everything else falls back to an institution-scoped bank
    reference, and returns nothing at all when ``institution_key`` is absent:
    an unscoped institution reference cannot be joined on, and returning it
    unscoped would be worse than returning nothing.
    """
    if not bank_reference:
        return ()
    value = bank_reference.strip()
    if not value:
        return ()

    canonical = _looks_like_uuid(value)
    if canonical is not None:
        return (
            ScopedReference(
                kind=REFERENCE_UUID,
                scope=ReferenceScope.global_,
                value=canonical,
            ),
        )

    is_nacha = (parser_name or "").endswith(".nacha")
    if _NACHA_TRACE_RE.match(value) and (is_nacha or parser_name is None):
        # The leading eight digits are the ODFI prefix, so the trace is its own
        # scope key.  Recording it explicitly rather than relying on the value
        # keeps the comparison uniform with every other scoped reference.
        return (
            ScopedReference(
                kind=REFERENCE_NACHA_TRACE,
                scope=ReferenceScope.institution,
                value=value,
                scope_key=value[:8],
            ),
        )

    if not institution_key:
        return ()
    return (
        ScopedReference(
            kind=REFERENCE_BANK_REFERENCE,
            scope=ReferenceScope.institution,
            value=value,
            scope_key=institution_key,
        ),
    )


# ---------------------------------------------------------------------------
# The unit of comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinkObservation:
    """One admitted ledger row, reduced to what matching reads.

    A narrow object rather than the ORM row, for the reason
    :func:`services.financial.reconcile.evaluate_identity` is pure: the rules
    are the part worth auditing, and they are easier to audit when the thing
    they run over can be written down in a test in four lines.  It also keeps
    the matcher from quietly depending on a column nobody meant it to read.

    ``holder_name`` is here and not obviously needed until the crossed name
    comparison in :func:`link_probabilistic`, which cannot be written without
    it.  ``is_reversal`` is here because a reversal legitimately carries the
    same identifier as the entry it reverses, in the same account, in the
    opposite direction -- the one arrangement that would otherwise be reported
    as an identifier conflict.
    """

    transaction_id: uuid.UUID
    account_id: uuid.UUID
    source_document_id: uuid.UUID
    amount: Money
    direction: TransactionDirection
    ordering_date: date
    ordering_date_source: DateSource
    transaction_date: Optional[date] = None
    posted_date: Optional[date] = None
    value_date: Optional[date] = None
    effective_date: Optional[date] = None
    counterparty_raw: Optional[str] = None
    holder_name: Optional[str] = None
    is_reversal: bool = False
    references: tuple[ScopedReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money):
            raise LinkageError(
                f"amount must be Money, got {type(self.amount).__name__}; "
                "matching compares integer minor units and a float would "
                "make equality a matter of luck"
            )

    @property
    def currency(self) -> str:
        return self.amount.currency

    def date_for(self, field: str) -> Optional[date]:
        if field == ORDERING_DATE_FIELD:
            return self.ordering_date
        return getattr(self, field, None)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DateAgreement:
    """Which two dates were compared, and how far apart they were.

    ``like_for_like`` is false in exactly one situation: neither row carried
    any of :data:`DATE_FIELD_PREFERENCE` in common, so the comparison fell back
    to ``ordering_date``, and the two rows' ordering dates were drawn from
    different underlying fields.  That is a booking date measured against a
    value date, and the gap between them is partly the rail's settlement lag
    rather than any evidence about whether these are one payment.  Tier 1
    refuses it; tier 2 admits it and records it.
    """

    field: str
    left: date
    right: date
    gap_days: int
    like_for_like: bool


@dataclass(frozen=True)
class Link:
    """A claim that two rows describe one payment, and what it rests on.

    The two transaction ids are stored in sorted order so that the link
    between a pair is one object however the pair was encountered.  Direction
    of travel is not lost by this: for a ``counterparty`` link the debit side
    is the payer and the row itself says which is which.
    """

    left_id: uuid.UUID
    right_id: uuid.UUID
    relation: LinkRelation
    tier: JoinTier
    outcome: LinkOutcome
    components: tuple[str, ...]
    date_agreement: Optional[DateAgreement] = None
    reference: Optional[ScopedReference] = None
    tolerance_days: Optional[int] = None
    name_similarity: Optional[float] = None

    def __post_init__(self) -> None:
        if self.left_id == self.right_id:
            raise LinkageError(
                "a row cannot be linked to itself; a self-link would make "
                "every row its own corroboration"
            )
        if self.left_id > self.right_id:
            raise LinkageError(
                "link endpoints must be stored in sorted order so that one "
                "pair yields one link object"
            )

    @property
    def is_asserted(self) -> bool:
        """True when this link may be relied on without a person seeing it.

        Two conditions, and the second is the one that gets forgotten.  Tier 2
        is a proposal by construction.  An ambiguous match at *any* tier is
        also a proposal, because it names several possible partners and
        choosing between them is not something the rule did.
        """
        return (
            self.tier is not JoinTier.probabilistic
            and self.outcome is LinkOutcome.resolved
        )

    @property
    def pair(self) -> tuple[uuid.UUID, uuid.UUID]:
        return (self.left_id, self.right_id)


@dataclass(frozen=True)
class LinkConflict:
    """Two rows sharing an identifier in a way no single payment explains.

    Tier 0 asserts that a shared scoped identifier means a shared payment.
    Some pairs falsify that: the same reference twice in one account in the
    same direction is either a duplicate reading or an identifier the issuer
    reused, and the same reference in two accounts in the same direction is a
    scope that is not as narrow as it was declared.

    This is not a link and not a failure.  It is a finding, in the same sense
    a failed check digit is one: the corpus said something that cannot
    be true, and somebody should learn which half of it is wrong.
    """

    left_id: uuid.UUID
    right_id: uuid.UUID
    reference: ScopedReference
    reason: str


@dataclass(frozen=True)
class LinkageResult:
    """Everything one pass produced, in a fixed order.

    Sorted so that two runs over the same corpus produce byte-identical
    output.  A join set that reshuffled between runs could not be cited, for
    the same reason `references` gives for refusing V1's random ``ref_id``.
    """

    links: tuple[Link, ...] = ()
    conflicts: tuple[LinkConflict, ...] = ()

    @property
    def asserted(self) -> tuple[Link, ...]:
        """The links that stand without a person having looked at them."""
        return tuple(link for link in self.links if link.is_asserted)

    @property
    def proposals(self) -> tuple[Link, ...]:
        """The rest: tier 2, and anything ambiguous at any tier."""
        return tuple(link for link in self.links if not link.is_asserted)


# ---------------------------------------------------------------------------
# Relation classification
# ---------------------------------------------------------------------------


def _opposed(left: LinkObservation, right: LinkObservation) -> bool:
    return left.direction is not right.direction


def classify_relation(
    left: LinkObservation, right: LinkObservation
) -> tuple[Optional[LinkRelation], Optional[str]]:
    """Which relation, if any, two rows could stand in.

    Returns the relation and ``None``, or ``None`` and a plain-language reason
    the pair cannot be one payment.  The reason is what
    :func:`link_exact_identifiers` turns into a :class:`LinkConflict`, because
    at tier 0 an identifier has already asserted that these rows *are* one
    payment, and a pair that cannot be one is therefore a contradiction rather
    than simply a non-match.  At tiers 1 and 2 nothing has been asserted yet
    and the same reason is merely a filter.

    The four cases, and why each falls where it does:

    Same account, same direction, different documents -- one movement seen
    twice.  ``same_side``.

    Same account, same direction, *same* document -- two rows in one document
    are two rows.  The document is a single reading and it says these are two
    movements; a genuine repeated payment reads exactly like this.

    Different accounts, opposite directions -- the two ends of a payment.
    ``counterparty``.

    Same account, opposite directions -- money cannot leave and arrive in one
    account under one identifier, unless one row reverses the other, which is
    the case ``is_reversal`` exists to admit.

    Different accounts, same direction -- two accounts do not both pay out
    under one identifier.  Where an identifier says otherwise the identifier's
    declared scope is wider than its real uniqueness.
    """
    same_account = left.account_id == right.account_id
    opposed = _opposed(left, right)

    if same_account and not opposed:
        if left.source_document_id == right.source_document_id:
            return None, (
                "both rows were read from one document, which states them as "
                "two movements; a repeated payment is indistinguishable from "
                "this and must stay two rows"
            )
        return LinkRelation.same_side, None

    if not same_account and opposed:
        return LinkRelation.counterparty, None

    if same_account and opposed:
        if left.is_reversal or right.is_reversal:
            return None, None  # Expected, and not a link: see the docstring.
        return None, (
            "the rows are in one account and move money in opposite "
            "directions, which one payment cannot do unless one reverses the "
            "other, and neither is marked as a reversal"
        )

    return None, (
        "the rows are in different accounts and move money in the same "
        "direction, so the identifier they share is not unique within the "
        "scope it was recorded under"
    )


def _relation_components(relation: LinkRelation) -> tuple[str, ...]:
    if relation is LinkRelation.same_side:
        return (MATCH_ACCOUNT, MATCH_DIRECTION)
    return (MATCH_ACCOUNTS_DIFFER, MATCH_DIRECTION)


# ---------------------------------------------------------------------------
# Date comparison
# ---------------------------------------------------------------------------


def compare_dates(
    left: LinkObservation, right: LinkObservation
) -> DateAgreement:
    """Compare the strongest date field both rows carry.

    Always returns an agreement, because ``ordering_date`` is never null; what
    varies is which field was used and whether the two rows meant the same
    thing by it.  The caller decides whether the gap is small enough and
    whether an unlike comparison is acceptable at its tier.
    """
    for field in DATE_FIELD_PREFERENCE:
        left_date = left.date_for(field)
        right_date = right.date_for(field)
        if left_date is not None and right_date is not None:
            return DateAgreement(
                field=field,
                left=left_date,
                right=right_date,
                gap_days=abs((left_date - right_date).days),
                like_for_like=True,
            )
    return DateAgreement(
        field=ORDERING_DATE_FIELD,
        left=left.ordering_date,
        right=right.ordering_date,
        gap_days=abs((left.ordering_date - right.ordering_date).days),
        like_for_like=(
            left.ordering_date_source is right.ordering_date_source
        ),
    )


# ---------------------------------------------------------------------------
# Name comparison
# ---------------------------------------------------------------------------


def normalise_name(text: Optional[str]) -> str:
    """A party name reduced to what two spellings of it have in common.

    Upper-cased, stripped of everything that is not a letter, digit or space,
    and with runs of space collapsed.  Deliberately shallow: it does not
    remove corporate suffixes, because "ACME LTD" and "ACME INC" are two
    companies and a normaliser that made them equal would hand tier 2 a
    confident wrong answer in the one place a person is meant to be able to
    trust the shortlist.
    """
    if not text:
        return ""
    upper = text.upper()
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", upper)).strip()


def name_similarity(left: Optional[str], right: Optional[str]) -> Optional[float]:
    """How alike two names are, or ``None`` when one of them is missing.

    ``None`` rather than ``0.0``, because absence and disagreement call for
    different handling: a missing counterparty string is a gap in the
    extraction, and scoring it zero would let a pair be rejected for a reason
    that is not about the pair.
    """
    left_key = normalise_name(left)
    right_key = normalise_name(right)
    if not left_key or not right_key:
        return None
    return difflib.SequenceMatcher(None, left_key, right_key).ratio()


# ---------------------------------------------------------------------------
# Tier 0: exact scoped identifiers
# ---------------------------------------------------------------------------


def _ordered(
    left: LinkObservation, right: LinkObservation
) -> tuple[LinkObservation, LinkObservation]:
    """The pair in transaction-id order, so one pair yields one link object."""
    if left.transaction_id <= right.transaction_id:
        return left, right
    return right, left


def _amount_components(
    left: LinkObservation, right: LinkObservation
) -> tuple[str, ...]:
    """Currency and amount, recorded when they agree and omitted when not.

    Tier 0 does not *require* either.  A payment can arrive net of a
    correspondent's fee, so a genuine counterparty pair joined by UETR may
    carry two different amounts, and demanding equality would reject the case
    the identifier exists to settle.  Recording the agreement when it happens
    costs nothing and lets an exhibit say how much of the pair was checked.
    """
    if left.currency != right.currency:
        return ()
    if left.amount != right.amount:
        return (MATCH_CURRENCY,)
    return (MATCH_CURRENCY, MATCH_AMOUNT)


def link_exact_identifiers(
    observations: Iterable[LinkObservation],
) -> LinkageResult:
    """Join rows that share an identifier inside a scope they both belong to.

    Grouping rather than pairing, because equality is transitive: if three
    rows carry one UETR, all three describe one payment and every pair among
    them is a link.  Tier 1 cannot do this -- see the module docstring on
    tolerance -- but tier 0 can, and doing it any other way would leave the
    third row attached to only whichever of the first two happened to be
    compared with it.

    Several counterparty partners do **not** make a tier-0 match ambiguous,
    which is the opposite of the rule at tier 1.  A UETR is designed to be
    carried unchanged through a correspondent chain, so one identifier
    legitimately spans a payer, one or more intermediaries and a payee, and
    every hop is a genuine counterparty pair.  Reporting that as ambiguity
    would flag the case the standard was built to make unambiguous.
    """
    by_key: dict[
        tuple[str, str, str, str], list[tuple[LinkObservation, ScopedReference]]
    ] = {}
    for observation in observations:
        for reference in observation.references:
            by_key.setdefault(reference.join_key, []).append(
                (observation, reference)
            )

    links: list[Link] = []
    conflicts: list[LinkConflict] = []

    for key in sorted(by_key):
        members = by_key[key]
        if len(members) < 2:
            continue
        for index, (first, first_ref) in enumerate(members):
            for second, _second_ref in members[index + 1 :]:
                if first.transaction_id == second.transaction_id:
                    # One row carrying the same reference twice.  Not a pair.
                    continue
                left, right = _ordered(first, second)
                reference = (
                    first_ref if left is first else _second_ref
                )
                relation, reason = classify_relation(left, right)
                if relation is None:
                    if reason is not None:
                        conflicts.append(
                            LinkConflict(
                                left_id=left.transaction_id,
                                right_id=right.transaction_id,
                                reference=reference,
                                reason=reason,
                            )
                        )
                    continue
                links.append(
                    Link(
                        left_id=left.transaction_id,
                        right_id=right.transaction_id,
                        relation=relation,
                        tier=JoinTier.exact_identifier,
                        outcome=LinkOutcome.resolved,
                        components=(
                            (MATCH_IDENTIFIER,)
                            + _relation_components(relation)
                            + _amount_components(left, right)
                        ),
                        date_agreement=compare_dates(left, right),
                        reference=reference,
                    )
                )

    return LinkageResult(
        links=tuple(sorted(links, key=_link_sort_key)),
        conflicts=tuple(sorted(conflicts, key=_conflict_sort_key)),
    )


def _link_sort_key(link: Link) -> tuple:
    return (
        link.left_id.bytes,
        link.right_id.bytes,
        int(link.tier),
        link.relation.value,
    )


def _conflict_sort_key(conflict: LinkConflict) -> tuple:
    return (
        conflict.left_id.bytes,
        conflict.right_id.bytes,
        conflict.reference.join_key,
    )


# ---------------------------------------------------------------------------
# Candidate resolution, shared by tiers 1 and 2
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    """A pair that passed a tier's predicate, before ambiguity is considered."""

    left: LinkObservation
    right: LinkObservation
    relation: LinkRelation
    agreement: DateAgreement
    similarity: Optional[float] = None

    @property
    def pair(self) -> tuple[uuid.UUID, uuid.UUID]:
        return (self.left.transaction_id, self.right.transaction_id)


def _connected_components(
    edges: Sequence[tuple[uuid.UUID, uuid.UUID]],
) -> list[set[uuid.UUID]]:
    """Group ids that are reachable from one another through ``edges``."""
    parent: dict[uuid.UUID, uuid.UUID] = {}

    def find(node: uuid.UUID) -> uuid.UUID:
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    for left, right in edges:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    groups: dict[uuid.UUID, set[uuid.UUID]] = {}
    for node in parent:
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())


def _resolve_same_side(
    candidates: Sequence[_Candidate],
    *,
    prior_equalities: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
) -> dict[tuple[uuid.UUID, uuid.UUID], LinkOutcome]:
    """Decide which same-side candidates stand, group by group.

    A same-side relation is a *group*, not a pairing: one payment can be
    sighted in a statement, an ACH file and a confirmation, and all three
    describe one movement.  So mutual uniqueness is the wrong test here; it
    would call a perfectly good triple ambiguous for having three members.

    Two rules stand in for it.

    A group must be a **clique**.  Membership is decided pairwise, and the
    pairwise test is a tolerance, which does not compose: A three days from B
    and B three days from C leaves A six days from C.  Accepting the group on
    the strength of the chain would assert a pair the tolerance rejects.
    Requiring every pair inside the group to have passed on its own is what
    makes the group mean what a group of same-side rows should mean.

    A group must draw on **distinct documents**.  Two rows from one document
    are two movements that document states separately, so if both are in one
    group at most one of them is the movement, and nothing here says which.

    ``prior_equalities`` are same-side pairs a tier joining on *equality*
    already established, and they satisfy the clique requirement without being
    candidates here.  This is not a relaxation of the rule but the reason the
    rule is stated in terms of tolerance: what does not compose is a tolerance,
    and a chain through an equality composes perfectly well.  If A and B carry
    one UETR, and C agrees with A on amount and date, then C agrees with the
    movement A and B both are.  Only tier 0 supplies these; a tier-1 pair is a
    tolerance and is never passed down to tier 2 as an equality, because two
    tolerances in a chain is exactly what the clique rule exists to forbid.
    """
    outcomes: dict[tuple[uuid.UUID, uuid.UUID], LinkOutcome] = {}
    by_pair = {candidate.pair: candidate for candidate in candidates}
    members: dict[uuid.UUID, LinkObservation] = {}
    for candidate in candidates:
        members[candidate.left.transaction_id] = candidate.left
        members[candidate.right.transaction_id] = candidate.right

    established = set(by_pair)
    established.update(
        pair
        for pair in prior_equalities
        if pair[0] in members and pair[1] in members
    )

    # Components are built from this tier's candidates alone.  A prior equality
    # can vouch for a pair inside a group but must not pull a row into one,
    # because the group this tier reports is a statement about what this tier
    # found.
    for component in _connected_components([c.pair for c in candidates]):
        ids = sorted(component, key=lambda value: value.bytes)
        expected = [
            (ids[i], ids[j])
            for i in range(len(ids))
            for j in range(i + 1, len(ids))
        ]
        is_clique = all(pair in established for pair in expected)
        documents = [members[i].source_document_id for i in ids]
        distinct_documents = len(set(documents)) == len(documents)
        outcome = (
            LinkOutcome.resolved
            if is_clique and distinct_documents
            else LinkOutcome.ambiguous
        )
        for pair in expected:
            if pair in by_pair:
                outcomes[pair] = outcome
    return outcomes


def _resolve_counterparty(
    candidates: Sequence[_Candidate],
    *,
    prior_partners: Optional[Mapping[uuid.UUID, frozenset[uuid.UUID]]] = None,
) -> dict[tuple[uuid.UUID, uuid.UUID], LinkOutcome]:
    """Decide which counterparty candidates stand, one pair at a time.

    A payment has two ends, so a debit answers to exactly one credit.  A pair
    is resolved only when each side's entire candidate set is the other side:
    mutual uniqueness, checked from both directions rather than one, because a
    debit with a single candidate credit that itself answers to four debits has
    not been resolved by anything.

    Everything else is ambiguous and stays recorded.  The alternative -- taking
    the first, or the nearest in date -- would write down a route through the
    money that no rule chose and no reviewer was asked about, and the
    ambiguity, which is the finding, would be the part not written down.

    ``prior_partners`` carries the counterparty pairings a *stronger* tier
    already made, and it is not an optimisation.  One-to-one is a property of
    the payment, not of the tier that noticed it, so a debit resolved to a
    credit by shared UETR is spoken for; a later tier finding it also agrees on
    amount and date with some second credit has found a competing claim, not a
    second payment.  Without this, :func:`link_transactions` could assert two
    contradictory routes for one payment and satisfy the uniqueness rule inside
    each tier while breaking it across them.
    """
    outcomes: dict[tuple[uuid.UUID, uuid.UUID], LinkOutcome] = {}
    partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    for node, existing in (prior_partners or {}).items():
        partners.setdefault(node, set()).update(existing)
    for candidate in candidates:
        left_id, right_id = candidate.pair
        partners.setdefault(left_id, set()).add(right_id)
        partners.setdefault(right_id, set()).add(left_id)

    for candidate in candidates:
        left_id, right_id = candidate.pair
        mutual = partners[left_id] == {right_id} and partners[right_id] == {
            left_id
        }
        outcomes[candidate.pair] = (
            LinkOutcome.resolved if mutual else LinkOutcome.ambiguous
        )
    return outcomes


def _links_from_candidates(
    candidates: Sequence[_Candidate],
    *,
    tier: JoinTier,
    tolerance_days: int,
    components_for: Callable[[_Candidate], tuple[str, ...]],
    prior_partners: Optional[Mapping[uuid.UUID, frozenset[uuid.UUID]]] = None,
    prior_equalities: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
) -> list[Link]:
    """Turn resolved and ambiguous candidates into links, relation by relation.

    The two relations are resolved by different rules and so are separated
    first.  Nothing is dropped: an ambiguous candidate becomes an ambiguous
    link, because the ambiguity is the finding.
    """
    same_side = [c for c in candidates if c.relation is LinkRelation.same_side]
    counterparty = [
        c for c in candidates if c.relation is LinkRelation.counterparty
    ]
    outcomes = _resolve_same_side(
        same_side, prior_equalities=prior_equalities
    )
    outcomes.update(
        _resolve_counterparty(counterparty, prior_partners=prior_partners)
    )

    links: list[Link] = []
    for candidate in candidates:
        links.append(
            Link(
                left_id=candidate.left.transaction_id,
                right_id=candidate.right.transaction_id,
                relation=candidate.relation,
                tier=tier,
                outcome=outcomes[candidate.pair],
                components=components_for(candidate),
                date_agreement=candidate.agreement,
                tolerance_days=tolerance_days,
                name_similarity=candidate.similarity,
            )
        )
    return links


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------


def _blocks(
    observations: Iterable[LinkObservation],
) -> list[list[LinkObservation]]:
    """Partition rows into sets that could possibly match each other.

    Every tier below tier 0 requires the same currency and the same integer
    amount, so two rows in different buckets cannot pair however else they
    agree.  Comparing all pairs would be quadratic in the size of a case --
    and a real case here runs to five figures of rows, where quadratic is
    hundreds of millions of comparisons for a rule that would reject almost
    all of them on the first field it read.

    This is an exact optimisation and not a heuristic: the bucket key is a
    condition the matcher enforces anyway, so no pair that would have matched
    is separated by it.  That is the reason amount tolerance is not offered.
    """
    buckets: dict[tuple[str, int], list[LinkObservation]] = {}
    for observation in observations:
        key = (observation.currency, observation.amount.minor_units)
        buckets.setdefault(key, []).append(observation)
    return [
        sorted(bucket, key=lambda o: o.transaction_id.bytes)
        for _, bucket in sorted(buckets.items())
    ]


def tolerance_for_rail(rail: Optional[str]) -> int:
    """The date window in force for a rail, falling back to the unknown rail.

    A function rather than a bare dictionary lookup so that an unrecognised
    rail resolves to the narrow default instead of raising.  A matter can
    carry a rail label this module has never heard of, and the safe reading of
    one is that nothing is known about settlement timing -- which is exactly
    what :data:`DEFAULT_TOLERANCE_DAYS` already encodes.
    """
    if rail is None:
        return DEFAULT_TOLERANCE_DAYS
    return RAIL_TOLERANCE_DAYS.get(rail, DEFAULT_TOLERANCE_DAYS)


# ---------------------------------------------------------------------------
# Tier 1: deterministic composite
# ---------------------------------------------------------------------------


def _composite_components(candidate: _Candidate) -> tuple[str, ...]:
    """What a tier-1 pair was shown to agree on.

    Currency and amount are guaranteed by the block the pair came out of, and
    date by the tolerance test, so all three are unconditional here.  They are
    still listed rather than assumed, because the components are what an
    exhibit reads back and "the block guaranteed it" is not a sentence that
    survives leaving this module.
    """
    return (
        (MATCH_CURRENCY, MATCH_AMOUNT)
        + _relation_components(candidate.relation)
        + (MATCH_DATE,)
    )


def link_composite(
    observations: Iterable[LinkObservation],
    *,
    tolerance_days: int = DEFAULT_TOLERANCE_DAYS,
    exclude_pairs: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
    prior_partners: Optional[Mapping[uuid.UUID, frozenset[uuid.UUID]]] = None,
    prior_equalities: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
) -> LinkageResult:
    """Join rows on amount, currency, direction and a date within tolerance.

    The deterministic tier is defined over amount, a date within the rail's
    settlement tolerance, and *both* account identifiers.  The ledger carries a
    row's own account but
    not its counterparty's, so the second half of that key cannot be read
    today.  Rather than claim it, the components recorded on each link say
    which fields actually participated -- so a tier-1 link made now is
    distinguishable from one made after counterparty account identifiers land,
    and neither has to be taken on trust.

    Two refusals are worth naming, because both look like over-caution until
    the case they prevent is written out.

    *An unlike date comparison is not a match here.*  Where the two rows share
    no preferred date field, :func:`compare_dates` falls back to
    ``ordering_date``, and if the two ordering dates came from different
    underlying fields the gap between them is partly the rail's settlement lag.
    Tier 1 is asserted without a person, so it declines; the pair is still
    reachable at tier 2, where somebody sees it.

    *No amount tolerance.*  Two payments that differ by a fee are two
    payments, and matching across a fee would silently merge them.  Where a
    fee genuinely splits one payment, the identifier that survives the fee is
    what joins it, at tier 0, where :func:`_amount_components` already records
    that the amounts did not agree.

    Produces no conflicts.  A conflict is a contradiction of something
    asserted, and at tier 1 nothing has been asserted for a non-matching pair
    to contradict -- it simply did not match.
    """
    candidates: list[_Candidate] = []
    for block in _blocks(observations):
        for index, first in enumerate(block):
            for second in block[index + 1 :]:
                left, right = _ordered(first, second)
                if (left.transaction_id, right.transaction_id) in exclude_pairs:
                    continue
                relation, _reason = classify_relation(left, right)
                if relation is None:
                    continue
                agreement = compare_dates(left, right)
                if not agreement.like_for_like:
                    continue
                if agreement.gap_days > tolerance_days:
                    continue
                candidates.append(
                    _Candidate(
                        left=left,
                        right=right,
                        relation=relation,
                        agreement=agreement,
                    )
                )

    links = _links_from_candidates(
        candidates,
        tier=JoinTier.deterministic_composite,
        tolerance_days=tolerance_days,
        components_for=_composite_components,
        prior_partners=prior_partners,
        prior_equalities=prior_equalities,
    )
    return LinkageResult(links=tuple(sorted(links, key=_link_sort_key)))


# ---------------------------------------------------------------------------
# Tier 2: probabilistic
# ---------------------------------------------------------------------------


def name_agreement(
    left: LinkObservation,
    right: LinkObservation,
    relation: LinkRelation,
) -> Optional[float]:
    """How well the party names support the relation, or ``None`` if unknown.

    The comparison differs by relation, and getting this wrong is the subtlest
    error in the module.

    For ``same_side`` the two rows are one movement in one account, so both
    ``counterparty_raw`` strings name the *same* other party and comparing
    them directly is right.

    For ``counterparty`` the two rows are opposite ends of one payment, so the
    payer's ``counterparty_raw`` names the payee and the payee's names the
    payer.  Comparing them to each other compares a payee's name with a
    payer's name, which for a *genuine* pair should not match at all -- a rule
    written the obvious way rejects precisely the pairs it exists to find.  The
    comparison is therefore crossed: each row's counterparty against the other
    row's account holder.

    Where both crossed comparisons are available the lower is returned.  One
    side agreeing while the other disagrees is not corroboration; it is one
    agreement and one disagreement, and the weaker half is what the pair is
    worth.
    """
    if relation is LinkRelation.same_side:
        return name_similarity(left.counterparty_raw, right.counterparty_raw)

    scores = [
        score
        for score in (
            name_similarity(left.counterparty_raw, right.holder_name),
            name_similarity(right.counterparty_raw, left.holder_name),
        )
        if score is not None
    ]
    if not scores:
        return None
    return min(scores)


def _probabilistic_components(candidate: _Candidate) -> tuple[str, ...]:
    return (
        (MATCH_CURRENCY, MATCH_AMOUNT)
        + _relation_components(candidate.relation)
        + (MATCH_DATE, MATCH_COUNTERPARTY_NAME)
    )


def link_probabilistic(
    observations: Iterable[LinkObservation],
    *,
    tolerance_days: int = PROBABILISTIC_TOLERANCE_DAYS,
    name_threshold: float = NAME_SIMILARITY_THRESHOLD,
    exclude_pairs: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
    prior_partners: Optional[Mapping[uuid.UUID, frozenset[uuid.UUID]]] = None,
    prior_equalities: frozenset[tuple[uuid.UUID, uuid.UUID]] = frozenset(),
) -> LinkageResult:
    """Propose pairs on amount, an approximate date and a similar party name.

    This tier is admissible as a *proposal* only, and every link it returns
    is a proposal whatever :class:`LinkOutcome` it carries: nothing here is
    :attr:`Link.is_asserted`, because :attr:`JoinTier.probabilistic` fails that
    test on its own.  The outcome still matters, since it separates a pair a
    reviewer can accept from a shortlist a reviewer has to choose within.

    All three of amount, date and name are required.  Dropping the name would
    leave amount and a fortnight, which in a corpus of round-numbered rent and
    payroll pairs everything with everything; a fuzzy name is what makes the
    shortlist short enough to be read.  A pair whose names are missing
    entirely scores ``None`` and is not proposed -- absence is not similarity,
    and a proposal a reviewer cannot evaluate is worse than none.

    Unlike tier 1 this tier accepts an unlike-for-like date comparison,
    recording it on the link's :class:`DateAgreement`.  A booking date against
    a value date is weak evidence rather than no evidence, and weak evidence
    in front of a person is what this tier is for.
    """
    candidates: list[_Candidate] = []
    for block in _blocks(observations):
        for index, first in enumerate(block):
            for second in block[index + 1 :]:
                left, right = _ordered(first, second)
                if (left.transaction_id, right.transaction_id) in exclude_pairs:
                    continue
                relation, _reason = classify_relation(left, right)
                if relation is None:
                    continue
                agreement = compare_dates(left, right)
                if agreement.gap_days > tolerance_days:
                    continue
                similarity = name_agreement(left, right, relation)
                if similarity is None or similarity < name_threshold:
                    continue
                candidates.append(
                    _Candidate(
                        left=left,
                        right=right,
                        relation=relation,
                        agreement=agreement,
                        similarity=similarity,
                    )
                )

    links = _links_from_candidates(
        candidates,
        tier=JoinTier.probabilistic,
        tolerance_days=tolerance_days,
        components_for=_probabilistic_components,
        prior_partners=prior_partners,
        prior_equalities=prior_equalities,
    )
    return LinkageResult(links=tuple(sorted(links, key=_link_sort_key)))


# ---------------------------------------------------------------------------
# The cascade
# ---------------------------------------------------------------------------


def _counterparty_partners(
    links: Iterable[Link],
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    """The counterparty pairings a set of links has already made.

    Only ``counterparty`` links and only resolved ones.  An ambiguous link
    names several possible partners and settles nothing, so treating it as a
    prior claim would let an unresolved match veto a later resolved one.
    """
    partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    for link in links:
        if link.relation is not LinkRelation.counterparty:
            continue
        if link.outcome is not LinkOutcome.resolved:
            continue
        partners.setdefault(link.left_id, set()).add(link.right_id)
        partners.setdefault(link.right_id, set()).add(link.left_id)
    return {node: frozenset(values) for node, values in partners.items()}


def _same_side_equalities(
    links: Iterable[Link],
) -> frozenset[tuple[uuid.UUID, uuid.UUID]]:
    """The same-side pairs an *equality* tier settled, for the clique test.

    Only resolved ``same_side`` links, and only ever called on tier 0's output.
    The restriction to tier 0 is the whole point: a pair joined by a shared
    identifier is an equality and chains soundly, a pair joined within a date
    tolerance does not, and passing tier 1's edges down to tier 2 as though
    they were equalities would rebuild precisely the chain-of-tolerances that
    :func:`_resolve_same_side` refuses.  An ambiguous link is excluded for the
    same reason it is excluded from :func:`_counterparty_partners`: it settles
    nothing, so it can vouch for nothing.
    """
    return frozenset(
        link.pair
        for link in links
        if link.relation is LinkRelation.same_side
        and link.outcome is LinkOutcome.resolved
    )


def link_transactions(
    observations: Iterable[LinkObservation],
    *,
    tolerance_days: int = DEFAULT_TOLERANCE_DAYS,
    probabilistic_tolerance_days: int = PROBABILISTIC_TOLERANCE_DAYS,
    name_threshold: float = NAME_SIMILARITY_THRESHOLD,
    include_probabilistic: bool = True,
) -> LinkageResult:
    """Run the three tiers strongest first and return everything they found.

    A pair claimed by a stronger tier is not offered to a weaker one.  The
    suppression is of the **pair**, not of either row: a third sighting that
    carries no identifier must still be able to join a group whose first two
    members were joined by one, and excluding a row because it already
    appeared somewhere would lose exactly that.

    Tier-0 conflicts need no explicit suppression, and the reason is an
    invariant rather than an oversight.  A conflict arises precisely when
    :func:`classify_relation` returns no relation, and every tier calls that
    same function first, so a pair that contradicted itself at tier 0 cannot
    reach a candidate list at tier 1 or 2 either.

    Two things carry forward between tiers, for two different reasons.

    Counterparty resolutions carry forward because one-to-one is a property of
    the payment and not of the tier that noticed it.  A payment resolved at
    tier 0 must not acquire a second, contradictory partner at tier 1.

    Tier-0 same-side pairs carry forward as *equalities*, which is what makes
    the paragraph above about suppressing pairs rather than rows true in
    practice.  A third sighting joining a group whose first two members share
    an identifier meets a clique test at tier 1 that can only see tier 1's own
    candidates -- the A-B edge is excluded as already claimed, so the group
    would fail the test and be reported ambiguous when it is not.  Passing the
    tier-0 edges as established repairs that.  They are passed from tier 0
    only: tier 1's own edges are tolerances, and a chain of tolerances is
    exactly what :func:`_resolve_same_side` exists to refuse.

    The result is one :class:`LinkageResult` holding every tier's links in a
    single deterministic order.  Callers separate them with
    :attr:`LinkageResult.asserted` and :attr:`LinkageResult.proposals`, or by
    reading :attr:`Link.tier`; they are not returned pre-separated because a
    caller that wants a row's full evidential picture wants all of it at once.
    """
    rows = list(observations)

    exact = link_exact_identifiers(rows)
    links: list[Link] = list(exact.links)
    claimed = {link.pair for link in exact.links}
    partners = _counterparty_partners(exact.links)
    equalities = _same_side_equalities(exact.links)

    composite = link_composite(
        rows,
        tolerance_days=tolerance_days,
        exclude_pairs=frozenset(claimed),
        prior_partners=partners,
        prior_equalities=equalities,
    )
    links.extend(composite.links)
    claimed.update(link.pair for link in composite.links)
    for node, values in _counterparty_partners(composite.links).items():
        partners[node] = partners.get(node, frozenset()) | values

    if include_probabilistic:
        probabilistic = link_probabilistic(
            rows,
            tolerance_days=probabilistic_tolerance_days,
            name_threshold=name_threshold,
            exclude_pairs=frozenset(claimed),
            prior_partners=partners,
            prior_equalities=equalities,
        )
        links.extend(probabilistic.links)

    return LinkageResult(
        links=tuple(sorted(links, key=_link_sort_key)),
        conflicts=exact.conflicts,
    )
