import { useState } from "react"
import { Filter } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getNodeColor } from "@/lib/theme"

interface EntityTypeFilterPopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  typeCounts: Map<string, number>
  selectedTypes: Set<string> | null
  onToggleType: (type: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  triggerVariant?: "ghost" | "outline"
}

export function EntityTypeFilterPopover({
  open,
  onOpenChange,
  typeCounts,
  selectedTypes,
  onToggleType,
  onSelectAll,
  onDeselectAll,
  triggerVariant = "ghost",
}: EntityTypeFilterPopoverProps) {
  const [search, setSearch] = useState("")

  const types = Array.from(typeCounts.entries())
    .sort(([, a], [, b]) => b - a)
    .filter(([type]) => type.toLowerCase().includes(search.trim().toLowerCase()))

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant={triggerVariant} size="sm" className="shrink-0">
          <Filter className="size-3.5" />
          Types
          {selectedTypes !== null && (
            <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
              {selectedTypes.size}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <div className="border-b border-border p-2">
          <Input
            placeholder="Filter types..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-7 text-xs"
          />
        </div>
        <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={onSelectAll}
            disabled={typeCounts.size === 0}
          >
            Select All
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={onDeselectAll}
            disabled={typeCounts.size === 0}
          >
            Deselect All
          </Button>
        </div>
        <ScrollArea className="h-64">
          <div className="p-1">
            {types.map(([type, count]) => {
              const checked = selectedTypes === null || selectedTypes.has(type)
              return (
                <div
                  key={type}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => onToggleType(type)}
                    aria-label={`Toggle ${type}`}
                  />
                  <button
                    type="button"
                    onClick={() => onToggleType(type)}
                    className="flex min-w-0 flex-1 items-center gap-2"
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: getNodeColor(type) }}
                    />
                    <span className="flex-1 text-left capitalize">{type}</span>
                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                      {count}
                    </Badge>
                  </button>
                </div>
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
