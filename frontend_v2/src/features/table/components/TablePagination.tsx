import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface TablePaginationProps {
  currentPage: number
  pageCount: number
  pageSize: number
  filteredCount: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

const PAGE_SIZES = [25, 50, 100, 250, -1] as const

export function TablePagination({
  currentPage,
  pageCount,
  pageSize,
  filteredCount,
  onPageChange,
  onPageSizeChange,
}: TablePaginationProps) {
  const start = pageSize === -1 ? 1 : currentPage * pageSize + 1
  const end = pageSize === -1 ? filteredCount : Math.min((currentPage + 1) * pageSize, filteredCount)

  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-1.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Rows per page</span>
        <Select
          value={String(pageSize)}
          onValueChange={(v) => onPageSizeChange(Number(v))}
        >
          <SelectTrigger className="h-7 w-[70px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size === -1 ? "All" : size}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="text-xs text-muted-foreground">
        {filteredCount > 0
          ? `Showing ${start}-${end} of ${filteredCount}`
          : "No results"}
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(0)}
          disabled={currentPage === 0}
        >
          <ChevronsLeft className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 0}
        >
          <ChevronLeft className="size-3.5" />
        </Button>

        <span className="mx-2 text-xs text-muted-foreground">
          {pageCount > 0 ? `${currentPage + 1} / ${pageCount}` : "—"}
        </span>

        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= pageCount - 1}
        >
          <ChevronRight className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(pageCount - 1)}
          disabled={currentPage >= pageCount - 1}
        >
          <ChevronsRight className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}
