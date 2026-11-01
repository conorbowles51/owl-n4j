import { cn } from "@/lib/cn"
import type { LucideIcon } from "lucide-react"
import { AREA_CLASSES } from "@/lib/areas"
import { useArea } from "@/components/ui/view-header"

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  // Inside a case view the icon takes the view's area colour (lx-style C); elsewhere it stays neutral.
  const area = useArea()
  const a = area ? AREA_CLASSES[area] : null
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-12 text-center",
        className
      )}
    >
      {Icon && (
        <div className={cn("rounded-lg p-3", a ? cn(a.soft, a.ring) : "bg-muted")} data-area={area ?? undefined}>
          <Icon className={cn("size-6", a ? a.text : "text-muted-foreground")} />
        </div>
      )}
      <div className="space-y-1">
        <h3 className="font-display text-sm font-semibold text-foreground">{title}</h3>
        {description && (
          <p className="max-w-sm text-xs text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  )
}
