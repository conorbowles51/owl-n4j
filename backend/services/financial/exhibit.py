"""Which kind of artefact this is: Rule 1006 evidence, or a Rule 107 aid.

A system that produces exhibits has to know which kind it is producing, and the
question got sharper on 1 December 2024, when two amendments took effect on the
same day.

**FRE 1006 as amended** lets a summary, chart or calculation of voluminous
writings be admitted *as substantive evidence* whether or not the underlying
materials were themselves introduced -- provided those materials are
**admissible**, and provided the proponent makes them available to the other
parties at a reasonable time and place.  The amendment also forbids the court to
instruct the jury that such a summary is not evidence.  It is evidence.

**FRE 107**, new the same day, governs illustrative aids: material that helps the
trier of fact understand evidence, which is **not** itself evidence and does not
go to the jury room unless the parties consent or the court orders it.

So there are two categories with different consequences, and no product on the
market distinguishes them.  Drawing the line costs almost
nothing and is worth a great deal, because it is the difference between an
exhibit the jury deliberates over and one it does not.

What this module decides, and what it does not
----------------------------------------------

It does not decide admissibility.  Whether a bank statement comes in under
803(6) is a question for counsel and the court, and a program that answered it
would be worse than one that stayed quiet.  What this module decides is the
narrower question the system is actually competent to answer: **does Loupe's own
record support offering this artefact as a Rule 1006 summary, or does it not?**

That question has two halves, and both must pass.

The first is *what the artefact asserts*.  Rule 1006's own words cover a
"summary, chart, or calculation", so the line is not tables-versus-pictures; a
bar chart of per-counterparty totals is a calculation displayed, and every value
in it traces to arithmetic over the rows.  The line is whether the artefact
proves the **content of the records** or adds something the records do not
contain -- a layout whose adjacency implies relationship, an arrow implying
influence, a doctrine's answer, a typology label.  Those help a trier understand
and are the paradigm of a 107 aid.  :class:`ContentKind` is where that judgment
is recorded, and it is the one input here the system cannot compute: the caller
declares it.  The module's contribution is to make the declaration explicit,
carried with the artefact, and checkable, rather than left implicit in whoever
built the screen.

The second half *is* computed, and it is the half a person gets wrong under time
pressure.  Rule 1006 requires the underlying material to be admissible, and
what this system can stand behind is fixed: **P0-P2 material is the
substrate of a Rule 1006 summary.**  One P3 row in a thousand takes the artefact
out of the category, and a person eyeballing a table will not see it.  A machine
counting classes will, every time.

P3 does not become substrate by being adjudicated
-------------------------------------------------

This is the tempting mistake, and :mod:`services.financial.adjudication` already
refuses it in its own domain: a recorded verdict explains *why* a document's
arithmetic does not close; it does not make it close.  Adjudication admits a row
to the ledger.  It does not turn a figure this system could not verify into one
it could, because the only thing that would do that is fixing the reader and
re-ingesting the document, after which the arithmetic closes on its own and the
class is no longer P3.

So an adjudicated P3 row still puts the artefact in 107, and the tag says so in
as many words.  The honest sentence under cross-examination is "we know why this
one fails and here is the corroboration", not "we decided this one is fine", and
a tag that let adjudication buy its way to 1006 would be the system saying the
second sentence on the investigator's behalf.

Unmet conditions are not the same as the wrong category
-------------------------------------------------------

Making the records available to the other parties is a thing the **proponent
does**, not a property of the data.  An exhibit whose sources have not yet been
disclosed is not thereby an illustrative aid; it is a 1006 summary with an
outstanding obligation, and the obligation is curable by an email.  Collapsing
the two would mislabel the artefact and hide the one item that is actually
actionable.  So the category lives in :attr:`ExhibitTag.rule` and the obligation
lives in :attr:`ExhibitTag.conditions`, and the manifest of exactly what must be
made available is built from the rows
rather than typed by hand, so it cannot omit a document the exhibit rests on.

Voluminousness is flagged, never asserted
-----------------------------------------

Rule 1006 applies to writings "that cannot be conveniently examined in court",
and supplies no number.  Neither does this module.  What it does is notice when
the underlying set is small enough that an opponent could plausibly argue the
records could have been examined directly, and say so as a caveat.
:data:`CONVENIENTLY_EXAMINABLE_ROWS` is a prompt to think, not a test, it is
arbitrary, it is documented as arbitrary, and it is a parameter.  A constant
that pretended to be a legal threshold would be worse than no constant at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

from postgres.models.enums import ProofClass
from services.financial.flow import ClassComposition
from services.financial.money import Money, get_currency, sum_money


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExhibitError(Exception):
    """Base class for every refusal in this module."""


class ExhibitContentError(ExhibitError):
    """A row or a declaration is not something an exhibit can be built from."""


class DuplicateReferenceError(ExhibitError):
    """Two rows claim the same reference identifier.

    The per-row reference is the join between an exhibit and the
    ledger -- the thing that lets an annotation made on an exported page be
    brought back.  Two rows sharing one reference break that join in the
    direction that is hardest to notice: the export looks fine and the round
    trip silently lands on the wrong row.
    """


class DisclosureError(ExhibitError):
    """The manifest and the rows disagree about what this exhibit rests on."""


class ExhibitCurrencyError(ExhibitError):
    """Rows in more than one currency, or in one the caller did not state."""


class ExhibitInvariantError(ExhibitError):
    """A total and its own composition disagree.  Never expected; never hidden.

    The same posture as :class:`~services.financial.flow.FlowInvariantError`.
    An exhibit whose stated total is not the sum of its own rows is the single
    worst thing this subsystem could emit, because it is the artefact a witness
    is asked to stand behind, and the discrepancy would be found by opposing
    counsel with a calculator rather than by us.
    """


# ---------------------------------------------------------------------------
# What the system will stand behind
# ---------------------------------------------------------------------------


#: The classes that can bear a Rule 1006 summary.
#:
#: This is presently the same membership as
#: :data:`~services.financial.proof_class.AUTO_ADMITTED_CLASSES`, and it is
#: still written out separately rather than aliased, because the two say
#: different things and are answerable to different authorities.  That one is
#: about whether a row enters the ledger without a human act; this one is about
#: whether a row can be offered as substantive evidence.  They coincide today.
#: If the ledger's admission rule were ever loosened -- and it is the kind of
#: rule that gets loosened under delivery pressure -- an alias would quietly
#: loosen the evidentiary claim along with it, which is precisely the coupling
#: not to have.
SUMMARY_SUBSTRATE_CLASSES: frozenset[ProofClass] = frozenset(
    {ProofClass.p0, ProofClass.p1, ProofClass.p2}
)


def may_bear_summary(proof_class: ProofClass) -> bool:
    """Whether a row of this class can be substrate for a Rule 1006 summary.

    False for P3 **whether or not it has been adjudicated**, and false for P4.
    See the module docstring: adjudication admits a row to the ledger and does
    not close its arithmetic, and the class is the record of the arithmetic.
    """
    return proof_class in SUMMARY_SUBSTRATE_CLASSES


#: Below this many underlying rows, the tag carries a caveat that an opponent
#: may contest whether the records were voluminous enough for Rule 1006 to be
#: reached at all.
#:
#: The number is arbitrary.  No rule supplies one, courts have found sets of
#: very different sizes to be voluminous, and the test is convenience of
#: examination in court rather than any count.  It exists so that the judgment
#: is surfaced on small exhibits rather than skipped, and it is a parameter on
#: :func:`tag_exhibit` so that a matter with a different sense of the word can
#: set its own.
CONVENIENTLY_EXAMINABLE_ROWS = 25


# ---------------------------------------------------------------------------
# What the artefact asserts
# ---------------------------------------------------------------------------


class ContentKind(str, Enum):
    """What an artefact asserts about the records behind it.

    Ordered by how far it travels from the records.  The first two prove their
    content and can therefore be offered under Rule 1006; the second two add
    something the records do not contain and are illustrative aids.

    This is a declaration, not a measurement.  The system cannot look at a
    rendered artefact and see whether its layout carries meaning, so the caller
    that builds the artefact says which it built.  What the module guarantees is
    that the answer is recorded, travels with the tag, and is visible to a
    reader who wants to disagree with it.
    """

    enumeration = "enumeration"
    """The underlying rows themselves, listed, filtered or sorted.

    The most direct form: every cell in the artefact appears in a record.  A
    reconciled transaction table is this.
    """

    calculation = "calculation"
    """Totals, subtotals, counts and their display, including as a chart.

    Rule 1006 names "calculation" and "chart" in its own text, so a bar chart of
    per-counterparty totals belongs here rather than with the aids: each bar is
    an arithmetic consequence of the rows and nothing else.  What keeps it here
    is completeness -- a top-N chart qualifies only because the remainder is
    drawn rather than dropped, which
    :meth:`~services.financial.flow.MoneyFlow.divergent_chart` enforces by
    checking that the bars sum to the cards.  A chart that quietly omitted a
    residue would be selecting for emphasis, and selection for emphasis is
    :attr:`arrangement`.
    """

    arrangement = "arrangement"
    """Figures positioned so that place, adjacency or connection carries meaning.

    A network diagram, a timeline, an entity graph.  The values may each be
    exact and the picture still asserts something the records do not: that these
    two parties belong side by side, that this edge matters.  That assertion is
    the aid's whole usefulness and the reason it is an aid.
    """

    interpretation = "interpretation"
    """A conclusion the records do not state.

    A tracing doctrine's answer, a typology label such as structuring or
    pass-through, a characterisation of a party's conduct.
    :mod:`services.financial.tracing` keeps the
    doctrine named and the alternatives visible for exactly this reason: the
    answer is a consequence of a legal rule applied to the records, not a fact
    in them.
    """


#: Weakest last.  Written out rather than derived from the member order, so that
#: reordering the class body cannot silently change what "weakest" means.
_CONTENT_ORDER: tuple[ContentKind, ...] = (
    ContentKind.enumeration,
    ContentKind.calculation,
    ContentKind.arrangement,
    ContentKind.interpretation,
)

_CONTENT_RANK: Mapping[ContentKind, int] = {
    kind: index for index, kind in enumerate(_CONTENT_ORDER)
}

#: The kinds that prove the content of the records rather than adding to it.
SUMMARISING_CONTENT: frozenset[ContentKind] = frozenset(
    {ContentKind.enumeration, ContentKind.calculation}
)


def weakest_content(kinds: Iterable[ContentKind]) -> ContentKind:
    """The furthest-travelled kind among ``kinds``.

    A compound exhibit -- a table with a flow diagram beside it on the same
    page -- is characterised by its weakest part, because the page is offered
    as one thing and the diagram does not stop asserting what it asserts by
    being next to a table.  Splitting the page into two exhibits is the way to
    get the table admitted as evidence, and this function's job is to make that
    consequence visible before the page is printed rather than at the bench.

    :raises ExhibitContentError: if ``kinds`` is empty or holds a non-member.
    """
    worst: Optional[ContentKind] = None
    for kind in kinds:
        if not isinstance(kind, ContentKind):
            raise ExhibitContentError(
                f"{kind!r} is not a ContentKind; what an exhibit asserts is a "
                "declaration from a fixed vocabulary, not free text"
            )
        if worst is None or _CONTENT_RANK[kind] > _CONTENT_RANK[worst]:
            worst = kind
    if worst is None:
        raise ExhibitContentError(
            "an exhibit made of no parts asserts nothing; there is no content "
            "kind to take"
        )
    return worst


class SummaryRule(str, Enum):
    """Which of the two December 2024 categories the artefact falls in."""

    rule_1006 = "rule_1006"
    """A summary, chart or calculation offered as substantive evidence.

    Goes to the jury room, and the court may not instruct that it is not
    evidence.  Requires admissible underlying material made available to the
    other parties.
    """

    rule_107 = "rule_107"
    """An illustrative aid.

    Helps the trier understand evidence and is not itself evidence.  Does not go
    to the jury room absent consent or an order.  This is not a demotion or a
    failure state: most of what a forensic tool draws is properly an aid, and
    the harm this module exists to prevent is an aid being offered as though it
    were the other thing.
    """


# ---------------------------------------------------------------------------
# The sentences the tag is built from
# ---------------------------------------------------------------------------
#
# Constants rather than inline strings so that a caller, a test or a screen can
# key on the ground without matching prose.  Each is a complete sentence; where
# there is detail it is appended in parentheses.

REASON_CONTENT_IS_AN_AID = (
    "the artefact asserts more than the content of the records, so it helps the "
    "trier understand evidence rather than proving what the evidence says"
)
REASON_SUBSTRATE_BELOW_SUMMARY = (
    "some underlying rows are not material this system can stand behind as "
    "substantive evidence"
)
REASON_SUMMARISES_ADMISSIBLE_RECORDS = (
    "every underlying row is P0-P2 and the artefact proves the content of those "
    "records"
)

CONDITION_MAKE_AVAILABLE = (
    "the underlying records must be made available to the other parties at a "
    "reasonable time and place before this may be offered"
)

CAVEAT_UNDISCLOSED_SOURCES = (
    "the aid rests on documents this system has no record of having been "
    "disclosed"
)
CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS = (
    "the underlying set is small enough that whether it could conveniently have "
    "been examined in court is contestable"
)
CAVEAT_SINGLE_DOCUMENT = (
    "everything summarised comes from one document, which may be offered "
    "directly instead"
)
CAVEAT_ASSERTIONS_PRESENT = (
    "some rows are P4 assertions from unstructured material, which never enter "
    "the ledger and are shown as claims"
)
CAVEAT_ADJUDICATION_RELIED_ON = (
    "some rows are P3 admitted by a recorded adjudication, which explains why "
    "the arithmetic does not close and does not make it close"
)
CAVEAT_UNADJUDICATED_P3 = (
    "some rows are P3 with no recorded adjudication, which is below the ledger's "
    "own admission rule"
)
CAVEAT_MIXED_COMPOSITION = (
    "the rows rest on more than one proof class, so the weakest qualifies the "
    "whole"
)


# ---------------------------------------------------------------------------
# The documents behind the exhibit
# ---------------------------------------------------------------------------


#: A SHA-256 digest as this system writes it: exactly 64 lower-case hex digits.
#:
#: Anchored with ``\A`` and ``\Z`` rather than ``^`` and ``$`` because ``$``
#: also matches before a trailing newline, and a digest read from a file with
#: the newline still attached would pass a ``$``-anchored check and then fail to
#: match the same document's digest computed anywhere else.
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One document the exhibit rests on, and whether it has been disclosed.

    The digest is required rather than optional.  Every artefact in this system
    carries a path back to the SHA-256 of the original bytes, and an exhibit is
    the artefact where that path is finally spent: FRE 902(14) makes a data copy
    self-authenticating on hash certification, and a manifest that named
    documents without their digests would hand the other side a list to argue
    about instead of a set of facts to check.
    """

    identifier: str
    """How this document is known in the matter.  Whatever the case names it."""

    sha256: str
    """Digest of the original bytes, lower-case hex."""

    made_available: bool = False
    """Whether the original or a duplicate has been put where the other parties
    can examine and copy it.

    Defaults to false, so that a caller who has not thought about disclosure
    produces an exhibit that says the obligation is outstanding rather than one
    that silently claims it is met.  The safe default is the one that
    understates.
    """

    availability_note: Optional[str] = None
    """Where and when it was made available.  Required once it has been.

    "Produced" with no particulars is not a record of anything, and the
    particulars are what a proponent has to state if the timing is challenged.
    """

    def __post_init__(self) -> None:
        if not self.identifier or not self.identifier.strip():
            raise DisclosureError(
                "a source document needs an identifier; an exhibit that cannot "
                "name what it rests on cannot make it available either"
            )
        if not isinstance(self.sha256, str) or not _SHA256.match(self.sha256):
            raise DisclosureError(
                f"{self.identifier}: {self.sha256!r} is not a SHA-256 digest in "
                "the form this system writes them, 64 lower-case hex digits"
            )
        if self.made_available:
            if not self.availability_note or not self.availability_note.strip():
                raise DisclosureError(
                    f"{self.identifier}: a document recorded as made available "
                    "must say where and when, since that is the part of the "
                    "obligation that can be challenged"
                )
        elif self.availability_note is not None:
            raise DisclosureError(
                f"{self.identifier}: an availability note on a document that has "
                "not been made available reads as though it had been"
            )


