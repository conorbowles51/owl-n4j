import { useState } from "react"
import { StoryLanes } from "./StoryLanes"
import { Button } from "@/components/ui/button"
import type { CellState, Check, Corroboration, GridRow } from "./result-types"

const CELL_WORDS: Record<CellState, string> = { present: "Present", absent: "Checked, absent", no_data: "No data" }
const CELL_MARK: Record<CellState, string> = { present: "●", absent: "○", no_data: "?" }
const LEVEL_CLASS: Record<string, string> = {
  strong: "border-green-700", probable: "border-green-500", possible: "border-amber-500",
  coincidence: "border-slate-400", cant_tell: "border-slate-400", no_link_found: "border-slate-400",
}
const CHECK_WORDS: Record<string, string> = {
  routine: "Routine contact", household: "Shared household", workplace: "Shared workplace", stock_phrase: "Stock phrase",
  busy_place: "Busy place", clock_zone: "Clock or time zone", recycled_number: "Recycled number", same_name: "Another person of the same name",
  shared_device: "Shared device", duplicate_copy: "Duplicate copies", received_media: "Received media",
}
const OUTCOME_WORDS: Record<Check["outcome"], string> = {
  checked: "Checked, nothing found", ruled_out: "Ruled out", weighed_low: "Weighed low", no_data: "No data to check",
}

/** Every number opens the records behind it. */
function Records({ refs, label }: { refs: string[]; label: string }) {
  const [open, setOpen] = useState(false)
  if (!refs.length) return <span>{label}</span>
  return (
    <span>
      <button type="button" className="underline" aria-expanded={open} onClick={() => setOpen(!open)}>{label}</button>
      {open && <ul className="text-xs text-muted-foreground">{refs.map((r) => <li key={r}>{r}</li>)}</ul>}
    </span>
  )
}

function Grid({ c, onOpen }: { c: Corroboration; onOpen?: (id: string) => void }) {
  const instances = [...c.comparison.incident.map((i) => ({ ...i, side: "Incident" })), ...c.comparison.ordinary.map((i) => ({ ...i, side: "Ordinary" }))]
  if (!c.grid.length) return <p className="text-sm">No signal was present on any instance.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="corroborate-grid">
        <caption className="text-left text-muted-foreground">{c.comparison.words}</caption>
        <thead>
          <tr>
            <th className="text-left">Signal</th>
            {instances.map((i) => <th key={i.id} scope="col" className="px-1 text-left font-normal" title={`${i.side}: ${i.label}`}>
              {onOpen ? <button type="button" className="underline" aria-label={`Open the story of ${i.side.toLowerCase()} ${i.label}`} onClick={() => onOpen(i.id)}>{i.side[0]} {i.label}</button> : <>{i.side[0]} {i.label}</>}
            </th>)}
            <th className="px-1 text-left">Incident</th>
            <th className="px-1 text-left">Ordinary</th>
          </tr>
        </thead>
        <tbody>
          {c.grid.map((r: GridRow) => (
            <tr key={r.signal} className="border-t align-top">
              <th scope="row" className="text-left font-normal">
                {r.label}
                {r.weight !== "full" && <span className="block text-xs text-muted-foreground">Weighed low: {r.why_low}</span>}
                {r.context && <span className="block text-xs text-muted-foreground">Shown, not weighed: {r.why_context}</span>}
                {r.picked_by && <span className="block text-xs text-muted-foreground">Chose the other instances; not evidence</span>}
              </th>
              {instances.map((i) => {
                const state = r.cells[i.id] ?? "no_data"
                return <td key={i.id} className="px-1" title={CELL_WORDS[state]} aria-label={CELL_WORDS[state]}><Records refs={r.records[i.id] ?? []} label={CELL_MARK[state]} /></td>
              })}
              <td className="px-1">{r.incident.present} of {r.incident.of}</td>
              <td className="px-1">{r.ordinary.present} of {r.ordinary.of}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted-foreground">● present · ○ checked and absent · ? no data (counts neither way)</p>
    </div>
  )
}

export function ResultView({ c, onAsk, onFurther, caseId, runId }: { c: Corroboration; onAsk?: () => void; onFurther?: (q: Corroboration["look_further"][number]) => void; caseId?: string; runId?: string }) {
  const lowers = c.checks
  const [lane, setLane] = useState<string | null>(null)
  return (
    <div className="space-y-4" data-testid="corroborate-result">
      <section aria-label="Level" className={`rounded border-l-4 p-3 ${LEVEL_CLASS[c.level.key] ?? ""}`}>
        <p className="text-sm text-muted-foreground">{c.question.text}</p>
        <h2 className="text-lg font-semibold">{c.level.name}</h2>
        <p>{c.level.sentence}</p>
        <p className="text-xs text-muted-foreground">Set by a stated rule from the signals below, not by a model.</p>
      </section>
      <section aria-label="Comparison grid"><h2 className="font-semibold">What was present, and on which instances</h2><Grid c={c} onOpen={caseId && runId ? setLane : undefined} />
        {lane && caseId && runId && <StoryLanes caseId={caseId} runId={runId} instance={lane} onClose={() => setLane(null)} />}
      </section>
      <section aria-label="What raises and lowers the level">
        <h2 className="font-semibold">What raises it, and what lowers it</h2>
        <ul className="list-disc pl-5 text-sm">{c.level.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <h3 className="mt-2 text-sm font-medium">Checks made ({lowers.length})</h3>
        <ul className="space-y-1 text-sm">
          {lowers.map((k, i) => (
            <li key={i}><strong>{CHECK_WORDS[k.check] ?? k.check}</strong>: {OUTCOME_WORDS[k.outcome]}. {k.words}{k.records?.length ? <> <Records refs={k.records} label={`${k.records.length} records`} /></> : null}</li>
          ))}
        </ul>
      </section>
      <section aria-label="Not in this pattern">
        <h2 className="font-semibold">Not in this pattern</h2>
        {c.not_in_pattern.length === 0 && <p className="text-sm">No one else was searched.</p>}
        <ul className="space-y-1 text-sm">
          {c.not_in_pattern.map((n, i) => (
            <li key={i} className="rounded border p-2"><strong>{n.who}</strong> {n.says}
              {n.searched.map((s, j) => <p key={j} className="text-muted-foreground">Searched: {s}</p>)}
              {(n.out_of_reach ?? []).map((s, j) => <p key={`o${j}`} className="text-muted-foreground">Out of reach: {s}</p>)}
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Gaps">
        <h2 className="font-semibold">Records missing</h2>
        {c.gaps.length === 0 ? <p className="text-sm">No gap was found in the records for these instances.</p>
          : <ul className="list-disc pl-5 text-sm">{c.gaps.map((g, i) => <li key={i}>{g.words}</li>)}</ul>}
      </section>
      {c.look_further.length > 0 && (
        <section aria-label="Look further">
          <h2 className="font-semibold">Look further</h2>
          <ul className="flex flex-wrap gap-2">
            {c.look_further.map((l, i) => (
              <li key={i}><Button size="sm" variant="outline" disabled={!onFurther} onClick={() => onFurther?.(l)}>{l.text} ({l.count.toLocaleString("en-US")})</Button></li>
            ))}
          </ul>
        </section>
      )}
      {onAsk && <Button size="sm" onClick={onAsk}>Ask the assistant to explain</Button>}
    </div>
  )
}
