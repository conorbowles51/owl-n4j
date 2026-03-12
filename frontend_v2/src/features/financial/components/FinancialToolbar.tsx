import {
  Search,
  Filter,
  BarChart3,
  Upload,
  Download,
  Palette,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useFinancialStore } from "../stores/financial.store"

interface FinancialToolbarProps {
  filteredCount: number
  totalCount: number
  caseId: string
  onOpenBulkImport: () => void
  onOpenCategoryManagement: () => void
}

export function FinancialToolbar({
  filteredCount,
  totalCount,
  caseId,
  onOpenBulkImport,
  onOpenCategoryManagement,
}: FinancialToolbarProps) {
  const {
    searchQuery,
    setSearchQuery,
    filterPanelOpen,
    setFilterPanelOpen,
    chartsPanelOpen,
    setChartsPanelOpen,
    selectedCategories,
    startDate,
    endDate,
    entityFilter,
    minAmount,
    maxAmount,
  } = useFinancialStore()

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
          placeholder="Search transactions..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8 w-64 pl-8 text-xs"
        />
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
          ? `${totalCount.toLocaleString()} transactions`
          : `${filteredCount.toLocaleString()} of ${totalCount.toLocaleString()}`}
      </Badge>

      <div className="flex-1" />

      <Button
        variant={chartsPanelOpen ? "secondary" : "ghost"}
        size="sm"
        onClick={() => setChartsPanelOpen(!chartsPanelOpen)}
      >
        <BarChart3 className="size-3.5" />
        Charts
      </Button>

      <Button variant="ghost" size="sm" onClick={onOpenBulkImport}>
        <Upload className="size-3.5" />
        Import
      </Button>

      <Button
        variant="ghost"
        size="sm"
        onClick={() =>
          window.open(
            `/api/financial/export/pdf?case_id=${encodeURIComponent(caseId)}`,
            "_blank"
          )
        }
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