@dataclass(frozen=True, slots=True)
class ExhibitRow:
    """One row of the underlying set, as an exhibit needs to see it.

    Deliberately not a ledger entry.  This carries the four things the
    evidentiary question turns on -- what it is called, how well it is proved,
    which document it came from, and how much -- and nothing else, so that the
    tagging logic cannot come to depend on a field that some callers have and
    others do not.
    """

    reference: str
    """The stable per-row key.

    V1 carried one and Loupe lost it; without it a reviewer's note on row 412
    of an exported PDF refers to nothing.
    """

    proof_class: ProofClass
    amount: Money
    document: str
    """Identifier of the :class:`SourceDocument` this row was read from."""

    adjudicated: bool = False
    """Whether a P3 row was admitted to the ledger by a recorded adjudication.

    Meaningful only for P3, and refused on any other class: on a P0 row it would
    imply a doubt that the arithmetic does not support, and on a P4 row it would
    imply an admission that never happened.
    """

    def __post_init__(self) -> None:
        if not self.reference or not self.reference.strip():
            raise ExhibitContentError(
                "an exhibit row needs a reference; without one the row cannot be "
                "pointed at from the export or found again in the ledger"
            )
        if not self.document or not self.document.strip():
            raise ExhibitContentError(
                f"{self.reference}: a row must name the document it was read "
                "from, since that document is what has to be made available"
            )
        if not isinstance(self.proof_class, ProofClass):
            raise ExhibitContentError(
                f"{self.reference}: {self.proof_class!r} is not a ProofClass; "
                "class is assigned mechanically and is not free text"
            )
        if not isinstance(self.amount, Money):
            raise ExhibitContentError(
                f"{self.reference}: amount is "
                f"{type(self.amount).__name__}, not Money"
            )
        if self.adjudicated and self.proof_class is not ProofClass.p3:
            raise ExhibitContentError(
                f"{self.reference}: only a P3 row is admitted by adjudication, "
                f"so recording one on a {self.proof_class.value} row states "
                "something that did not happen"
            )


