"""Where on the page a value was read, exactly enough to draw a box on it.

Every figure the ledger reports is eventually going to be questioned by someone
whose job is to break it, and the answer that ends the argument is the page
with the number on it.  This module is the value type that makes that answer
mechanical rather than a matter of going and looking.

Three decisions here are not obvious, and all three are consequences of
measurement rather than taste.

Coordinates are integers
------------------------

There is no float in a stored rectangle, for the same reason there is no float
in :mod:`services.financial.money`, plus one that is specific to geometry: an
export has to regenerate byte for byte, and a float that reaches JSON is a
value whose text form depends on the platform that wrote it.  Rectangles are
therefore stored in **integer millipoints** — thousandths of a PostScript
point, so a US Letter page is 612,000 by 792,000.  That is roughly 25 nanometres
per unit, which is absurd precision for something a scanner produced, and that
is the point: the resolution is far below any real disagreement, so rounding
can never be what two readings differ about.

Rounding goes outward, never to nearest.  ``x0`` and ``y0`` floor, ``x1`` and
``y1`` ceil.  A box a hair too large still contains the value it points at; a
box a hair too small can clip the leading digit off an amount, and the whole
purpose of the rectangle is to survive being looked at closely.  This is the
same asymmetry :mod:`services.financial.proof_class` applies to class
assignment: the two errors are not equally cheap, so the tie is broken toward
the one that cannot mislead.

The coordinate space is recorded, because it cannot be recovered
---------------------------------------------------------------

:class:`~postgres.models.enums.CoordinateSpace` carries the measurement in
full.  The short version is that ``get_text`` and ``find_tables`` disagree
about what a rectangle means on a rotated page — one reports pre-rotation
coordinates and the other post-rotation — and no amount of inspecting the four
numbers afterwards will tell you which convention produced them.  At 180
degrees both readings of the same table land inside the page and look equally
sensible.

So the space is a required argument at capture, and only one space is ever
stored.  :func:`capture` converts into :attr:`CoordinateSpace.pdf_displayed`
and everything downstream may assume it.  The alternative — storing the space
alongside the numbers and converting at read time — was rejected because it
puts the conversion in every consumer, and a consumer that forgets is a
highlight in the wrong place with nothing to flag it.

Absence has four meanings and they are not interchangeable
----------------------------------------------------------

:class:`~postgres.models.enums.LocatorKind` is the vocabulary.  A missing
rectangle can mean the source has no pages at all, or that it has pages and
the reader failed, or that the row predates any attempt to capture geometry.
Those want three different sentences in front of a court and three different
engineering responses, and an optional ``bbox`` field renders all of them as
``null``.

The corpus settles that this is not hypothetical.  Every extracted row
available today carries ``source_page`` and nothing else, so the honest kind
for all of them is :attr:`LocatorKind.page_only`, and the count of
:attr:`LocatorKind.unlocated` rows is a defect measure that only means
something because it is separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Mapping, Optional

from postgres.models.enums import CoordinateSpace, LocatorKind


MILLIPOINTS_PER_POINT = 1000


class LocatorError(Exception):
    """Base for every refusal in this module."""


class RectangleError(LocatorError):
    """A rectangle was described that does not describe a place."""


class LocatorCoherenceError(LocatorError):
    """The kind and the payload disagree about what is known."""


def _floor_millipoints(value: float) -> int:
    return int(
        (Decimal(str(value)) * MILLIPOINTS_PER_POINT).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )


def _ceil_millipoints(value: float) -> int:
    return int(
        (Decimal(str(value)) * MILLIPOINTS_PER_POINT).to_integral_value(
            rounding=ROUND_CEILING
        )
    )


@dataclass(frozen=True, slots=True)
class SourceRectangle:
    """A rectangle on one page, in integer millipoints of displayed space.

    The page dimensions travel with the rectangle rather than being looked up
    from the document later.  A viewer needs both to place a highlight, and
    holding them together means the pair cannot drift apart if the file is
    replaced by a re-scan at a different size — the stored rectangle stays
    interpretable against the page it was actually measured on.
    """

    page_number: int
    x0: int
    y0: int
    x1: int
    y1: int
    page_width: int
    page_height: int

    def __post_init__(self) -> None:
        for name in ("page_number", "x0", "y0", "x1", "y1", "page_width", "page_height"):
            value = getattr(self, name)
            # bool is an int subclass and would silently pass every check below.
            if not isinstance(value, int) or isinstance(value, bool):
                raise RectangleError(
                    f"{name} must be an int in millipoints, got {value!r}"
                )

        if self.page_number < 1:
            raise RectangleError(
                f"page_number is 1-based; got {self.page_number}"
            )
        if self.page_width <= 0 or self.page_height <= 0:
            raise RectangleError(
                f"page is {self.page_width}x{self.page_height} millipoints; "
                "a page with no extent cannot carry a rectangle"
            )
        # Degenerate rectangles are refused rather than stored.  A zero-width
        # box is not a location, and it would render as an invisible highlight
        # that reads to a viewer as though nothing was found.
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise RectangleError(
                f"rectangle ({self.x0}, {self.y0}, {self.x1}, {self.y1}) has no "
                "area; x0 < x1 and y0 < y1 are required"
            )
        if self.x0 < 0 or self.y0 < 0:
            raise RectangleError(
                f"rectangle starts at ({self.x0}, {self.y0}), outside the page"
            )
        if self.x1 > self.page_width or self.y1 > self.page_height:
            raise RectangleError(
                f"rectangle ends at ({self.x1}, {self.y1}), outside the "
                f"{self.page_width}x{self.page_height} page"
            )

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def normalised(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """The rectangle as fractions of the page, for a viewer at any zoom.

        Returned as :class:`~decimal.Decimal` rather than float so that a
        caller rendering at a known pixel width gets an exact product.  This is
        computed on demand and never stored: storing both the millipoints and
        the fractions would create two representations that can disagree.
        """
        width = Decimal(self.page_width)
        height = Decimal(self.page_height)
        return (
            Decimal(self.x0) / width,
            Decimal(self.y0) / height,
            Decimal(self.x1) / width,
            Decimal(self.y1) / height,
        )


_LEGAL_ROTATIONS = (0, 90, 180, 270)


def _to_displayed(
    rect: tuple[float, float, float, float],
    rotation: int,
    unrotated_width: float,
    unrotated_height: float,
) -> tuple[float, float, float, float]:
    """Rotate an unrotated rectangle into displayed space.

    Equivalent to multiplying by PyMuPDF's ``page.rotation_matrix``, written
    out here so that the backend does not take a PDF library as a dependency
    to interpret four numbers.  Verified against PyMuPDF 1.28.2 at all four
    rotations; the test that does so is the reason this can be trusted.
    """
    x0, y0, x1, y1 = rect
    width, height = unrotated_width, unrotated_height
    if rotation == 0:
        corners = ((x0, y0), (x1, y1))
    elif rotation == 90:
        corners = ((height - y0, x0), (height - y1, x1))
    elif rotation == 180:
        corners = ((width - x0, height - y0), (width - x1, height - y1))
    else:  # 270
        corners = ((y0, width - x0), (y1, width - x1))
    (ax, ay), (bx, by) = corners
    # Rotation moves which corner is the minimum, so the pair is re-ordered
    # rather than assumed.
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def capture(
    *,
    page_number: int,
    rect: tuple[float, float, float, float],
    space: CoordinateSpace,
    rotation: int,
    page_width: float,
    page_height: float,
) -> SourceRectangle:
    """Convert one reader's rectangle into a stored :class:`SourceRectangle`.

    ``page_width`` and ``page_height`` are the **displayed** dimensions — what
    PyMuPDF's ``page.rect`` reports, already rotated.  That is deliberate: it
    is the value most directly to hand at every call site, and it is the space
    the result is stored in, so the caller is never asked to convert anything
    before calling and never asked which of two page sizes is wanted.

    ``space`` says which convention ``rect`` follows and has no default.  A
    default would be wrong half the time and silently: see
    :class:`~postgres.models.enums.CoordinateSpace`.
    """
    if rotation not in _LEGAL_ROTATIONS:
        raise RectangleError(
            f"rotation {rotation} is not one of {_LEGAL_ROTATIONS}"
        )
    if page_width <= 0 or page_height <= 0:
        raise RectangleError(
            f"displayed page is {page_width}x{page_height}; nothing can be "
            "located on a page with no extent"
        )

    if space is CoordinateSpace.pdf_displayed:
        placed = rect
    elif space is CoordinateSpace.pdf_unrotated:
        # The unrotated page is the displayed one turned back: a quarter turn
        # swaps the axes, a half turn does not.
        if rotation in (90, 270):
            unrotated_width, unrotated_height = page_height, page_width
        else:
            unrotated_width, unrotated_height = page_width, page_height
        placed = _to_displayed(rect, rotation, unrotated_width, unrotated_height)
    else:
        raise RectangleError(f"unknown coordinate space {space!r}")

    width_mp = _ceil_millipoints(page_width)
    height_mp = _ceil_millipoints(page_height)

    # Outward rounding, then clamped to the page.  A reader that reports a
    # rectangle a fraction of a point over the edge is describing ink at the
    # margin, not making an error worth discarding evidence over; a rectangle
    # with no overlap at all is a different matter and refuses below.
    x0 = max(0, _floor_millipoints(placed[0]))
    y0 = max(0, _floor_millipoints(placed[1]))
    x1 = min(width_mp, _ceil_millipoints(placed[2]))
    y1 = min(height_mp, _ceil_millipoints(placed[3]))

    if x1 <= x0 or y1 <= y0:
        raise RectangleError(
            f"rectangle {rect} in {space.value} on a {page_width}x{page_height} "
            f"page at rotation {rotation} does not meet the page"
        )

    return SourceRectangle(
        page_number=page_number,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        page_width=width_mp,
        page_height=height_mp,
    )


@dataclass(frozen=True, slots=True)
class Locator:
    """What is known about where a value came from, and nothing more.

    The coherence rules below are enforced in the constructor rather than
    trusted, for the reason
    ``ck_financial_transactions_quarantine_coherent`` exists in the schema: a
    pair of fields that must agree will eventually stop agreeing unless
    something refuses the moment they do not.  A locator claiming
    :attr:`LocatorKind.page_rectangle` with no rectangle would render as a
    working click-through that opens nothing.
    """

    kind: LocatorKind
    page_number: Optional[int] = None
    rectangle: Optional[SourceRectangle] = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LocatorKind):
            raise LocatorCoherenceError(
                f"kind must be a LocatorKind, got {self.kind!r}"
            )

        if self.kind is LocatorKind.page_rectangle:
            if self.rectangle is None:
                raise LocatorCoherenceError(
                    "page_rectangle promises a rectangle and none was given"
                )
            if self.page_number is not None and self.page_number != self.rectangle.page_number:
                raise LocatorCoherenceError(
                    f"locator says page {self.page_number} and its rectangle "
                    f"says page {self.rectangle.page_number}"
                )
            return

        if self.rectangle is not None:
            raise LocatorCoherenceError(
                f"{self.kind.value} carries a rectangle; only page_rectangle may"
            )

        if self.kind is LocatorKind.page_only:
            if self.page_number is None:
                raise LocatorCoherenceError(
                    "page_only is a claim to know the page, and none was given"
                )
        elif self.kind is LocatorKind.not_positional:
            if self.page_number is not None:
                raise LocatorCoherenceError(
                    f"not_positional means the source has no pages, but page "
                    f"{self.page_number} was given"
                )
        # unlocated deliberately permits either: a reader can fail to find the
        # value on a page it knows, or fail before it knows the page, and both
        # are the same defect.

        if self.page_number is not None and self.page_number < 1:
            raise LocatorCoherenceError(
                f"page_number is 1-based; got {self.page_number}"
            )

    @property
    def page(self) -> Optional[int]:
        """The page, however it is known: from the rectangle or on its own."""
        if self.rectangle is not None:
            return self.rectangle.page_number
        return self.page_number

    @property
    def is_clickable(self) -> bool:
        """Whether click-through resolves to a highlight rather than a page."""
        return self.kind is LocatorKind.page_rectangle

    def to_json(self) -> dict[str, Any]:
        """A dict whose key order is fixed, for stable serialisation.

        Key order is not cosmetic here.  ``provenance`` is JSONB on the
        transaction and an export has to regenerate byte for byte, so the
        mapping is built in one declared order and the optional members are
        omitted rather than written as nulls — an omitted key and a null key
        are different bytes for the same fact.
        """
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.rectangle is not None:
            rectangle = self.rectangle
            payload["page"] = rectangle.page_number
            payload["rect"] = [
                rectangle.x0,
                rectangle.y0,
                rectangle.x1,
                rectangle.y1,
            ]
            payload["page_size"] = [rectangle.page_width, rectangle.page_height]
            payload["units"] = "millipoints"
            payload["space"] = CoordinateSpace.pdf_displayed.value
        elif self.page_number is not None:
            payload["page"] = self.page_number
        return payload

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "Locator":
        """Rebuild a locator, refusing anything this module would not have written.

        Unknown keys are rejected rather than ignored.  A key this version does
        not understand is either a newer writer or a corrupted row, and
        silently dropping it would turn a rectangle into a page reference
        without anything saying so.
        """
        if not isinstance(payload, Mapping):
            raise LocatorCoherenceError(
                f"locator payload must be a mapping, got {type(payload).__name__}"
            )
        allowed = {"kind", "page", "rect", "page_size", "units", "space"}
        unknown = set(payload) - allowed
        if unknown:
            raise LocatorCoherenceError(
                f"unknown locator keys {sorted(unknown)}; refusing to guess"
            )

        raw_kind = payload.get("kind")
        try:
            kind = LocatorKind(raw_kind)
        except ValueError:
            raise LocatorCoherenceError(
                f"{raw_kind!r} is not a known locator kind"
            ) from None

        if kind is not LocatorKind.page_rectangle:
            for key in ("rect", "page_size", "units", "space"):
                if key in payload:
                    raise LocatorCoherenceError(
                        f"{kind.value} carries {key!r}; only page_rectangle may"
                    )
            return cls(kind=kind, page_number=payload.get("page"))

        units = payload.get("units")
        if units != "millipoints":
            raise LocatorCoherenceError(
                f"rectangle is in {units!r}; this reader only understands "
                "millipoints and will not rescale a unit it does not know"
            )
        space = payload.get("space")
        if space != CoordinateSpace.pdf_displayed.value:
            raise LocatorCoherenceError(
                f"rectangle is in space {space!r}; stored rectangles are always "
                f"{CoordinateSpace.pdf_displayed.value} and a different space "
                "cannot be drawn without knowing the page rotation"
            )

        rect = payload.get("rect")
        size = payload.get("page_size")
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise LocatorCoherenceError(f"rect must be four numbers, got {rect!r}")
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise LocatorCoherenceError(
                f"page_size must be two numbers, got {size!r}"
            )

        return cls(
            kind=kind,
            rectangle=SourceRectangle(
                page_number=payload.get("page"),
                x0=rect[0],
                y0=rect[1],
                x1=rect[2],
                y1=rect[3],
                page_width=size[0],
                page_height=size[1],
            ),
        )
