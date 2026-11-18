import { X } from "lucide-react"
import { useEffect, type CSSProperties, type ReactNode } from "react"
import { cn } from "@/lib/cn"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

/**
 * The docked record panel slot (07 4.1, 4.3): a non-modal aside beside the work area, built like the financial
 * naming panel and not like the modal Sheet, so j/k keep moving the list while it is open and it follows the
 * focused row. Esc closes it (when focus is inside it) and returns focus to `returnFocus`.
 */
export function DockedPanel({
  title,
  open,
  onClose,
  children,
  width = 400,
  returnFocus,
  className,
}: {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
  width?: number
  returnFocus?: () => HTMLElement | null
  className?: string
}) {
  useEffect(() => {
    if (!open) return
    return () => returnFocus?.()?.focus()
  }, [open, returnFocus])
  if (!open) return null
  return (
    <aside
      aria-label={title}
      // Below 768 px a docked width leaves the page beside it no room and pushes Close off the screen: the panel
      // becomes a sheet over the page, and Close returns to the page (lx-leads live check, 390 wide).
      className={cn("flex h-full shrink-0 flex-col border-l bg-card text-foreground w-[var(--docked-w)]",
        "max-md:fixed max-md:inset-0 max-md:z-40 max-md:w-full max-md:border-l-0", className)}
      style={{ "--docked-w": `${width}px` } as CSSProperties}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation()
          onClose()
        }
      }}
      data-testid="docked-panel"
    >
      <header className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" onClick={onClose} aria-label={`Close ${title}`} className="rounded p-1 hover:bg-muted">
              <X className="size-4" aria-hidden />
            </button>
          </TooltipTrigger>
          <TooltipContent>{`Close ${title}`}</TooltipContent>
        </Tooltip>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </aside>
  )
}
