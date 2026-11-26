import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { PhoneChip } from "@/features/phones/ui/PhoneChip"
import { useCasePhones } from "@/features/phones/ui/use-case-phones"
import type { RelationMember } from "@/features/relations/api"
import { leadsAPI } from "@/features/leads/api"
import { TheoryPicker } from "@/features/leads/LeadCard"
import { corroborateAPI } from "../api"
import { ResultView } from "../ResultView"
import { StoryLanes } from "../StoryLanes"
import type { CellState, Corroboration, DayTile } from "../result-types"
import { changes, innocentExplanations, LEVEL_GLOSS, names, nextSteps, SCALE, tally, type Pill } from "./answer-model"

const PILL_CLASS: Record<Pill, string> = {
  "Ruled out": "bg-status-success-soft text-status-success",
  "Counts for less": "bg-status-warning-soft text-status-warning",
  "Not known": "bg-status-neutral-soft text-status-neutral",
  "Did not arise": "bg-muted text-muted-foreground",
}
const CELL_CLASS: Record<CellState, string> = {
  present: "bg-status-success",
  absent: "bg-muted-foreground/30",
  no_data: "border border-dashed border-muted-foreground bg-transparent",
}

/** The answer to one question (design screen 5): the level, the evidence day by day, the innocent explanations
 * tested, what would change it, next steps, and what to do with the result. Everything is the engine's, by rule. */
export function AnswerView({ c, caseId, runId, selectionId, members, onAsk }: {
  c: Corroboration
  caseId: string
  runId: string
  selectionId: string
  members: RelationMember[]
  onAsk: (q: { kind: string; chips: Record<string, unknown> }) => void
}) {
  const [lane, setLane] = useState<string | null>(null)
  const steps = nextSteps(c, caseId)
  return (
    <div className="space-y-5" data-testid="corroborate-answer">
      <Level c={c} />
      <DayByDay c={c} caseId={caseId} onOpen={setLane} />
      {lane && <StoryLanes caseId={caseId} runId={runId} instance={lane} onClose={() => setLane(null)} />}
      <Innocent c={c} caseId={caseId} runId={runId} />
      <WouldChange c={c} caseId={caseId} runId={runId} />
      <section aria-label="Next steps" className="space-y-2 rounded-lg border bg-card p-4">
        <h2 className="text-lg font-semibold">Next steps</h2>
        <p className="text-sm text-muted-foreground">Most useful first. Each one opens with this question's people and days already filled in.</p>
        {steps.length === 0 && <p className="text-sm">This answer leaves no gap, contact or untested explanation to follow up.</p>}
        <ol className="space-y-2">
          {steps.map((s, i) => (
            <li key={i} className="flex flex-col gap-2 rounded border p-3 sm:flex-row sm:items-start" data-step={i + 1}>
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold" aria-hidden>{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">{s.title}</p>
                <p className="text-sm text-muted-foreground">{s.why}</p>
              </div>
              {s.to
                ? <Button size="sm" variant={i === 0 ? "primary" : "outline"} asChild><Link to={s.to}>{s.action}</Link></Button>
                : <Button size="sm" variant={i === 0 ? "primary" : "outline"} onClick={() => s.ask && onAsk(s.ask)}>{s.action}</Button>}
            </li>
          ))}
        </ol>
      </section>
      <Keep caseId={caseId} runId={runId} members={members} />
      <details className="rounded-lg border p-4">
        <summary className="cursor-pointer text-sm font-semibold">Every link Loupe weighed, day by day ({c.grid.length})</summary>
        <div className="mt-3"><ResultView c={c} caseId={caseId} runId={runId} /></div>
      </details>
      <p className="text-xs text-muted-foreground">Question id {selectionId.slice(0, 8)} · the level is set by stated rules from the records, never by a model.</p>
    </div>
  )
}

function Level({ c }: { c: Corroboration }) {
  return (
    <section aria-label="The answer" className="space-y-2 rounded-lg border bg-card p-4 sm:p-5">
      <p className="text-sm text-muted-foreground">{c.question.text}</p>
      <p className="flex flex-wrap items-baseline gap-x-3">
        <span className="text-2xl font-semibold" data-level={c.level.key}>{c.level.name}</span>
        {LEVEL_GLOSS[c.level.key] && <span className="text-sm text-muted-foreground">{LEVEL_GLOSS[c.level.key]}</span>}
      </p>
      <p className="text-xs text-muted-foreground">
        Scale: {SCALE.map((s, i) => <span key={s.key}>{i > 0 && " · "}<span className={cn(s.key === c.level.key && "font-semibold text-foreground underline")}>{s.name}</span></span>)}
      </p>
      <p>{c.level.sentence}</p>
    </section>
  )
}

