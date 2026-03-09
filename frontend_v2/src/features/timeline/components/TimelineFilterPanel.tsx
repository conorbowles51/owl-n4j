import { useState } from "react"
import { Filter } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"

interface TimelineFilterPanelProps {
  eventTypes: string[]
  selectedTypes: Set<string>
  onToggleType: (type: string) => void
  onSelectAll: () => void
  onClearAll: () => void
}

export function TimelineFilterPanel({
  eventTypes,
  selectedTypes,
  onToggleType,
  onSelectAll,
  onClearAll,
}: TimelineFilterPanelProps) {
  const [open, setOpen] = useState(false)
  const activeCount = selectedTypes.size

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
          {activeCount > 0 && activeCount < eventTypes.length && (
            <Badge variant="amber" className="ml-1 h-4 px-1 text-[10px]">
              {activeCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-xs font-semibold">Event Types</p>
          <div className="flex gap-1">
            <button
              onClick={onSelectAll}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              All
            </button>
            <span className="text-[10px] text-muted-foreground">|</span>
            <button
              onClick={onClearAll}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              None
            </button>
          </div>
        </div>
        <ScrollArea className="max-h-64">
          <div className="p-1">
            {eventTypes.map((type) => (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
              >
                <Checkbox checked={selectedTypes.has(type)} />
                <span className="flex-1 text-left">{type}</span>
              </button>
            ))}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
