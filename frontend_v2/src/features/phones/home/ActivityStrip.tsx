import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { LensBuckets } from "@/features/timeline/lens/lens-api"
import { phoneMark } from "../lib/phone-palette"
import { weekInWindow, weeksToWindow } from "./home-api"
import { monthTicks, weekWords } from "./home-words"

const n = (x: number) => x.toLocaleString("en-US")

/**
 * "Activity on each phone, by week" (screen 1): one lane per phone that is on, a bar per week whose height is that
 * week's count under every filter but the dates. Dragging across weeks (or arrow keys, then Enter; Shift extends)
 * sets the dates for the whole page; the picked weeks are drawn full, the rest faded. A week where the phone holds no
 * data is drawn hatched, never as zero.
 */
export function ActivityStrip({ buckets, phoneIndex, window, onPick, loading, error }: {
  buckets: LensBuckets | null
  phoneIndex: (id: string) => number
  window: { from: string; to: string } | null
  onPick: (w: { from: string; to: string } | null) => void
  loading?: boolean
  error?: string | null
}) {
  const lanes = buckets?.lanes ?? []
  const walls = lanes[0]?.buckets.map((b) => b.wall) ?? []
  const max = Math.max(1, ...lanes.flatMap((l) => l.buckets.map((b) => b.count)))
  const [drag, setDrag] = useState<{ a: number; b: number } | null>(null)
  const [cursor, setCursor] = useState(0)
  const [anchor, setAnchor] = useState<number | null>(null)
  const grid = useRef<HTMLDivElement>(null)
  const at = (clientX: number) => {
    const r = grid.current?.getBoundingClientRect()
    if (!r || !walls.length) return 0
    return Math.min(walls.length - 1, Math.max(0, Math.floor(((clientX - r.left) / r.width) * walls.length)))
  }
  const shown = (i: number) => (drag ? i >= Math.min(drag.a, drag.b) && i <= Math.max(drag.a, drag.b) : window ? weekInWindow(walls[i], window) : true)
  const total = (i: number) => lanes.map((l) => `${l.label} ${n(l.buckets[i]?.count ?? 0)}`).join(", ")
  const cols = { gridTemplateColumns: `repeat(${Math.max(1, walls.length)}, minmax(0, 1fr))` }
  return (
    <section aria-label="Activity on each phone" className="border-t bg-muted/30 px-4 py-3 md:px-7">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="text-sm font-semibold text-foreground">Activity on each phone, by week</span>
        <span className="flex items-center gap-2">
          {window ? <>Showing {window.from} to {window.to}. <Button size="sm" variant="outline" className="h-7" onClick={() => onPick(null)}>Every week</Button></> : "Drag across the weeks to narrow everything above"}
        </span>
      </div>
      {error && <p role="alert" className="text-sm">{error}</p>}
      {loading && !buckets && <p role="status" className="text-sm text-muted-foreground">Counting each phone's weeks</p>}
      {buckets && walls.length === 0 && <p className="text-sm text-muted-foreground">Nothing with a time matches, so there are no weeks to draw.</p>}
      {walls.length > 0 && (
        <div
          className="flex cursor-col-resize touch-none select-none flex-col gap-1.5"
          data-testid="activity-weeks"
          onPointerDown={(e) => {
            const i = at(e.clientX)
            ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
            setDrag({ a: i, b: i })
          }}
          onPointerMove={(e) => drag && setDrag({ ...drag, b: at(e.clientX) })}
          onPointerUp={() => {
            if (drag) onPick(weeksToWindow(walls, drag.a, drag.b))
            setDrag(null)
          }}
        >
          {lanes.map((l) => {
            const mark = phoneMark(phoneIndex(l.key))
            return (
              <div key={l.key} className="flex items-end gap-2.5" data-lane={l.key}>
                <div className="w-24 shrink-0 truncate text-xs text-foreground" title={l.label}>{l.label}</div>
                <div className="grid h-7 flex-1 items-end gap-px" style={cols} aria-hidden>
                  {l.buckets.map((b, i) => (
                    <span key={b.wall} className={`block rounded-sm ${b.no_data ? "bg-[repeating-linear-gradient(45deg,transparent_0_2px,currentColor_2px_3px)] text-muted-foreground/50" : "bg-[var(--phone-light)] dark:bg-[var(--phone-dark)]"}`}
                      style={{ height: b.no_data ? "100%" : `${Math.max(2, Math.round((b.count / max) * 28))}px`, opacity: shown(i) ? 1 : 0.4, ["--phone-light" as string]: mark.light, ["--phone-dark" as string]: mark.dark }}
                      title={`${l.label}, ${weekWords(b.wall)}: ${b.no_data ? "no data on the phone" : n(b.count)}`} />
                  ))}
                </div>
              </div>
            )
          })}
          <div className="flex gap-2.5">
            <div className="w-24 shrink-0" />
            <div
              ref={grid}
              role="slider"
              tabIndex={0}
              aria-label="Weeks to show"
              aria-valuemin={0}
              aria-valuemax={walls.length - 1}
              aria-valuenow={cursor}
              aria-valuetext={`${weekWords(walls[cursor])}: ${total(cursor)}. Enter picks it; Shift with the arrows picks a run of weeks.`}
              className="relative flex-1 rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onKeyDown={(e) => {
                const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0
                if (step) {
                  e.preventDefault()
                  const next = Math.min(walls.length - 1, Math.max(0, cursor + step))
                  if (e.shiftKey) {
                    const a = anchor ?? cursor
                    setAnchor(a)
                    onPick(weeksToWindow(walls, a, next))
                  } else setAnchor(null)
                  setCursor(next)
                } else if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  onPick(weeksToWindow(walls, anchor ?? cursor, cursor))
                } else if (e.key === "Escape" && window) {
                  e.preventDefault()
                  onPick(null)
                }
              }}
            >
              <div className="relative h-4 font-mono text-[11px] text-muted-foreground">
                {monthTicks(walls).map((t) => (
                  <span key={t.i} className="absolute top-0 whitespace-nowrap" style={{ left: `${(t.i / walls.length) * 100}%` }}>{t.label}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