function DayByDay({ c, caseId, onOpen }: { c: Corroboration; caseId: string; onOpen: (id: string) => void }) {
  const d = c.days
  const phones = useCasePhones(caseId)
  if (!d) return null
  if (!d.relation) {
    return (
      <section aria-label="The evidence, day by day" className="rounded-lg border p-4 text-sm">
        <h2 className="text-lg font-semibold">The evidence, day by day</h2>
        <p>No link between {names(d.people)} was present on any day asked about, so there is no day to draw. What was searched is under “Every link Loupe weighed”.</p>
      </section>
    )
  }
  const rel = d.relation
  const t = tally(d.tiles)
  const relPeople = c.people.filter((p) => rel.people.includes(p.key))
  const chips = relPeople.flatMap((p) => (p.phones ?? []).map((ph) => ({ ph, owner: p.label, index: phones.find((x) => x.id === ph.id)?.index })))
  return (
    <section aria-label="The evidence, day by day" className="space-y-4 rounded-lg border bg-card p-4 sm:p-5">
      <h2 className="text-lg font-semibold">The evidence, day by day</h2>
      <p className="text-sm">{rel.definition} Open a day to see the places and times.</p>
      {chips.length > 0 && (
        <p className="flex flex-wrap gap-2" aria-label="The phones in this answer">
          {chips.map((x) => <PhoneChip key={x.ph.id} label={`${x.ph.label} · ${x.owner}`} index={x.index ?? 0} />)}
        </p>
      )}
      <div>
        <p className="mb-2 text-sm font-semibold">{cap(d.events_phrase)} · {d.events_source} · {rel.present} on {t.present} of {t.of}</p>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" aria-label="The days asked about">
          {d.tiles.map((tile) => <Tile key={tile.instance} tile={tile} onOpen={() => onOpen(tile.instance)} />)}
        </ul>
      </div>
      {d.ordinary && d.ordinary.of > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">For comparison: {d.relation ? `“${d.relation.word}” on ` : ""}{d.ordinary.of.toLocaleString("en-US")} {d.ordinary.noun}{d.ordinary.span ? ` · ${d.ordinary.span}` : ""}</p>
          <p className="text-sm">{d.ordinary.words}.</p>
          <ul className="flex flex-wrap gap-1" aria-label={`The ${d.ordinary.noun}`}>
            {d.ordinary.cells.map((x) => (
              <li key={x.instance} title={`${x.date}: ${x.state === "present" ? rel.present : x.state === "absent" ? rel.absent : rel.no_data}`}
                aria-label={`${x.date}: ${x.state === "present" ? rel.present : x.state === "absent" ? rel.absent : rel.no_data}`}
                className={cn("block h-[18px] w-3 rounded-sm", CELL_CLASS[x.state])} />
            ))}
          </ul>
          <p className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><span className={cn("inline-block h-3 w-3 rounded-sm", CELL_CLASS.present)} aria-hidden />{rel.present} that day</span>
            <span className="flex items-center gap-1"><span className={cn("inline-block h-3 w-3 rounded-sm", CELL_CLASS.absent)} aria-hidden />{rel.absent} all day</span>
            <span className="flex items-center gap-1"><span className={cn("inline-block h-3 w-3 rounded-sm", CELL_CLASS.no_data)} aria-hidden />{rel.no_data}: the records do not cover that day, so it counts neither way</span>
          </p>
        </div>
      )}
    </section>
  )
}

function cap(s: string): string { return s.charAt(0).toUpperCase() + s.slice(1) }

function Tile({ tile, onOpen }: { tile: DayTile; onOpen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOpen} data-outcome={tile.outcome} aria-label={`${tile.date}: ${tile.outcome_words}. ${tile.detail}. Open the day.`}
        className={cn("flex h-full w-full flex-col gap-1 rounded-lg border p-2.5 text-left text-sm hover:ring-2 hover:ring-ring",
          tile.outcome === "present" && "border-status-success bg-status-success-soft",
          tile.outcome === "no_data" && "border-dashed")}>
        <span className="font-semibold">{tile.date}</span>
        {tile.events.length > 0 && <span className="text-xs text-muted-foreground">{tile.events.join(" · ")}</span>}
        <span className={cn("mt-1 font-bold", tile.outcome === "present" ? "text-status-success" : "text-foreground")}>{tile.outcome_words}</span>
        <span className="text-xs text-muted-foreground">{tile.detail}</span>
      </button>
    </li>
  )
}

