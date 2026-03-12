import { memo, useCallback } from "react"
import { cn } from "@/lib/cn"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { getEventTypeColor } from "../api"
import type { TimelineEvent } from "../api"

interface EventCardProps {
  event: TimelineEvent
  isSelected: boolean
  isMultiSelected: boolean
  searchTerm: string
  highlightedEntityKeys: Set<string>
  onSelect: (key: string) => void
  onMultiSelect: (key: string) => void
}

function highlightText(text: string, term: string) {
  if (!term.trim()) return text
  const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi")
  const parts = text.split(regex)
  return parts.map((part, i) =>
    regex.test(part) ? (
      <mark key={i} className="bg-amber-500/30 text-inherit rounded-sm px-0.5">
        {part}
      </mark>
    ) : (
      part
    )
  )
}

export const EventCard = memo(function EventCard({
  event,
  isSelected,
  isMultiSelected,
  searchTerm,
  highlightedEntityKeys,
  onSelect,
  onMultiSelect,
}: EventCardProps) {
  const color = getEventTypeColor(event.type)
  const active = isSelected || isMultiSelected

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.ctrlKey || e.metaKey) {
        onMultiSelect(event.key)
      } else {
        onSelect(event.key)
      }
    },
    [event.key, onSelect, onMultiSelect]
  )

  return (
    <button
      onClick={handleClick}
      className={cn(
        "group w-full text-left rounded-lg border px-3 py-2.5 transition-all duration-150",
        "hover:bg-muted/50",
        active
          ? "ring-2 ring-amber-500 bg-amber-500/5 border-amber-500/30"
          : "border-border"
      )}
      style={{ borderLeftWidth: 3, borderLeftColor: color }}
    >
      {/* Row 1: type badge, name, date, amount */}
      <div className="flex items-start gap-2">
        <Badge
          variant="outline"
          className="shrink-0 text-[10px] font-medium"
          style={{ borderColor: `${color}50`, color }}
        >
          {event.type}
        </Badge>
        <span className="flex-1 text-sm font-medium leading-tight truncate">
          {highlightText(event.name, searchTerm)}
        </span>
        <div className="shrink-0 flex items-center gap-2 text-xs text-muted-foreground">
          {event.amount && (
            <span className="font-semibold text-amber-600 dark:text-amber-400">
              {event.amount}
            </span>
          )}
          <span>
            {new Date(event.date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
            {event.time && `, ${event.time}`}
          </span>
        </div>
      </div>

      {/* Row 2: summary */}
      {event.summary && (
        <p className="mt-1 text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {highlightText(event.summary, searchTerm)}
        </p>
      )}

      {/* Row 3: entity chips */}
      {event.connections.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {event.connections.map((conn) => (
            <NodeBadge
              key={conn.key}
              type={conn.type}
              className={cn(
                "text-[9px] py-0",
                highlightedEntityKeys.has(conn.key) &&
                  "ring-1 ring-amber-500/50"
              )}
            >
              {conn.name}
            </NodeBadge>
          ))}
        </div>
      )}
    </button>
  )
})
