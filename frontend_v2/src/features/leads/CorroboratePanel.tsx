import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { corroborateAPI, type SuggestedQuestion } from "@/features/corroborate/api"
import { ResultView } from "@/features/corroborate/ResultView"
import { QuestionMenu } from "@/features/corroborate/QuestionMenu"
import { selectionCount, useSelection } from "@/features/corroborate/selection-store"
import { relationAPI, runIsWorking } from "@/features/relations/api"
import { leadsAPI } from "./api"
import { LeadCard } from "./LeadCard"
import { CORROBORATE_OPEN, takePendingCorroborate, type CorroborateRequest } from "./open"
import { clearLeadRecords, showLeadRecords, useShownLead } from "./highlight-store"
import { EMPTY_SCOPE, scopeHref } from "@/features/phones/ui/scope"

/**
 * Corroborate from anywhere (lx-leads C, screen 7): the panel over the current page. "Leads already here" is the one
 * list filtered to the selection's records, people and period; "Ask a new question" runs Corroborate, shows the
 * answer here, and the answer is saved to Leads. Closing returns to the page as it was.
 */
export function CorroboratePanel() {
  const [req, setReq] = useState<CorroborateRequest | null>(() => takePendingCorroborate())
  useEffect(() => {
    const open = (e: Event) => setReq((e as CustomEvent<CorroborateRequest>).detail)
    window.addEventListener(CORROBORATE_OPEN, open)
    return () => window.removeEventListener(CORROBORATE_OPEN, open)
  }, [])
  useEffect(() => {
    if (!req) return
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setReq(null) }
    window.addEventListener("keydown", esc)
    return () => window.removeEventListener("keydown", esc)
  }, [req])
  return (
    <>
      <ShownLeadBar />
      {req && <Panel key={`${req.caseId}:${req.label}:${req.members.length}`} req={req} onClose={() => setReq(null)} />}
    </>
  )
}

function Panel({ req, onClose }: { req: CorroborateRequest; onClose: () => void }) {
  const [tab, setTab] = useState<"here" | "ask">("here")
  const refs = req.members.map((m) => `${m.type}:${m.id}`)
  const here = useQuery({
    queryKey: ["leads", req.caseId, "here", refs.join(","), (req.people ?? []).join(","), req.period?.from, req.period?.to],
    queryFn: () => leadsAPI.here(req.caseId, { records: refs, people: req.people, from: req.period?.from, to: req.period?.to }),
  })
  const n = here.data?.leads.length
  return (
    <aside role="dialog" aria-label="Corroborate" className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-background shadow-2xl sm:w-[440px]">
      <div className="flex items-center justify-between border-b p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Corroborate · from {req.label}</p>
        <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
      </div>
      {!!req.skipped?.length && (
        <p className="border-b bg-amber-50 p-2 text-xs dark:bg-amber-400/10" role="status">
          Corroborate cannot read {req.skipped.map((x) => `${x.count.toLocaleString()} ${x.type}`).join(", ")} of what you chose yet; the rest is asked about.
        </p>
      )}
      <div className="flex border-b text-sm" role="tablist">
        <button role="tab" aria-selected={tab === "here"} className={cn("flex-1 p-2", tab === "here" && "border-b-2 border-slate-900 font-semibold")} onClick={() => setTab("here")}>
          Leads already here{n !== undefined ? ` ${n}` : ""}
        </button>
        <button role="tab" aria-selected={tab === "ask"} className={cn("flex-1 p-2", tab === "ask" && "border-b-2 border-slate-900 font-semibold")} onClick={() => setTab("ask")}>
          Ask a new question
        </button>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {tab === "here" && (
          <>
            {here.isLoading && <p className="text-sm text-muted-foreground">Reading the leads…</p>}
            {here.error && <p className="text-sm text-red-700" role="alert">The leads could not be read.</p>}
            {here.data && here.data.leads.length === 0 && <p className="text-sm text-muted-foreground">No lead touches these records, people or dates yet. Ask a new question.</p>}
            {here.data?.leads.map((l) => <LeadCard key={l.id} caseId={req.caseId} lead={l} compact />)}
          </>
        )}
        {tab === "ask" && <Ask req={req} />}
      </div>
    </aside>
  )
}

