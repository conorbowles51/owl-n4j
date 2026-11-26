import { cn } from "@/lib/cn"
import { getNodeColor } from "@/lib/theme"
import { typeLabel } from "@/lib/type-label"

interface NodeBadgeProps {
  type: string
  className?: string
  children?: React.ReactNode
  /** A colour chosen by the caller's own named mapping (the entity panel's, GR-04) instead of the shared lookup. */
  color?: string
}

/**
 * The label is the type colour mixed with the theme's text colour: the raw type colours (graph node fills) read only
 * 2.9-4.0:1 as text on their own tint. At 65% every type reads 5.1:1 or more on every surface in both themes
 * (followups 26 Nov, node-badge.test.tsx). The dot keeps the pure type colour.
 */
export const BADGE_TEXT_SHARE = 65

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
        color: `color-mix(in srgb, ${color} ${BADGE_TEXT_SHARE}%, hsl(var(--foreground)))`,
      }}
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {children ?? typeLabel(type)}
    </span>
  )
}
