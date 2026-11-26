import { useMemo, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { cn } from "@/lib/cn"
import { useSwitch } from "@/lib/ui-switches"
import { relationAPI, runIsWorking, setCurrentQuery, type RelationMember } from "@/features/relations/api"
import { leadsAPI } from "@/features/leads/api"
import { LeadCard } from "@/features/leads/LeadCard"
import { LeadsPage } from "@/features/leads/LeadsPage"
import { readCorroborateRequest } from "@/features/leads/open"
import { corroborateAPI } from "../api"
import { selectionMembers, useSelection } from "../selection-store"
import { ClaimResult } from "../ClaimResult"
import { QuestionSentence, type Draft } from "./QuestionSentence"
import { AnswerView } from "./AnswerView"

type Tab = "ask" | "leads" | "earlier"

/**
 * Corroborate (lx-corroredo, design screen 5): the one place answers are read. Three tabs: Ask a question, Leads Loupe
 * found, Your earlier questions. The question is a sentence whose parts can be changed; nothing runs until Ask.
 * ``?q=<question id>`` opens an asked question's answer; ``?from=selection`` fills the question from what was chosen
 * on another screen; ``?from=tray`` (or nothing) from the case-wide selection.
 */
export function CorroboratePage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const on = useSwitch("corroborate-v2")
  const tab = (["ask", "leads", "earlier"].includes(params.get("tab") ?? "") ? params.get("tab") : "ask") as Tab
  const setTab = (t: Tab) => { const next = new URLSearchParams(params); next.set("tab", t); setParams(next) }
  const leads = useQuery({ queryKey: ["leads", caseId], queryFn: () => leadsAPI.list(caseId), enabled: !!caseId && on })
  const all = leads.data?.leads ?? []
  const found = all.filter((l) => l.origin !== "asked").length
  const earlier = all.filter((l) => l.origin === "asked")
  if (!on) return <div className="p-6 text-sm text-muted-foreground">Corroborate is turned off in this browser. Add ?corroborate-v2=on to the address to turn it on.</div>
  return (
    <main className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6" data-guide="corroborate-page">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Corroborate a claim</p>
        <h1 className="text-2xl font-semibold">Corroborate</h1>
        <p className="text-sm text-muted-foreground">Is a pattern more than coincidence? Loupe compares the moments that matter with ordinary days, using fixed rules, never AI.</p>
      </header>
      <div role="tablist" aria-label="Corroborate" data-guide="corroborate-tabs" className="flex flex-wrap gap-1 border-b">
        <TabButton on={tab === "ask"} onClick={() => setTab("ask")}>Ask a question</TabButton>
        <TabButton on={tab === "leads"} onClick={() => setTab("leads")}>Leads Loupe found{leads.data ? ` (${found})` : ""}</TabButton>
        <TabButton on={tab === "earlier"} onClick={() => setTab("earlier")}>Your earlier questions{leads.data ? ` (${earlier.length})` : ""}</TabButton>
      </div>
      {tab === "ask" && <AskTab caseId={caseId} />}
      {tab === "leads" && <LeadsPage embedded exclude="asked" />}
      {tab === "earlier" && (
        <section aria-label="Your earlier questions" className="space-y-3">
          {leads.isLoading && <p className="text-sm text-muted-foreground" role="status">Reading your earlier questions…</p>}
          {leads.error && <p className="text-sm text-status-error" role="alert">Your earlier questions could not be read. Reload the page to try again.</p>}
          {leads.data && earlier.length === 0 && <p className="rounded border p-4 text-sm text-muted-foreground">You have not asked a question in this case yet. Every answer you get is kept here.</p>}
          {earlier.map((l) => (
            <div key={l.id} className="space-y-1">
              <LeadCard caseId={caseId} lead={l} />
              <Link className="text-sm text-status-info underline" to={`?tab=ask&q=${encodeURIComponent(l.selection_id)}`}>Open the answer</Link>
            </div>
          ))}
        </section>
      )}
    </main>
  )
}

