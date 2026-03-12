import { useState, forwardRef } from "react"
import { Search, X, SlidersHorizontal } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface TimelineToolbarProps {
  searchTerm: string
  onSearchChange: (term: string) => void
  dateRange: { start: string | null; end: string | null }
  onDateRangeChange: (range: { start: string | null; end: string | null }) => void
  filteredCount: number
  totalCount: number
  onToggleFilterSidebar: () => void
  activeFilterCount: number
}

type DatePreset = "all" | "30d" | "90d" | "1yr" | "custom"

export const TimelineToolbar = forwardRef<HTMLInputElement, TimelineToolbarProps>(
  function TimelineToolbar(
    {
      searchTerm,
      onSearchChange,
      dateRange,
      onDateRangeChange,
      filteredCount,
      totalCount,
      onToggleFilterSidebar,
      activeFilterCount,
    },
    searchInputRef
  ) {
    const [datePreset, setDatePreset] = useState<DatePreset>(
      dateRange.start || dateRange.end ? "custom" : "all"
    )

    const handlePreset = (preset: DatePreset) => {
      setDatePreset(preset)
      if (preset === "all") {
        onDateRangeChange({ start: null, end: null })
      } else if (preset === "custom") {
        // Keep existing
      } else {
        const now = new Date()
        const days = preset === "30d" ? 30 : preset === "90d" ? 90 : 365
        const start = new Date(now.getTime() - days * 86400000)
        onDateRangeChange({
          start: start.toISOString().split("T")[0],
          end: now.toISOString().split("T")[0],
        })
      }
    }

    return (
      <div className="flex items-center gap-2 border-b border-border bg-card px-3 py-2">
        {/* Filter sidebar toggle */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleFilterSidebar}
          className="shrink-0"
        >
          <SlidersHorizontal className="size-3.5" />
          Filters
          {activeFilterCount > 0 && (
            <Badge variant="amber" className="ml-1 h-4 px-1 text-[10px]">
              {activeFilterCount}
            </Badge>
          )}
        </Button>

        <div className="h-4 w-px bg-border shrink-0" />

        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2 size-3.5 text-muted-foreground" />
          <Input
            ref={searchInputRef}
            placeholder="Search events... ( / )"
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-8 h-7 text-xs"
          />
          {searchTerm && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-2 top-1.5 text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        <div className="h-4 w-px bg-border shrink-0" />

        {/* Date presets */}
        <div className="flex items-center gap-1">
          {(["all", "30d", "90d", "1yr", "custom"] as const).map((preset) => (
            <button
              key={preset}
              onClick={() => handlePreset(preset)}
              className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                datePreset === preset
                  ? "bg-foreground text-background"
                  : "bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              {preset === "all"
                ? "All"
                : preset === "custom"
                  ? "Custom"
                  : preset.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Custom date inputs */}
        {datePreset === "custom" && (
          <>
            <input
              type="date"
              value={dateRange.start ?? ""}
              onChange={(e) =>
                onDateRangeChange({ ...dateRange, start: e.target.value || null })
              }
              className="rounded border border-border bg-transparent px-2 py-0.5 text-[10px] h-7"
            />
            <span className="text-[10px] text-muted-foreground">–</span>
            <input
              type="date"
              value={dateRange.end ?? ""}
              onChange={(e) =>
                onDateRangeChange({ ...dateRange, end: e.target.value || null })
              }
              className="rounded border border-border bg-transparent px-2 py-0.5 text-[10px] h-7"
            />
          </>
        )}

        {/* Event count */}
        <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
          {filteredCount === totalCount
            ? `${totalCount} events`
            : `${filteredCount} of ${totalCount} events`}
        </span>
      </div>
    )
  }
)
