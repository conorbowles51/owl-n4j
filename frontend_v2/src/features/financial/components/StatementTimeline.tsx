import { useState } from "react"
import { StatementSourceButton } from "./StatementSourceButton"
export type CoveragePeriod = {
  period_id: string
  source_document_id: string
  currency: string
  start: string | null
  end: string | null
  included: boolean
  exclusion_reason: string | null
}
type Gap = { start: string; end: string; days: number }
// UTC calendar positions; bad or reversed dates stay outside the diagram.
function day(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const time = Date.parse(value + "T00:00:00Z")
  return Number.isFinite(time) &&
    new Date(time).toISOString().slice(0, 10) === value
    ? time / 86400000
    : null
}
export function StatementTimeline({
  caseId,
  currency,
  periods,
  gaps,
  overlaps,
}: {
  caseId: string
  currency: string
  periods: CoveragePeriod[]
  gaps: Gap[]
  overlaps: { period_id: string }[]
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const rows = periods
    .filter((p) => p.currency === currency)
    .flatMap((p) => {
      const start = day(p.start),
        end = day(p.end)
      return start !== null && end !== null && end >= start
        ? [{ ...p, from: start, to: end }]
        : []
    })
    .sort(
      (a, b) =>
        a.from - b.from || a.to - b.to || a.period_id.localeCompare(b.period_id)
    )
  const unknown =
    periods.filter((p) => p.currency === currency).length - rows.length
  if (!rows.length)
    return (
      <p>
        {currency}: no complete date ranges to draw. Statement coverage is
        unknown.
      </p>
    )
  const first = Math.min(...rows.map((p) => p.from)),
    last = Math.max(...rows.map((p) => p.to)),
    span = last - first + 1
  const position = (from: number, to: number) => ({
    left: `${(100 * (from - first)) / span}%`,
    width: `${(100 * (to - from + 1)) / span}%`,
  })
  const active = rows.find((p) => p.period_id === selected)
  return (
    <section
      aria-label={`${currency} statement timeline`}
      className="space-y-3 rounded border p-3"
    >
      <h5 className="font-semibold">{currency} statement timeline</h5>
      <p className="text-sm">
        Select a bar to open its statement. Solid bars count towards covered
        dates. Dashed bars are left out because their dates or source need
        review.
      </p>
      <div className="flex justify-between gap-2 text-xs">
        <span>{new Date(first * 86400000).toISOString().slice(0, 10)}</span>
        <span>{new Date(last * 86400000).toISOString().slice(0, 10)}</span>
      </div>
      {gaps.length > 0 && (
        <div
          aria-label="Gaps between eligible statements"
          className="relative h-6 rounded bg-muted/30"
        >
          {gaps.map((gap) => {
            const start = day(gap.start),
              end = day(gap.end)
            return start !== null &&
              end !== null &&
              start >= first &&
              end <= last &&
              end >= start ? (
              <span
                key={gap.start}
                title={`Gap: ${gap.start} to ${gap.end} (${gap.days} days)`}
                aria-label={`Gap: ${gap.start} to ${gap.end}, ${gap.days} days`}
                className="absolute h-full border border-amber-500 bg-amber-500/25"
                style={position(start, end)}
              />
            ) : null
          })}
        </div>
      )}
      <div
        className="max-h-80 space-y-2 overflow-auto"
        aria-label="Statement date ranges"
      >
        {rows.map((period, index) => (
          <div key={period.period_id} className="space-y-1">
            <div className="flex justify-between gap-2 text-xs">
              <span>
                Statement {index + 1}: {period.start} to {period.end}
              </span>
              <span>
                {period.included ? "Dates included" : "Dates left out"}
                {overlaps.some((p) => p.period_id === period.period_id)
                  ? " · overlap"
                  : ""}
              </span>
            </div>
            <div className="relative h-7 rounded bg-muted/30">
              <button
                type="button"
                aria-label={`Inspect statement ${index + 1}: ${period.start} to ${period.end}`}
                aria-pressed={selected === period.period_id}
                onClick={() => setSelected(period.period_id)}
                style={position(period.from, period.to)}
                className={`absolute h-full min-w-1 rounded border-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring ${period.included ? "border-sky-500 bg-sky-500/40" : "border-dashed border-amber-500 bg-amber-500/15"}`}
              />
            </div>
          </div>
        ))}
      </div>
      {unknown > 0 && (
        <p>
          {unknown} periods have missing or invalid dates and cannot be placed
          on this timeline.
        </p>
      )}
      {active && (
        <section
          className="space-y-2 rounded border p-3"
          aria-label="Selected statement period"
        >
          <p>
            {active.start} to {active.end} ·{" "}
            {active.included
              ? "Dates included"
              : `Excluded: ${active.exclusion_reason?.replaceAll("_", " ") ?? "unknown reason"}`}
          </p>
          <StatementSourceButton
            key={active.period_id}
            caseId={caseId}
            periodId={active.period_id}
            sourceDocumentId={active.source_document_id}
          />
        </section>
      )}
    </section>
  )
}
