import { useMemo, useState, type KeyboardEvent } from "react"
import { cn } from "@/lib/cn"
import { dayWords, stripSummary } from "./strip-words"

/**
 * The time strip (07 J-4, 5): message density for the scope, one bar per day, under the stream. Resizable (48 px
 * by default, keyboard and pointer) and collapsible. "No data" days are drawn apart from quiet days and are never
 * shown as no activity. Arrow keys move a day cursor; Enter goes to that day.
 */
export interface StripDay {
  /** YYYY-MM-DD in the display zone. */
  date: string
  /** Records that day, or null when the phone holds no data for it. */
  count: number | null
}

export const STRIP_DEFAULT_PX = 48
export const STRIP_MIN_PX = 32
export const STRIP_MAX_PX = 240

export function TimeStrip({
  days,
  noun = "messages",
  zone,
  onPickDay,
  selected,
  defaultHeight = STRIP_DEFAULT_PX,
}: {
  days: StripDay[]
  noun?: string
  /** The zone in words, e.g. "Eastern time (UTC-5)". */
  zone: string
  onPickDay?: (date: string) => void
  selected?: string
  defaultHeight?: number
}) {
  const [height, setHeight] = useState(defaultHeight)
  const [collapsed, setCollapsed] = useState(false)
  const [cursor, setCursor] = useState(() => Math.max(0, days.findIndex((d) => d.date === selected)))
  const max = useMemo(() => Math.max(1, ...days.map((d) => d.count ?? 0)), [days])
  const summary = stripSummary(days, noun)
  const current = days[cursor]

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : e.key === "PageDown" ? 7 : e.key === "PageUp" ? -7 : 0
    if (step) {
      e.preventDefault()
      setCursor((c) => Math.min(days.length - 1, Math.max(0, c + step)))
    } else if (e.key === "Home") setCursor(0)
    else if (e.key === "End") setCursor(days.length - 1)
    else if (e.key === "Enter" && current) onPickDay?.(current.date)
  }

  const resize = (delta: number) => setHeight((h) => Math.min(STRIP_MAX_PX, Math.max(STRIP_MIN_PX, h + delta)))

  return (
    <section aria-label="Time strip" className="border-t bg-card text-foreground" data-testid="time-strip">
      <div className="flex items-center justify-between gap-2 px-2 py-1 text-xs">
        <span>
          {summary}. Times in {zone}.
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-2.5 w-3 bg-[repeating-linear-gradient(45deg,hsl(var(--muted-foreground))_0_1px,transparent_1px_4px)]" /> No data
          </span>
          <button type="button" className="rounded border px-1.5 py-0.5" aria-expanded={!collapsed} onClick={() => setCollapsed((c) => !c)}>
            {collapsed ? "Show time strip" : "Hide time strip"}
          </button>
        </span>
      </div>
      {!collapsed && (
        <>
          <svg
            role="slider"
            tabIndex={0}
            aria-label={`Day picker, ${noun} per day`}
            aria-valuemin={0}
            aria-valuemax={days.length - 1}
            aria-valuenow={cursor}
            aria-valuetext={current ? `${dayWords(current.date)}: ${current.count === null ? "no data" : `${current.count.toLocaleString("en-US")} ${noun}`}` : "no days"}
            onKeyDown={onKey}
            viewBox={`0 0 ${Math.max(1, days.length)} 100`}
            preserveAspectRatio="none"
            className="block w-full cursor-pointer focus-visible:outline-2 focus-visible:outline-ring"
            style={{ height }}
          >
            <defs>
              <pattern id="strip-nodata" width="2" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="0.6" height="8" className="fill-muted-foreground" />
              </pattern>
            </defs>
            {days.map((d, i) =>
              d.count === null ? (
                <rect key={d.date} x={i} y={0} width={1} height={100} fill="url(#strip-nodata)" onClick={() => setCursor(i)}>
                  <title>{`${dayWords(d.date)}: no data`}</title>
                </rect>
              ) : (
                <rect
                  key={d.date}
                  x={i + 0.1}
                  width={0.8}
                  y={100 - (d.count / max) * 100}
                  height={Math.max(d.count ? 2 : 0, (d.count / max) * 100)}
                  className={cn(i === cursor ? "fill-primary" : "fill-foreground/60")}
                  onClick={() => {
                    setCursor(i)
                    onPickDay?.(d.date)
                  }}
                >
                  <title>{`${dayWords(d.date)}: ${d.count.toLocaleString("en-US")} ${noun}`}</title>
                </rect>
              )
            )}
          </svg>
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize the time strip"
            aria-valuemin={STRIP_MIN_PX}
            aria-valuemax={STRIP_MAX_PX}
            aria-valuenow={height}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "ArrowUp") resize(8)
              if (e.key === "ArrowDown") resize(-8)
            }}
            onPointerDown={(e) => {
              const startY = e.clientY
              const startH = height
              const move = (ev: PointerEvent) => setHeight(Math.min(STRIP_MAX_PX, Math.max(STRIP_MIN_PX, startH + (startY - ev.clientY))))
              const up = () => {
                window.removeEventListener("pointermove", move)
                window.removeEventListener("pointerup", up)
              }
              window.addEventListener("pointermove", move)
              window.addEventListener("pointerup", up)
            }}
            className="h-1.5 cursor-row-resize bg-border focus-visible:outline-2 focus-visible:outline-ring"
          />
        </>
      )}
    </section>
  )
}
