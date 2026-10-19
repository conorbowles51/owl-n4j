/**
 * Reading a stored locator without guessing.
 *
 * The backend writes `provenance["locator"]` through one module
 * (`services/financial/locators.py`) and that module's `from_json` refuses
 * anything it would not itself have written: unknown keys, unknown kinds, a
 * rectangle in units or a coordinate space it does not store.  This file is
 * the same contract on the reading side, mirrored refusal for refusal, so a
 * payload the backend would reject renders here as a visible defect rather
 * than as a highlight in a place nobody measured.
 *
 * The refusals matter more than the happy path.  A locator is the answer to
 * "show me where that number came from", and the two ways to get that answer
 * wrong are not equal: saying "the stored location could not be read" is an
 * honest defect report, while drawing a confident box in the wrong place is
 * manufactured evidence.  Every check below exists to keep the second kind of
 * error impossible, at the cost of more of the first.
 *
 * Nothing here throws.  A parse failure is an expected state of real data
 * (an old row, a newer writer, a corrupted value) and the component showing
 * it needs the reason as a value, not as an exception unwinding through
 * React.  `readLocator` therefore returns a discriminated union and the
 * reason strings are written to be shown to an investigator as-is.
 *
 * Units are integer millipoints — thousandths of a PostScript point — and
 * the only stored coordinate space is `pdf_displayed`.  Both facts are
 * checked, not assumed, because the backend records them in the payload for
 * exactly this reason: a rectangle whose units are unknown cannot be drawn,
 * only mistaken.
 */

/** The four ways a value relates to a place, from `LocatorKind` in the backend. */
export type LocatorKind =
  | "page_rectangle"
  | "page_only"
  | "not_positional"
  | "unlocated"

/**
 * A rectangle on one page, in integer millipoints of displayed space.
 *
 * The page dimensions travel with the rectangle — the backend stores them
 * together so the pair cannot drift apart if the file is re-scanned at a
 * different size, and a viewer needs both to place a highlight.
 */
export interface SourceRectangle {
  page: number
  x0: number
  y0: number
  x1: number
  y1: number
  pageWidth: number
  pageHeight: number
}

/** What is known about where a value came from, and nothing more. */
export type Locator =
  | { kind: "page_rectangle"; page: number; rectangle: SourceRectangle }
  | { kind: "page_only"; page: number }
  | { kind: "not_positional" }
  | { kind: "unlocated"; page: number | null }

/**
 * The outcome of reading a payload.  `ok: false` is an expected state, not
 * an error path; `reason` is written to be shown to the user unedited.
 */
export type LocatorReading =
  | { ok: true; locator: Locator }
  | { ok: false; reason: string }

const ALLOWED_KEYS = new Set(["kind", "page", "rect", "page_size", "units", "space"])
const KINDS: ReadonlySet<string> = new Set([
  "page_rectangle",
  "page_only",
  "not_positional",
  "unlocated",
])

/** The only units the backend stores.  A different value is refused, not rescaled. */
const STORED_UNITS = "millipoints"
/** The only coordinate space the backend stores (`CoordinateSpace.pdf_displayed`). */
const STORED_SPACE = "pdf_displayed"

function refuse(reason: string): LocatorReading {
  return { ok: false, reason }
}

/**
 * True for a plain integer and false for everything else, including
 * booleans: in the backend `bool` is an `int` subclass and is checked for
 * explicitly, and `Number.isInteger(true)` is already false here, but the
 * `typeof` guard keeps the intent readable rather than incidental.
 */
function isPlainInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value)
}

function describe(value: unknown): string {
  if (value === null) return "null"
  if (Array.isArray(value)) return JSON.stringify(value)
  if (typeof value === "object") return "an object"
  return JSON.stringify(value)
}

/**
 * Rebuild a locator from a stored payload, refusing anything the backend
 * would not have written.
 *
 * Mirrors `Locator.from_json` and the constructor coherence rules behind it:
 * unknown keys are rejected rather than ignored, because a key this version
 * does not understand is either a newer writer or a corrupted row, and
 * silently dropping it would turn a rectangle into a page reference without
 * anything saying so.
 */
