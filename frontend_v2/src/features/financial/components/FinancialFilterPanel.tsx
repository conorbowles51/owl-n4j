import { useState } from "react"
import { Filter } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { FinancialCategory } from "../api"

interface FinancialFilters {
  startDate: string
  endDate: string
  categories: Set<string>
  minAmount: string
  maxAmount: string
}

interface FinancialFilterPanelProps {
  categories: FinancialCategory[]
  filters: FinancialFilters
  onChange: (filters: FinancialFilters) => void
  onReset: () => void
}

export function FinancialFilterPanel({
  categories,
  filters,
  onChange,
  onReset,
}: FinancialFilterPanelProps) {
  const [open, setOpen] = useState(false)
  const activeCount =
    (filters.startDate ? 1 : 0) +
    (filters.endDate ? 1 : 0) +
    (filters.categories.size > 0 ? 1 : 0) +
    (filters.minAmount ? 1 : 0) +
    (filters.maxAmount ? 1 : 0)

  const toggleCategory = (name: string) => {
    const next = new Set(filters.categories)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    onChange({ ...filters, categories: next })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
          {activeCount > 0 && (
            <Badge variant="amber" className="ml-1 h-4 px-1 text-[10px]">
              {activeCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-xs font-semibold">Filters</p>
          <button
            onClick={onReset}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            Reset
          </button>
        </div>

        <div className="space-y-3 p-3">
          {/* Date range */}
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Date Range
            </p>
            <div className="flex items-center gap-2">
              <Input
                type="date"
                value={filters.startDate}
                onChange={(e) =>
                  onChange({ ...filters, startDate: e.target.value })
                }
                className="h-7 text-xs"
              />
              <span className="text-xs text-muted-foreground">to</span>
              <Input
                type="date"
                value={filters.endDate}
                onChange={(e) =>
                  onChange({ ...filters, endDate: e.target.value })
                }
                className="h-7 text-xs"
              />
            </div>
          </div>

          {/* Amount range */}
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Amount Range
            </p>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                placeholder="Min"
                value={filters.minAmount}
                onChange={(e) =>
                  onChange({ ...filters, minAmount: e.target.value })
                }
                className="h-7 text-xs"
              />
              <span className="text-xs text-muted-foreground">to</span>
              <Input
                type="number"
                placeholder="Max"
                value={filters.maxAmount}
                onChange={(e) =>
                  onChange({ ...filters, maxAmount: e.target.value })
                }
                className="h-7 text-xs"
              />
            </div>
          </div>

          {/* Categories */}
          {categories.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Categories
              </p>
              <ScrollArea className="max-h-32">
                <div className="space-y-0.5">
                  {categories.map((cat) => (
                    <button
                      key={cat.name}
                      onClick={() => toggleCategory(cat.name)}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-muted"
                    >
                      <Checkbox checked={filters.categories.has(cat.name)} />
                      <div
                        className="size-2 rounded-full"
                        style={{ backgroundColor: cat.color }}
                      />
                      <span>{cat.name}</span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export type { FinancialFilters }
