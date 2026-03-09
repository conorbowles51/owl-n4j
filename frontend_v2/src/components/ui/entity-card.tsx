import { cn } from "@/lib/cn"
import { NodeBadge } from "@/components/ui/node-badge"
import type { EntityType } from "@/lib/theme"

interface EntityCardProps {
  name: string
  type: EntityType
  connectionCount?: number
  className?: string
  onClick?: () => void
}

export function EntityCard({
  name,
  type,
  connectionCount,
  className,
  onClick,
}: EntityCardProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border p-3",
        "bg-card",
        "border-border",
        "transition-colors duration-200",
        "hover:border-slate-300 dark:hover:border-slate-600",
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      <NodeBadge type={type} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{name}</p>
        {connectionCount !== undefined && (
          <p className="text-xs text-muted-foreground">
            {connectionCount} connection{connectionCount !== 1 ? "s" : ""}
          </p>
        )}
      </div>
    </div>
  )
}
