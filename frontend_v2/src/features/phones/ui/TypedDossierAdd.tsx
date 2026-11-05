import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { dossiersAPI } from "@/features/dossiers/api"
import { liveCollectClient, resultSentence, undoCollect, type CollectLink, type CollectResult, type CollectTarget } from "../collect.api"

const WORDS = { device: "device", address: "address" } as const

/**
 * A phone goes into a device dossier and a place into an address dossier (07 J-2, J-10, 6.1): an existing dossier of
 * that type, or a new one under a name a person types. A saved link keeps the record behind it; undo takes the link
 * away and leaves the dossier.
 */
export function TypedDossierAdd({ caseId, type, link, suggestedName, origin, disabledReason }: {
  caseId: string
  type: "device" | "address"
  link: CollectLink
  suggestedName: string
  origin: string
  disabledReason?: string
}) {
  const word = WORDS[type]
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState("")
  const [name, setName] = useState(suggestedName)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ words: string; target: CollectTarget; result: CollectResult } | null>(null)
  const list = useQuery({
    queryKey: ["dossiers", caseId, "typed", type],
    queryFn: () => dossiersAPI.list({ caseId, dossierType: type, limit: 200 }),
    enabled: open,
  })
  const add = async () => {
    setBusy(true)
    setError(null)
    try {
      const existing = list.data?.dossiers.find((d) => d.id === target)
      const dossier = existing ?? (await dossiersAPI.create({ case_id: caseId, display_name: name.trim(), dossier_type: type }))
      const chosen: CollectTarget = { kind: "dossier", id: dossier.id, label: dossier.display_name }
      const result = await liveCollectClient.add(caseId, chosen, [link], { relationship: "unclassified", role: "link", origin })
      setDone({ words: resultSentence(result, "item", chosen), target: chosen, result })
      setOpen(false)
      await client.invalidateQueries({ queryKey: ["dossiers", caseId] })
      await client.invalidateQueries({ queryKey: ["collect-targets", caseId] })
    } catch (e) {
      setError(e instanceof Error ? e.message : "It could not be added.")
    } finally {
      setBusy(false)
    }
  }
  const undo = async () => {
    if (!done) return
    try {
      await undoCollect(caseId, done.target, done.result)
      setDone(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "It could not be undone.")
    }
  }
  return (
    <div className="inline-flex flex-col gap-1 text-sm">
      <Button size="sm" variant="outline" aria-expanded={open} disabled={!!disabledReason} title={disabledReason} onClick={() => setOpen((v) => !v)}>
        Add to {word === "address" ? "an" : "a"} {word} dossier
      </Button>
      {open && (
        <div className="flex flex-col gap-1 rounded border bg-card p-2 text-xs" role="group" aria-label={`Add to ${word === "address" ? "an" : "a"} ${word} dossier`}>
          <label className="flex flex-col gap-0.5">
            {word === "device" ? "Device dossier" : "Address dossier"}
            <select className="rounded border bg-background px-1 py-0.5" value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">A new {word} dossier</option>
              {(list.data?.dossiers ?? []).map((d) => <option key={d.id} value={d.id}>{d.display_name}</option>)}
            </select>
          </label>
          {!target && (
            <label className="flex flex-col gap-0.5">
              Name of the new dossier
              <input className="rounded border bg-background px-1 py-0.5" maxLength={255} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          )}
          {(list.data?.total ?? 0) > (list.data?.dossiers.length ?? 0) && (
            <p>Offering the {list.data!.dossiers.length.toLocaleString("en-US")} most recently changed of {list.data!.total.toLocaleString("en-US")}.</p>
          )}
          <div>
            <Button size="sm" disabled={busy || (!target && !name.trim())} onClick={() => void add()}>Add</Button>
          </div>
        </div>
      )}
      {disabledReason && <span className="text-xs text-muted-foreground">{disabledReason}</span>}
      {done && (
        <p role="status" className="text-xs">
          {done.words}{" "}
          {done.result.added > 0 && <button type="button" className="underline underline-offset-2" onClick={() => void undo()}>Undo</button>}
        </p>
      )}
      {error && <p role="alert" className="text-xs">{error}</p>}
    </div>
  )
}
