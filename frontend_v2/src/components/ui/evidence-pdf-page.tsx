import { useEffect, useState } from "react"
import { Button } from "./button"
import { loadPageImage } from "./pdf-page-images"

export function EvidencePdfPage({
  evidenceId,
  page,
  onPageCount,
  inline = false,
  documentZoom = 100,
  placeholderSize,
  onPageSize,
}: {
  evidenceId: string
  page: number
  onPageCount: (fileId: string, count: number) => void
  inline?: boolean
  documentZoom?: number
  /** Pixel size of a page of this document, so a page still loading takes the room it will take once shown. */
  placeholderSize?: { width: number; height: number } | null
  onPageSize?: (size: { width: number; height: number }) => void
}) {
  const [retry, setRetry] = useState(0)
  const [zoom, setZoom] = useState(100)
  const [result, setResult] = useState<{
    key: string
    url?: string
    error?: string
  } | null>(null)
  const token = localStorage.getItem("authToken")
  const key = JSON.stringify([evidenceId, page, token, retry])
  const current = result?.key === key ? result : null

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | undefined
    async function load() {
      try {
        const image = await loadPageImage(evidenceId, page, {
          token,
          signal: controller.signal,
        })
        if (
          controller.signal.aborted ||
          localStorage.getItem("authToken") !== token
        )
          return
        objectUrl = URL.createObjectURL(image.blob)
        setResult({ key, url: objectUrl })
        if (image.size) onPageSize?.(image.size)
        if (image.pageCount !== null) onPageCount(evidenceId, image.pageCount)
      } catch (error) {
        if (
          !controller.signal.aborted &&
          localStorage.getItem("authToken") === token
        )
          setResult({
            key,
            error:
              error instanceof Error
                ? error.message
                : "The PDF page could not be loaded.",
          })
      }
    }
    void load()
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [evidenceId, page, token, key, onPageCount, onPageSize])

  return (
    <div className={inline ? "" : "flex h-full min-h-0 flex-col"}>
      {!inline && (
        <div className="flex shrink-0 items-center gap-2 border-b px-4 py-2">
          <Button
            variant="outline"
            size="sm"
            aria-label="Zoom out PDF page"
            disabled={zoom <= 50}
            onClick={() => setZoom((v) => Math.max(50, v - 25))}
          >
            −
          </Button>
          <span className="text-sm">{zoom}%</span>
          <Button
            variant="outline"
            size="sm"
            aria-label="Zoom in PDF page"
            disabled={zoom >= 250}
            onClick={() => setZoom((v) => Math.min(250, v + 25))}
          >
            +
          </Button>
          <Button variant="outline" size="sm" onClick={() => setZoom(100)}>
            Fit page width
          </Button>
        </div>
      )}
      <div
        className={inline ? "p-4" : "min-h-0 flex-1 overflow-auto p-4"}
        aria-label="PDF page area"
      >
        {!current &&
          (placeholderSize ? (
            <div
              className="bg-muted/30"
              style={{
                width: `${inline ? documentZoom : zoom}%`,
                aspectRatio: `${placeholderSize.width} / ${placeholderSize.height}`,
              }}
            >
              <p role="status">Loading page {page}...</p>
            </div>
          ) : (
            <p role="status">Loading page {page}...</p>
          ))}
        {current?.error && (
          <div className="space-y-3">
            <p role="alert">{current.error}</p>
            <Button onClick={() => setRetry((v) => v + 1)}>Retry page</Button>
          </div>
        )}
        {current?.url && (
          <img
            className="block max-w-none bg-white"
            style={{ width: `${inline ? documentZoom : zoom}%` }}
            src={current.url}
            alt={`Page ${page} of the original PDF`}
            onLoad={(event) => {
              const { naturalWidth, naturalHeight } = event.currentTarget
              if (naturalWidth > 0 && naturalHeight > 0)
                onPageSize?.({ width: naturalWidth, height: naturalHeight })
            }}
            onError={() =>
              setResult({
                key,
                error: "The page image could not be displayed. Try again.",
              })
            }
          />
        )}
      </div>
    </div>
  )
}