@dataclass(frozen=True, slots=True)
class Disclosure:
    """Exactly what must be made available, and what still has to be.

    A Rule 1006 export has to carry a manifest of exactly what must be made
    available.  This is that manifest, and it is derived from the rows
    rather than supplied, so that it cannot omit a document the exhibit rests
    on -- which is the only way this list is ever wrong in practice, and the way
    that is fatal.
    """

    documents: tuple[SourceDocument, ...]

    @property
    def outstanding(self) -> tuple[SourceDocument, ...]:
        """Those not yet made available, in identifier order."""
        return tuple(d for d in self.documents if not d.made_available)

    @property
    def available(self) -> tuple[SourceDocument, ...]:
        return tuple(d for d in self.documents if d.made_available)

    @property
    def is_complete(self) -> bool:
        return not self.outstanding

    def describe(self) -> str:
        if not self.documents:
            return "no documents"
        outstanding = self.outstanding
        head = (
            f"{len(self.documents)} document"
            f"{'' if len(self.documents) == 1 else 's'}"
        )
        if not outstanding:
            return f"{head}, all made available"
        return (
            f"{head}, {len(outstanding)} not yet made available: "
            + ", ".join(d.identifier for d in outstanding)
        )


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def _composition(rows: Sequence[ExhibitRow]) -> ClassComposition:
    """Counts and subtotals per proof class.

    Reuses :class:`~services.financial.flow.ClassComposition` rather than
    growing a second one here.  There is one question about composition
    and there should be one answer to it; two structures with the same fields
    would drift, and the one that drifted would be the one a reader had not
    looked at recently.  Ordering comes from that class's own ``classes``
    property, so strongest-first means the same thing in an exhibit as in a
    flow figure.

    No currency parameter, and so no total here: this returns per-class
    subtotals only, each in the currency of the rows that produced it.  The
    exhibit's own total is formed in :func:`tag_exhibit` with the currency the
    caller stated, which is the one place a currency can be checked against
    something rather than assumed from the data it is meant to be checking.
    """
    counts: dict[ProofClass, int] = {}
    amounts: dict[ProofClass, Money] = {}
    for row in rows:
        counts[row.proof_class] = counts.get(row.proof_class, 0) + 1
        running = amounts.get(row.proof_class)
        amounts[row.proof_class] = (
            row.amount if running is None else running + row.amount
        )
    return ClassComposition(counts=counts, amounts=amounts)


