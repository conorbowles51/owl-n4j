import { useCallback } from "react"
import {
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  ChevronUp,
  Edit2,
  MoreHorizontal,
  AlertCircle,
  Link,
  Unlink,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { CostBadge } from "@/components/ui/cost-badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useFinancialStore } from "../stores/financial.store"
import { TransactionDetailPanel } from "./TransactionDetailPanel"
import type { Transaction, FinancialCategory } from "../api"
import type { SortColumn } from "../stores/financial.store"
import { formatFinancialDate } from "../lib/date-utils"

interface TransactionTableProps {
  transactions: Transaction[]
  allTransactions: Transaction[]
  categories: FinancialCategory[]
  sortColumns: SortColumn[]
  onCategorize: (nodeKey: string, category: string) => void
  onAmountClick: (transaction: Transaction) => void
  onEntityEdit: (transaction: Transaction, field: "from" | "to") => void
  onGroupSubTransactions: (transaction: Transaction) => void
  onRemoveFromGroup: (transaction: Transaction) => void
  onSaveDetails: (
    nodeKey: string,
    fields: { purpose?: string; counterpartyDetails?: string; notes?: string }
  ) => void
}

export function TransactionTable({
  transactions,
  allTransactions,
  categories,
  sortColumns,
  onCategorize,
  onAmountClick,
  onEntityEdit,
  onGroupSubTransactions,
  onRemoveFromGroup,
  onSaveDetails,
}: TransactionTableProps) {
  const {
    checkedKeys,
    toggleChecked,
    checkRange,
    clearChecked,
    setCheckedKeys,
    lastClickedKey,
    setLastClickedKey,
    expandedRowKeys,
    toggleExpandedRow,
    toggleSort,
  } = useFinancialStore()

  const handleRowCheckbox = useCallback(
    (key: string, e: React.MouseEvent) => {
      if (e.shiftKey && lastClickedKey) {
        const allKeys = transactions.map((t) => t.key)
        const lastIdx = allKeys.indexOf(lastClickedKey)
        const curIdx = allKeys.indexOf(key)
        if (lastIdx >= 0 && curIdx >= 0) {
          const start = Math.min(lastIdx, curIdx)
          const end = Math.max(lastIdx, curIdx)
          checkRange(allKeys.slice(start, end + 1))
          setLastClickedKey(key)
          return
        }
      }
      toggleChecked(key)
      setLastClickedKey(key)
    },
    [lastClickedKey, transactions, toggleChecked, checkRange, setLastClickedKey]
  )

  const allChecked =
    transactions.length > 0 && checkedKeys.size === transactions.length

  const handleSelectAll = () => {
    if (allChecked) clearChecked()
    else setCheckedKeys(new Set(transactions.map((t) => t.key)))
  }

  const handleSort = (key: string, e: React.MouseEvent) => {
    toggleSort(key, e.shiftKey)
  }

  const getSortInfo = (key: string) => {
    const idx = sortColumns.findIndex((c) => c.key === key)
    if (idx < 0) return null
    return { asc: sortColumns[idx].asc, index: sortColumns.length > 1 ? idx + 1 : null }
  }

  const renderSortIcon = (key: string) => {
    const info = getSortInfo(key)
    if (!info) return <ChevronsUpDown className="size-3 text-muted-foreground" />
    return (
      <span className="inline-flex items-center gap-0.5">
        {info.asc ? (
          <ChevronUp className="size-3" />
        ) : (
          <ChevronDown className="size-3" />
        )}
        {info.index && (
          <span className="text-[9px] text-muted-foreground">{info.index}</span>
        )}
      </span>
    )
  }

  // Group parent/children: children appear right after their parent
  const displayRows: Array<{ tx: Transaction; indent: boolean }> = []
  const childKeys = new Set<string>()
  for (const tx of transactions) {
    if (tx.parent_transaction_key) childKeys.add(tx.key)
  }
  for (const tx of transactions) {
    if (childKeys.has(tx.key)) continue
    displayRows.push({ tx, indent: false })
    if (tx.is_parent && expandedRowKeys.has(tx.key)) {
      const children = allTransactions.filter(
        (c) => c.parent_transaction_key === tx.key
      )
      for (const child of children) {
        displayRows.push({ tx: child, indent: true })
      }
    }
  }

  return (
    <div className="overflow-auto">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-8">
              <Checkbox
                checked={allChecked}
                onCheckedChange={handleSelectAll}
              />
            </TableHead>
            <TableHead className="w-8" />
            <TableHead className="w-24">
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("date", e)}
              >
                Date {renderSortIcon("date")}
              </button>
            </TableHead>
            <TableHead className="w-16">
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("name", e)}
              >
                Name {renderSortIcon("name")}
              </button>
            </TableHead>
            <TableHead>
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("from", e)}
              >
                Sender {renderSortIcon("from")}
              </button>
            </TableHead>
            <TableHead />
            <TableHead>
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("to", e)}
              >
                Receiver {renderSortIcon("to")}
              </button>
            </TableHead>
            <TableHead className="text-right">
              <button
                className="ml-auto flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("amount", e)}
              >
                Amount {renderSortIcon("amount")}
              </button>
            </TableHead>
            <TableHead>
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("type", e)}
              >
                Type {renderSortIcon("type")}
              </button>
            </TableHead>
            <TableHead>
              <button
                className="flex items-center gap-1 text-xs"
                onClick={(e) => handleSort("category", e)}
              >
                Category {renderSortIcon("category")}
              </button>
            </TableHead>
            <TableHead className="w-8" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {displayRows.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={11}
                className="h-24 text-center text-sm text-muted-foreground"
              >
                No transactions found
              </TableCell>
            </TableRow>
          ) : (
            displayRows.map(({ tx, indent }) => {
              const isChecked = checkedKeys.has(tx.key)
              const isExpanded = expandedRowKeys.has(tx.key)
              const categoryColor = categories.find(
                (c) => c.name === tx.category
              )?.color

              return (
                <TransactionRow
                  key={tx.key}
                  tx={tx}
                  indent={indent}
                  isChecked={isChecked}
                  isExpanded={isExpanded}
                  categoryColor={categoryColor}
                  categories={categories}
                  onCheckbox={handleRowCheckbox}
                  onToggleExpand={() => toggleExpandedRow(tx.key)}
                  onCategorize={onCategorize}
                  onAmountClick={onAmountClick}
                  onEntityEdit={onEntityEdit}
                  onGroupSubTransactions={onGroupSubTransactions}
                  onRemoveFromGroup={onRemoveFromGroup}
                  onSaveDetails={onSaveDetails}
                />
              )
            })
          )}
        </TableBody>
      </Table>
    </div>
  )
}

