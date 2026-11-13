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
  // Only scrolling the person does names the page they are on, and until they scroll the list holds the requested
  // page. Live 13 Nov at 390 px a statement starting at page 5 settled on page 4 while page sizes were measured.
  const personScrolling = useRef(false)
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const mark = () => {
      personScrolling.current = true
    }
    const events = ["wheel", "touchstart", "pointerdown", "keydown"] as const
    for (const name of events) element.addEventListener(name, mark, { passive: true })
    return () => {
      for (const name of events) element.removeEventListener(name, mark)
    }
  }, [])
  const [pageCount, setPageCount] = useState<number | null>(null)
  const [zoom, setZoom] = useState(100)
  // The first page's pixel size, from the first image to arrive. Pages still loading take that shape, so the
  // list mounts only the pages that fit on screen (a one-line placeholder let about 15 mount at once).
  const [pageSize, setPageSize] = useState<{
    width: number
    height: number
  } | null>(null)
  const reportSize = useCallback(
    (size: { width: number; height: number }) =>
      setPageSize((known) => known ?? size),
    []
  )
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
    estimateSize: () => {
      const width = scrollRef.current?.clientWidth
      if (!pageSize || !width) return (1000 * zoom) / 100
      // The label line, the page's own padding, and the image at the zoomed width in the page's proportions.
      return 24 + 32 + ((width - 32) * zoom * pageSize.height) / (100 * pageSize.width)
    },
    initialOffset: () => (page - 1) * 1000,
    overscan: 1,
    onChange: (instance, scrolling) => {
      if (!pageCount || !positioned.current) return
      if (!personScrolling.current) {
        // Until the person scrolls, keep the requested page at the top while the pages around it are measured
        // and their sizes replace the estimates (the list otherwise drifted to page 4 when page 5 was asked for).
        const target = instance.measurementsCache[visiblePage.current - 1]
        const element = scrollRef.current
        if (!target || !element) return
        const wanted = Math.min(target.start, Math.max(0, instance.getTotalSize() - element.clientHeight))
        if (Math.abs((instance.scrollOffset ?? 0) - wanted) > 2)
          requestAnimationFrame(() => {
            if (!personScrolling.current) instance.scrollToOffset(wanted)
          })
        return
      }
      if (!scrolling) return
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
      personScrolling.current = false
      virtualizer.scrollToIndex(page - 1, { align: "start" })
      positioned.current = true
      return
    }
    if (page === visiblePage.current) return
    visiblePage.current = page
    personScrolling.current = false
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
            onPageSize={reportSize}
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
                  onPageSize={reportSize}
                  placeholderSize={pageSize}
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