def _build_disclosure(
    rows: Sequence[ExhibitRow],
    documents: Sequence[SourceDocument],
) -> Disclosure:
    """Match the manifest against what the rows actually cite.

    Three ways this can be wrong, and all three are refused rather than
    repaired, because each of them means the caller believes something untrue
    about the exhibit:

    A document named twice.  The second entry may disagree with the first about
    digest or availability, and there is no principled way to choose between
    them.

    A row citing a document the manifest does not list.  This is the fatal
    one.  It produces an exhibit that rests on material the other side was
    never told about, and it does so silently.

    A manifest entry no row cites.  Less dangerous and still wrong: it
    overstates what the exhibit rests on, and an obligation recorded as
    outstanding against a document that is not in fact underlying material
    would send someone to produce papers this exhibit does not need.
    """
    by_identifier: dict[str, SourceDocument] = {}
    for document in documents:
        if not isinstance(document, SourceDocument):
            raise DisclosureError(
                f"{type(document).__name__} is not a SourceDocument; the "
                "manifest is a list of documents with digests, not of names"
            )
        if document.identifier in by_identifier:
            raise DisclosureError(
                f"{document.identifier} is listed twice in the manifest; the "
                "two entries may disagree about digest or availability and "
                "there is no honest way to pick one"
            )
        by_identifier[document.identifier] = document

    cited = {row.document for row in rows}

    missing = sorted(cited - set(by_identifier))
    if missing:
        raise DisclosureError(
            f"rows cite {', '.join(missing)}, which the manifest does not "
            "list; an exhibit that rests on a document nobody has been told "
            "about is the failure this manifest exists to prevent"
        )

    unused = sorted(set(by_identifier) - cited)
    if unused:
        raise DisclosureError(
            f"the manifest lists {', '.join(unused)}, which no row cites; a "
            "manifest that overstates what the exhibit rests on sends someone "
            "to produce papers this exhibit does not need"
        )

    return Disclosure(
        documents=tuple(
            by_identifier[identifier] for identifier in sorted(by_identifier)
        )
    )


