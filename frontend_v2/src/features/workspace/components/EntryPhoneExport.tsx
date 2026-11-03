import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ExportDialog } from "@/features/conversations/ExportDialog"
import { failureText, prepareEntryExport } from "@/features/phones/api"

type Prepared = Awaited<ReturnType<typeof prepareEntryExport>>
const fmt = (n: number) => n.toLocaleString("en-US")

/**
 * Export a finding, theory or note's phone records for counsel (07 XF-7, CO-12). The records collected into the
 * entry (single messages, saved selections and whole conversations) are frozen as one selection, and the export
 * dialog draws exactly those: its total is the collected count, and anything linked that is not a message or call
 * is named as not in the export.
 */
export function EntryPhoneExport({ caseId, entryId }: { caseId: string; entryId: string }) {
  const [prepared, setPrepared] = useState<Prepared | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      setPrepared(await prepareEntryExport(caseId, entryId))
      setOpen(true)
    } catch (e) {
      setError(failureText(e, "The phone records could not be gathered for the export."))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Button size="sm" variant="outline" disabled={busy} onClick={prepare}>
        {busy ? "Gathering the phone records…" : "Export the phone records"}
      </Button>
      {prepared && !open && (
        <span>{fmt(prepared.collected)} {prepared.collected === 1 ? "phone record" : "phone records"} gathered.</span>
      )}
      {error && <span role="alert" className="text-destructive">{error}</span>}
      {prepared && (
        <ExportDialog caseId={caseId} filter={prepared.filter} words={prepared.words} open={open} onOpenChange={setOpen}
          source="finding" note={prepared.sentence} />
      )}
    </div>
  )
}
