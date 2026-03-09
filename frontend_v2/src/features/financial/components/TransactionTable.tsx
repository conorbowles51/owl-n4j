import { useState, useMemo } from "react"
import { ArrowUpDown, Edit2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { CostBadge } from "@/components/ui/cost-badge"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import type { Transaction } from "../api"

interface TransactionTableProps {
  transactions: Transaction[]
  selectedKeys: Set<string>
  onToggleSelect: (key: string) => void
  onSelectAll: () => void
  onClearSelection: () => void
  onEditCategory: (transaction: Transaction) => void
  onRowClick?: (transaction: Transaction) => void
}

export function TransactionTable({
  transactions,
  selectedKeys,
  onToggleSelect,
  onSelectAll,
  onClearSelection,
  onEditCategory,
  onRowClick,
}: TransactionTableProps) {
  const [sortKey, setSortKey] = useState<"date" | "amount">("date")
  const [sortAsc, setSortAsc] = useState(false)

  const sorted = useMemo(() => {
    const copy = [...transactions]
    copy.sort((a, b) => {
      if (sortKey === "date") {
        const cmp = new Date(a.date).getTime() - new Date(b.date).getTime()
        return sortAsc ? cmp : -cmp
      }
      const cmp = a.amount - b.amount
      return sortAsc ? cmp : -cmp
    })
    return copy
  }, [transactions, sortKey, sortAsc])

  const toggleSort = (key: "date" | "amount") => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(true) }
  }

  const columns: DataTableColumn<Transaction>[] = [
    {
      key: "select",
      header: (
        <input
          type="checkbox"
          checked={selectedKeys.size === transactions.length && transactions.length > 0}
          onChange={() =>
            selectedKeys.size === transactions.length
              ? onClearSelection()
              : onSelectAll()
          }
          className="rounded border-border"
        />
      ),
      cell: (row) => (
        <input
          type="checkbox"
          checked={selectedKeys.has(row.key)}
          onChange={(e) => { e.stopPropagation(); onToggleSelect(row.key) }}
          className="rounded border-border"
        />
      ),
      className: "w-8",
    },
    {
      key: "date",
      header: (
        <button className="flex items-center gap-1" onClick={() => toggleSort("date")}>
          Date <ArrowUpDown className="size-3" />
        </button>
      ),
      cell: (row) => (
        <span className="font-mono text-xs">
          {new Date(row.date).toLocaleDateString()}
        </span>
      ),
      sortable: true,
    },
    {
      key: "from",
      header: "From",
      cell: (row) => (
        <span className="max-w-[120px] truncate text-xs">{row.from_name || "—"}</span>
      ),
    },
    {
      key: "to",
      header: "To",
      cell: (row) => (
        <span className="max-w-[120px] truncate text-xs">{row.to_name || "—"}</span>
      ),
    },
    {
      key: "amount",
      header: (
        <button className="flex items-center gap-1" onClick={() => toggleSort("amount")}>
          Amount <ArrowUpDown className="size-3" />
        </button>
      ),
      cell: (row) => <CostBadge amount={row.amount} />,
      className: "text-right",
    },
    {
      key: "category",
      header: "Category",
      cell: (row) => (
        <div className="flex items-center gap-1">
          {row.category ? (
            <Badge variant="outline">{row.category}</Badge>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            className="opacity-0 group-hover:opacity-100"
            onClick={(e) => { e.stopPropagation(); onEditCategory(row) }}
          >
            <Edit2 className="size-3" />
          </Button>
        </div>
      ),
    },
    {
      key: "purpose",
      header: "Purpose",
      cell: (row) => (
        <span className="max-w-[160px] truncate text-xs text-muted-foreground">
          {row.purpose || "—"}
        </span>
      ),
    },
  ]

  return (
    <DataTable<Transaction>
      columns={columns}
      data={sorted}
      getRowKey={(row) => row.key}
      onRowClick={onRowClick}
      emptyMessage="No transactions found"
    />
  )
}