# ---------------------------------------------------------------------------
# The tag
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExhibitTag:
    """What this artefact is, what it rests on, and what is still owed.

    Everything a Rule 1006 export has to carry, in one object that
    travels with the artefact: the complete underlying row set, the documents
    those rows came from with hashes, the proof-class composition, and the
    arithmetic demonstrating internal consistency.  The one thing it does not
    carry is the filter and sort state that produced the row set, because that
    belongs to whatever built the row set and this module would have to be told
    it rather than know it -- see the module docstring.

    The reasons, conditions and caveats are three different kinds of sentence
    and are kept in three different fields on purpose.  A *reason* says why the
    artefact is in the category it is in.  A *condition* is an obligation the
    proponent has not yet met and can meet.  A *caveat* is something an
    opponent may raise that no act of the proponent's will make go away.
    Flattening them into one list of warnings, which is what a screen wants to
    do, loses the distinction that tells a reader which items are work and
    which are argument.
    """

    rule: SummaryRule
    content: ContentKind
    currency: str
    rows: tuple[ExhibitRow, ...]
    total: Money
    disclosure: Disclosure
    composition: ClassComposition
    reasons: tuple[str, ...]
    conditions: tuple[str, ...]
    caveats: tuple[str, ...]
    voluminous_threshold: int

    def __post_init__(self) -> None:
        if not self.rows:
            raise ExhibitContentError(
                "an exhibit with no rows summarises nothing; a total of zero "
                "meaning 'no rows' is indistinguishable on the page from a "
                "total of zero meaning 'the money nets out'"
            )

        stated = sum_money((row.amount for row in self.rows), self.currency)
        if stated != self.total:
            raise ExhibitInvariantError(
                f"the exhibit total {self.total.format()} is not the sum of its "
                f"own rows {stated.format()}"
            )

        charted = sum_money(
            self.composition.amounts.values(), self.currency
        )
        if charted != self.total:
            raise ExhibitInvariantError(
                f"the exhibit total {self.total.format()} is not the sum of its "
                f"proof-class subtotals {charted.format()}"
            )

        counted = sum(self.composition.counts.values())
        if counted != len(self.rows):
            raise ExhibitInvariantError(
                f"the composition accounts for {counted} row"
                f"{'' if counted == 1 else 's'} against "
                f"{len(self.rows)} in the exhibit"
            )

        if not self.reasons:
            raise ExhibitInvariantError(
                "a tag must say why the artefact is in the category it is in; "
                "an unexplained category is one a witness cannot defend"
            )

    # -- What it is ---------------------------------------------------------

    @property
    def is_evidence(self) -> bool:
        """Whether this goes to the jury room as evidence in its own right.

        True only under Rule 1006.  Deliberately a property rather than a
        stored field, so that it cannot be set to disagree with
        :attr:`rule`.
        """
        return self.rule is SummaryRule.rule_1006

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def references(self) -> tuple[str, ...]:
        """Every row reference, in row order.

        The join back to the ledger.  In row order rather than
        sorted, because the order the rows are in is the order they appear on
        the page, and a reviewer's note on the fourth line means the fourth
        line.
        """
        return tuple(row.reference for row in self.rows)

    @property
    def is_offerable(self) -> bool:
        """Whether everything within the proponent's control has been done.

        A Rule 1006 summary with an outstanding disclosure obligation is still
        a Rule 1006 summary; it is just not one that may be offered yet.  An
        aid has no such precondition, so this is true for every Rule 107 tag.
        Caveats do not bear on it: they are arguments, and an exhibit does not
        become unofferable because someone may argue about it.
        """
        return not self.conditions

    def describe(self) -> str:
        head = (
            f"{self.rule.value}: {self.row_count} row"
            f"{'' if self.row_count == 1 else 's'} "
            f"totalling {self.total.format()} "
            f"({self.composition.describe()})"
        )
        parts = [head]
        if self.conditions:
            parts.append(f"outstanding: {'; '.join(self.conditions)}")
        if self.caveats:
            parts.append(f"contestable: {'; '.join(self.caveats)}")
        return ". ".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def tag_exhibit(
    rows: Sequence[ExhibitRow],
    documents: Sequence[SourceDocument],
    *,
    content: ContentKind,
    currency: str,
    voluminous_threshold: int = CONVENIENTLY_EXAMINABLE_ROWS,
) -> ExhibitTag:
    """Decide whether this artefact is Rule 1006 evidence or a Rule 107 aid.

    Two independent grounds send an artefact to Rule 107, and **both are
    recorded when both hold**.  A tag that stopped at the first would tell a
    proponent that fixing one thing would move the artefact, when fixing it
    would leave the artefact exactly where it was.

    :param rows: the complete underlying set, in the order it appears.
    :param documents: the manifest, which must name every document the rows
        cite and no others.
    :param content: what the artefact asserts.  A declaration by the caller
        that builds it; see :class:`ContentKind`.
    :param currency: the currency the total is stated in.  Checked against the
        rows rather than inferred from them.
    :param voluminous_threshold: below this many rows, a caveat is added.  Zero
        suppresses it, for a caller who has satisfied themselves on the point.

    :raises ExhibitContentError: no rows, or a declaration outside the
        vocabulary.
    :raises ExhibitCurrencyError: an unknown currency, or rows not all in it.
    :raises DuplicateReferenceError: two rows sharing a reference.
    :raises DisclosureError: the manifest and the rows disagree.
    """
    if not isinstance(content, ContentKind):
        raise ExhibitContentError(
            f"{content!r} is not a ContentKind; what an exhibit asserts is a "
            "declaration from a fixed vocabulary, not free text"
        )
    if not isinstance(voluminous_threshold, int) or isinstance(
        voluminous_threshold, bool
    ):
        raise ExhibitContentError(
            f"voluminous_threshold is {type(voluminous_threshold).__name__}, "
            "not an int; it is a row count"
        )
    if voluminous_threshold < 0:
        raise ExhibitContentError(
            f"voluminous_threshold {voluminous_threshold} is negative; a set "
            "cannot have fewer than no rows, so the caveat could never fire "
            "and the number would read as though it had been considered"
        )

    rows = tuple(rows)
    if not rows:
        raise ExhibitContentError(
            "an exhibit with no rows summarises nothing; a total of zero "
            "meaning 'no rows' is indistinguishable on the page from a total "
            "of zero meaning 'the money nets out'"
        )
    for index, row in enumerate(rows):
        if not isinstance(row, ExhibitRow):
            raise ExhibitContentError(
                f"row {index} is {type(row).__name__}, not an ExhibitRow"
            )

    try:
        resolved = get_currency(currency)
    except Exception as exc:  # UnknownCurrencyError, and anything it grows into
        raise ExhibitCurrencyError(
            f"{currency!r} is not a currency this system knows, so no exhibit "
            "total can be formed in it"
        ) from exc
    others = sorted({row.amount.currency for row in rows} - {resolved.code})
    if others:
        raise ExhibitCurrencyError(
            f"rows in {', '.join(others)} were supplied for an exhibit stated "
            f"in {resolved.code}; money in different currencies cannot be "
            "added, and dropping the others would produce a total that looks "
            "complete and is not"
        )

    seen: set[str] = set()
    for row in rows:
        if row.reference in seen:
            raise DuplicateReferenceError(
                f"{row.reference} is used by more than one row; the reference "
                "is what an annotation on the exported page comes back to, and "
                "a repeated one lands the round trip on the wrong row without "
                "anything looking wrong"
            )
        seen.add(row.reference)

    disclosure = _build_disclosure(rows, documents)
    composition = _composition(rows)
    total = sum_money((row.amount for row in rows), resolved.code)

    # -- The two grounds ----------------------------------------------------

    reasons: list[str] = []

    aid_by_content = content not in SUMMARISING_CONTENT
    if aid_by_content:
        reasons.append(f"{REASON_CONTENT_IS_AN_AID} ({content.value})")

    below = tuple(row for row in rows if not may_bear_summary(row.proof_class))
    if below:
        weak = sorted({row.proof_class.value for row in below})
        reasons.append(
            f"{REASON_SUBSTRATE_BELOW_SUMMARY} ({len(below)} row"
            f"{'' if len(below) == 1 else 's'} at {', '.join(weak)})"
        )

    rule = (
        SummaryRule.rule_107
        if (aid_by_content or below)
        else SummaryRule.rule_1006
    )
    if rule is SummaryRule.rule_1006:
        reasons.append(REASON_SUMMARISES_ADMISSIBLE_RECORDS)

    # -- Obligations, which are curable -------------------------------------

    conditions: list[str] = []
    caveats: list[str] = []

    if not disclosure.is_complete:
        if rule is SummaryRule.rule_1006:
            # Not a downgrade.  Making records available is an act of the
            # proponent's, not a property of the data, and is cured by an
            # email; calling it a change of category would mislabel the
            # artefact and bury the one item that can be acted on.
            conditions.append(
                f"{CONDITION_MAKE_AVAILABLE} ({disclosure.describe()})"
            )
        else:
            # Rule 107 imposes no such requirement, so this is not an
            # obligation.  It is still worth saying, because an aid built on
            # undisclosed material tends to be an aid someone will later want
            # to offer as a summary.
            caveats.append(
                f"{CAVEAT_UNDISCLOSED_SOURCES} ({disclosure.describe()})"
            )

    # -- Arguments, which are not ------------------------------------------
    #
    # Fixed order, strongest-bearing first, so that two tags over the same
    # material read the same way and a diff between them is legible.

    if rule is SummaryRule.rule_1006:
        if len(rows) < voluminous_threshold:
            caveats.append(
                f"{CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS} "
                f"({len(rows)} rows, below {voluminous_threshold})"
            )
        if len(disclosure.documents) == 1:
            caveats.append(
                f"{CAVEAT_SINGLE_DOCUMENT} "
                f"({disclosure.documents[0].identifier})"
            )

    assertions = sum(
        1 for row in rows if row.proof_class is ProofClass.p4
    )
    if assertions:
        caveats.append(f"{CAVEAT_ASSERTIONS_PRESENT} ({assertions})")

    adjudicated = sum(1 for row in rows if row.adjudicated)
    if adjudicated:
        caveats.append(f"{CAVEAT_ADJUDICATION_RELIED_ON} ({adjudicated})")

    unadjudicated = sum(
        1
        for row in rows
        if row.proof_class is ProofClass.p3 and not row.adjudicated
    )
    if unadjudicated:
        caveats.append(f"{CAVEAT_UNADJUDICATED_P3} ({unadjudicated})")

    if not composition.is_uniform:
        caveats.append(
            f"{CAVEAT_MIXED_COMPOSITION} ({composition.describe()})"
        )

    return ExhibitTag(
        rule=rule,
        content=content,
        currency=resolved.code,
        rows=rows,
        total=total,
        disclosure=disclosure,
        composition=composition,
        reasons=tuple(reasons),
        conditions=tuple(conditions),
        caveats=tuple(caveats),
        voluminous_threshold=voluminous_threshold,
    )