interface TransactionRowProps {
  tx: Transaction
  indent: boolean
  isChecked: boolean
  isExpanded: boolean
  categoryColor?: string
  categories: FinancialCategory[]
  onCheckbox: (key: string, e: React.MouseEvent) => void
  onToggleExpand: () => void
  onCategorize: (nodeKey: string, category: string) => void
  onAmountClick: (tx: Transaction) => void
  onEntityEdit: (tx: Transaction, field: "from" | "to") => void
  onGroupSubTransactions: (tx: Transaction) => void
  onRemoveFromGroup: (tx: Transaction) => void
  onSaveDetails: (
    nodeKey: string,
    fields: { purpose?: string; counterpartyDetails?: string; notes?: string }
  ) => void
}

function TransactionRow({
  tx,
  indent,
  isChecked,
  isExpanded,
  categoryColor,
  categories,
  onCheckbox,
  onToggleExpand,
  onCategorize,
  onAmountClick,
  onEntityEdit,
  onGroupSubTransactions,
  onRemoveFromGroup,
  onSaveDetails,
}: TransactionRowProps) {
  return (
    <>
      <TableRow
        className={`group h-9 ${
          isChecked ? "bg-amber-500/10 border-l-2 border-l-amber-500" : ""
        } ${indent ? "bg-muted/20" : ""}`}
      >
        {/* Checkbox */}
        <TableCell className="py-1.5">
          <Checkbox
            checked={isChecked}
            onClick={(e) => {
              e.stopPropagation()
              onCheckbox(tx.key, e as unknown as React.MouseEvent)
            }}
          />
        </TableCell>

        {/* Expand */}
        <TableCell className="py-1.5">
          <button onClick={onToggleExpand} className="text-muted-foreground hover:text-foreground">
            {isExpanded ? (
              <ChevronDown className="size-3.5" />
            ) : (
              <ChevronRight className="size-3.5" />
            )}
          </button>
        </TableCell>

        {/* Date */}
        <TableCell className="py-1.5">
          <span className="font-mono text-[11px]">
            {indent && <span className="mr-1 text-muted-foreground">└</span>}
            {formatFinancialDate(tx.date)}
          </span>
          {tx.time && (
            <span className="ml-1 text-[10px] text-muted-foreground">
              {tx.time}
            </span>
          )}
        </TableCell>

        {/* Name */}
        <TableCell className="py-1.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="max-w-[120px] truncate text-xs block">
                {tx.name || "—"}
              </span>
            </TooltipTrigger>
            {tx.name && <TooltipContent>{tx.name}</TooltipContent>}
          </Tooltip>
        </TableCell>

        {/* From */}
        <TableCell className="py-1.5">
          <div className="group/from flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="max-w-[120px] truncate text-xs block">
                  {tx.from_entity?.name || "—"}
                </span>
              </TooltipTrigger>
              {tx.from_entity?.name && (
                <TooltipContent>{tx.from_entity.name}</TooltipContent>
              )}
            </Tooltip>
            {tx.has_manual_from && (
              <span className="text-[8px] text-amber-500" title="Manually set">
                M
              </span>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-5 opacity-0 group-hover/from:opacity-100"
              onClick={() => onEntityEdit(tx, "from")}
            >
              <Edit2 className="size-2.5" />
            </Button>
          </div>
        </TableCell>

        {/* Arrow */}
        <TableCell className="py-1.5 text-center text-muted-foreground">
          →
        </TableCell>

        {/* To */}
        <TableCell className="py-1.5">
          <div className="group/to flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="max-w-[120px] truncate text-xs block">
                  {tx.to_entity?.name || "—"}
                </span>
              </TooltipTrigger>
              {tx.to_entity?.name && (
                <TooltipContent>{tx.to_entity.name}</TooltipContent>
              )}
            </Tooltip>
            {tx.has_manual_to && (
              <span className="text-[8px] text-amber-500" title="Manually set">
                M
              </span>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-5 opacity-0 group-hover/to:opacity-100"
              onClick={() => onEntityEdit(tx, "to")}
            >
              <Edit2 className="size-2.5" />
            </Button>
          </div>
        </TableCell>

        {/* Amount */}
        <TableCell className="py-1.5 text-right">
          <button
            className="inline-flex items-center gap-1 hover:underline"
            onClick={() => onAmountClick(tx)}
          >
            <CostBadge amount={tx.amount} />
            {tx.amount_corrected && (
              <Tooltip>
                <TooltipTrigger>
                  <AlertCircle className="size-3 text-amber-500" />
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">
                    Corrected from{" "}
                    {tx.original_amount?.toLocaleString("en-US", {
                      style: "currency",
                      currency: tx.currency || "USD",
                    })}
                  </p>
                  {tx.correction_reason && (
                    <p className="text-[10px] text-muted-foreground">
                      {tx.correction_reason}
                    </p>
                  )}
                </TooltipContent>
              </Tooltip>
            )}
          </button>
        </TableCell>

        {/* Type */}
        <TableCell className="py-1.5">
          {tx.type && (
            <Badge variant="outline" className="text-[10px]">
              {tx.type}
            </Badge>
          )}
        </TableCell>

        {/* Category */}
        <TableCell className="py-1.5">
          <Select
            value={tx.category || ""}
            onValueChange={(val) => onCategorize(tx.key, val)}
          >
            <SelectTrigger className="h-6 w-28 text-[10px] border-none bg-transparent hover:bg-muted">
              <div className="flex items-center gap-1.5">
                {categoryColor && (
                  <div
                    className="size-2 rounded-full"
                    style={{ backgroundColor: categoryColor }}
                  />
                )}
                <SelectValue placeholder="—" />
              </div>
            </SelectTrigger>
            <SelectContent>
              {categories.map((cat) => (
                <SelectItem key={cat.name} value={cat.name}>
                  <div className="flex items-center gap-2">
                    <div
                      className="size-2 rounded-full"
                      style={{ backgroundColor: cat.color }}
                    />
                    {cat.name}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TableCell>

        {/* Actions */}
        <TableCell className="py-1.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="size-6 opacity-0 group-hover:opacity-100"
              >
                <MoreHorizontal className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onGroupSubTransactions(tx)}>
                <Link className="size-3.5 mr-2" />
                Group Sub-Transactions
              </DropdownMenuItem>
              {tx.parent_transaction_key && (
                <DropdownMenuItem onClick={() => onRemoveFromGroup(tx)}>
                  <Unlink className="size-3.5 mr-2" />
                  Remove from Group
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </TableCell>
      </TableRow>

      {/* Expanded detail panel */}
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={11} className="p-0">
            <TransactionDetailPanel
              transaction={tx}
              onSave={(fields) => onSaveDetails(tx.key, fields)}
            />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
