import { useEffect, useState } from "react"
import { Button } from "./button"
import { evidenceAPI } from "@/features/evidence/api"

export function EvidencePdfPage({
  evidenceId,
  page,
  onPageCount,
}: {
  evidenceId: string
  page: number
  onPageCount: (fileId: string, count: number) => void
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
        const response = await fetch(
          evidenceAPI.getPageImageUrl(evidenceId, page),
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            credentials: "include",
            signal: controller.signal,
          }
        )
        if (!response.ok)
          throw new Error(
            response.status === 401 || response.status === 403
              ? "You do not currently have access to this file. Sign in again or check your case access."
              : `Page ${page} could not be loaded. Try again or open the original file in a new tab.`
          )
        if (!response.headers.get("content-type")?.startsWith("image/png"))
          throw new Error("The server did not return a PDF page. Try again.")
        const count = Number(response.headers.get("X-PDF-Page-Count"))
        const blob = await response.blob()
        if (blob.size > 20 * 1024 * 1024)
          throw new Error(
            "This page is too large to display. Open the original file in a new tab."
          )
        if (
          controller.signal.aborted ||
          localStorage.getItem("authToken") !== token
        )
          return
        objectUrl = URL.createObjectURL(blob)
        setResult({ key, url: objectUrl })
        if (Number.isSafeInteger(count) && count >= page)
          onPageCount(evidenceId, count)
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
  }, [evidenceId, page, token, key, onPageCount])

  return (
    <div className="flex h-full min-h-0 flex-col">
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
      <div
        className="min-h-0 flex-1 overflow-auto p-4"
        aria-label="PDF page area"
      >
        {!current && <p role="status">Loading page {page}...</p>}
        {current?.error && (
          <div className="space-y-3">
            <p role="alert">{current.error}</p>
            <Button onClick={() => setRetry((v) => v + 1)}>Retry page</Button>
          </div>
        )}
        {current?.url && (
          <img
            className="block max-w-none bg-white"
            style={{ width: `${zoom}%` }}
            src={current.url}
            alt={`Page ${page} of the original PDF`}
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
