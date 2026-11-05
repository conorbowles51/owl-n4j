import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import type { PhoneMapItem, PhoneMapPoints, PhoneMapSummary } from "@/features/phones/api"
import { recordPath } from "@/lib/record-links"
import { installKeymap, register } from "@/lib/keymap"
import { useMapStore } from "../stores/map.store"
import { TypedDossierAdd } from "@/features/phones/ui/TypedDossierAdd"
import { phoneSummaryWords } from "./phone-summary-words"
import { PLACE_LABEL } from "../lib/place-label"
import { cn } from "@/lib/cn"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * The Map phone layer's panel: the totals line, why some records cannot be placed, any clustering limit, and
 * every point in view as a keyboard-steppable list with its accuracy and the record behind it (03 section 13.3).
 */
export function PhoneLayerPanel({ caseId, summary, points, addDisabled }: { caseId: string; summary: PhoneMapSummary; points?: PhoneMapPoints; addDisabled?: string }) {
  const [why, setWhy] = useState(false)
  const shown = points?.total ?? 0
  const words = phoneSummaryWords(summary, shown)
  const items = (points?.items ?? []).filter((i): i is Extract<PhoneMapItem, { type: "point" }> => i.type === "point")
  const flyTo = useMapStore((s) => s.flyTo)
  const [current, setCurrent] = useState<string | null>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const index = items.findIndex((p) => p.point_uid === current)
  // kept by id: the map moves to each position, so the list in view can change under it
  const step = useRef<(by: number) => void>(() => undefined)
  useEffect(() => {
    step.current = (by: number) => {
      if (!items.length) return
      const at = index < 0 ? (by > 0 ? 0 : items.length - 1) : Math.min(items.length - 1, Math.max(0, index + by))
      const p = items[at]
      setCurrent(p.point_uid)
      flyTo({ longitude: p.lon, latitude: p.lat })
      listRef.current?.querySelector(`[data-point="${CSS.escape(p.point_uid)}"]`)?.scrollIntoView?.({ block: "nearest" })
    }
  })
  const hasItems = items.length > 0
  useEffect(() => {
    if (!hasItems) return
    installKeymap()
    const run = (by: number) => (event: KeyboardEvent) => {
      // arrow keys over the map canvas pan the map; everywhere else they step through this list
      if ((event.target as HTMLElement | null)?.closest?.(".maplibregl-map")) return
      step.current(by)
    }
    return register("Map", [
      { key: "ArrowDown", label: "Next position", run: run(1) },
      { key: "ArrowUp", label: "Previous position", run: run(-1) },
      { key: "j", label: "Next position", run: run(1) },
      { key: "k", label: "Previous position", run: run(-1) },
    ])
  }, [hasItems])
  return (
    <section aria-label="Phone positions" className="absolute bottom-3 left-3 z-10 flex max-h-[45%] w-80 flex-col gap-1 overflow-hidden rounded-lg border border-border bg-card/95 p-3 text-xs shadow-md backdrop-blur">
      <h2 className="text-sm font-semibold">Phone positions</h2>
      <p className="font-medium">{PLACE_LABEL}.</p>
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
        <div className="flex items-center gap-1">
          <Button size="sm" variant="outline" className="h-6 px-2 text-xs" aria-label="Previous position" onClick={() => step.current(-1)}>↑</Button>
          <Button size="sm" variant="outline" className="h-6 px-2 text-xs" aria-label="Next position" onClick={() => step.current(1)}>↓</Button>
          <span role="status">{index >= 0 ? `Position ${n(index + 1)} of ${n(items.length)}` : `${n(items.length)} in the list. Arrow keys step through them.`}</span>
        </div>
      )}
      {items.length > 0 && (
        <ul ref={listRef} aria-label="Positions in view" className="flex flex-col gap-1 overflow-auto">
          {items.map((p) => (
            <li key={p.point_uid} data-point={p.point_uid} aria-current={p.point_uid === current ? "true" : undefined}
              className={cn("rounded border border-border/60 px-2 py-1", p.point_uid === current && "border-primary bg-muted")}>
              <div className="font-medium">{p.phone_label} · {p.time?.full ?? "No time recorded"}</div>
              <div>
                {p.source_words} · <span className={p.accuracy_m === null ? "italic" : undefined}>{p.accuracy_words}</span>
                {p.affiliation && /sync/i.test(p.affiliation) ? " · May come from another device" : ""}
                {p.deleted_state ? ` · ${p.deleted_state}` : ""}
              </div>
              <span className="flex flex-wrap gap-x-3">
                <Link className="underline" to={recordPath(caseId, p.record_uid)}>Open the record behind this</Link>
                {p.instant && (
                  <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/timeline?phone_record=${encodeURIComponent(p.record_uid)}`}>Show on Timeline</Link>
                )}
              </span>
              <TypedDossierAdd caseId={caseId} type="address" origin="Added from the Map" suggestedName={`${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`} disabledReason={addDisabled}
                link={{ target_type: "phone_record", target_id: p.record_uid, label: `${p.phone_label} · ${p.time?.full ?? "No time recorded"}`, source_anchor: { extraction_id: p.extraction_id, lat: p.lat, lon: p.lon, accuracy_m: p.accuracy_m } }} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
