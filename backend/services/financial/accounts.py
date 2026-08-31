"""Account identity: deciding once whether two printed accounts are one account.

Every join in this subsystem eventually rests on the answer to one question:
when two documents print an account, are they printing the same account?  The
schema forces the answer to be given explicitly.  ``FinancialAccount`` is
unique on ``(case_id, identity_key)`` rather than on any identifier column,
because uniqueness over nullable columns is not uniqueness in Postgres and
because a masked number, a full number and an IBAN are three different
spellings that no index can reconcile on its own.

This module computes that key, and it is the only place that does.

Two failure directions, and they are not symmetric
--------------------------------------------------

Merging two accounts that are not the same account puts two people's money in
one total.  Nothing downstream can detect it: the balance identity still runs,
continuity still looks contiguous, and the resulting figure is wrong in a way
that reads as ordinary.  Splitting one account into two is the opposite kind of
error — it is visible as two rows in a list a human reads, it produces an
obvious gap in continuity, and ``AdjudicationSubject.account`` exists precisely
so that someone can say the two are one and have the correction recorded.

So every judgement here is biased toward splitting.  Where a document does not
say enough to identify an account, this module does not guess a weaker match;
it gives that document's account its own key and leaves the merge to a person.

Placeholders are not identifiers
--------------------------------

Thirty-six documents in the working corpus print ``see statement`` in the
account-number field.  Read literally that is a cross-reference, not a number,
and it is the same cross-reference in all thirty-six.  Anything that treats it
as a value therefore concludes that thirty-six documents describe one account —
and because :func:`services.financial.duplicates._period_signature` builds a
period's signature from the account identity key, those documents then collapse
into a single duplicate group as well.  One unexamined string, and both the
account index and the duplicate detector are wrong in the same direction.

:data:`NON_VALUES` is the guard.  It applies to identifying fields only.
``institution_name`` and ``holder_name`` are carried verbatim wherever they are
carried at all, for the reason ``corpus.INSTITUTION_FIELD`` gives: they are raw
extractor output, and mapping them onto a controlled vocabulary would be
manufacturing a fact about the document rather than reading one.  A placeholder
in a descriptive field is a thing the document said.  A placeholder in an
identifying field is a thing that must never become identity.

Where nothing identifies the account, the caller says so
--------------------------------------------------------

The guard does not silently degrade.  Passing ``see statement`` as an account
number raises; a caller that has read a placeholder out of an identifier field
must call :meth:`AccountDraft.unidentified` and pass a distinguisher.  This is
the discipline :class:`~postgres.models.enums.IdentifierKind` sets out — the
caller read the value out of a named field and therefore already knows what it
is, so it is asked to say so rather than have a module guess — and it has the
same payoff: the degradation is visible at the call site, visible in the row's
metadata, and cannot happen by accident.

Case is folded here, and is not folded in ``references.py``
-----------------------------------------------------------

:func:`services.financial.references._text` preserves case deliberately: it is
canonicalising the content of a row that will be quoted back, and the case is
on the page.  This module folds it.  The difference is what the string is for.
An identity key is a join across documents, and ``CHASE BANK`` and
``Chase Bank`` are one bank printed by two extractors.  Preserving case there
would split a real account on a formatting difference.  Folding cannot merge
two different institutions, so it errs in the direction this module errs in
everywhere else.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from postgres.models.enums import IdentifierKind
from postgres.models.financial import FinancialAccount
from services.financial.check_digits import verify
from services.financial.money import UnknownCurrencyError, get_currency

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from services.financial.runs import IngestionRunHandle


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AccountError(Exception):
    """An account could not be identified or recorded as described."""


class AccountIdentityError(AccountError):
    """Nothing in the draft can serve as identity, or the key is unusable."""


class PlaceholderIdentifierError(AccountIdentityError):
    """A non-value was offered in a field whose purpose is to identify.

    Separate from :class:`AccountIdentityError` because the two call for
    different responses.  A draft with no identifiers at all is a document that
    did not print any; a draft carrying ``see statement`` in the account-number
    field is a caller that has not looked at what it read.  The second is
    recoverable at the call site by :meth:`AccountDraft.unidentified`, and the
    error says so.
    """


class AccountCurrencyError(AccountError):
    """An account's currency is not a currency."""


class AccountFieldError(AccountError):
    """A field is longer than the column that has to hold it.

    Checked here because SQLite ignores ``String`` lengths and Postgres does
    not, so an unchecked overlong value passes every test and fails in
    production against real evidence.
    """


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------

