import { useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useSwitch } from "@/lib/ui-switches"
import { KIND_FILTERS, leadsAPI, searchedWords, type Lead } from "./api"
import { LeadCard } from "./LeadCard"

const MAIN = new Set(["strong", "probable", "possible", "cant_tell"])

function when(iso?: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

/** The Leads page (lx-leads B, screen 1): every lead strongest first, the only place leads are listed. */
export function LeadsPage() {
  const { id: caseId = "" } = useParams()
  const on = useSwitch("corroborate-v2")
  const qc = useQueryClient()
  const [kind, setKind] = useState<string | null>(null)
  const [openCoincidence, setOpenCoincidence] = useState(false)
  const list = useQuery({
    queryKey: ["leads", caseId],
    queryFn: () => leadsAPI.list(caseId),
    enabled: !!caseId && on,
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.finder.status) ? 3000 : false),
  })
  const find = useMutation({ mutationFn: () => leadsAPI.find(caseId), onSuccess: () => qc.invalidateQueries({ queryKey: ["leads", caseId] }) })
  const leads = useMemo(() => list.data?.leads ?? [], [list.data])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const f of KIND_FILTERS) c[f.key] = leads.filter((l) => MAIN.has(l.level.key) || l.level.key === "coincidence").filter((l) => l.kinds.some((k) => f.kinds.includes(k))).length
    return c
  }, [leads])
  if (!on) return <div className="p-6 text-sm text-muted-foreground">Leads are not turned on for this browser.</div>
  const kinds = kind ? KIND_FILTERS.find((f) => f.key === kind)?.kinds ?? [] : null
  const fits = (l: Lead) => !kinds || l.kinds.some((k) => kinds.includes(k))
  const main = leads.filter((l) => MAIN.has(l.level.key) && l.state !== "not_relevant" && fits(l))
  const coincidence = leads.filter((l) => l.level.key === "coincidence" && l.state !== "not_relevant" && fits(l))
  const noLink = leads.filter((l) => l.level.key === "no_link_found")
  const aside = leads.filter((l) => l.level.key === "set_aside")
  const notRelevant = leads.filter((l) => l.state === "not_relevant" && l.level.key !== "set_aside" && l.level.key !== "no_link_found")
  const all = leads.filter((l) => MAIN.has(l.level.key) || l.level.key === "coincidence").length
  const finder = list.data?.finder
  const busy = finder && ["queued", "running"].includes(finder.status)
  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4 sm:p-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">Leads</h1>
          <Button size="sm" variant="outline" data-guide="leads-find" disabled={!!busy || find.isPending} onClick={() => find.mutate()}>
            {busy ? (finder?.step || "Looking for leads…") : "Look for leads now"}
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Patterns across every kind of record that may show people acting together. Each is graded by Loupe's rules
          against the case's ordinary days, with what raises and lowers it. Open one to Corroborate it further.
        </p>
        {find.error && <p className="text-xs text-red-700" role="alert">{find.error instanceof Error ? find.error.message : "Loupe could not start looking."}</p>}
        {finder?.new_material && !busy && <p className="text-xs font-medium" role="status">New material has arrived since Loupe last looked. Look again to bring the leads up to date.</p>}
        {finder?.status === "failed" && <p className="text-xs text-red-700" role="alert">The last search for leads stopped: {finder.error}</p>}
      </header>
      <div className="flex flex-wrap gap-2" role="toolbar" aria-label="Filter leads by kind" data-guide="leads-filters">
        <FilterChip active={!kind} onClick={() => setKind(null)}>All {all}</FilterChip>
        {KIND_FILTERS.map((f) => <FilterChip key={f.key} active={kind === f.key} onClick={() => setKind(f.key)}>{f.label} {counts[f.key] ?? 0}</FilterChip>)}
      </div>
      {list.isLoading && <p className="text-sm text-muted-foreground">Loading leads…</p>}
      {list.error && <p className="text-sm text-red-700" role="alert">The leads could not be read: {list.error instanceof Error ? list.error.message : "error"}</p>}
      {list.data && leads.length === 0 && (
        <p className="rounded border p-4 text-sm text-muted-foreground">
          {finder?.status === "never" ? "Loupe has not looked for leads in this case yet. Press Look for leads now, or Corroborate any selection: each answer is saved here." : "No leads yet."}
        </p>
      )}
      <section className="space-y-3" aria-label="Leads, strongest first" data-guide="leads-list">
        {main.map((l) => <LeadCard key={l.id} caseId={caseId} lead={l} />)}
      </section>
      {coincidence.length > 0 && (
        <section className="rounded-lg border">
          <button type="button" className="flex w-full items-center justify-between p-3 text-sm font-semibold" aria-expanded={openCoincidence} onClick={() => setOpenCoincidence((x) => !x)}>
            <span>Coincidence likely ({coincidence.length})</span><span aria-hidden>{openCoincidence ? "−" : "+"}</span>
          </button>
          {openCoincidence && <div className="space-y-3 p-3 pt-0">{coincidence.map((l) => <LeadCard key={l.id} caseId={caseId} lead={l} />)}</div>}
        </section>
      )}
      {noLink.length > 0 && (
        <section className="space-y-2" aria-label="No link found">
          <h2 className="text-sm font-semibold">No link found</h2>
          {noLink.map((l) => (
            <div key={l.id} className="rounded-lg border p-3 text-sm" data-lead={l.id} data-level="no_link_found">
              <p className="font-medium">{l.people.find((p) => p.key === l.detail.person)?.label ?? l.title}</p>
              <p className="text-muted-foreground">{l.summary}</p>
              {searchedWords(l.searched) && <p className="mt-1 text-xs text-muted-foreground">Searched: {searchedWords(l.searched)}</p>}
            </div>
          ))}
        </section>
      )}
      {(aside.length > 0 || notRelevant.length > 0) && (
        <section className="space-y-1" aria-label="Weighed down or set aside">
          <h2 className="text-sm font-semibold">Weighed down or set aside</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {aside.map((l) => <li key={l.id} data-lead={l.id}>{l.summary || l.title}</li>)}
            {notRelevant.map((l) => <li key={l.id} data-lead={l.id}>Marked not relevant: {l.title}</li>)}
          </ul>
        </section>
      )}
      <footer className="border-t pt-3 text-xs text-muted-foreground">
        <p className="font-semibold">How leads are found</p>
        <p>
          Loupe looks across every record for contact through a third number, phones in the same place on the same
          night, people acting in step, payments after events, the same words or files in separate places, silences
          and deletions around key dates, and documents naming people together. Each lead is compared with the case's
          ordinary days before it is shown. Photos are never read as where a phone was.
        </p>
        {finder?.finished_at && <p className="mt-1">Last checked {when(finder.finished_at)}.{finder.new_material ? " New material has arrived since then: press Look for leads now to bring the leads up to date." : ""}</p>}
      </footer>
    </div>
  )
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
      className={cn("rounded-full border px-3 py-1 text-xs", active ? "border-slate-900 bg-slate-900 text-white" : "hover:bg-muted")}>
      {children}
    </button>
  )
}