export function readLocator(payload: unknown): LocatorReading {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return refuse(`locator payload must be an object, got ${describe(payload)}`)
  }
  const record = payload as Record<string, unknown>

  const unknown = Object.keys(record).filter((key) => !ALLOWED_KEYS.has(key))
  if (unknown.length > 0) {
    return refuse(`unknown locator keys ${JSON.stringify(unknown.sort())}; refusing to guess`)
  }

  const rawKind = record["kind"]
  if (typeof rawKind !== "string" || !KINDS.has(rawKind)) {
    return refuse(`${describe(rawKind)} is not a known locator kind`)
  }
  const kind = rawKind as LocatorKind

  if (kind !== "page_rectangle") {
    for (const key of ["rect", "page_size", "units", "space"]) {
      if (key in record) {
        return refuse(`${kind} carries "${key}"; only page_rectangle may`)
      }
    }
    const page = "page" in record ? record["page"] : null
    if (page !== null && !isPlainInteger(page)) {
      return refuse(`page must be an integer, got ${describe(page)}`)
    }
    if (page !== null && page < 1) {
      return refuse(`page is 1-based; got ${page}`)
    }
    if (kind === "page_only") {
      if (page === null) {
        return refuse("page_only is a claim to know the page, and none was given")
      }
      return { ok: true, locator: { kind, page } }
    }
    if (kind === "not_positional") {
      if (page !== null) {
        return refuse(`not_positional means the source has no pages, but page ${page} was given`)
      }
      return { ok: true, locator: { kind } }
    }
    // unlocated deliberately permits either: a reader can fail to find the
    // value on a page it knows, or fail before it knows the page.
    return { ok: true, locator: { kind, page } }
  }

  const units = record["units"]
  if (units !== STORED_UNITS) {
    return refuse(
      `rectangle is in ${describe(units)}; this reader only understands ` +
        `${STORED_UNITS} and will not rescale a unit it does not know`,
    )
  }
  const space = record["space"]
  if (space !== STORED_SPACE) {
    return refuse(
      `rectangle is in space ${describe(space)}; stored rectangles are always ` +
        `${STORED_SPACE} and a different space cannot be drawn without knowing ` +
        "the page rotation",
    )
  }

  const rect = record["rect"]
  if (!Array.isArray(rect) || rect.length !== 4) {
    return refuse(`rect must be four numbers, got ${describe(rect)}`)
  }
  const size = record["page_size"]
  if (!Array.isArray(size) || size.length !== 2) {
    return refuse(`page_size must be two numbers, got ${describe(size)}`)
  }

  const page = record["page"]
  const fields: Array<[string, unknown]> = [
    ["page", page],
    ["rect x0", rect[0]],
    ["rect y0", rect[1]],
    ["rect x1", rect[2]],
    ["rect y1", rect[3]],
    ["page_size width", size[0]],
    ["page_size height", size[1]],
  ]
  for (const [name, value] of fields) {
    if (!isPlainInteger(value)) {
      return refuse(`${name} must be an integer in millipoints, got ${describe(value)}`)
    }
  }

  const rectangle: SourceRectangle = {
    page: page as number,
    x0: rect[0] as number,
    y0: rect[1] as number,
    x1: rect[2] as number,
    y1: rect[3] as number,
    pageWidth: size[0] as number,
    pageHeight: size[1] as number,
  }

  // The same shape checks `SourceRectangle.__post_init__` enforces, in the
  // same order, so both sides refuse the same payloads for the same reasons.
  if (rectangle.page < 1) {
    return refuse(`page is 1-based; got ${rectangle.page}`)
  }
  if (rectangle.pageWidth <= 0 || rectangle.pageHeight <= 0) {
    return refuse(
      `page is ${rectangle.pageWidth}x${rectangle.pageHeight} millipoints; ` +
        "a page with no extent cannot carry a rectangle",
    )
  }
  if (rectangle.x1 <= rectangle.x0 || rectangle.y1 <= rectangle.y0) {
    return refuse(
      `rectangle (${rectangle.x0}, ${rectangle.y0}, ${rectangle.x1}, ${rectangle.y1}) ` +
        "has no area; x0 < x1 and y0 < y1 are required",
    )
  }
  if (rectangle.x0 < 0 || rectangle.y0 < 0) {
    return refuse(`rectangle starts at (${rectangle.x0}, ${rectangle.y0}), outside the page`)
  }
  if (rectangle.x1 > rectangle.pageWidth || rectangle.y1 > rectangle.pageHeight) {
    return refuse(
      `rectangle ends at (${rectangle.x1}, ${rectangle.y1}), outside the ` +
        `${rectangle.pageWidth}x${rectangle.pageHeight} page`,
    )
  }

  return { ok: true, locator: { kind, page: rectangle.page, rectangle } }
}

/**
 * The rectangle as fractions of its page, for rendering at any zoom.
 *
 * The backend computes the same thing (`SourceRectangle.normalised`) and
 * deliberately never stores it: two representations of one rectangle would
 * eventually disagree.  Computed here for the same reason, from the same
 * integers.  The divisions are exact enough for the purpose — a double
 * carries the ratio of two page-sized integers to far below a pixel at any
 * zoom a screen can show.
 */
export function normalised(rectangle: SourceRectangle): {
  x0: number
  y0: number
  x1: number
  y1: number
} {
  return {
    x0: rectangle.x0 / rectangle.pageWidth,
    y0: rectangle.y0 / rectangle.pageHeight,
    x1: rectangle.x1 / rectangle.pageWidth,
    y1: rectangle.y1 / rectangle.pageHeight,
  }
}