#: Strings that appear where an identifier belongs and identify nothing.
#:
#: Compared after :func:`_fold`, so casing, spacing, wrapping brackets and
#: trailing punctuation are already gone and each entry appears once.  The list
#: is deliberately short and deliberately made of phrases: a token like ``"x"``
#: or ``"0"`` would reject values that some institution really does print.
#:
#: ``see statement``, ``varies`` and ``various`` are the three the working
#: corpus actually contains.  The rest are the neighbouring spellings of the
#: same act — a field left unfilled by a person who typed something into it —
#: and are listed because the cost of omitting one is a silent merge while the
#: cost of including one that never occurs is nothing.
NON_VALUES: frozenset[str] = frozenset(
    {
        "",
        "-",
        "--",
        "---",
        "?",
        "??",
        "n/a",
        "n/a n/a",
        "na",
        "nil",
        "none",
        "null",
        "not applicable",
        "not available",
        "not given",
        "not known",
        "not provided",
        "not stated",
        "not supplied",
        "pending",
        "redacted",
        "see attached",
        "see above",
        "see below",
        "see document",
        "see statement",
        "see statements",
        "tbc",
        "tbd",
        "unavailable",
        "unknown",
        "various",
        "varies",
        "withheld",
    }
)

#: Characters used to mask an identifier in print.
_MASK_CHARS = "*•#●·"

#: Two or more consecutive ``x`` also masks.  One does not: a single ``x`` can
#: appear in a real identifier, and rejecting it would cost more than it saves.
_XMASK = re.compile(r"xx+")

_WHITESPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"[^0-9]")

#: Stripped from the ends before the vocabulary is consulted, so ``[REDACTED]``
#: and ``N/A.`` are recognised as the values they are.
_WRAPPERS = " \t\r\n\"'`[](){}<>.,;:"

_SEP = "\x1f"

#: ``FinancialAccount.identity_key`` is ``String(512)``.
_MAX_IDENTITY_KEY = 512

#: Column widths, checked before the insert.  Keyed by draft attribute.
_MAX_LENGTHS = {
    "institution_name": 255,
    "identifier_as_printed": 128,
    "identifier_normalised": 128,
    "account_type": 32,
    "holder_name": 255,
    "iban": 34,
    "bic": 11,
    "routing_number": 9,
}


def _fold(value: Optional[str]) -> str:
    """One field reduced to the form the guard and the identity key compare.

    NFC first, so two encodings of one accented character are one string.
    Then wrappers off the ends, internal whitespace collapsed, and case folded
    — ``casefold`` rather than ``lower`` so that ``STRASSE`` and ``straße``
    agree, which ``lower`` does not deliver.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", value)
    text = _WHITESPACE.sub(" ", text).strip(_WRAPPERS)
    return text.casefold()


def digits_only(value: Optional[str]) -> str:
    """Every digit in ``value``, in order, and nothing else.

    This is what ``FinancialAccount.identifier_normalised`` holds, and what
    lets one document's ``12-34-56 78901234`` join another's ``1234567 8901234``
    without either being rewritten.
    """
    if value is None:
        return ""
    return _DIGITS.sub("", value)


def is_masked(value: Optional[str]) -> bool:
    """Whether an identifier was printed with part of it hidden.

    Masking matters because a masked number and a full one are different
    evidence about the same thing.  Four visible digits narrow an account to
    one in ten thousand at that institution; a full number names it.  The two
    are given different identity tiers so that a masked reading can never be
    mistaken for, or collide with, a complete one.
    """
    if not value:
        return False
    if any(char in value for char in _MASK_CHARS):
        return True
    return bool(_XMASK.search(value.casefold()))


def is_non_value(value: Optional[str]) -> bool:
    """Whether ``value`` identifies nothing.

    Three ways to identify nothing: absent, in :data:`NON_VALUES`, or made
    entirely of mask characters and punctuation so that not one digit of the
    original survives.  ``****`` is the third: it is a statement that an
    account number was withheld, and it is the same statement on every
    document that carries it.
    """
    folded = _fold(value)
    if folded in NON_VALUES:
        return True
    if value and is_masked(value) and not digits_only(value):
        return True
    return False


def _identifying(value: Optional[str], field_name: str) -> Optional[str]:
    """Return ``value`` if it can identify, ``None`` if absent, else raise.

    The three-way return is the point.  A field the document left empty is a
    fact about the document and the draft continues without it.  A field the
    document filled with a placeholder is also a fact about the document, but
    one the caller has to acknowledge, because the alternative is that
    thirty-six statements quietly become one account.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlaceholderIdentifierError(
            f"{field_name} must be a string or None, got {type(value).__name__}"
        )
    if _fold(value) == "":
        return None
    if is_non_value(value):
        raise PlaceholderIdentifierError(
            f"{field_name} is {value!r}, which identifies nothing; if the "
            "document really printed that, build the draft with "
            "AccountDraft.unidentified() so the account gets a key of its own "
            "rather than sharing one with every other document that printed it"
        )
    return value


