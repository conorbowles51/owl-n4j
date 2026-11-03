import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { agentAPI } from "../api"

/** CO-18 (agent): the agent never adds to a dossier itself. A person may accept one of its answers into a dossier
 * assessment; it is stored as AI-assisted and shows "Read by <model>, accepted by <name>". The phone records the
 * answer cites become the assessment's supporting links. */
export function AcceptAnswerIntoAssessment({ caseId, messageId }: { caseId: string; messageId: string }) {
  const [open, setOpen] = useState(false)
  const [dossier, setDossier] = useState("")
  const [category, setCategory] = useState("Assessment")
  const [done, setDone] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const targets = useCollectTargets(open ? caseId : "")
  const dossiers = targets.targets.filter((t) => t.kind === "dossier")
  if (!open) {
    return (
      <Button size="sm" variant="ghost" className="mt-1 h-7 px-2 text-xs" onClick={() => setOpen(true)}>
        Use in a dossier assessment
      </Button>
    )
  }
  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await agentAPI.acceptIntoAssessment(caseId, messageId, dossier, category.trim())
      const linked = r.cited_records.linked
      setDone(
        [
          r.read_by ?? "Added.",
          linked ? `${linked} cited phone record${linked === 1 ? "" : "s"} linked as support.` : null,
          r.cited_records.sentence,
        ]
          .filter(Boolean)
          .join(" "),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "The assessment could not be saved.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-2 flex max-w-xl flex-col gap-1 rounded border p-2 text-xs" aria-label="Use this answer in a dossier assessment">
      <label className="flex flex-col gap-0.5">
        Dossier
        <select className="rounded border bg-background p-1" value={dossier} onChange={(e) => setDossier(e.target.value)}>
          <option value="">Choose a dossier</option>
          {dossiers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </label>
      {targets.note && <p className="text-muted-foreground">{targets.note}</p>}
      <label className="flex flex-col gap-0.5">
        Assessment category
        <input className="rounded border bg-background p-1" value={category} maxLength={128} onChange={(e) => setCategory(e.target.value)} />
      </label>
      <p className="text-muted-foreground">
        Stored as AI-assisted: the assessment names the model that wrote this answer and you as the person who accepted it.
      </p>
      {done ? (
        <p role="status">Added to the dossier. {done}</p>
      ) : (
        <div className="flex gap-1">
          <Button size="sm" disabled={busy || !dossier || !category.trim()} onClick={save}>
            Add to the assessment
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
