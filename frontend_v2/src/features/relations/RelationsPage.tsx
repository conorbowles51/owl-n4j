import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { useCollectTargets } from "@/features/phones/collect-targets"
import { downloadRelationReport, relationAPI, runIsWorking, type Candidate, type Hypothesis, type NoLink, type RelationResult, type Strength } from "./api"

const STRENGTH_WORDS: Record<Strength, string> = { strong: "Strong", moderate: "Moderate", weak: "Weak", faint: "Faint" }
const KIND_WORDS: Record<string, string> = {
  time_proximity: "Close in time", sequence: "Order of events", shared_identifier: "Same number, email or name", same_amount: "Same amount",
  place_overlap: "Same place, same time", relay_chain: "Relay", shared_silence: "Both quiet at once", together_apart: "Alternating use",
}
const RELATION_WORKFLOW = "link-group"

function Names({ refs, labels }: { refs: string[]; labels: Map<string, string> }) {
  return <span className="text-muted-foreground">{refs.map((r) => labels.get(r) ?? r.slice(0, 8)).join(" · ")}</span>
}

function CandidateRow({ c, labels }: { c: Candidate; labels: Map<string, string> }) {
  return (
    <li className="rounded border p-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <strong>{STRENGTH_WORDS[c.strength]}</strong>
        <span>{KIND_WORDS[c.kind] ?? c.kind}</span>
        <Names refs={c.members} labels={labels} />
      </div>
      <p className="text-sm">{c.reasons.join(" ")}</p>
      {c.chance.words && <p className="text-sm text-muted-foreground">Chance: {c.chance.words}</p>}
    </li>
  )
}