# ---------------------------------------------------------------------------
# Identity tiers
# ---------------------------------------------------------------------------

#: A verified IBAN.  Self-checking and internationally unique, so nothing else
#: is needed and nothing else is consulted.
TIER_IBAN = "iban"

#: A verified routing number and a full account number.  Together these name a
#: US account exactly, and the routing number having passed its check digit is
#: what distinguishes this from the institution-name tier below.
TIER_ROUTING_ACCOUNT = "routing_account"

#: An institution name and a full account number.  The institution is a string
#: an extractor produced, so this tier can split one account across two
#: spellings that :func:`_fold` does not reconcile.  It cannot merge two
#: accounts unless they share both a full number and a bank.
TIER_INSTITUTION_ACCOUNT = "institution_account"

#: An institution name and the visible tail of a masked number.  The weakest
#: tier that is still an identification, and the only one that can merge two
#: genuinely different accounts: two accounts at one bank whose numbers end in
#: the same four digits would share a key.  Rows on this tier are marked
#: ``identity_provisional`` in metadata so that a reviewer can find them, and
#: so that nothing downstream can treat the match as equal in strength to a
#: full-number match without having said so.
TIER_INSTITUTION_MASKED = "institution_masked"

#: Nothing on the document identified the account.  The key is built from a
#: caller-supplied distinguisher, so each such document gets its own account
#: rather than all of them sharing one.  Merging them is an adjudication.
TIER_UNIDENTIFIED = "unidentified"

#: Every tier, strongest first.  Ordered because the order is the rule.
IDENTITY_TIERS: tuple[str, ...] = (
    TIER_IBAN,
    TIER_ROUTING_ACCOUNT,
    TIER_INSTITUTION_ACCOUNT,
    TIER_INSTITUTION_MASKED,
    TIER_UNIDENTIFIED,
)


@dataclass(frozen=True)
class AccountIdentity:
    """A computed identity key and the reasoning that produced it.

    Frozen and returned whole rather than as a bare string, because the tier
    and the check-digit verdicts are what a reviewer needs when two accounts
    that should be one are not, and recomputing them later means guessing at
    what the inputs were.
    """

    key: str
    tier: str
    #: Check-digit outcomes by field name, for every structured identifier the
    #: draft carried — including ones that failed and were therefore not used.
    #: A failure is a finding about the document, not a reason to drop it.
    verdicts: dict[str, str] = field(default_factory=dict)

    @property
    def is_provisional(self) -> bool:
        """Whether this key could name more than one real account."""
        return self.tier in (TIER_INSTITUTION_MASKED, TIER_UNIDENTIFIED)


