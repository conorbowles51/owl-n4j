import { useState } from "react"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { openProtectedFile, useProtectedObjectUrl } from "@/lib/protected-file"

/** Source tools stay alongside the editor; switching views never remounts its draft. */
export function StatementSourceTools({
  fileId,
  page,
  text,
}: {
  fileId: string
  page: number
  text: string
}) {
  const [view, setView] = useState<"page" | "pdf" | "text">("page")
  const [error, setError] = useState("")
  const [opening, setOpening] = useState(false)
  const url = evidenceAPI.getFileUrl(fileId)
  const pdf = useProtectedObjectUrl(url, view === "pdf")
  return (
    <section className="space-y-2 mb-3" aria-label="Statement source tools">
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={opening}
          onClick={async () => {
            setError("")
            setOpening(true)
            try {
              await openProtectedFile(url, page)
            } catch (e) {
              setError(
                e instanceof Error
                  ? e.message
                  : "Could not open the original. Try again."
              )
            } finally {
              setOpening(false)
            }
          }}
        >
          {opening ? "Opening original…" : "Open original in new tab"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-pressed={view === "pdf"}
          onClick={() => setView(view === "pdf" ? "page" : "pdf")}
        >
          Select text in original PDF
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-pressed={view === "text"}
          onClick={() => setView(view === "text" ? "page" : "text")}
        >
          Copy page text
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {view === "pdf" && (
        <>
          <p className="text-xs text-muted-foreground">
            Select and copy text from the original. For scanned pages, use Copy
            page text and check the reading against the image below. Your
            corrections stay open. If the PDF does not display in your browser,
            use Open original in new tab or Copy page text.
          </p>
          {pdf.loading && <p role="status">Loading original PDF…</p>}
          {pdf.error && (
            <p role="alert">
              The original could not be loaded. Close this view and reopen it to
              retry.
            </p>
          )}
          {pdf.objectUrl && (
            <iframe
              title={`Original statement, page ${page}`}
              src={`${pdf.objectUrl}#page=${page}`}
              className="w-full h-[50vh] border rounded"
            />
          )}
        </>
      )}
      {view === "text" && (
        <>
          <label
            className="text-xs font-medium"
            htmlFor={`source-text-${fileId}`}
          >
            Read page text · page {page}
          </label>
          <p className="text-xs text-muted-foreground">
            This is extracted text and may contain reading errors or a different
            order. Compare it with the original before saving a correction.
          </p>
          <textarea
            id={`source-text-${fileId}`}
            readOnly
            value={text}
            onFocus={(e) => e.currentTarget.select()}
            className="w-full h-48 border rounded p-2 text-sm"
          />
          {!text && (
            <p role="status">
              No extracted text is available on this page. Open the original to
              inspect it.
            </p>
          )}
        </>
      )}
    </section>
  )
}
