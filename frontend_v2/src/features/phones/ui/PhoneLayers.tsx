import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"
import { Button } from "@/components/ui/button"
import { phonesQuery } from "../phones-query"
import { layersOn, onlyLayer, toChosen, toggleLayer } from "../lib/phone-layers"
import { PhoneShape } from "./PhoneChip"

export interface LayerPhone { id: string; label: string; index: number }

/** Every phone of the case in the case's stable order (the order PhoneChip's colour index uses). */
export function useCasePhones(caseId: string): LayerPhone[] {
  const q = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  return useMemo(() => (q.data?.phones ?? []).map((p, index) => ({ id: p.extraction_id, label: p.label, index })), [q.data])
}

const n = (v: number) => v.toLocaleString("en-US")

/**
 * The phone layer control: each phone of the case with its colour, shape, label and its count in the current view,
 * on or off on its own, with All and Only this. A phone off is not drawn and not counted by the screen; a phone with
 * nothing in the view says 0.
 */
export function PhoneLayers({ phones, chosen, onChange, counts, noun }: {
  phones: LayerPhone[]
  /** The `phones` address parameter: empty means every phone is on. */
  chosen: string[]
  onChange: (chosen: string[]) => void
  /** Per phone count in the current view; undefined while it is being counted. */
  counts?: Record<string, number>
  /** What the counts are of, plural: "positions", "messages". */
  noun: string
}) {
  const all = phones.map((p) => p.id)
  const on = layersOn(all, chosen)
  if (phones.length < 2) return null
  return (
    <section role="group" aria-label="Phone layers" className="flex flex-col gap-1 border-b bg-card px-3 py-2 text-sm" data-testid="phone-layers">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Phones</span>
        {phones.map((p) => {
          const isOn = on.includes(p.id)
          const count = counts?.[p.id]
          return (
            <span key={p.id} className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 ${isOn ? "" : "opacity-60"}`} data-phone-layer={p.id} data-on={isOn}>
              <input type="checkbox" id={`pl-${p.id}`} checked={isOn} onChange={() => onChange(toggleLayer(all, chosen, p.id))} aria-label={`${p.label} on`} />
              <PhoneShape index={p.index} />
              <label htmlFor={`pl-${p.id}`} className={isOn ? "" : "line-through"}>{p.label}</label>
              <span className="text-muted-foreground">{count === undefined ? "counting" : `${n(count)} ${count === 1 ? noun.replace(/s$/, "") : noun}`}</span>
              <button type="button" className="text-xs underline" onClick={() => onChange(onlyLayer(all, p.id))}>Only this</button>
            </span>
          )
        })}
        <Button size="sm" variant="outline" disabled={on.length === all.length} onClick={() => onChange(toChosen(all, all))}>All</Button>
      </div>
      <p role="status" className="text-xs text-muted-foreground">
        {on.length === all.length ? `All ${n(all.length)} phones are on.` : `${n(on.length)} of ${n(all.length)} phones are on. The ${n(all.length - on.length)} off ${all.length - on.length === 1 ? "is" : "are"} not drawn or counted.`}
      </p>
    </section>
  )
}
