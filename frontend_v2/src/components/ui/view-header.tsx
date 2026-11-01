import { createContext, useContext, useEffect } from "react"
import { cn } from "@/lib/cn"
import { AREA_CLASSES, AREAS, type AreaId, type CaseView } from "@/lib/areas"

/** The area of the view being shown, for shared primitives (EmptyState) that tint themselves by area. */
export const AreaContext = createContext<AreaId | null>(null)
export const useArea = () => useContext(AreaContext)

/**
 * The case view's identity band (lx-style C): the area's tinted surface with an area-coloured rule, the view's
 * icon in the area colour, the area name and the view title. Rendered once by CaseLayout for every case view,
 * so no view hand-rolls its own. Sets the tab title (07 4.2 item 8).
 */
export function ViewHeader({ view, className }: { view: CaseView; className?: string }) {
  const a = AREA_CLASSES[view.area]
  const Icon = view.icon
  useEffect(() => {
    const previous = document.title
    document.title = `${view.title} · Loupe`
    return () => {
      document.title = previous
    }
  }, [view.title])
  return (
    <header
      data-area={view.area}
      data-testid="view-header"
      aria-label={`${view.title} view`}
      className={cn(
        "relative flex h-9 shrink-0 items-center gap-2.5 border-b border-border px-3 md:h-10 md:px-4",
        a.soft,
        className
      )}
    >
      <span aria-hidden="true" className={cn("absolute inset-x-0 top-0 h-[3px]", a.bg)} />
      <span
        aria-hidden="true"
        className={cn("flex size-6 shrink-0 items-center justify-center rounded-md bg-card", a.ring)}
      >
        <Icon className={cn("size-3.5", a.text)} />
      </span>
      <span className={cn("type-eyebrow hidden sm:inline", a.fg)}>
        {AREAS[view.area].label}
      </span>
      <span aria-hidden="true" className={cn("hidden sm:inline", a.fg)}>
        /
      </span>
      <span className="type-section truncate text-foreground">
        {view.title}
      </span>
    </header>
  )
}
