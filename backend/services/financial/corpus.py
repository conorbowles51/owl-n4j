"""Run the whole corpus through the reader and say what came out.

Everything else in this package reasons about one document.  This module is
the only thing that looks at all of them at once, and it exists because the
claims the rest of the package rests on are *measurements*, not arguments.
That 182 documents close under one dialect and 2 under the other, that 12
close under neither, that the deposits/withdrawals pair travels under six
different names — none of that is deducible.  It was counted, and a number
that was counted once and then written into a docstring is a number that
starts drifting the moment anyone touches the reader.

So the point of a harness is not to demonstrate that the reader works.  It is
to fail when a change alters what the reader sees, *including* changes that
look like improvements.  Six documents in this corpus were re-extracted with
a newer toolchain and lost a balance identity that had closed to the cent;
nothing in the pipeline noticed, because a document that stops carrying a
testable control block does not raise an error, it simply stops being
checked.  :meth:`CorpusReport.disagreements` is that finding turned into a
standing check.

Three constraints shape the design.

**The corpus is evidence and is not in this repository.**  It cannot be
committed, so the harness has to be useful when it is absent rather than
merely inert.  Discovery raises :class:`CorpusUnavailableError`, which a test
turns into a skip; the classification logic underneath is pure and takes a
mapping, so it is exercised on synthetic blocks that contain no case content
whatsoever.  The part that is tested everywhere and the part that needs the
evidence are deliberately different functions.

**A failure has to be reportable, not fatal.**  A survey that aborts on the
first unreadable figure tells you about one document and nothing about the
other 325.  So an unreadable control block is an *outcome*
(:attr:`CorpusOutcome.unreadable`) that is counted and named, in the same
census as every other outcome.  There are none in the corpus today, which is
a fact the expectation asserts; the first one will surface as a count that
moved rather than as a stack trace.

**Nothing here decides anything.**  This module classifies and counts.  It
does not choose a convention for a document — :func:`.infer_convention`
proposes and a caller records — it does not nominate a primary among
re-extractions, and it does not explain a failure.  A harness that could
adjudicate its own results would be marking its own homework, and the
separation is what lets a test assert that the twelve documents this module
finds failing are exactly the twelve that
:mod:`services.financial.adjudication` has verdicts for.  Either set moving
independently of the other is the thing worth catching: a reader fix that
makes a document close leaves a verdict stale, and a regression that breaks a
new one leaves a failure unexplained.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, Mapping, Optional, Sequence

from postgres.models.enums import TotalsConvention
from services.financial.money import Money
from services.financial.statement_totals import (
    FIELD_ALIASES,
    StatementTotalsError,
    TotalsRole,
    infer_convention,
    read_header_totals,
)


class CorpusError(Exception):
    """Something went wrong surveying a corpus."""


class CorpusUnavailableError(CorpusError):
    """The corpus is not present on this machine.

    Raised rather than returning an empty report, because an empty report and
    a corpus of zero documents are the same object and mean opposite things.
    A caller that wants to skip catches this; a caller that expected the
    evidence to be there gets told it is not.
    """


class MalformedExtractionError(CorpusError):
    """An extraction file is not shaped like an extraction file.

    Distinct from an unreadable *figure*, which is a finding about a document.
    This is a finding about the file: it has no control block at all, or one
    that is not a mapping.  That is a fault in whatever produced it, and it is
    not classified alongside documents whose blocks were read.
    """


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

#: Names beginning with this are the corpus's own bookkeeping — inventories,
#: queues, audit summaries, an archive of a superseded extraction run, an OCR
#: cache — and are not extractions.  The corpus already uses this convention
#: throughout, so honouring it is more durable than a hand-maintained list of
#: names to exclude, which silently stops excluding the moment a new one
#: appears.
PRIVATE_PREFIX = "_"

#: The key holding the statement's printed control totals.
HEADER_TOTALS_FIELD = "header_totals"

#: The key naming the institution.  Read verbatim and never normalised: the
#: values are raw extractor output and include things like
#: ``'Capital One 360 (subpoena response)'`` and ``'see statement'``, so
#: mapping them onto a controlled vocabulary would be manufacturing a fact
#: about the document rather than reading one.  It is carried because drift in
#: this reader is overwhelmingly per-institution, and a census that cannot
#: group by institution cannot localise a defect.
INSTITUTION_FIELD = "bank"


@dataclass(frozen=True, slots=True)
class ExtractionFile:
    """One extraction on disk: which batch, which document, which path.

    The document identifier is the filename stem, and that is a property of
    how the corpus is laid out rather than an assumption about it — a document
    re-extracted in a later batch keeps its stem, which is exactly what makes
    re-extraction detectable by grouping.
    """

    batch: str
    document: str
    path: Path


def iter_extraction_files(root: Path) -> Iterator[ExtractionFile]:
    """Walk a corpus root, yielding extractions in a stable order.

    Batches are the immediate subdirectories; extractions are the ``.json``
    files inside them.  Both skip :data:`PRIVATE_PREFIX` names.  Sorted at
    both levels so that two runs on the same tree produce byte-identical
    reports, which is what makes a diff between two reports meaningful.
    """
    if not root.exists():
        raise CorpusUnavailableError(
            f"no corpus at {root}; the ET-Fraud extractions are case material "
            "and are not committed to this repository"
        )
    if not root.is_dir():
        raise CorpusUnavailableError(f"corpus root {root} is not a directory")

    for batch in sorted(p for p in root.iterdir() if p.is_dir()):
        if batch.name.startswith(PRIVATE_PREFIX):
            continue
        for path in sorted(batch.glob("*.json")):
            if path.name.startswith(PRIVATE_PREFIX):
                continue
            yield ExtractionFile(
                batch=batch.name, document=path.stem, path=path
            )


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


class CorpusOutcome(str, Enum):
    """What the survey concluded about one extraction's control block.

    The five classified outcomes partition the corpus exactly, which is the
    property that makes the counts an assertion rather than a summary: they
    must add to the file count, so a document cannot quietly move between
    categories without the total noticing.
    """

    unreadable = "unreadable"
    """A figure in the block is not a monetary quantity.

    Counted rather than raised.  The document is named in the report with the
    reader's own diagnosis, and the survey continues.
    """

    not_testable = "not_testable"
    """The block lacks both balances, or lacks any flow figure.

    Not a defect on its own — plenty of documents in a disclosure are not bank
    statements and print no control block.  It is a defect when a document
    that *was* testable becomes untestable, which is why the outcome is
    recorded per extraction rather than per document.
    """

    magnitude = "magnitude"
    """Closes only under the subtracting dialect.  The common case."""

    signed = "signed"
    """Closes only under the adding dialect: outflows printed negative.

    Two documents in the ET-Fraud corpus.  Both are exact to the cent under
    this reading and miss by roughly $280,000 under the other.
    """

    ambiguous = "ambiguous"
    """Closes under both dialects, so it evidences neither.

    Happens when every printed outflow is zero.  The block is arithmetically
    fine and carries no information about its own convention.
    """

    unexplained = "unexplained"
    """Testable, and closes under neither dialect.

    The interesting outcome, and the only one that implies something was
    mis-read.  Each of these owes an explanation; see
    :mod:`services.financial.adjudication`.
    """


#: The outcomes reached by running the identity, as opposed to by failing to.
#: Their sum is the testable count.
TESTED_OUTCOMES: tuple[CorpusOutcome, ...] = (
    CorpusOutcome.magnitude,
    CorpusOutcome.signed,
    CorpusOutcome.ambiguous,
    CorpusOutcome.unexplained,
)


@dataclass(frozen=True, slots=True)
class DocumentReading:
    """What one extraction's control block turned out to be.

    Carries identifiers, amounts, field names and an institution.  It does not
    carry an account number, an account holder, a transaction description or a
    date, and the type has no field to put them in — the same structural
    guarantee :class:`~services.financial.adjudication.Adjudication` makes,
    for the same reason: this record is destined for a report that will be
    read, pasted and mailed around, and case content must not be able to
    travel with it by accident.

    Both deltas are kept, not just the failing one.  The magnitude delta is
    the residual an adjudication has to account for; the signed delta is what
    distinguishes a document in the other dialect from a document that is
    simply wrong, and a near miss from a wild one.
    """

    document: str
    batch: str
    outcome: CorpusOutcome
    currency: str
    institution: Optional[str]
    balancing: frozenset[TotalsConvention]
    delta_magnitude: Optional[Money]
    delta_signed: Optional[Money]
    unmapped: tuple[str, ...]
    signs_coherent: bool
    unreadable_reason: Optional[str] = None

    @property
    def is_testable(self) -> bool:
        return self.outcome in TESTED_OUTCOMES

    @property
    def residual(self) -> Optional[Money]:
        """The amount an explanation of this document has to account for.

        The magnitude delta, under the name the adjudication records use, so
        that a verdict's recorded residual can be checked against the corpus
        without the caller having to know which dialect the residual was
        measured in.
        """
        return self.delta_magnitude


# ---------------------------------------------------------------------------
# Classifying one extraction
# ---------------------------------------------------------------------------


def read_extraction(
    payload: Mapping[str, object],
    *,
    document: str,
    batch: str,
    currency: str,
    aliases: Mapping[TotalsRole, Sequence[str]] = FIELD_ALIASES,
) -> DocumentReading:
    """Classify one already-parsed extraction.  Pure: no I/O, no database.

    The currency is a required argument with no default.  No document in the
    corpus states its own currency, so the fact has to come from somewhere,
    and the only honest place is the caller who knows what disclosure this is.
    Defaulting to USD here would put a guess about a case into a library.

    A missing or non-mapping ``header_totals`` raises rather than classifying
    as :attr:`~CorpusOutcome.not_testable`, because those are different facts.
    A statement that prints no control block and an extraction that lost the
    block it printed both end up untestable, but only the second is a bug, and
    a survey that merges them cannot report the second.
    """
    if not isinstance(payload, Mapping):
        raise MalformedExtractionError(
            f"{document}: extraction is {type(payload).__name__}, not a mapping"
        )
    if not document.strip():
        raise MalformedExtractionError("a reading must name its document")
    if not batch.strip():
        raise MalformedExtractionError(
            f"{document}: a reading must name the batch it came from, because "
            "the same document is extracted more than once and the outcomes "
            "differ"
        )
    if HEADER_TOTALS_FIELD not in payload:
        raise MalformedExtractionError(
            f"{document}: no {HEADER_TOTALS_FIELD!r} key; an extraction that "
            "lost its control block is a different fact from a document that "
            "never printed one, and only the first is a defect"
        )

    raw = payload[HEADER_TOTALS_FIELD]
    if not isinstance(raw, Mapping):
        raise MalformedExtractionError(
            f"{document}: {HEADER_TOTALS_FIELD} is "
            f"{type(raw).__name__}, not a mapping"
        )

    institution = payload.get(INSTITUTION_FIELD)
    if institution is not None and not isinstance(institution, str):
        institution = None

    def reading(
        outcome: CorpusOutcome,
        *,
        balancing: frozenset[TotalsConvention] = frozenset(),
        delta_magnitude: Optional[Money] = None,
        delta_signed: Optional[Money] = None,
        unmapped: tuple[str, ...] = (),
        signs_coherent: bool = True,
        unreadable_reason: Optional[str] = None,
    ) -> DocumentReading:
        return DocumentReading(
            document=document,
            batch=batch,
            outcome=outcome,
            currency=currency,
            institution=institution,
            balancing=balancing,
            delta_magnitude=delta_magnitude,
            delta_signed=delta_signed,
            unmapped=unmapped,
            signs_coherent=signs_coherent,
            unreadable_reason=unreadable_reason,
        )

    try:
        inference = infer_convention(raw, currency=currency, aliases=aliases)
        totals = read_header_totals(
            raw,
            currency=currency,
            convention=TotalsConvention.magnitude,
            aliases=aliases,
        )
    except StatementTotalsError as exc:
        return reading(CorpusOutcome.unreadable, unreadable_reason=str(exc))

    if not inference.testable:
        outcome = CorpusOutcome.not_testable
    elif inference.is_ambiguous:
        outcome = CorpusOutcome.ambiguous
    elif inference.is_evidenced:
        outcome = (
            CorpusOutcome.signed
            if inference.proposed is TotalsConvention.signed
            else CorpusOutcome.magnitude
        )
    else:
        outcome = CorpusOutcome.unexplained

    return reading(
        outcome,
        balancing=inference.balancing,
        delta_magnitude=inference.deltas.get(TotalsConvention.magnitude),
        delta_signed=inference.deltas.get(TotalsConvention.signed),
        unmapped=totals.unmapped,
        signs_coherent=totals.outflow_signs_coherent,
    )


# ---------------------------------------------------------------------------
# The survey
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Disagreement:
    """One document whose re-extractions did not agree about its own block.

    The whole reason primaries are nominated by evidence rather than by
    recency.  ``outcomes`` is ordered by batch, so the direction of travel is
    visible: a document going ``magnitude`` then ``not_testable`` lost a
    working identity, which is a regression however new the toolchain that
    produced it.
    """

    document: str
    outcomes: tuple[tuple[str, CorpusOutcome], ...]

    @property
    def lost_a_testable_identity(self) -> bool:
        """An earlier batch could test this block and a later one could not."""
        seen_testable = False
        for _, outcome in self.outcomes:
            if outcome in TESTED_OUTCOMES:
                seen_testable = True
            elif seen_testable:
                return True
        return False


@dataclass(frozen=True, slots=True)
class CorpusReport:
    """Every reading, plus the questions worth asking of all of them at once."""

    readings: tuple[DocumentReading, ...]

    @property
    def file_count(self) -> int:
        """Extractions surveyed.  Not the number of documents."""
        return len(self.readings)

    @property
    def documents(self) -> tuple[str, ...]:
        return tuple(sorted({r.document for r in self.readings}))

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def testable_count(self) -> int:
        return sum(1 for r in self.readings if r.is_testable)

    def counts(self) -> dict[CorpusOutcome, int]:
        """Every outcome, including the ones that did not occur.

        Absent keys would make a count of zero indistinguishable from an
        outcome the survey forgot to look for, so all of them are present.
        """
        tally = {outcome: 0 for outcome in CorpusOutcome}
        for reading in self.readings:
            tally[reading.outcome] += 1
        return tally

    def documents_with(self, outcome: CorpusOutcome) -> tuple[str, ...]:
        return tuple(
            sorted({r.document for r in self.readings if r.outcome is outcome})
        )

    def readings_for(self, document: str) -> tuple[DocumentReading, ...]:
        return tuple(
            sorted(
                (r for r in self.readings if r.document == document),
                key=lambda r: r.batch,
            )
        )

    @property
    def re_extracted(self) -> tuple[str, ...]:
        """Documents surveyed more than once."""
        counts: dict[str, int] = {}
        for reading in self.readings:
            counts[reading.document] = counts.get(reading.document, 0) + 1
        return tuple(sorted(d for d, n in counts.items() if n > 1))

    def disagreements(self) -> tuple[Disagreement, ...]:
        """Re-extracted documents whose extractions reached different outcomes.

        Empty is the expected state and is not the same as no re-extractions;
        eighteen of nineteen agreeing and one not is the shape this defect
        actually takes, so the two are counted separately.
        """
        found = []
        for document in self.re_extracted:
            readings = self.readings_for(document)
            outcomes = tuple((r.batch, r.outcome) for r in readings)
            if len({o for _, o in outcomes}) > 1:
                found.append(Disagreement(document=document, outcomes=outcomes))
        return tuple(found)

    def unmapped_census(self) -> dict[str, int]:
        """Field names in the control blocks that no role claimed.

        The drift alarm.  Most entries are legitimately not roles — counts,
        averages, page-check metadata — and the census is not a list of
        aliases to adopt.  What matters is the arrival of a *new* name on a
        document whose identity stopped closing, which is what a withdrawals
        figure appearing under an unrecognised name looks like from here.
        """
        census: dict[str, int] = {}
        for reading in self.readings:
            for field in reading.unmapped:
                census[field] = census.get(field, 0) + 1
        return dict(sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))

    def institutions(self) -> dict[str, int]:
        census: dict[str, int] = {}
        for reading in self.readings:
            name = reading.institution or "(unstated)"
            census[name] = census.get(name, 0) + 1
        return dict(sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))

    def render(self) -> str:
        """A plain-text report, deterministic given the same corpus.

        Deterministic because the value of a report like this is the diff
        between two of them.  Amounts are formatted; no account numbers,
        holders or transaction text appear, because no reading carries any.
        """
        tally = self.counts()
        lines = [
            "Corpus survey",
            "=============",
            f"extractions:  {self.file_count}",
            f"documents:    {self.document_count}",
            f"re-extracted: {len(self.re_extracted)}",
            f"testable:     {self.testable_count}",
            "",
            "Outcomes",
            "--------",
        ]
        width = max(len(o.value) for o in CorpusOutcome)
        for outcome in CorpusOutcome:
            lines.append(f"  {outcome.value:<{width}}  {tally[outcome]:>4}")

        unexplained = self.documents_with(CorpusOutcome.unexplained)
        if unexplained:
            lines += ["", "Unexplained", "-----------"]
            for document in unexplained:
                for reading in self.readings_for(document):
                    if reading.outcome is not CorpusOutcome.unexplained:
                        continue
                    residual = reading.residual
                    shown = residual.format() if residual is not None else "—"
                    lines.append(
                        f"  {document}  {reading.batch}  residual {shown}"
                    )

        unreadable = self.documents_with(CorpusOutcome.unreadable)
        if unreadable:
            lines += ["", "Unreadable", "----------"]
            for document in unreadable:
                for reading in self.readings_for(document):
                    if reading.unreadable_reason:
                        lines.append(
                            f"  {document}  {reading.batch}  "
                            f"{reading.unreadable_reason}"
                        )

        disagreements = self.disagreements()
        if disagreements:
            lines += ["", "Re-extraction disagreements", "---------------------------"]
            for item in disagreements:
                trail = " -> ".join(
                    f"{batch}:{outcome.value}" for batch, outcome in item.outcomes
                )
                flag = " (lost a testable identity)" if item.lost_a_testable_identity else ""
                lines.append(f"  {item.document}  {trail}{flag}")

        census = self.unmapped_census()
        if census:
            lines += ["", "Unmapped control-block fields", "-----------------------------"]
            for field, count in census.items():
                lines.append(f"  {field:<40} {count:>4}")

        return "\n".join(lines) + "\n"


def survey(readings: Sequence[DocumentReading]) -> CorpusReport:
    """Assemble a report from readings, whatever produced them."""
    return CorpusReport(readings=tuple(readings))


def load_corpus(
    root: Path,
    *,
    currency: str,
    aliases: Mapping[TotalsRole, Sequence[str]] = FIELD_ALIASES,
) -> CorpusReport:
    """Read every extraction under ``root`` and survey the lot.

    Raises :class:`CorpusUnavailableError` when the corpus is absent, and
    :class:`MalformedExtractionError` on a file that is not an extraction.
    A malformed *file* stops the survey; an unreadable *figure* does not.
    """
    readings = []
    for found in iter_extraction_files(root):
        try:
            payload = json.loads(found.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MalformedExtractionError(
                f"{found.document}: could not be read as JSON: {exc}"
            ) from exc
        readings.append(
            read_extraction(
                payload,
                document=found.document,
                batch=found.batch,
                currency=currency,
                aliases=aliases,
            )
        )
    if not readings:
        raise CorpusUnavailableError(
            f"no extractions found under {root}; the directory exists but "
            "holds no batch containing .json files"
        )
    return survey(readings)
