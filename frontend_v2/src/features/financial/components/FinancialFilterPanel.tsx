import { useState } from "react"
import { X } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useFinancialStore } from "../stores/financial.store"
import type { FinancialCategory, TransactionEntity } from "../api"

interface FinancialFilterPanelProps {
  categories: FinancialCategory[]
  categoryCounts: Map<string, number>
  allEntities: TransactionEntity[]
}

export function FinancialFilterPanel({
  categories,
  categoryCounts,
  allEntities,
}: FinancialFilterPanelProps) {
  const {
    filterPanelOpen,
    selectedCategories,
    toggleCategory,
    selectAllCategories,
    clearCategories,
    startDate,
    setStartDate,
    endDate,
    setEndDate,
    minAmount,
    setMinAmount,
    maxAmount,
    setMaxAmount,
    entityFilter,
    setEntityFilter,
    resetFilters,
  } = useFinancialStore()

  if (!filterPanelOpen) return null

  const allCats = Array.from(categoryCounts.keys()).sort()

  const hasActiveFilters =
    selectedCategories.size > 0 ||
    startDate ||
    endDate ||
    minAmount ||
    maxAmount ||
    entityFilter

  const categoryColorMap = new Map(categories.map((c) => [c.name, c.color]))

  return (
    <div className="border-b border-border bg-muted/30 px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold">Filters</span>
        {hasActiveFilters && (
          <button
            onClick={resetFilters}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            Reset all
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-4">
        {/* Categories */}
        {allCats.length > 0 && (
          <div className="min-w-[160px]">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Categories
              </span>
              <button
                onClick={() => selectAllCategories(allCats)}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                All
              </button>
              <button
                onClick={clearCategories}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                None
              </button>
            </div>
            <div className="flex flex-wrap gap-1">
              {allCats.map((cat) => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] transition ${
                    selectedCategories.has(cat)
                      ? "border-amber-500/50 bg-amber-500/10 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {categoryColorMap.has(cat) && (
                    <div
                      className="size-2 rounded-full"
                      style={{ backgroundColor: categoryColorMap.get(cat) }}
                    />
                  )}
                  {cat}
                  <span className="text-muted-foreground">
                    {categoryCounts.get(cat) || 0}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Date Range */}
        <div>
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Date Range
          </span>
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="h-7 w-32 text-xs"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="h-7 w-32 text-xs"
            />
          </div>
        </div>

        {/* Amount Range */}
        <div>
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Amount Range
          </span>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              placeholder="Min"
              value={minAmount}
              onChange={(e) => setMinAmount(e.target.value)}
              className="h-7 w-24 text-xs"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="number"
              placeholder="Max"
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value)}
              className="h-7 w-24 text-xs"
            />
          </div>
        </div>

        {/* Entity Filter */}
        <div>
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Entity
          </span>
          {entityFilter ? (
            <Badge
              variant="outline"
              className="gap-1 text-xs cursor-pointer"
              onClick={() => setEntityFilter(null)}
            >
              {entityFilter.name}
              <X className="size-3" />
            </Badge>
          ) : (
            <EntityCombobox
              entities={allEntities}
              onSelect={(e) =>
                setEntityFilter({ key: e.key || "", name: e.name || "" })
              }
            />
          )}
        </div>
      </div>
    </div>
  )
}

function EntityCombobox({
  entities,
  onSelect,
}: {
  entities: TransactionEntity[]
  onSelect: (entity: TransactionEntity) => void
}) {
  const [search, setSearch] = useState("")
  const [open, setOpen] = useState(false)

  const filtered = entities.filter(
    (e) => e.name && e.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="relative">
      <Input
        placeholder="Filter by entity..."
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        className="h-7 w-48 text-xs"
      />
      {open && search && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 max-h-40 w-48 overflow-auto rounded-md border border-border bg-popover shadow-md">
          {filtered.slice(0, 20).map((entity) => (
            <button
              key={entity.key || entity.name}
              className="w-full px-2 py-1.5 text-left text-xs hover:bg-muted"
              onClick={() => {
                onSelect(entity)
                setSearch("")
                setOpen(false)
              }}
            >
              {entity.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