# ---------------------------------------------------------------------------
# The draft
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountDraft:
    """An account as one document printed it, before it has been identified.

    Construct through :meth:`observed` or :meth:`unidentified`.  The two
    constructors are what make the distinction visible at the call site, where
    the caller still knows which one it is looking at — the same reasoning
    ``periods.BalanceObservation`` applies to a balance that is absent versus
    one that is zero.
    """

    institution_name: Optional[str] = None
    identifier_as_printed: Optional[str] = None
    account_type: Optional[str] = None
    holder_name: Optional[str] = None
    currency: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    routing_number: Optional[str] = None
    #: Set only by :meth:`unidentified`.  Anything stable and unique to the
    #: document — its content hash, its id — so that re-reading one document
    #: reaches the same account rather than creating a second.
    distinguisher: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def observed(
        cls,
        *,
        institution_name: Optional[str] = None,
        identifier_as_printed: Optional[str] = None,
        account_type: Optional[str] = None,
        holder_name: Optional[str] = None,
        currency: Optional[str] = None,
        iban: Optional[str] = None,
        bic: Optional[str] = None,
        routing_number: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> "AccountDraft":
        """An account the document identified.

        Raises :class:`PlaceholderIdentifierError` if any identifying field
        holds a non-value, and :class:`AccountIdentityError` if, after the
        guard, nothing identifying is left.  Both are recoverable by calling
        :meth:`unidentified` instead, which is the point: the caller decides,
        and the decision is on the page.
        """
        draft = cls(
            institution_name=institution_name,
            identifier_as_printed=_identifying(
                identifier_as_printed, "identifier_as_printed"
            ),
            account_type=account_type,
            holder_name=holder_name,
            currency=currency,
            iban=_identifying(iban, "iban"),
            bic=_identifying(bic, "bic"),
            routing_number=_identifying(routing_number, "routing_number"),
            metadata=dict(metadata or {}),
        )
        # Computed now rather than at write time so that an unidentifiable
        # draft fails while the document that produced it is still in hand.
        draft.identity()
        return draft

    @classmethod
    def unidentified(
        cls,
        *,
        distinguisher: str,
        institution_name: Optional[str] = None,
        identifier_as_printed: Optional[str] = None,
        account_type: Optional[str] = None,
        holder_name: Optional[str] = None,
        currency: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> "AccountDraft":
        """An account the document did not identify, given its own key anyway.

        ``identifier_as_printed`` is accepted and stored unguarded here,
        because ``see statement`` is what the page said and the page is the
        evidence.  It simply takes no part in the key.

        ``distinguisher`` must be stable across re-reads of the same document
        and unique across documents.  A content hash is the obvious choice; a
        row counter is not, because the same counter in two documents would
        merge two unrelated accounts, which is the one outcome this module is
        built to prevent.
        """
        if not isinstance(distinguisher, str) or not distinguisher.strip():
            raise AccountIdentityError(
                "unidentified() needs a non-empty distinguisher; without one "
                "every unidentifiable account in the case shares a single key, "
                "which is exactly the merge this constructor exists to avoid"
            )
        return cls(
            institution_name=institution_name,
            identifier_as_printed=identifier_as_printed,
            account_type=account_type,
            holder_name=holder_name,
            currency=currency,
            distinguisher=distinguisher.strip(),
            metadata=dict(metadata or {}),
        )

    def __post_init__(self) -> None:
        if self.currency is not None:
            try:
                get_currency(self.currency)
            except UnknownCurrencyError as exc:
                raise AccountCurrencyError(
                    f"account currency {self.currency!r} is not an ISO 4217 "
                    f"code: {exc}"
                ) from exc

        for name, limit in _MAX_LENGTHS.items():
            value = getattr(self, name, None)
            if value is not None and len(value) > limit:
                raise AccountFieldError(
                    f"{name} is {len(value)} characters and the column holds "
                    f"{limit}; truncating it here would silently change an "
                    "identifier, so the caller has to decide what to do"
                )

    # -- identity ----------------------------------------------------------

    @property
    def identifier_normalised(self) -> Optional[str]:
        """The printed identifier reduced to its digits, or ``None``."""
        digits = digits_only(self.identifier_as_printed)
        return digits or None

    def identity(self) -> AccountIdentity:
        """The identity key for this draft, with the tier that produced it.

        Tiers are tried strongest first and the first one that applies wins.
        A structured identifier whose check digit fails is not used for
        identity and does not stop the draft: a failed check digit is quite
        often a correctly-read transcription of an error the document itself
        contains, so it is recorded as a verdict and the next tier is tried.
        """
        verdicts: dict[str, str] = {}

        iban = self._verified(IdentifierKind.iban, self.iban, "iban", verdicts)
        if iban is not None:
            return AccountIdentity(
                key=_build_key(TIER_IBAN, iban),
                tier=TIER_IBAN,
                verdicts=verdicts,
            )

        # Recorded whether or not it is used, because a BIC that failed its
        # structure check is a finding even when an IBAN carried the identity.
        self._verified(IdentifierKind.bic, self.bic, "bic", verdicts)

        routing = self._verified(
            IdentifierKind.aba_routing, self.routing_number, "routing_number", verdicts
        )
        digits = self.identifier_normalised
        masked = is_masked(self.identifier_as_printed)
        institution = _fold(self.institution_name)
        if institution in NON_VALUES:
            # A descriptive placeholder is stored as printed but cannot join.
            institution = ""

        if routing is not None and digits and not masked:
            return AccountIdentity(
                key=_build_key(TIER_ROUTING_ACCOUNT, routing, digits),
                tier=TIER_ROUTING_ACCOUNT,
                verdicts=verdicts,
            )

        if institution and digits and not masked:
            return AccountIdentity(
                key=_build_key(TIER_INSTITUTION_ACCOUNT, institution, digits),
                tier=TIER_INSTITUTION_ACCOUNT,
                verdicts=verdicts,
            )

        if institution and digits and masked:
            return AccountIdentity(
                key=_build_key(TIER_INSTITUTION_MASKED, institution, digits),
                tier=TIER_INSTITUTION_MASKED,
                verdicts=verdicts,
            )

        if self.distinguisher:
            return AccountIdentity(
                key=_build_key(TIER_UNIDENTIFIED, self.distinguisher),
                tier=TIER_UNIDENTIFIED,
                verdicts=verdicts,
            )

        raise AccountIdentityError(
            "nothing in this draft identifies an account: "
            f"iban={self.iban!r}, routing_number={self.routing_number!r}, "
            f"identifier_as_printed={self.identifier_as_printed!r}, "
            f"institution_name={self.institution_name!r}. "
            "If the document genuinely printed no identifier, use "
            "AccountDraft.unidentified() with a distinguisher"
        )

    @staticmethod
    def _verified(
        kind: IdentifierKind,
        value: Optional[str],
        field_name: str,
        verdicts: dict[str, str],
    ) -> Optional[str]:
        """Verify ``value`` and return its normalised form if it may identify.

        Returns ``None`` both when the field is absent and when it is present
        but did not clear the gate, because in both cases the tier cannot be
        built.  The difference between the two is preserved in ``verdicts``,
        which is where it belongs: it is a fact about the document, and a
        reviewer looking at a weakly identified account needs to see that a
        stronger identifier was present and disagreed with itself.
        """
        if value is None:
            return None
        result = verify(kind, value)
        verdicts[field_name] = result.outcome.value
        if not result.passes_gate:
            return None
        if kind is IdentifierKind.bic:
            # Structure-only; there is no check digit and it names an
            # institution rather than an account, so it never carries identity.
            return None
        return result.normalised


def _build_key(tier: str, *components: str) -> str:
    """Join a tier and its components into the stored key.

    The tier leads, so two tiers can never produce the same string even where
    their components coincide.  Components are separated by a unit separator
    rather than by a printable character, so that an institution name
    containing the separator cannot shift the field boundaries and make one
    account look like another.
    """
    if any(_SEP in part for part in components):
        raise AccountIdentityError(
            "an identity component contains the field separator; it would "
            "move the field boundaries and could make two accounts one"
        )
    key = _SEP.join((tier, *components))
    if len(key) > _MAX_IDENTITY_KEY:
        raise AccountIdentityError(
            f"identity key is {len(key)} characters and the column holds "
            f"{_MAX_IDENTITY_KEY}; truncating it would merge every account "
            "sharing the surviving prefix"
        )
    return key


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


def record_account(
    session: "Session",
    run: "IngestionRunHandle",
    draft: AccountDraft,
) -> FinancialAccount:
    """Find or create the account this draft describes, within the run's case.

    Get-or-create rather than insert, because an account is not an observation
    the way a statement period is.  A period belongs to one document; an
    account is the thing many documents are about, and the second statement for
    an account must reach the first statement's row or every join in the
    subsystem breaks.

    ``run.stamp()`` is not used and cannot be: ``FinancialAccount`` carries
    ``first_seen_run_id``, not ``ingestion_run_id``, and ``stamp`` raises on any
    row without the latter.  That is the schema being right rather than
    inconsistent — an account outlives the run that first saw it, and stamping
    it with the current run would rewrite its provenance on every re-ingestion.
    So the case and the run are set here, explicitly, and ``first_seen_run_id``
    is never changed once set.

    On a hit, fields already holding a value are left alone.  Only nulls are
    filled, and a draft that contradicts a stored value has the contradiction
    recorded in metadata rather than applied.  Overwriting would make the row
    describe the most recent document rather than the account, and would do it
    without leaving a trace; raising would stop an ingestion over a holder name
    printed two ways.  Recording is the only one of the three that keeps both
    readings.
    """
    if not isinstance(draft, AccountDraft):
        raise AccountError(
            f"draft must be an AccountDraft, got {type(draft).__name__}"
        )

    identity = draft.identity()

    existing = (
        session.query(FinancialAccount)
        .filter(
            FinancialAccount.case_id == run.case_id,
            FinancialAccount.identity_key == identity.key,
        )
        .one_or_none()
    )
    if existing is not None:
        _reconcile(existing, draft, identity, run)
        session.flush()
        return existing

    account = FinancialAccount(
        case_id=run.case_id,
        identity_key=identity.key,
        institution_name=draft.institution_name,
        identifier_as_printed=draft.identifier_as_printed,
        identifier_normalised=draft.identifier_normalised,
        account_type=draft.account_type,
        holder_name=draft.holder_name,
        currency=draft.currency,
        iban=draft.iban,
        bic=draft.bic,
        routing_number=draft.routing_number,
        first_seen_run_id=run.run_id,
        metadata_=_initial_metadata(draft, identity, run),
    )
    session.add(account)
    # Flushed so that a constraint violation is raised here, where the draft
    # that caused it is still in hand, rather than at some later commit.
    session.flush()
    return account


#: Fields filled from a later document when the first left them empty.
#: ``currency`` is absent deliberately: an account seen in two currencies is a
#: finding, and quietly adopting whichever arrived first would hide it.
_FILLABLE = (
    "institution_name",
    "identifier_as_printed",
    "identifier_normalised",
    "account_type",
    "holder_name",
    "iban",
    "bic",
    "routing_number",
)


def _initial_metadata(
    draft: AccountDraft, identity: AccountIdentity, run: "IngestionRunHandle"
) -> dict:
    """The metadata a new account is created with.

    The tier is recorded here rather than as a column so that adding a tier
    does not require a migration, and — more to the point — so that it does not
    require a new database enum.  The schema's structural test maps every
    ``IN``-list check constraint to the enum that owns it, and a tier vocabulary
    that lives only in this module has nothing to map.
    """
    meta = dict(draft.metadata)
    meta["identity_tier"] = identity.tier
    meta["identity_provisional"] = identity.is_provisional
    if identity.verdicts:
        meta["check_digits"] = dict(identity.verdicts)
    if draft.distinguisher:
        meta["identity_distinguisher"] = draft.distinguisher
    return meta


def _reconcile(
    account: FinancialAccount,
    draft: AccountDraft,
    identity: AccountIdentity,
    run: "IngestionRunHandle",
) -> None:
    """Fill what is missing on an existing account; record what disagrees."""
    meta = dict(account.metadata_ or {})
    filled: list[str] = []
    conflicts: list[dict] = list(meta.get("identity_conflicts", []))

    for name in _FILLABLE:
        offered = getattr(draft, name)
        if offered is None:
            continue
        stored = getattr(account, name)
        if stored is None:
            setattr(account, name, offered)
            filled.append(name)
        elif stored != offered:
            conflicts.append(
                {
                    "field": name,
                    "stored": stored,
                    "offered": offered,
                    "run_id": str(run.run_id),
                }
            )

    if draft.currency is not None and account.currency != draft.currency:
        if account.currency is None:
            account.currency = draft.currency
            filled.append("currency")
        else:
            conflicts.append(
                {
                    "field": "currency",
                    "stored": account.currency,
                    "offered": draft.currency,
                    "run_id": str(run.run_id),
                }
            )

    if identity.verdicts:
        merged = dict(meta.get("check_digits", {}))
        merged.update(identity.verdicts)
        meta["check_digits"] = merged
    if conflicts:
        meta["identity_conflicts"] = conflicts
    if filled:
        contributions = dict(meta.get("enriched_by_runs", {}))
        contributions[str(run.run_id)] = sorted(
            set(contributions.get(str(run.run_id), [])) | set(filled)
        )
        meta["enriched_by_runs"] = contributions

    # Reassigned rather than mutated: SQLAlchemy does not track in-place
    # changes to a JSON column, so a mutated dict is a change that is never
    # written and never noticed.
    account.metadata_ = meta


def read_identity_tier(account: FinancialAccount) -> str:
    """The tier an account's key was built on, for a row read back.

    Returns :data:`TIER_UNIDENTIFIED` for a row whose metadata does not say,
    which is the safe reading: a key of unknown strength must not be treated
    as a strong one.
    """
    tier = (account.metadata_ or {}).get("identity_tier")
    if tier in IDENTITY_TIERS:
        return tier
    return TIER_UNIDENTIFIED
