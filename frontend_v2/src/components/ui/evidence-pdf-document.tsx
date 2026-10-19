import { useCallback, useEffect, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { Button } from "./button"
import { EvidencePdfPage } from "./evidence-pdf-page"

/** Continuous PDF scrolling with only nearby authenticated page images mounted. */
export function EvidencePdfDocument({
  evidenceId,
  page,
  onPageCount,
  onVisiblePageChange,
}: {
  evidenceId: string
  page: number
  onPageCount: (fileId: string, count: number) => void
  onVisiblePageChange: (page: number) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const visiblePage = useRef(page)
  const positioned = useRef(false)
  const [pageCount, setPageCount] = useState<number | null>(null)
  const [zoom, setZoom] = useState(100)
  const reportCount = useCallback(
    (fileId: string, count: number) => {
      setPageCount(count)
      onPageCount(fileId, count)
    },
    [onPageCount]
  )

  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: pageCount ?? page,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => (1000 * zoom) / 100,
    initialOffset: () => (page - 1) * 1000,
    overscan: 2,
    onChange: (instance, scrolling) => {
      if (!scrolling || !pageCount || !positioned.current) return
      const offset = instance.scrollOffset ?? 0
      const item = instance
        .getVirtualItems()
        .find((item) => item.end > offset + 32)
      if (item && item.index + 1 !== visiblePage.current) {
        visiblePage.current = item.index + 1
        onVisiblePageChange(item.index + 1)
      }
    },
  })

  useEffect(() => {
    if (!pageCount) return
    if (!positioned.current) {
      virtualizer.scrollToIndex(page - 1, { align: "start" })
      positioned.current = true
      return
    }
    if (page === visiblePage.current) return
    visiblePage.current = page
    virtualizer.scrollToIndex(page - 1, { align: "start" })
  }, [page, pageCount, virtualizer])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b px-4 py-2">
        <Button
          variant="outline"
          size="sm"
          aria-label="Zoom out PDF page"
          disabled={zoom <= 50}
          onClick={() => setZoom((value) => Math.max(50, value - 25))}
        >
          −
        </Button>
        <span className="text-sm">{zoom}%</span>
        <Button
          variant="outline"
          size="sm"
          aria-label="Zoom in PDF page"
          disabled={zoom >= 250}
          onClick={() => setZoom((value) => Math.min(250, value + 25))}
        >
          +
        </Button>
        <Button variant="outline" size="sm" onClick={() => setZoom(100)}>
          Fit page width
        </Button>
      </div>
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-auto overscroll-contain"
        role="region"
        aria-label="PDF document pages"
        tabIndex={0}
      >
        {!pageCount ? (
          <EvidencePdfPage
            evidenceId={evidenceId}
            page={page}
            onPageCount={reportCount}
            inline
            documentZoom={zoom}
          />
        ) : (
          <div
            style={{
              height: virtualizer.getTotalSize(),
              position: "relative",
              width: "100%",
            }}
          >
            {virtualizer.getVirtualItems().map((item) => (
              <div
                key={item.key}
                data-index={item.index}
                ref={virtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${item.start}px)`,
                }}
                className="border-b"
              >
                <p className="px-4 pt-2 text-xs text-muted-foreground">
                  Page {item.index + 1}
                </p>
                <EvidencePdfPage
                  evidenceId={evidenceId}
                  page={item.index + 1}
                  onPageCount={reportCount}
                  inline
                  documentZoom={zoom}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