function Innocent({ c, caseId, runId }: { c: Corroboration; caseId: string; runId: string }) {
  const list = innocentExplanations(c)
  return (
    <section aria-label="Innocent explanations Loupe tested" className="space-y-2 rounded-lg border bg-card p-4 sm:p-5">
      <h2 className="text-lg font-semibold">Innocent explanations Loupe tested</h2>
      {list.length === 0 && <p className="text-sm text-muted-foreground">None yet: this question could not be weighed, so no innocent explanation was tested. “What would change the answer” says what is missing.</p>}
      <ul className="space-y-2">
        {list.map((x) => (
          <li key={x.check} className="flex flex-col gap-2 border-t pt-2 first:border-t-0 first:pt-0 sm:flex-row">
            <span className={cn("w-32 shrink-0 self-start rounded-full px-2 py-1 text-center text-xs font-semibold", PILL_CLASS[x.pill])}>{x.pill}</span>
            <div className="min-w-0 text-sm">
              <p className="font-medium">{x.question}</p>
              <p className="text-muted-foreground">{x.words}{x.records.length ? ` (${x.records.length} record${x.records.length === 1 ? "" : "s"})` : ""}</p>
              {x.fact && x.pill !== "Ruled out" && <FactForm c={c} caseId={caseId} runId={runId} fact={x.fact} />}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function WouldChange({ c, caseId, runId }: { c: Corroboration; caseId: string; runId: string }) {
  const list = changes(c)
  return (
    <section aria-label="What would change the answer" className="space-y-2 rounded-lg border bg-card p-4 sm:p-5">
      <h2 className="text-lg font-semibold">What would change the answer</h2>
      {list.length === 0 && <p className="text-sm text-muted-foreground">The records cover every day asked about, and no innocent explanation is left that a case fact would settle.</p>}
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {list.map((x, i) => <li key={i}>{x.text}{x.fact && <FactForm c={c} caseId={caseId} runId={runId} fact={x.fact} />}</li>)}
      </ul>
    </section>
  )
}

/** Recording a case fact ("they live together") under the person's own name; the next answer weighs it. */
function FactForm({ c, caseId, runId, fact }: { c: Corroboration; caseId: string; runId: string; fact: { kind: string; words: string } }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState(`${names(c.people.map((p) => p.label))} ${fact.words.replace(/^They /, "").toLowerCase()}`)
  const save = useMutation({ mutationFn: () => corroborateAPI.addFact(caseId, { kind: fact.kind, text, people: c.people.map((p) => p.key), run_id: runId }) })
  if (save.isSuccess) return <p className="text-xs" role="status">Recorded under your name. Press Ask again to weigh it.</p>
  if (!open) return <button type="button" className="text-xs text-status-info underline" onClick={() => setOpen(true)}>Record it</button>
  return (
    <form className="mt-1 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <input className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm" aria-label="The case fact" value={text} onChange={(e) => setText(e.target.value)} />
      <Button size="sm" type="submit" disabled={save.isPending || !text.trim()}>Save</Button>
      <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      {save.isError && <p className="w-full text-xs text-status-error" role="alert">The fact was not saved: {save.error instanceof Error ? save.error.message : "it failed"}.</p>}
    </form>
  )
}

/** Keep this result: Add to theory, Keep watching as a lead, Not relevant. The answer is already saved as a lead. */
function Keep({ caseId, runId, members }: { caseId: string; runId: string; members: RelationMember[] }) {
  const qc = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const lead = useQuery({
    queryKey: ["leads", caseId, "run", runId],
    queryFn: () => leadsAPI.here(caseId, { records: members.slice(0, 2000).map((m) => `${m.type}:${m.id}`) }),
    select: (d) => d.leads.find((l) => l.run_id === runId) ?? null,
  })
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leads", caseId] }),
    onError: (e) => setMsg(e instanceof Error ? `That did not work: ${e.message}. Nothing was changed.` : "That did not work. Nothing was changed."),
  })
  const l = lead.data
  return (
    <section aria-label="Keep this result" className="flex flex-wrap items-center gap-2 rounded-lg border p-4 text-sm">
      <span className="font-medium">Keep this result:</span>
      <Button size="sm" variant="outline" disabled={!l || !!l.finding_id} onClick={() => setPicking((x) => !x)}>{l?.finding_id ? "In the theory" : "Add to theory"}</Button>
      <Button size="sm" variant="outline" disabled={!!l?.watching || act.isPending} onClick={() => act.mutate(() => corroborateAPI.watch(caseId, runId).then(() => setMsg("Loupe asks this again when new material arrives, and the lead shows any change.")))}>{l?.watching ? "Watching as a lead" : "Keep watching as a lead"}</Button>
      <Button size="sm" variant="ghost" disabled={!l || l.state === "not_relevant"} onClick={() => l && act.mutate(() => leadsAPI.state(caseId, l.id, "not_relevant").then(() => setMsg("Marked not relevant. It stays under Your earlier questions.")))}>{l?.state === "not_relevant" ? "Marked not relevant" : "Not relevant"}</Button>
      {lead.isSuccess && !l && <span className="text-xs text-muted-foreground">The answer is being saved as a lead; Add to theory opens once it is.</span>}
      {picking && l && <div className="w-full"><TheoryPicker caseId={caseId} onPick={(id) => { setPicking(false); act.mutate(() => leadsAPI.confirm(caseId, l.id, id)) }} /></div>}
      {msg && <p className="w-full text-xs" role="status">{msg}</p>}
      {l && <p className="w-full text-xs text-muted-foreground">{l.read.words}</p>}
    </section>
  )
}
