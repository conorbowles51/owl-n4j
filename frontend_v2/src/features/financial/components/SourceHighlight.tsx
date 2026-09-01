/**
 * The page with the number on it.
 *
 * Every figure the ledger reports is eventually questioned by someone whose
 * job is to break it, and the answer that ends the argument is the source
 * page with the value boxed on it.  This component draws that answer when it
 * exists, and — just as deliberately — says exactly what is missing when it
 * does not.
 *
 * Absence has four meanings and they are not interchangeable
 * ----------------------------------------------------------
 *
 * A missing highlight can mean the source has no pages at all (a CSV feed —
 * honest, not a shortcoming), that the page is known but the position was
 * never captured (every row extracted before geometry existed), that capture
 * was attempted and failed (a defect, and counted as one), or that the
 * stored locator itself cannot be read.  Those want four different sentences
 * in front of an investigator, because they call for four different
 * responses, and this component renders all four rather than one vague
 * "source unavailable".
 *
 * The rectangle is placed by fractions of the page, so it stays on the value
 * at any rendered width.  The image is expected to be the full page, exactly
 * — a cropped or padded render would put the box in the wrong place, which
 * is the one error this whole chain of custody exists to make impossible.
 *
 * The page image is a prop rather than a fetch because no page-render
 * endpoint exists yet; when one lands, the caller supplies its URL and
 * nothing here changes.  Without an image the component still says what is
 * known — kind and page — instead of rendering nothing.
 */

import type { ReactNode } from "react"

import { readLocator, normalised } from "../lib/locator"

interface SourceHighlightProps {
  /** The raw stored value of `provenance["locator"]`, unparsed. */
  payload: unknown
  /**
   * A rendering of the full source page the locator points at, if the caller
   * has one.  Must be the entire page: the rectangle is placed by fractions
   * of the page dimensions the backend measured.
   */
  pageImageUrl?: string | null
  /** What the highlighted value is, for the highlight's accessible name. */
  valueLabel?: string
}

function percent(fraction: number): string {
  return `${fraction * 100}%`
}

/** One sentence, styled alike wherever the page itself cannot be shown. */
function Sentence({ children, testId }: { children: ReactNode; testId: string }) {
  return (
    <p data-testid={testId} className="text-xs text-muted-foreground">
      {children}
    </p>
  )
}

export function SourceHighlight({ payload, pageImageUrl, valueLabel }: SourceHighlightProps) {
  const reading = readLocator(payload)

  if (!reading.ok) {
    // A payload the backend would not have written. Shown as a defect with
    // the reason verbatim, never guessed into a box.
    return (
      <Sentence testId="locator-unreadable">
        The stored location could not be read: {reading.reason}
      </Sentence>
    )
  }

  const locator = reading.locator

  if (locator.kind === "not_positional") {
    return (
      <Sentence testId="locator-not-positional">
        This source has no pages, so there is no place on a page to point at.
      </Sentence>
    )
  }

  if (locator.kind === "unlocated") {
    return (
      <Sentence testId="locator-unlocated">
        {locator.page === null
          ? "The place this value was read from could not be captured."
          : `The value was read from page ${locator.page}, but its place on the page could not be captured.`}
      </Sentence>
    )
  }

  if (locator.kind === "page_only") {
    return (
      <div className="space-y-1">
        <Sentence testId="locator-page-only">
          Read from page {locator.page}. The position on the page was not captured for
          this row, so the page is shown without a highlight.
        </Sentence>
        {pageImageUrl ? (
          <img
            src={pageImageUrl}
            alt={`Page ${locator.page} of the source document`}
            className="w-full rounded-md border border-border"
          />
        ) : null}
      </div>
    )
  }

  // page_rectangle: the full answer, when an image is available to draw on.
  if (!pageImageUrl) {
    return (
      <Sentence testId="locator-no-page-image">
        The exact place on page {locator.page} is recorded, but no rendering of the
        page is available to draw it on.
      </Sentence>
    )
  }

  const box = normalised(locator.rectangle)
  return (
    <div data-testid="locator-highlight" className="relative w-full">
      <img
        src={pageImageUrl}
        alt={`Page ${locator.page} of the source document`}
        className="block w-full rounded-md border border-border"
      />
      <div
        data-testid="locator-highlight-box"
        role="img"
        aria-label={
          valueLabel
            ? `Highlighted source of ${valueLabel} on page ${locator.page}`
            : `Highlighted source region on page ${locator.page}`
        }
        className="pointer-events-none absolute border-2 border-amber-500 bg-amber-400/20"
        style={{
          left: percent(box.x0),
          top: percent(box.y0),
          width: percent(box.x1 - box.x0),
          height: percent(box.y1 - box.y0),
        }}
      />
    </div>
  )
}
