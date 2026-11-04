import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ExportDialog } from "@/features/conversations/ExportDialog"
import { failureText, prepareSourceExport } from "@/features/phones/api"

type Prepared = Awaited<ReturnType<typeof prepareSourceExport>>
const fmt = (n: number) => n.toLocaleString("en-US")

/**
 * Export the phone records of a collection (a collected selection) or of a dossier for counsel (03 section 12.2,
 * 07 6.4 item 14). The records are gathered on the server (a collection is drawn as collected; a dossier's record
 * links and the members of its selections and conversations are frozen as one selection), and the export dialog draws
 * exactly those: its total is the collected count, and what is not a message or call is named as not in the export.
 */
export function CollectedPhoneExport(props: {
  caseId: string
  source: "collection" | "dossier"
  /** the collection's selection id, or the dossier's id */
  id: string
  label?: string
}) {
  const { caseId, source, id } = props
  const [prepared, setPrepared] = useState<Prepared | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      setPrepared(await prepareSourceExport(caseId, source, source === "collection" ? { selection_id: id } : { dossier_id: id }))
      setOpen(true)
    } catch (e) {
      setError(failureText(e, "The phone records could not be gathered for the export."))
    } finally {
      setBusy(false)
    }
  }
  const label = props.label ?? (source === "collection" ? "Export this collection" : "Export the phone records")
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-xs">
      <Button size="sm" variant="outline" disabled={busy} onClick={prepare}>
        {busy ? "Gathering the phone records…" : label}
      </Button>
      {prepared && !open && (
        <span>{fmt(prepared.collected)} {prepared.collected === 1 ? "phone record" : "phone records"} gathered.</span>
      )}
      {error && <span role="alert" className="text-destructive">{error}</span>}
      {prepared && (
        <ExportDialog caseId={caseId} filter={prepared.filter} words={prepared.words} open={open} onOpenChange={setOpen}
          source={source} note={prepared.sentence} />
      )}
    </span>
  )
}