/** The rows after the first page, read a page at a time ("Show more"); the counts above them are always whole. */
function MoreRows<T>({ caseId, runId, section, total, shown, render }: {
  caseId: string; runId: string; section: "candidates" | "no_links"; total: number; shown: number; render: (row: T, index: number) => React.ReactNode
}) {
  const [rows, setRows] = useState<T[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const loaded = shown + rows.length
  const more = async () => {
    setBusy(true)
    setError(null)
    try {
      const page = await relationAPI.rows<T>(caseId, runId, section, loaded)
      setRows((r) => [...r, ...page.rows])
    } catch (e) {
      setError(e instanceof Error ? e.message : "The next rows could not be read.")
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      {rows.map((r, i) => render(r, shown + i))}
      {total > loaded && (
        <li className="list-none">
          <p className="text-sm text-muted-foreground">Showing {loaded.toLocaleString("en-US")} of {total.toLocaleString("en-US")}.</p>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void more()}>{busy ? "Reading…" : "Show more"}</Button>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </li>
      )}
    </>
  )
}

function NoLinkRow({ n, labels }: { n: NoLink; labels: Map<string, string> }) {
  return (
    <li className="rounded border p-2 text-sm">
      <Names refs={n.members} labels={labels} /><p>{n.says}</p>
      {n.searched.map((s, j) => <p key={`s${j}`} className="text-muted-foreground">Searched: {s}</p>)}
      {n.out_of_reach.map((s, j) => <p key={`o${j}`} className="text-muted-foreground">Out of reach: {s}</p>)}
    </li>
  )
}

function Summary({ r }: { r: RelationResult }) {
  const s = r.counts.by_strength
  return (
    <p className="text-sm" data-testid="relation-summary">
      {r.counts.items.toLocaleString("en-US")} items, {r.counts.pairs.toLocaleString("en-US")} pairs. {r.counts.candidates.toLocaleString("en-US")} candidate links
      ({s.strong} strong, {s.moderate} moderate, {s.weak} weak, {s.faint} faint). {r.counts.no_links.toLocaleString("en-US")} pairs with no link found.
      Took {r.seconds} seconds. {r.says}
    </p>
  )
}

function HypothesisCard({ h, model, caseId, runId }: { h: Hypothesis; model: string; caseId: string; runId: string }) {
  const targets = useCollectTargets(caseId)
  const theories = targets.targets.filter((t) => t.kind === "theory")
  const [entry, setEntry] = useState("")
  const [msg, setMsg] = useState<string | null>(null)
  const qc = useQueryClient()
  const accept = async (rel: "supports" | "contradicts") => {
    try {
      await relationAPI.accept(caseId, runId, h.id, entry, rel)
      setMsg(`Added to the theory as ${rel}, marked as written by ${model}.`)
      void qc.invalidateQueries({ queryKey: ["relation-query", caseId] })
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "It could not be added.")
    }
  }
  return (
    <li className="rounded border p-2 space-y-1">
      <div><strong className="capitalize">{h.kind.replace(/_/g, " ")}</strong> {h.statement}</div>
      {h.predicts && <p className="text-sm text-muted-foreground">Predicts: {h.predicts}</p>}
      {h.for.map((x, i) => <p key={`f${i}`} className="text-sm">For: {x.cite} {x.text}</p>)}
      {h.against.map((x, i) => <p key={`a${i}`} className="text-sm">Against: {x.cite} {x.text}</p>)}
      <p className="text-sm">Would tell it apart: {h.distinguishing_record}</p>
      <p className="text-sm">Searched: {h.search}</p>
      {h.accepted ? (
        <p className="text-sm">Accepted by {h.accepted.by} as {h.accepted.relationship}.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Theory to add to" className="rounded border bg-background px-2 py-1 text-sm" value={entry} onChange={(e) => setEntry(e.target.value)}>
            <option value="">Choose a theory…</option>
            {theories.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <Button size="sm" variant="outline" disabled={!entry} onClick={() => void accept("supports")}>Accept as supports</Button>
          <Button size="sm" variant="outline" disabled={!entry} onClick={() => void accept("contradicts")}>Accept as contradicts</Button>
        </div>
      )}
      {msg && <p role="status" className="text-sm">{msg}</p>}
    </li>
  )
}

export function RelationsPage() {
  const { id: caseId = "", selectionId = "" } = useParams()
  const navigate = useNavigate()
  const [reportError, setReportError] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ["relation-query", caseId, selectionId],
    queryFn: () => relationAPI.get(caseId, selectionId),
    enabled: !!caseId && !!selectionId,
    refetchInterval: (q) => (runIsWorking(q.state.data?.run) && q.state.data !== undefined ? 1500 : false),
  })
  const qc = useQueryClient()
  const run = query.data?.run
  const result = run?.result ?? null
  const labels = new Map((result?.items ?? []).map((i) => [i.ref, i.label]))
  const askAssistant = () => {
    const question = `The group ${selectionId} was marked as possibly related. State what the link analysis found, name the competing explanations, and say where no link was found and what was searched.`
    navigate(`/cases/${caseId}/agent?workflow=${RELATION_WORKFLOW}&question=${encodeURIComponent(question)}`)
  }
  if (query.isError) return <main className="p-4"><p role="alert">This look could not be opened: {query.error instanceof Error ? query.error.message : "it failed"}.</p></main>
  if (!query.data) return <main className="p-4"><p role="status">Opening this look…</p></main>
  const members = query.data.group.member_count
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-4">
      <header>
        <h1 className="text-xl font-semibold">How these items could be linked</h1>
        <p className="text-sm text-muted-foreground">
          {query.data.group.member_count.toLocaleString("en-US")} items marked as possibly related
          {query.data.group.left_out > 0 && `, ${query.data.group.left_out} left out because they are not in this case`}. The records show what occurs together, never why.
        </p>
      </header>
      {runIsWorking(run) && (
        <section role="status" aria-live="polite" className="rounded border p-3">
          <p className="font-medium">{run?.step || "Starting"}</p>
          <p className="text-sm text-muted-foreground">Working on {members.toLocaleString("en-US")} items. You can leave this page; the analysis carries on.</p>
        </section>
      )}
      {run?.status === "failed" && (
        <section role="alert" className="rounded border border-destructive p-3">
          <p className="font-medium">The analysis stopped.</p>
          <p className="text-sm">{run.error}</p>
          <Button size="sm" variant="outline" onClick={() => void relationAPI.rerun(caseId, selectionId).then(() => qc.invalidateQueries({ queryKey: ["relation-query", caseId, selectionId] }))}>Run again</Button>
        </section>
      )}
      {result && run && (
        <>
          <Summary r={result} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={askAssistant}>Ask how they could be linked</Button>
            <Button size="sm" variant="outline" onClick={() => void downloadRelationReport(caseId, run.id).then(() => setReportError(null)).catch((e) => setReportError(e instanceof Error ? e.message : "The report failed"))}>Export report (PDF)</Button>
            <Button size="sm" variant="outline" onClick={() => void relationAPI.rerun(caseId, selectionId).then(() => qc.invalidateQueries({ queryKey: ["relation-query", caseId, selectionId] }))}>Run again</Button>
            <Link className="text-sm underline self-center" to={`/cases/${caseId}/workspace`}>Workspace</Link>
          </div>
          {reportError && <p role="alert" className="text-sm text-destructive">{reportError}</p>}
          <section aria-label="Items">
            <h2 className="font-semibold">The items</h2>
            <ul className="text-sm">{result.items.map((i) => <li key={i.ref}>{i.label} <span className="text-muted-foreground">({i.type.replace(/_/g, " ")}{i.at ? `, ${i.at.slice(0, i.precision === "day" ? 10 : 16).replace("T", " ")}` : ", no date on record"})</span></li>)}</ul>
          </section>
          <section aria-label="Candidate links">
            <h2 className="font-semibold">Candidate links ({result.counts.candidates.toLocaleString("en-US")})</h2>
            <p className="text-sm text-muted-foreground">Strongest first. Weak links are listed as weak.</p>
            <ul className="space-y-2">
              {result.candidates.map((c, i) => <CandidateRow key={i} c={c} labels={labels} />)}
              <MoreRows<Candidate> caseId={caseId} runId={run.id} section="candidates" total={result.paging?.candidates.total ?? result.candidates.length}
                shown={result.candidates.length} render={(c, i) => <CandidateRow key={`m${i}`} c={c} labels={labels} />} />
            </ul>
            {result.candidates.length === 0 && <p className="text-sm">No candidate link was found.</p>}
          </section>
          <section aria-label="No link found">
            <h2 className="font-semibold">Pairs with no link found ({result.counts.no_links.toLocaleString("en-US")})</h2>
            <p className="text-sm text-muted-foreground">Each says what was searched. It is not proof that no link exists.</p>
            <ul className="space-y-2">
              {result.no_links.map((n, i) => <NoLinkRow key={i} n={n} labels={labels} />)}
              <MoreRows<NoLink> caseId={caseId} runId={run.id} section="no_links" total={result.paging?.no_links.total ?? result.no_links.length}
                shown={result.no_links.length} render={(n, i) => <NoLinkRow key={`m${i}`} n={n} labels={labels} />} />
            </ul>
          </section>
          <section aria-label="Analyses run">
            <h2 className="font-semibold">Analyses run</h2>
            <ul className="text-sm">{result.analyses.map((a) => <li key={a.id}>{a.title}: {a.pairs.toLocaleString("en-US")} pairs, {a.found.toLocaleString("en-US")} links{a.note ? `. ${a.note}` : ""}</li>)}</ul>
            {result.out_of_reach.map((o, i) => <p key={i} className="text-sm text-muted-foreground">Out of reach: {o.analysis}. {o.reason}</p>)}
          </section>
          <section aria-label="How they could be linked">
            <h2 className="font-semibold">How they could be linked</h2>
            {run.hypotheses ? (
              <>
                <p className="text-sm text-muted-foreground">A model reading by {run.hypotheses.model}. {run.hypotheses.status}</p>
                <ul className="space-y-2">{run.hypotheses.items.map((h) => <HypothesisCard key={h.id} h={h} model={run.hypotheses!.model} caseId={caseId} runId={run.id} />)}</ul>
                {run.hypotheses.no_links && <p className="text-sm">{run.hypotheses.no_links}</p>}
              </>
            ) : <p className="text-sm text-muted-foreground">No explanations have been drafted. Use "Ask how they could be linked".</p>}
          </section>
        </>
      )}
    </main>
  )
}

export default RelationsPage
