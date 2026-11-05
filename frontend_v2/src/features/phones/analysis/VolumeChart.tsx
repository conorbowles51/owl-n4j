import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { relationshipVolume, type RelationshipVolume } from "./analysis-api"
import { changeWords, countWords, weekRecordsPath } from "./volume-words"

const HEIGHT = 96
const AXIS = 16
const MIN_STEP = 4 // px per week: the hit target of a week; a longer span scrolls sideways rather than dropping weeks

/** One series, so the title names it and there is no legend; bars from a zero baseline, changepoints as labelled rules. */
function Bars({ caseId, v }: { caseId: string; v: RelationshipVolume }) {
  const navigate = useNavigate()
  const [tip, setTip] = useState<{ at: number; week: string; count: number } | null>(null)
  const peak = Math.max(1, ...v.weeks.map((w) => w.count))
  const step = Math.max(MIN_STEP, Math.min(24, 640 / v.weeks.length))
  const width = step * v.weeks.length
  const barWidth = Math.max(2, step - 2)
  const scale = (n: number) => (n / peak) * (HEIGHT - 8)
  const index = useMemo(() => new Map(v.weeks.map((w, i) => [w.week_start, i])), [v.weeks])
  const years = v.weeks.flatMap((w, i) => (i === 0 || w.week_start.slice(0, 4) !== v.weeks[i - 1].week_start.slice(0, 4) ? [{ i, year: w.week_start.slice(0, 4) }] : []))
  return (
    <div className="relative overflow-x-auto" onMouseLeave={() => setTip(null)}>
      <svg role="img" width={width} height={HEIGHT + AXIS} aria-label={`Contact each week on ${v.phone_label ?? "this phone"}, highest ${peak.toLocaleString("en-US")} in a week. The table below lists every week.`}>
        <line x1={0} x2={width} y1={HEIGHT} y2={HEIGHT} className="stroke-border" />
        {v.weeks.map((w, i) => (
          <g key={w.week_start} data-week={w.week_start} className="cursor-pointer" onClick={() => navigate(weekRecordsPath(caseId, v, w.week_start))} onMouseEnter={() => setTip({ at: i * step, week: w.week_start, count: w.count })}>
            <rect x={i * step} y={0} width={step} height={HEIGHT + AXIS} fill="transparent" />
            {w.count > 0 && <rect x={i * step + (step - barWidth) / 2} y={HEIGHT - Math.max(2, scale(w.count))} width={barWidth} height={Math.max(2, scale(w.count))} rx={Math.min(2, barWidth / 2)} className="fill-foreground/60" />}
          </g>
        ))}
        {v.changepoints.map((c) => {
          const i = index.get(c.week_start)
          return i === undefined ? null : <line key={c.result_id} x1={i * step} x2={i * step} y1={0} y2={HEIGHT} strokeWidth={2} strokeDasharray="4 3" className="pointer-events-none stroke-foreground" data-changepoint={c.week_start} />
        })}
        {years.map((y) => <text key={y.year} x={y.i * step} y={HEIGHT + 12} className="fill-muted-foreground text-[10px]">{y.year}</text>)}
      </svg>
      {tip && (
        <p role="status" className="pointer-events-none absolute top-0 z-10 rounded border bg-popover px-1.5 py-0.5 text-xs shadow-sm" style={{ left: Math.max(0, tip.at - 60) }}>
          Week of {tip.week}: {countWords(tip.count)}
        </p>
      )}
    </div>
  )
}

/**
 * The volume chart of relationships over time (05 14.4): contact each week with one person on one phone and the
 * weeks where it changed. Every count opens to its records: a bar or a table row opens that week in Conversations,
 * the total opens all of them.
 */
export function VolumeChart({ caseId, resultId }: { caseId: string; resultId: string }) {
  const q = useQuery({ queryKey: ["phone-relationship-volume", caseId, resultId], queryFn: () => relationshipVolume(caseId, resultId) })
  if (q.isError) return <p role="alert" className="text-xs">The weekly chart could not be loaded.</p>
  if (!q.data) return <p role="status" className="text-xs text-muted-foreground">Loading the weekly chart.</p>
  const v = q.data
  if (!v.weeks.length) return <p className="text-xs text-muted-foreground">No call, message or email with this person has a time, so there is no chart.</p>
  const held = v.weeks.filter((w) => w.count > 0)
  return (
    <figure className="space-y-1 text-xs" aria-label="Contact each week" data-testid="volume-chart">
      <figcaption className="font-medium">
        Contact each week on {v.phone_label ?? "this phone"}: <Link className="underline" to={weekRecordsPath(caseId, v)}>{countWords(v.total)}</Link>, in {v.weeks.length.toLocaleString("en-US")} weeks (UTC)
      </figcaption>
      <Bars caseId={caseId} v={v} />
      {v.changepoints.length > 0 ? (
        <ul className="space-y-0.5" aria-label="Weeks where contact changed">
          {v.changepoints.map((c) => <li key={c.result_id}>Dashed line: <Link className="underline" to={weekRecordsPath(caseId, v, c.week_start)}>{changeWords(c)}</Link>.</li>)}
        </ul>
      ) : <p className="text-muted-foreground">No week where the amount of contact rose or fell.</p>}
      {v.untimed > 0 && <p>{countWords(v.untimed)} with no time {v.untimed === 1 ? "is" : "are"} not on the chart.</p>}
      {v.changed_words && <p role="note">{v.changed_words}</p>}
      <details>
        <summary className="cursor-pointer">The {held.length.toLocaleString("en-US")} {held.length === 1 ? "week" : "weeks"} with contact, as a table</summary>
        <table className="mt-1">
          <thead><tr><th className="pr-4 text-left font-medium">Week of</th><th className="text-right font-medium">Count</th></tr></thead>
          <tbody>
            {held.map((w) => <tr key={w.week_start}><td className="pr-4">{w.week_start}</td><td className="text-right"><Link className="underline" to={weekRecordsPath(caseId, v, w.week_start)}>{w.count.toLocaleString("en-US")}</Link></td></tr>)}
          </tbody>
        </table>
      </details>
    </figure>
  )
}
