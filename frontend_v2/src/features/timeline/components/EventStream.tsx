import { useRef, useEffect, useCallback } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { CalendarOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EventCard } from "./EventCard"
import type { StreamItem } from "../hooks/use-filtered-events"

interface EventStreamProps {
  items: StreamItem[]
  totalCount: number
  selectedEventKey: string | null
  multiSelectedKeys: Set<string>
  searchTerm: string
  selectedEntityKeys: Set<string>
  scrollToEventKey: string | null
  onSelectEvent: (key: string) => void
  onMultiSelectEvent: (key: string) => void
  onClearScrollTarget: () => void
  onClearFilters: () => void
}

const HEADER_HEIGHT = 36
const CARD_HEIGHT = 100

export function EventStream({
  items,
  totalCount,
  selectedEventKey,
  multiSelectedKeys,
  searchTerm,
  selectedEntityKeys,
  scrollToEventKey,
  onSelectEvent,
  onMultiSelectEvent,
  onClearScrollTarget,
  onClearFilters,
}: EventStreamProps) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) =>
      items[index].kind === "header" ? HEADER_HEIGHT : CARD_HEIGHT,
    overscan: 5,
  })

  // Scroll to event when scrollToEventKey changes
  useEffect(() => {
    if (!scrollToEventKey) return
    const idx = items.findIndex(
      (it) => it.kind === "event" && it.event.key === scrollToEventKey
    )
    if (idx >= 0) {
      virtualizer.scrollToIndex(idx, { align: "center", behavior: "smooth" })
    }
    onClearScrollTarget()
  }, [scrollToEventKey, items, virtualizer, onClearScrollTarget])

  const getItemKey = useCallback(
    (index: number) => {
      const item = items[index]
      return item.kind === "header" ? `h:${item.date}` : `e:${item.event.key}`
    },
    [items]
  )

  if (items.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
        <CalendarOff className="size-10 opacity-40" />
        <p className="text-sm">No events match your filters</p>
        {totalCount > 0 && (
          <Button variant="outline" size="sm" onClick={onClearFilters}>
            Clear filters
          </Button>
        )}
      </div>
    )
  }

  return (
    <div ref={parentRef} className="flex-1 overflow-auto">
      <div
        style={{
          height: virtualizer.getTotalSize(),
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => {
          const item = items[virtualItem.index]
          return (
            <div
              key={getItemKey(virtualItem.index)}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: virtualItem.size,
                transform: `translateY(${virtualItem.start}px)`,
              }}
              data-index={virtualItem.index}
              ref={virtualizer.measureElement}
            >
              {item.kind === "header" ? (
                <div className="sticky top-0 z-10 flex items-center gap-2 bg-background/95 backdrop-blur-sm px-3 py-1.5 border-b border-border/50">
                  <span className="text-xs font-semibold text-foreground">
                    {item.label}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {item.count} event{item.count !== 1 ? "s" : ""}
                  </span>
                </div>
              ) : (
                <div className="px-2 py-1">
                  <EventCard
                    event={item.event}
                    isSelected={selectedEventKey === item.event.key}
                    isMultiSelected={multiSelectedKeys.has(item.event.key)}
                    searchTerm={searchTerm}
                    highlightedEntityKeys={selectedEntityKeys}
                    onSelect={onSelectEvent}
                    onMultiSelect={onMultiSelectEvent}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