function TabButton({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" role="tab" aria-selected={on} onClick={onClick}
      className={cn("-mb-px border-b-2 px-3 py-2 text-sm", on ? "border-foreground font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
      {children}
    </button>
  )
}

/** Where the question's records come from: an asked question, a request from another screen, or the selection. */
function useSource(caseId: string, q: string | null, from: string | null) {
  const parts = useSelection(caseId)
  const asked = useQuery({
    queryKey: ["relation-query", caseId, q],
    queryFn: () => relationAPI.get(caseId, q as string),
    enabled: !!q,
    refetchInterval: (x) => (runIsWorking(x.state.data?.run) ? 2000 : false),
  })
  const request = useMemo(() => (from === "selection" ? readCorroborateRequest(caseId) : null), [caseId, from])
  const members: RelationMember[] = q ? asked.data?.group.members ?? [] : request ? request.members : selectionMembers(parts)
  const label = q ? `${asked.data?.group.member_count ?? 0} records asked about` : request ? `${request.label} · from ${request.screen}` : parts.length ? parts.map((p) => p.label).join(" · ") : ""
  return { members, label, asked, request, parts, skipped: request?.skipped ?? parts.flatMap((p) => p.skipped) }
}

function AskTab({ caseId }: { caseId: string }) {
  const [params, setParams] = useSearchParams()
  const q = params.get("q")
  const src = useSource(caseId, q, params.get("from"))
  const run = src.asked.data?.run
  const corro = run?.result?.corroboration
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ask = async (members: RelationMember[], d: Draft) => {
    setBusy(true)
    setError(null)
    try {
      const made = await corroborateAPI.run(caseId, { members: d.members ?? members, surface: "corroborate", question: { kind: d.kind, text: d.text, chips: d.chips } })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      const next = new URLSearchParams(params)
      next.set("q", made.group.id)
      next.set("tab", "ask")
      next.delete("from")
      setParams(next)
    } catch (e) {
      setError(e instanceof Error ? `Corroborate could not start: ${e.message}. Nothing was saved.` : "Corroborate could not start. Nothing was saved.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-5">
      <QuestionSentence key={q ?? params.get("from") ?? "selection"} caseId={caseId} members={src.members} sourceLabel={src.label}
        skipped={src.skipped} scope={q ? undefined : src.request?.scope} initialKind={q ? undefined : src.request?.kind} drafted={!q && !!src.request?.drafted} asked={corro} busy={busy} onAsk={(d) => void ask(src.members, d)} parts={q || src.request ? undefined : src.parts} />
      {error && <p role="alert" className="text-sm text-status-error">{error}</p>}
      {q && src.asked.isLoading && <p role="status" className="text-sm text-muted-foreground">Opening the answer…</p>}
      {q && src.asked.isError && <p role="alert" className="text-sm text-status-error">This answer could not be opened. It may belong to another case; go back to Your earlier questions.</p>}
      {run && runIsWorking(run) && (
        <section role="status" aria-live="polite" className="rounded-lg border bg-card p-4">
          <p className="font-medium">{run.step || "Corroborate is weighing the records…"}</p>
          <p className="text-sm text-muted-foreground">You can leave this page; the answer is kept under Your earlier questions.</p>
        </section>
      )}
      {run?.status === "failed" && <p role="alert" className="rounded-lg border border-status-error p-4 text-sm">Corroborate stopped: {run.error}. Press Ask to try again.</p>}
      {corro?.claim && <ClaimResult c={corro} />}
      {corro && !corro.claim && run && q && (
        <AnswerView c={corro} caseId={caseId} runId={run.id} selectionId={q} members={src.members}
          onAsk={(question) => void ask(src.members, { kind: question.kind, text: "", chips: question.chips })} />
      )}
    </div>
  )
}
