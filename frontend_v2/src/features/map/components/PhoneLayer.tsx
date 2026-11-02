import { useState } from "react"
import { Link } from "react-router-dom"
import type { PhoneMapItem, PhoneMapPoints, PhoneMapSummary } from "@/features/phones/api"
import { recordPath } from "@/lib/record-links"

const n = (v: number) => v.toLocaleString("en-US")

/** The words above the phone layer (03 13.3): "Showing 1,204 of 1,260 positioned records. 56 cannot be placed (why)." */
export function phoneSummaryWords(summary: PhoneMapSummary, shown: number) {
  const unplaced = summary.not_positionable.reduce((a, m) => a + m.count, 0)
  return {
    showing: `Showing ${n(shown)} of ${n(summary.total)} positioned records.`,
    unplaced: unplaced ? `${n(unplaced)} cannot be placed` : null,
  }
}

/**
 * The Map phone layer's panel: the totals line, why some records cannot be placed, any clustering limit, and
 * every point in view as a keyboard-steppable list with its accuracy and the record behind it (03 section 13.3).
 */
export function PhoneLayerPanel({ caseId, summary, points }: { caseId: string; summary: PhoneMapSummary; points?: PhoneMapPoints }) {
  const [why, setWhy] = useState(false)
  const shown = points?.total ?? 0
  const words = phoneSummaryWords(summary, shown)
  const items = (points?.items ?? []).filter((i): i is Extract<PhoneMapItem, { type: "point" }> => i.type === "point")
  return (
    <section aria-label="Phone positions" className="absolute bottom-3 left-3 z-10 flex max-h-[45%] w-80 flex-col gap-1 overflow-hidden rounded-lg border border-border bg-card/95 p-3 text-xs shadow-md backdrop-blur">
      <h2 className="text-sm font-semibold">Phone positions</h2>
      <p role="status">
        {words.showing}
        {words.unplaced && (
          <>
            {" "}{words.unplaced} (
            <button type="button" className="underline" aria-expanded={why} onClick={() => setWhy((w) => !w)}>why</button>
            ).
          </>
        )}
      </p>
      {why && (
        <ul className="list-disc pl-4">
          {summary.not_positionable.map((m) => (
            <li key={m.model_type}>{m.reason} ({n(m.count)} across {n(m.phones)} {m.phones === 1 ? "phone" : "phones"}). They are counted here and never sent to a lookup service.</li>
          ))}
        </ul>
      )}
      {points?.limits.map((l) => (
        <p key={l.message} role="alert">{l.message}</p>
      ))}
      {items.length > 0 && (
        <ul aria-label="Positions in view" className="flex flex-col gap-1 overflow-auto">
          {items.map((p) => (
            <li key={p.point_uid} className="rounded border border-border/60 px-2 py-1">
              <div className="font-medium">{p.phone_label} · {p.time?.full ?? "No time recorded"}</div>
              <div>
                {p.source_words} · <span className={p.accuracy_m === null ? "italic" : undefined}>{p.accuracy_words}</span>
                {p.affiliation && /sync/i.test(p.affiliation) ? " · May come from another device" : ""}
                {p.deleted_state ? ` · ${p.deleted_state}` : ""}
              </div>
              <Link className="underline" to={recordPath(caseId, p.record_uid)}>Open the record behind this</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
