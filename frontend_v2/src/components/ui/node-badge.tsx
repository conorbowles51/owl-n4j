import { cn } from "@/lib/cn"
import { getNodeColor } from "@/lib/theme"

interface NodeBadgeProps {
  type: string
  className?: string
  children?: React.ReactNode
  /** A colour chosen by the caller's own named mapping (the entity panel's, GR-04) instead of the shared lookup. */
  color?: string
}

export function NodeBadge({ type, className, children, color: chosen }: NodeBadgeProps) {
  const color = chosen ?? getNodeColor(type)
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5",
        "text-[11px] font-semibold",
        className
      )}
      style={{
        backgroundColor: `${color}15`,
        color: color,
      }}
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {children ?? type}
    </span>
  )
}
