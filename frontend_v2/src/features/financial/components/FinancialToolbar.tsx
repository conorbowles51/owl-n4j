import {
  useEffect,
  useState,
} from "react"
import {
  Search,
  Filter,
  Upload,
  Download,
  Palette,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useFinancialStore } from "../stores/financial.store"
import type { FinancialDatasetMode } from "../api"

interface FinancialToolbarProps {
  mode: FinancialDatasetMode
  filteredCount: number
  totalCount: number
  onOpenBulkImport: () => void
  onOpenCategoryManagement: () => void
  onExportPdf: () => void
}

export function FinancialToolbar({
  mode,
  filteredCount,
  totalCount,
  onOpenBulkImport,
  onOpenCategoryManagement,
  onExportPdf,
}: FinancialToolbarProps) {
  const {
    searchQuery,
    setSearchQuery,
    filterPanelOpen,
    setFilterPanelOpen,
    selectedCategories,
    startDate,
    endDate,
    entityFilter,
    minAmount,
    maxAmount,
    setMode,
  } = useFinancialStore()
  const [searchInput, setSearchInput] = useState(searchQuery)

  useEffect(() => {
    setSearchInput(searchQuery)
  }, [searchQuery])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (searchInput !== searchQuery) {
        setSearchQuery(searchInput)
      }
    }, 300)

    return () => window.clearTimeout(timeoutId)
  }, [searchInput, searchQuery, setSearchQuery])

  const activeFilterCount =
    (selectedCategories.size > 0 ? 1 : 0) +
    (startDate ? 1 : 0) +
    (endDate ? 1 : 0) +
    (entityFilter ? 1 : 0) +
    (minAmount ? 1 : 0) +
    (maxAmount ? 1 : 0)

  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={mode === "transactions" ? "Search transactions..." : "Search financial intelligence..."}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="h-8 w-64 pl-8 text-xs"
        />
      </div>

      <div className="flex items-center rounded-md border border-border p-0.5">
        <Button
          variant={mode === "transactions" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => setMode("transactions")}
        >
          Transactions
        </Button>
        <Button
          variant={mode === "intelligence" ? "secondary" : "ghost"}
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => setMode("intelligence")}
        >
          Financial Intelligence
        </Button>
      </div>

      <Button
        variant={filterPanelOpen ? "secondary" : "ghost"}
        size="sm"
        onClick={() => setFilterPanelOpen(!filterPanelOpen)}
      >
        <Filter className="size-3.5" />
        Filters
        {activeFilterCount > 0 && (
          <Badge variant="amber" className="ml-1 h-4 px-1 text-[10px]">
            {activeFilterCount}
          </Badge>
        )}
      </Button>

      <Badge variant="slate" className="text-[10px]">
        {filteredCount === totalCount
          ? `${totalCount.toLocaleString()} ${mode === "transactions" ? "transactions" : "records"}`
          : `${filteredCount.toLocaleString()} of ${totalCount.toLocaleString()}`}
      </Badge>

      <div className="flex-1" />

      {mode === "transactions" && (
        <Button variant="ghost" size="sm" onClick={onOpenBulkImport}>
          <Upload className="size-3.5" />
          Import
        </Button>
      )}

      <Button
        variant="ghost"
        size="sm"
        onClick={onExportPdf}
      >
        <Download className="size-3.5" />
        PDF
      </Button>

      <Button variant="ghost" size="sm" onClick={onOpenCategoryManagement}>
        <Palette className="size-3.5" />
        Categories
      </Button>
    </div>
  )
}
