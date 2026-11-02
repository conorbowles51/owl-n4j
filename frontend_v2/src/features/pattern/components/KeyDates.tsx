import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { patternAPI } from "../api"
import { errorWords, keyDateWords, zonedResult } from "../lanes-lib"
import { WindowPanel } from "./WindowPanel"

/**
 * Key dates (04 section 8.6): entered once per case as Workspace notes, offered by every view. Choosing one opens
 * the window around it (07 J-5 "from a key date").
 */
export function KeyDatesBar({ caseId }: { caseId: string }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["pattern-key-dates", caseId], queryFn: () => patternAPI.keyDates(caseId, "date") })
  const [open, setOpen] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [label, setLabel] = useState("")
  const [local, setLocal] = useState("")
  const [zone, setZone] = useState("UTC")
  const [err, setErr] = useState<string | null>(null)
  async function save() {
    setErr(null)
    try {
      const { instant, problem } = zonedResult(local, zone)
      if (problem === "missing") { setErr(`${local.replace("T", " ")} did not happen in ${zone}: the clocks went forward over it. Enter the time as the person meant it.`); return }
      if (!instant) { setErr(`${zone} is not a time zone Loupe knows (for example America/New_York or UTC).`); return }
      await patternAPI.createKeyDate(caseId, { kind: "date", label, instant, zone })
      setAdding(false); setLabel(""); setLocal("")
      await qc.invalidateQueries({ queryKey: ["pattern-key-dates", caseId] })
    } catch (e) { setErr(errorWords(e)) }
  }
  const items = q.data?.items || []
  return (
    <section aria-label="Key dates" className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-1">
        <span className="font-medium">Key dates ({items.length.toLocaleString("en-US")})</span>
        {items.map((k) => (
          <Button key={k.entry_id} size="sm" variant={open === k.instant_utc ? "primary" : "outline"} onClick={() => setOpen(open === k.instant_utc ? null : k.instant_utc)}>
            {keyDateWords(k)}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={() => setAdding(!adding)}>Add a key date</Button>
      </div>
      {adding && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col">Name<input value={label} onChange={(e) => setLabel(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
          <label className="flex flex-col">When<input type="datetime-local" value={local} onChange={(e) => setLocal(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
          <label className="flex flex-col">In zone<input value={zone} onChange={(e) => setZone(e.target.value)} className="rounded border bg-background px-2 py-1" /></label>
          <Button size="sm" disabled={!label || !local} onClick={save}>Save to Workspace</Button>
        </div>
      )}
      {err && <p role="alert" className="text-destructive">{err}</p>}
      {open && <WindowPanel caseId={caseId} at={open} caseEvents={[]} onClose={() => setOpen(null)} />}
    </section>
  )
}

