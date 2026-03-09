import { useState } from "react"
import { useParams } from "react-router-dom"
import { DollarSign, Filter, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { CostBadge } from "@/components/ui/cost-badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

interface Transaction {
  key: string
  date: string
  amount: number
  from_name: string
  to_name: string
  category: string
  purpose: string
}

interface FinancialSummary {
  total_inflow: number
  total_outflow: number
  transaction_count: number
  unique_entities: number
}

function useFinancialData(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", caseId],
    queryFn: () =>
      fetchAPI<Transaction[]>(`/api/financial?case_id=${caseId}`),
    enabled: !!caseId,
  })
}

function useFinancialSummary(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", "summary", caseId],
    queryFn: () =>
      fetchAPI<FinancialSummary>(`/api/financial/summary?case_id=${caseId}`),
    enabled: !!caseId,
  })
}

export function FinancialPage() {
  const { id: caseId } = useParams()
  const { data: transactions, isLoading } = useFinancialData(caseId)
  const { data: summary } = useFinancialSummary(caseId)
  const [search, setSearch] = useState("")

  const filtered = transactions?.filter(
    (t) =>
      t.from_name?.toLowerCase().includes(search.toLowerCase()) ||
      t.to_name?.toLowerCase().includes(search.toLowerCase()) ||
      t.purpose?.toLowerCase().includes(search.toLowerCase())
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!transactions?.length) {
    return (
      <EmptyState
        icon={DollarSign}
        title="No financial data"
        description="Process evidence with financial information to populate this view"
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-4 gap-3 border-b border-border p-4">
          <Card className="p-3">
            <CardHeader className="p-0">
              <CardTitle className="text-xs text-muted-foreground">
                Total Inflow
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 pt-1">
              <CostBadge amount={summary.total_inflow} />
            </CardContent>
          </Card>
          <Card className="p-3">
            <CardHeader className="p-0">
              <CardTitle className="text-xs text-muted-foreground">
                Total Outflow
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 pt-1">
              <CostBadge amount={summary.total_outflow} />
            </CardContent>
          </Card>
          <Card className="p-3">
            <CardHeader className="p-0">
              <CardTitle className="text-xs text-muted-foreground">
                Transactions
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 pt-1">
              <span className="font-mono text-sm font-semibold">
                {summary.transaction_count}
              </span>
            </CardContent>
          </Card>
          <Card className="p-3">
            <CardHeader className="p-0">
              <CardTitle className="text-xs text-muted-foreground">
                Entities
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 pt-1">
              <span className="font-mono text-sm font-semibold">
                {summary.unique_entities}
              </span>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Input
          placeholder="Filter transactions..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
        </Button>
        <div className="flex-1" />
        <Badge variant="slate">{filtered?.length ?? 0} transactions</Badge>
        <Button variant="outline" size="sm">
          <Download className="size-3.5" />
          Export
        </Button>
      </div>

      {/* Transaction table */}
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>From</TableHead>
              <TableHead>To</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Purpose</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered?.map((tx) => (
              <TableRow key={tx.key}>
                <TableCell className="font-mono text-xs">
                  {new Date(tx.date).toLocaleDateString()}
                </TableCell>
                <TableCell className="max-w-[150px] truncate text-sm">
                  {tx.from_name || "—"}
                </TableCell>
                <TableCell className="max-w-[150px] truncate text-sm">
                  {tx.to_name || "—"}
                </TableCell>
                <TableCell className="text-right">
                  <CostBadge amount={tx.amount} />
                </TableCell>
                <TableCell>
                  {tx.category && (
                    <Badge variant="outline">{tx.category}</Badge>
                  )}
                </TableCell>
                <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                  {tx.purpose || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
