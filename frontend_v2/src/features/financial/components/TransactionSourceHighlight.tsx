/**
 * The bridge between a stored locator and the page it points at.
 *
 * `SourceHighlight` draws a locator against a page image it is handed; it
 * does not know how to get one, deliberately (see its own docstring — no
 * page-render endpoint existed when it was written). This component is that
 * fetch, added now that one does: `GET /api/evidence/{id}/page/{n}/image`.
 *
 * The fetch is conditional, not automatic. Two of the four locator kinds
 * (`not_positional`, `unlocated`) have nothing to draw an image under —
 * `SourceHighlight` ignores `pageImageUrl` for both — so requesting one
 * would be a wasted authenticated fetch against a route that may not even
 * resolve the evidence id. Only `page_only` and `page_rectangle` are asked
 * for an image, and only when a source document id is on the row to ask
 * for. `readLocator` is the parse used to decide this, the same parse
 * `SourceHighlight` runs internally, so the two never disagree about which
 * kind a payload is.
 *
 * The image itself is served behind the same auth as every other evidence
 * file, so it is fetched as an authenticated blob (`useProtectedObjectUrl`,
 * the house pattern for this — see `DocumentViewer`) rather than handed to
 * `SourceHighlight` as a bare URL an `<img>` tag could not authenticate.
 */

import { useCallback, useLayoutEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Loader2 } from "lucide-react"

import { evidenceAPI } from "@/features/evidence/api"
import { useProtectedObjectUrl } from "@/lib/protected-file"

import { readLocator } from "../lib/locator"
import { SourceHighlight } from "./SourceHighlight"

interface TransactionSourceHighlightProps {
  /** The raw stored value of `provenance["locator"]`, unparsed. */
  locatorPayload: unknown
  sourceDocumentId?: string | null
  valueLabel?: string
}

/** The one page number a `page_only` or `page_rectangle` locator asks for; null otherwise. */
function pageNeedingImage(payload: unknown): number | null {
  const reading = readLocator(payload)
  if (!reading.ok) return null
  if (
    reading.locator.kind === "page_only" ||
    reading.locator.kind === "page_rectangle"
  ) {
    return reading.locator.page
  }
  return null
}

export function TransactionSourceHighlight({
  locatorPayload,
  sourceDocumentId,
  valueLabel,
}: TransactionSourceHighlightProps) {
  const page = pageNeedingImage(locatorPayload)
  const imageUrl =
    page !== null && sourceDocumentId
      ? evidenceAPI.getPageImageUrl(sourceDocumentId, page)
      : null

  const { objectUrl, loading, error } = useProtectedObjectUrl(
    imageUrl,
    imageUrl !== null
  )

  if (error) {
    return (
      <p role="alert" className="text-xs text-destructive">
        Source page {page} could not be loaded. No source highlight is shown.
        Close and reopen the source to retry.
      </p>
    )
  }

  if (imageUrl !== null && loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Loading the source page...
      </div>
    )
  }

  return (
    <ZoomableSource
      key={imageUrl ?? "unlocated"}
      locatorPayload={locatorPayload}
      objectUrl={objectUrl}
      valueLabel={valueLabel}
    />
  )
}

function ZoomableSource({
  locatorPayload,
  objectUrl,
  valueLabel,
}: {
  locatorPayload: unknown
  objectUrl: string | null
  valueLabel?: string
}) {
  const [zoom, setZoom] = useState(100)
  const viewport = useRef<HTMLDivElement>(null)
  const reading = readLocator(locatorPayload)
  const rectangle =
    reading.ok && reading.locator.kind === "page_rectangle"
      ? reading.locator.rectangle
      : null
  const centerX = rectangle
    ? (rectangle.x0 + rectangle.x1) / 2 / rectangle.pageWidth
    : null
  const centerY = rectangle
    ? (rectangle.y0 + rectangle.y1) / 2 / rectangle.pageHeight
    : null
  const focus = useCallback(() => {
    const node = viewport.current
    if (!node || centerX === null || centerY === null) return
    const content = node.firstElementChild as HTMLElement | null
    if (!content) return
    node.scrollLeft = content.offsetWidth * centerX - node.clientWidth / 2
    node.scrollTop = content.offsetHeight * centerY - node.clientHeight / 2
  }, [centerX, centerY])
  useLayoutEffect(() => {
    focus()
  }, [zoom, focus, objectUrl])
  return (
    <div className="min-w-0 space-y-2">
      {objectUrl && (
        <div
          className="flex flex-wrap items-center gap-2"
          role="group"
          aria-label="Source image zoom"
        >
          <Button
            size="sm"
            variant="outline"
            disabled={zoom === 100}
            onClick={() => setZoom((z) => Math.max(100, z - 50))}
            aria-label="Zoom source out"
          >
            −
          </Button>
          <span aria-live="polite">{zoom}%</span>
          <Button
            size="sm"
            variant="outline"
            disabled={zoom === 400}
            onClick={() => setZoom((z) => Math.min(400, z + 50))}
            aria-label="Zoom source in"
          >
            +
          </Button>
          <Button size="sm" variant="outline" onClick={() => setZoom(100)}>
            Fit source width
          </Button>
          {rectangle && (
            <Button size="sm" variant="outline" onClick={focus}>
              Show highlighted value
            </Button>
          )}
        </div>
      )}
      <div
        ref={viewport}
        tabIndex={objectUrl ? 0 : undefined}
        role={objectUrl ? "region" : undefined}
        aria-label={objectUrl ? "Scrollable source page" : undefined}
        className="max-h-[560px] overflow-auto rounded-md"
        onLoad={focus}
      >
        <div style={{ width: `${zoom}%` }}>
          <SourceHighlight
            payload={locatorPayload}
            pageImageUrl={objectUrl}
            valueLabel={valueLabel}
          />
        </div>
      </div>
    </div>
  )
}
