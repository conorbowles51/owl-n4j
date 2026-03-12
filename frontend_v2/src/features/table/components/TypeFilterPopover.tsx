import { useState } from "react"
import { Filter } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getNodeColor } from "@/lib/theme"

interface TypeFilterPopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  typeCounts: Map<string, number>
  selectedTypes: Set<string>
  onToggleType: (type: string) => void
  onSelectAll: () => void
  onClearAll: () => void
}

export function TypeFilterPopover({
  open,
  onOpenChange,
  typeCounts,
  selectedTypes,
  onToggleType,
  onSelectAll,
  onClearAll,
}: TypeFilterPopoverProps) {
  const [search, setSearch] = useState("")

  const types = Array.from(typeCounts.entries())
    .sort(([, a], [, b]) => b - a)
    .filter(([type]) => type.toLowerCase().includes(search.toLowerCase()))

  const allTypes = Array.from(typeCounts.keys())
  const isAllSelected = selectedTypes.size === 0 || selectedTypes.size === allTypes.length
  const activeCount = selectedTypes.size > 0 && selectedTypes.size < allTypes.length
    ? selectedTypes.size
    : null

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Types
          {activeCount != null && (
            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
              {activeCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <div className="border-b border-border p-2">
          <Input
            placeholder="Filter types..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 text-xs"
          />
        </div>
        <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={onSelectAll}
          >
            Select All
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={onClearAll}
          >
            Clear All
          </Button>
        </div>
        <ScrollArea className="max-h-64">
          <div className="p-1">
            {types.map(([type, count]) => {
              const color = getNodeColor(type)
              const checked =
                selectedTypes.size === 0 || selectedTypes.has(type)
              return (
                <button
                  key={type}
                  onClick={() => onToggleType(type)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                >
                  <Checkbox checked={checked} />
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="flex-1 text-left capitalize">{type}</span>
                  <Badge variant="outline" className="h-4 px-1 text-[10px]">
                    {count}
                  </Badge>
                </button>
              )
            })}
            {types.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-muted-foreground">
                No types found
              </p>
            )}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
