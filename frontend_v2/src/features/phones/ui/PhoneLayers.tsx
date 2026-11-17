import { useEffect, useRef, useState } from "react"
import { LearnMore } from "@/components/ui/learn-more"
import { announce } from "@/features/guidance/announce"
import { Button } from "@/components/ui/button"
import { groupByOwner, layersOn, MANY_PHONES, onlyLayer, toChosen, toggleLayer } from "../lib/phone-layers"
import { PhoneShape } from "./PhoneChip"

import type { LayerPhone } from "./use-case-phones"

const n = (v: number) => v.toLocaleString("en-US")

/**
 * The phone layer control: each phone of the case with its colour, shape, label and its count in the current view,
 * on or off on its own, with All and Only this. A phone off is not drawn and not counted by the screen; a phone with
 * nothing in the view says 0.
 */
export function PhoneLayers({ phones, chosen, onChange: setChosen, counts, noun }: {
  phones: LayerPhone[]
  /** The `phones` address parameter: empty means every phone is on. */
  chosen: string[]
  onChange: (chosen: string[]) => void
  /** Per phone count in the current view; undefined while it is being counted, null when the screen cannot give one. */
  counts?: Record<string, number> | null
  /** What the counts are of, plural: "positions", "messages". */
  noun: string
}) {
  const all = phones.map((p) => p.id)
  const on = layersOn(all, chosen)
  // a phone turned on (or All, Only this): the next steps follow once the person stops changing them (lx-guidecover E)
  const settle = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(settle.current), [])
  const onChange = (next: string[]) => {
    setChosen(next)
    const nowOn = layersOn(all, next).length
    window.clearTimeout(settle.current)
    if (nowOn > on.length || next.length === 0)
      settle.current = window.setTimeout(() => announce(null, { kind: "layers-changed", on: nowOn, total: all.length }), 1500)
  }
  // on a narrow screen the list opens on request, so it does not push the screen's own content out of view
  const [open, setOpen] = useState(() => typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 768px)").matches)
  const many = phones.length > MANY_PHONES
  const [query, setQuery] = useState("")
  const renderPhone = (p: LayerPhone) => {
    const isOn = on.includes(p.id)
    const count = counts === null ? null : counts?.[p.id]
    return (
      <span key={p.id} className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 ${isOn ? "" : "opacity-60"}`} data-phone-layer={p.id} data-on={isOn}>
        <input type="checkbox" id={`pl-${p.id}`} checked={isOn} onChange={() => onChange(toggleLayer(all, chosen, p.id))} aria-label={`${p.label} on`} />
        <PhoneShape index={p.index} />
        <label htmlFor={`pl-${p.id}`} className={isOn ? "" : "line-through"}>{p.label}</label>
        {p.owner && !many && <span className="text-muted-foreground">({p.owner})</span>}
        {count !== null && <span className="text-muted-foreground">{count === undefined ? "counting" : `${n(count)} ${count === 1 ? noun.replace(/s$/, "") : noun}`}</span>}
        <button type="button" className="text-xs underline" onClick={() => onChange(onlyLayer(all, p.id))}>Only this</button>
      </span>
    )
  }
  if (phones.length < 2) return null
  return (
    <section role="group" aria-label="Phone layers" className="flex flex-col gap-1 border-b bg-card px-3 py-2 text-sm" data-testid="phone-layers" data-guide="phone-layers">
      <button type="button" className="flex items-center gap-2 text-left font-medium md:hidden" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Phones: {on.length === all.length ? `all ${n(all.length)} on` : `${n(on.length)} of ${n(all.length)} on`} <span aria-hidden>{open ? "▾" : "▸"}</span>
      </button>
      <div className={`flex-wrap items-center gap-2 ${open ? "flex" : "hidden md:flex"}`}>
        <span className="hidden font-medium md:inline">Phones</span>
        {many && (
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a phone or owner" aria-label="Find a phone or owner"
            className="rounded border bg-background px-2 py-0.5 text-sm" />
        )}
        {many ? null : phones.map(renderPhone)}
        <Button size="sm" variant="outline" disabled={on.length === all.length} onClick={() => onChange(toChosen(all, all))}>All</Button>
      </div>
      {many && open && (
        <div className="flex flex-col gap-1" data-testid="phone-layer-groups">
          {groupByOwner(phones, query).map((g) => (
            <div key={g.owner ?? "none"} className="flex flex-wrap items-center gap-2" role="group" aria-label={g.owner ?? "No owner named"}>
              <span className="w-40 shrink-0 text-xs font-medium text-muted-foreground">{g.owner ?? "No owner named"}</span>
              {g.phones.map(renderPhone)}
            </div>
          ))}
          {query.trim() && groupByOwner(phones, query).length === 0 && <p className="text-xs text-muted-foreground">No phone or owner matches "{query.trim()}".</p>}
        </div>
      )}
      <p role="status" className={`text-xs text-muted-foreground ${open ? "" : "hidden md:block"}`}>
        {on.length === all.length ? `All ${n(all.length)} phones are on.` : `${n(on.length)} of ${n(all.length)} phones are on. The ${n(all.length - on.length)} off ${all.length - on.length === 1 ? "is" : "are"} not drawn or counted.`}
        <LearnMore term="Phone layers" />
      </p>
    </section>
  )
}
