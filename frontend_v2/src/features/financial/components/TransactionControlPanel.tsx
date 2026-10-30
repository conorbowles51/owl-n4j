import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { SlidersHorizontal, X } from "lucide-react"

/**
 * Every filter, page switch and display choice for the Transactions page in one panel that floats over the
 * right side. It opens from a tab on the right edge and collapses back to it (the tab, Esc or the close
 * button); collapsed, it covers nothing. It stays mounted while collapsed so open sub-sections and typed
 * values are kept, and is inert then: nothing in it can be reached by keyboard or screen reader.
 */
export function TransactionControlPanel({
  open,
  onOpenChange,
  activeCount,
  anchor,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Filters in force, shown on the tab so a collapsed panel never hides that the list is narrowed. */
  activeCount: number
  /** The page section the panel docks to: its right edge is where the tab sits. */
  anchor: HTMLElement | null
  children: ReactNode
}) {
  const handleRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const [edge, setEdge] = useState(0)
  // Moving focus into the panel only when a person opens it, never when it was left open on an earlier visit.
  const focusOnOpen = useRef(false)
  useLayoutEffect(() => {
    if (!anchor || typeof window === "undefined") return
    const measure = () => setEdge(Math.max(0, Math.round(window.innerWidth - anchor.getBoundingClientRect().right)))
    measure()
    window.addEventListener("resize", measure)
    const watch = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure)
    watch?.observe(anchor)
    return () => {
      window.removeEventListener("resize", measure)
      watch?.disconnect()
    }
  }, [anchor])
  useEffect(() => {
    if (open && focusOnOpen.current) panelRef.current?.focus()
    focusOnOpen.current = false
  }, [open])
  const collapse = () => {
    onOpenChange(false)
    handleRef.current?.focus()
  }
  const toggle = () => {
    if (open) collapse()
    else {
      focusOnOpen.current = true
      onOpenChange(true)
    }
  }
  return (
    <div
      className="pointer-events-none fixed bottom-3 top-3 z-40 flex items-start"
      style={{ right: Math.max(0, edge - 12) }}
      data-testid="transaction-controls-dock"
    >
      <button
        ref={handleRef}
        type="button"
        aria-expanded={open}
        aria-controls="transaction-controls"
        aria-label={`${open ? "Collapse" : "Open"} filters and page controls${activeCount ? ` (${activeCount} filters on)` : ""}`}
        onClick={toggle}
        className="pointer-events-auto mt-40 flex flex-col items-center gap-2 rounded-l-lg border border-r-0 bg-background px-1.5 py-3 text-xs font-semibold shadow-md hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <SlidersHorizontal className="size-4" aria-hidden="true" />
        <span className="[writing-mode:vertical-rl]">Controls</span>
        {activeCount > 0 && (
          <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground" aria-hidden="true">
            {activeCount}
          </span>
        )}
      </button>
      <aside
        ref={panelRef}
        id="transaction-controls"
        aria-label="Filters and page controls"
        tabIndex={-1}
        inert={!open}
        onKeyDown={(event) => {
          if (event.key === "Escape" && !event.defaultPrevented) {
            event.preventDefault()
            collapse()
          }
        }}
        className={`pointer-events-auto h-full overflow-y-auto rounded-lg border bg-background shadow-2xl outline-none transition-[width,opacity] duration-150 ${open ? "w-[min(420px,calc(100vw-4rem))] opacity-100" : "invisible w-0 border-0 opacity-0"}`}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-background px-4 py-3">
          <h2 className="text-base font-semibold">Filters and page controls</h2>
          <button
            type="button"
            onClick={collapse}
            aria-label="Collapse filters and page controls"
            className="rounded p-1 hover:bg-muted"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        <div className="space-y-5 p-4 text-sm">{children}</div>
      </aside>
    </div>
  )
}

/** A group of controls inside the panel, under its own heading. */
export function ControlGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

/** One page part as an on/off switch: on = shown on the page. */
export function SectionSwitch({
  label,
  hint,
  on,
  onChange,
}: {
  label: string
  hint?: string
  on: boolean
  onChange: (on: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="flex w-full items-start gap-3 rounded-md px-2 py-1.5 text-left hover:bg-muted"
    >
      <span
        aria-hidden="true"
        className={`mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors ${on ? "bg-primary" : "bg-muted-foreground/30"}`}
      >
        <span className={`size-4 rounded-full bg-background shadow transition-transform ${on ? "translate-x-4" : ""}`} />
      </span>
      <span>
        <span className="block font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </button>
  )
}
