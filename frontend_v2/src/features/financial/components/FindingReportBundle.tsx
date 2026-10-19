import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { findingReportBundle } from "../lib/finding-report-bundle"
export function FindingReportBundle({
  entry,
  caseId,
}: {
  entry: CaseworkEntry
  caseId: string
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const request = useRef<AbortController | null>(null)
  useEffect(
    () => () => {
      request.current?.abort()
    },
    []
  )
  const files = entry.links.filter((link) => link.target_type === "evidence")
  return (
    <div className="space-y-2 text-sm">
      <p>
        The report package includes the note, saved payments and these whole
        source PDFs. A PDF may contain other statement periods.
      </p>
      <ul className="list-disc pl-5">
        {files.map((file) => (
          <li key={file.id}>{file.target_label || "Supporting file"}</li>
        ))}
      </ul>
      <Button
        variant="outline"
        disabled={busy || !files.length}
        onClick={async () => {
          if (request.current) return
          const controller = new AbortController()
          request.current = controller
          setBusy(true)
          setError("")
          const timer = setTimeout(() => controller.abort(), 120000)
          try {
            const bytes = await findingReportBundle(
              entry,
              caseId,
              controller.signal
            )
            if (controller.signal.aborted) return
            const url = URL.createObjectURL(
              new Blob([bytes], { type: "application/zip" })
            )
            const link = document.createElement("a")
            link.href = url
            link.download = `financial-note-${entry.id}.zip`
            link.click()
            setTimeout(() => URL.revokeObjectURL(url), 1000)
          } catch (failure) {
            if (!controller.signal.aborted)
              setError(
                failure instanceof Error
                  ? failure.message
                  : "The report package could not be prepared."
              )
            else
              setError(
                "Report preparation was cancelled or timed out. Try again."
              )
          } finally {
            clearTimeout(timer)
            request.current = null
            setBusy(false)
          }
        }}
      >
        {busy
          ? "Preparing report and PDFs…"
          : "Download report with source PDFs"}
      </Button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
