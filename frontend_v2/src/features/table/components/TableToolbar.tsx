import { Search, Download, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { TableColumnConfig, type ColumnConfig } from "./TableColumnConfig"
import { TypeFilterPopover } from "./TypeFilterPopover"

interface TableToolbarProps {
  searchTerm: string
  onSearchChange: (term: string) => void
  // Type filter
  typeFilterOpen: boolean
  onTypeFilterOpenChange: (open: boolean) => void
  typeCounts: Map<string, number>
  selectedTypes: Set<string>
  onToggleType: (type: string) => void
  onSelectAllTypes: () => void
  onClearTypes: () => void
  // Column config
  columns: ColumnConfig[]
  onColumnsChange: (columns: ColumnConfig[]) => void
  // Counts
  filteredCount: number
  totalCount: number
  // Actions
  onExportCSV: () => void
  onAddEntity: () => void
  // Ref for keyboard nav
  searchInputRef: React.RefObject<HTMLInputElement | null>
}

export function TableToolbar({
  searchTerm,
  onSearchChange,
  typeFilterOpen,
  onTypeFilterOpenChange,
  typeCounts,
  selectedTypes,
  onToggleType,
  onSelectAllTypes,
  onClearTypes,
  columns,
  onColumnsChange,
  filteredCount,
  totalCount,
  onExportCSV,
  onAddEntity,
  searchInputRef,
}: TableToolbarProps) {
  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={searchInputRef}
          placeholder="Search entities..."
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-8 w-64 pl-8 pr-8 text-xs"
        />
        {!searchTerm && (
          <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1 text-[10px] text-muted-foreground">
            /
          </kbd>
        )}
      </div>

      <TypeFilterPopover
        open={typeFilterOpen}
        onOpenChange={onTypeFilterOpenChange}
        typeCounts={typeCounts}
        selectedTypes={selectedTypes}
        onToggleType={onToggleType}
        onSelectAll={onSelectAllTypes}
        onClearAll={onClearTypes}
      />

      <TableColumnConfig columns={columns} onChange={onColumnsChange} />

      <div className="flex-1" />

      <Badge variant="slate" className="text-xs">
        {filteredCount === totalCount
          ? `${totalCount} entities`
          : `${filteredCount} of ${totalCount} entities`}
      </Badge>

      <Button variant="ghost" size="sm" onClick={onAddEntity}>
        <Plus className="size-3.5" />
        Add Entity
      </Button>

      <Button variant="outline" size="sm" onClick={onExportCSV}>
        <Download className="size-3.5" />
        Export CSV
      </Button>
    </div>
  )
}