function Ask({ req }: { req: CorroborateRequest }) {
  const qc = useQueryClient()
  const preview = useQuery({ queryKey: ["corroborate-preview", req.caseId, req.members.map((m) => `${m.type}:${m.id}`).join("|")], queryFn: () => corroborateAPI.preview(req.caseId, req.members), enabled: req.members.length > 0 })
  const [group, setGroup] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [menu, setMenu] = useState(false)
  const gathered = selectionCount(useSelection(req.caseId))
  const run = useQuery({
    queryKey: ["relation-query", req.caseId, group],
    queryFn: () => relationAPI.get(req.caseId, group as string),
    enabled: !!group,
    refetchInterval: (q) => (runIsWorking(q.state.data?.run) ? 2000 : false),
  })
  const r = run.data?.run
  const corro = r?.result?.corroboration
  const lead = useQuery({
    queryKey: ["leads", req.caseId, "run", r?.id],
    queryFn: () => leadsAPI.here(req.caseId, { records: req.members.map((m) => `${m.type}:${m.id}`) }),
    enabled: !!corro && !!r?.id,
    select: (d) => d.leads.find((l) => l.run_id === r?.id) ?? null,
  })
  const ask = async (q: SuggestedQuestion) => {
    setBusy(true)
    setError(null)
    try {
      const made = await corroborateAPI.run(req.caseId, { members: req.members, surface: "corroborate", question: { kind: q.kind, text: q.text, chips: q.chips } })
      setGroup(made.group.id)
      qc.invalidateQueries({ queryKey: ["leads", req.caseId] })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Corroborate could not start. Nothing was saved.")
    } finally {
      setBusy(false)
    }
  }
  if (!req.members.length) return <p className="text-sm text-muted-foreground">Nothing is selected to ask about.</p>
  if (group) {
    return (
      <div className="space-y-3">
        {(!r || runIsWorking(r)) && <p className="text-sm text-muted-foreground">{r?.step || "Corroborate is weighing the records…"}</p>}
        {r?.status === "failed" && <p className="text-sm text-red-700" role="alert">Corroborate stopped: {r.error}</p>}
        {corro && <ResultView c={corro} caseId={req.caseId} runId={r?.id} />}
        {corro && (
          <div className="rounded border bg-muted/40 p-3 text-sm">
            <p>✓ Saved to Leads as <strong>Asked by you</strong>, a reading by Loupe until you confirm it.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" asChild><Link to={`/cases/${req.caseId}/leads`}>Open in Leads</Link></Button>
              {lead.data && <Button size="sm" variant="outline" onClick={() => showLeadRecords(lead.data!.id, lead.data!.title, lead.data!.record_refs, { caseId: req.caseId, period: lead.data!.period })}>Show these records</Button>}
            </div>
            {lead.data && <div className="mt-3"><LeadCard caseId={req.caseId} lead={lead.data} compact /></div>}
          </div>
        )}
        <Button size="sm" variant="ghost" onClick={() => setGroup(null)}>Ask another question</Button>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">What do you want to know?</p>
      {preview.isLoading && <p className="text-sm text-muted-foreground">Reading what you chose…</p>}
      {preview.data?.questions.map((q) => (
        <button key={q.kind} type="button" disabled={busy} onClick={() => ask(q)} className="block w-full rounded border p-2 text-left text-sm hover:bg-muted">
          <span className="font-medium">{q.text}</span>
          {q.count_words && <span className="block text-xs text-muted-foreground">{q.count_words}</span>}
        </button>
      ))}
      {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
      <Button size="sm" variant="outline" onClick={() => setMenu(true)}>
        Choose the question yourself{gathered > req.members.length ? ` (all ${gathered.toLocaleString("en-US")} selected items)` : ""}…
      </Button>
      {menu && <QuestionMenu caseId={req.caseId} initialScope={req.scope} onClose={() => setMenu(false)} />}
    </div>
  )
}

const LEAD_PAGES: [string, string][] = [["conversations", "Conversations"], ["timeline", "Timeline"], ["map", "Map"]]

/** Conversations opens its first thread unless a record is named; naming the lead's first phone record opens every
 * message on the lead's days instead, with that record beside them. */
function firstPhoneRecord(refs: Set<string>): Record<string, string> {
  for (const r of refs) if (r.startsWith("phone_record:")) return { record: r.slice("phone_record:".length) }
  return {}
}

/** The lead's days as a phone scope window (null when the lead has no dates: the page then opens on everything). */
function leadWindow(period?: { from?: string; to?: string }): { from: string; to: string } | null {
  const from = period?.from ?? period?.to
  const to = period?.to ?? period?.from
  return from && to ? { from: from.slice(0, 10), to: to.slice(0, 10) } : null
}

/** While a lead's records are shown, a bar says so on every page, with links to the lead's days on Conversations,
 * the timeline and the map (in-page links, so the marks stay), and the way to stop. */
function ShownLeadBar() {
  const shown = useShownLead()
  if (!shown) return null
  return (
    <div className="fixed bottom-3 left-1/2 z-50 flex max-w-[95vw] -translate-x-1/2 flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl border bg-background px-4 py-2 text-xs shadow-lg sm:flex-nowrap sm:rounded-full" role="status">
      <span className="min-w-0 truncate">Showing {shown.refs.size.toLocaleString()} records of the lead “{shown.title}”</span>
      {shown.caseId && (
        <span className="flex shrink-0 gap-2" aria-label="Open the lead's days">
          {LEAD_PAGES.map(([path, words]) => (
            <Link key={path} className="underline" to={scopeHref(`/cases/${shown.caseId}/${path}`, { ...EMPTY_SCOPE, window: leadWindow(shown.period) },
                                                                 path === "conversations" ? firstPhoneRecord(shown.refs) : {})}>{words}</Link>
          ))}
        </span>
      )}
      <Button size="sm" variant="ghost" onClick={() => clearLeadRecords()}>Close</Button>
    </div>
  )
}
