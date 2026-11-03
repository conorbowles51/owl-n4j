import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ExportDialog } from "@/features/conversations/ExportDialog"
import { failureText, prepareSourceExport } from "@/features/phones/api"

type Prepared = Awaited<ReturnType<typeof prepareSourceExport>>

/**
 * Export the messages and calls behind an analysis result, a kept result, a statement check or an incident window
 * (07 J-14b). The records are frozen as one selection first, so the export holds exactly them; what behind it is not a
 * message or call is said in the dialog, and a source with none is refused with that reason.
 */
export function SourceExport({ caseId, source, refBody, label = "Export…" }: {
  caseId: string; source: "analysis_result" | "statement_check" | "incident_window"; refBody: Record<string, unknown>; label?: string
}) {
  const [prepared, setPrepared] = useState<Prepared | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      setPrepared(await prepareSourceExport(caseId, source, refBody))
      setOpen(true)
    } catch (e) {
      setError(failureText(e, "The records could not be gathered for the export."))
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-xs">
      <Button size="sm" variant="outline" disabled={busy} onClick={prepare}>{busy ? "Gathering the records…" : label}</Button>
      {error && <span role="alert" className="text-destructive">{error}</span>}
      {prepared && (
        <ExportDialog caseId={caseId} filter={prepared.filter} words={prepared.words} open={open} onOpenChange={setOpen}
          source={source} note={prepared.sentence} />
      )}
    </span>
  )
}
