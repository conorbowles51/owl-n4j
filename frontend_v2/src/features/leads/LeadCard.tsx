import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { LEVEL_DOT, leadsAPI, type Lead } from "./api"
import { openCorroborate } from "./open"
import { leadMembers } from "./lead-members"
import { clearLeadRecords, showLeadRecords, useShownLead } from "./highlight-store"


export function LevelBadge({ lead }: { lead: Lead }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
      <span className={cn("inline-block size-2.5 rounded-full", LEVEL_DOT[lead.level.key] ?? "bg-slate-300")} aria-hidden />
      {lead.level.name}
    </span>
  )
}

/** One lead on the Leads page or in the panel: its level, where it came from, what raises and lowers it, and the
 * actions. Loupe's own words stay visible beside a person's correction. */
export function LeadCard({ caseId, lead, compact = false }: { caseId: string; lead: Lead; compact?: boolean }) {
  const qc = useQueryClient()
  const shown = useShownLead()
  const showing = shown?.leadId === lead.id
  const [picking, setPicking] = useState(false)
  const [editing, setEditing] = useState(false)
  const [words, setWords] = useState(lead.title)
  const [error, setError] = useState<string | null>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ["leads", caseId] })
  const act = useMutation({
    mutationFn: (fn: () => Promise<Lead>) => fn(),
    onSuccess: () => { setError(null); refresh() },
    onError: (e) => setError(e instanceof Error ? e.message : "That did not work. Nothing was changed."),
  })
  const corrected = lead.corrections.length > 0
  const n = lead.detail.refs_total ?? lead.record_refs.length
  return (
    <article className="rounded-lg border bg-card p-4 shadow-sm" data-lead={lead.id} data-level={lead.level.key}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <LevelBadge lead={lead} />
        {lead.kind_words.map((k) => <span key={k} className="rounded bg-muted px-1.5 py-0.5">{k}</span>)}
        <span>{lead.origin_words}</span>
        {lead.state !== "new" && <span className="font-medium text-foreground">{lead.state_words}</span>}
        {n > 0 && <span>{n.toLocaleString()} record{n === 1 ? "" : "s"}</span>}
      </div>
      {editing ? (
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); act.mutate(() => leadsAPI.correct(caseId, lead.id, "title", words)); setEditing(false) }}>
          <input className="min-w-0 flex-1 rounded border px-2 py-1 text-sm" value={words} onChange={(e) => setWords(e.target.value)} aria-label="Your words for this lead" />
          <Button size="sm" type="submit">Save</Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setEditing(false)}>Cancel</Button>
        </form>
      ) : (
        <h3 className="mt-2 text-sm font-semibold leading-snug">{lead.title}</h3>
      )}
      {corrected && <p className="mt-1 text-xs text-muted-foreground">Loupe read: {lead.read.title}</p>}
      {lead.summary && lead.summary !== lead.title && <p className="mt-1 text-sm text-muted-foreground">{lead.summary}</p>}
      {!compact && lead.raises.length > 0 && (
        <div className="mt-2 text-xs"><span className="font-semibold">Raises it: </span>{lead.raises.join(" · ")}</div>
      )}
      {!compact && lead.lowers.length > 0 && (
        <div className="mt-1 text-xs"><span className="font-semibold">Lowers it: </span>{lead.lowers.join(" · ")}</div>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">{lead.read.words}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => openCorroborate({ caseId, screen: "Leads", label: lead.title, ...leadMembers(lead), people: lead.people.map((p) => p.key), ...(lead.period.from ? { period: { from: lead.period.from, to: lead.period.to ?? lead.period.from } } : {}) }, { keep: false })}>Corroborate</Button>
        {n > 0 && (showing
          ? <Button size="sm" variant="outline" onClick={() => clearLeadRecords(lead.id)}>Stop showing these records</Button>
          : <Button size="sm" variant="outline" data-guide="lead-show-records" onClick={() => showLeadRecords(lead.id, lead.title, lead.record_refs, { caseId, period: lead.period })}>Show these records</Button>)}
        {!lead.finding_id && <Button size="sm" variant="outline" onClick={() => setPicking((x) => !x)}>Add to theory</Button>}
        {lead.state !== "looking" && lead.state !== "in_theory" && <Button size="sm" variant="ghost" onClick={() => act.mutate(() => leadsAPI.state(caseId, lead.id, "looking"))}>Looking into it</Button>}
        {lead.state !== "not_relevant" && lead.state !== "in_theory" && <Button size="sm" variant="ghost" onClick={() => act.mutate(() => leadsAPI.state(caseId, lead.id, "not_relevant"))}>Not relevant</Button>}
        {lead.state === "not_relevant" && <Button size="sm" variant="ghost" onClick={() => act.mutate(() => leadsAPI.state(caseId, lead.id, "new"))}>Relevant after all</Button>}
        {!editing && <Button size="sm" variant="ghost" onClick={() => { setWords(lead.title); setEditing(true) }}>Edit words</Button>}
      </div>
      {picking && <TheoryPicker caseId={caseId} onPick={(id) => { setPicking(false); act.mutate(() => leadsAPI.confirm(caseId, lead.id, id)) }} />}
      {lead.confirmed && <p className="mt-2 text-xs">In the theory: confirmed by {lead.confirmed.by}, with Loupe named as the reading's author.</p>}
      {error && <p className="mt-2 text-xs text-red-700" role="alert">{error}</p>}
    </article>
  )
}

export function TheoryPicker({ caseId, onPick }: { caseId: string; onPick: (id: string) => void }) {
  const t = useCollectTargets(caseId)
  const theories = t.targets.filter((x) => x.kind === "theory")
  return (
    <div className="mt-2 rounded border bg-muted/40 p-2 text-sm">
      <p className="text-xs text-muted-foreground">Confirming adds this lead to the theory as a finding under your name.</p>
      {theories.length === 0 ? <p className="mt-1 text-xs">This case has no theory yet. Start one in Workspace, then add the lead.</p> : (
        <ul className="mt-1 space-y-1">
          {theories.map((x) => <li key={x.id}><button type="button" className="underline" onClick={() => onPick(x.id)}>{x.label}</button></li>)}
        </ul>
      )}
    </div>
  )
}
