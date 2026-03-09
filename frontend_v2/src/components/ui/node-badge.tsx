import { cn } from "@/lib/cn"
import { nodeColors, type EntityType } from "@/lib/theme"

interface NodeBadgeProps {
  type: EntityType
  className?: string
  children?: React.ReactNode
}

export function NodeBadge({ type, className, children }: NodeBadgeProps) {
  const color = nodeColors[type]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
        "text-[11px] font-semibold",
        className
      )}
      style={{
        backgroundColor: `${color}15`,
        color: color,
      }}
    >
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {children ?? type}
    </span>
  )
}
