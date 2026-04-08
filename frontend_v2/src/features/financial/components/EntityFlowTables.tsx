import { useMemo, useState } from "react"
import { ArrowLeftRight, Search, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"
import type { EntityFlowRow } from "../lib/filter-transactions"

interface EntityFlowTablesProps {
  senders: EntityFlowRow[]
  beneficiaries: EntityFlowRow[]
  selectedSenders: Set<string>
  selectedBeneficiaries: Set<string>
  onSelectedSendersChange: (value: Set<string>) => void
  onSelectedBeneficiariesChange: (value: Set<string>) => void
  className?: string
}

type SortField = "amount" | "count" | "name"

function formatCompactCurrency(value: number) {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(0)}`
}

function toggleSelection(setter: (value: Set<string>) => void, current: Set<string>, key: string) {
  const next = new Set(current)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  setter(next)
}

function EntityFlowTable({
  title,
  rows,
  selected,
  onSelectedChange,
  emptyLabel,
}: {
  title: string
  rows: EntityFlowRow[]
  selected: Set<string>
  onSelectedChange: (value: Set<string>) => void
  emptyLabel: string
}) {
  const [search, setSearch] = useState("")
  const [sortField, setSortField] = useState<SortField>("amount")
  const [sortDesc, setSortDesc] = useState(true)

  const filteredRows = useMemo(() => {
    const normalized = search.trim().toLowerCase()
    const list = normalized
      ? rows.filter((row) => row.name.toLowerCase().includes(normalized))
      : rows

    return [...list].sort((a, b) => {
      let cmp = 0
      if (sortField === "name") cmp = a.name.localeCompare(b.name)
      if (sortField === "count") cmp = a.count - b.count
      if (sortField === "amount") cmp = a.totalAmount - b.totalAmount
      return sortDesc ? -cmp : cmp
    })
  }, [rows, search, sortField, sortDesc])

  const updateSort = (field: SortField) => {
    if (sortField === field) {
      setSortDesc((value) => !value)
      return
    }
    setSortField(field)
    setSortDesc(field !== "name")
  }

  return (
    <Card className="flex min-h-0 flex-col">
      <CardHeader className="border-b border-border/60 pb-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="text-sm">{title}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {rows.length} entities
            </p>
          </div>
          {selected.size > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => onSelectedChange(new Set())}
            >
              <X className="size-3.5" />
              Clear {selected.size}
            </Button>
          )}
        </div>
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={`Search ${title.toLowerCase()}...`}
          className="mt-3 h-8 text-xs"
        />
        <div className="mt-3 grid grid-cols-[1fr_auto_auto] gap-2 text-[11px] text-muted-foreground">
          <button className="text-left hover:text-foreground" onClick={() => updateSort("name")}>
            Name
          </button>
          <button className="text-right hover:text-foreground" onClick={() => updateSort("count")}>
            Txns
          </button>
          <button className="text-right hover:text-foreground" onClick={() => updateSort("amount")}>
            Amount
          </button>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        {selected.size > 0 && (
          <div className="flex flex-wrap gap-1 border-b border-border/60 px-4 py-2">
            {[...selected].map((key) => {
              const row = rows.find((entry) => entry.key === key)
              const label = row?.name || key
              return (
                <Badge
                  key={key}
                  variant="outline"
                  className="cursor-pointer gap-1 text-[11px]"
                  onClick={() => toggleSelection(onSelectedChange, selected, key)}
                >
                  {label}
                  <X className="size-3" />
                </Badge>
              )
            })}
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-auto">
          {filteredRows.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-muted-foreground">
              {emptyLabel}
            </div>
          ) : (
            filteredRows.map((row) => {
              const active = selected.has(row.key)
              return (
                <button
                  key={row.key}
                  className={`grid w-full grid-cols-[1fr_auto_auto] gap-2 border-b border-border/40 px-4 py-2 text-left transition hover:bg-muted/50 ${
                    active ? "bg-amber-500/10" : ""
                  }`}
                  onClick={() => toggleSelection(onSelectedChange, selected, row.key)}
                >
                  <span className="truncate text-xs font-medium">{row.name}</span>
                  <span className="text-right font-mono text-[11px] text-muted-foreground">
                    {row.count}
                  </span>
                  <span className="text-right font-mono text-[11px]">
                    {formatCompactCurrency(row.totalAmount)}
                  </span>
                </button>
              )
            })
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function EntityFlowTables({
  senders,
  beneficiaries,
  selectedSenders,
  selectedBeneficiaries,
  onSelectedSendersChange,
  onSelectedBeneficiariesChange,
  className,
}: EntityFlowTablesProps) {
  const hasSelections = selectedSenders.size > 0 || selectedBeneficiaries.size > 0

  return (
    <div className={cn("flex h-full min-h-0 flex-col space-y-4", className)}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Sender / Beneficiary Analysis</h2>
          <p className="text-xs text-muted-foreground">
            Cross-filter the visible financial records by directional counterparties.
          </p>
        </div>
        {hasSelections ? (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              onSelectedSendersChange(new Set())
              onSelectedBeneficiariesChange(new Set())
            }}
          >
            <X className="size-3.5" />
            Clear analysis filters
          </Button>
        ) : (
          <Badge variant="outline" className="gap-1 text-[11px]">
            <Search className="size-3" />
            Optional analysis filters
          </Badge>
        )}
      </div>

      {hasSelections && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-muted-foreground">
          <ArrowLeftRight className="size-3.5 text-amber-600" />
          Sender and beneficiary selections are filtering the summary, charts, table, and export.
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <EntityFlowTable
          title="Senders"
          rows={senders}
          selected={selectedSenders}
          onSelectedChange={onSelectedSendersChange}
          emptyLabel="No sender matches for the current filters."
        />
        <EntityFlowTable
          title="Beneficiaries"
          rows={beneficiaries}
          selected={selectedBeneficiaries}
          onSelectedChange={onSelectedBeneficiariesChange}
          emptyLabel="No beneficiary matches for the current filters."
        />
      </div>
    </div>
  )
}
