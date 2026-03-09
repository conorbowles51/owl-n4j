import { DollarSign, TrendingUp } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CostBadge } from "@/components/ui/cost-badge"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

interface UsageEntry {
  date: string
  provider: string
  model: string
  requests: number
  cost: number
}

interface UsageSummary {
  total_cost: number
  total_requests: number
  by_provider: Record<string, { cost: number; requests: number }>
}

export function UsagePage() {
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["admin", "usage", "summary"],
    queryFn: () => fetchAPI<UsageSummary>("/api/admin/usage/summary"),
  })

  const { data: entries = [], isLoading: entriesLoading } = useQuery({
    queryKey: ["admin", "usage"],
    queryFn: () => fetchAPI<UsageEntry[]>("/api/admin/usage"),
  })

  if (summaryLoading || entriesLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <DollarSign className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Usage & Costs</span>
      </div>

      <div className="space-y-6 p-6">
        {/* Summary cards */}
        {summary && (
          <div className="grid grid-cols-3 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs text-muted-foreground">
                  Total Cost
                </CardTitle>
              </CardHeader>
              <CardContent>
                <CostBadge amount={summary.total_cost} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs text-muted-foreground">
                  Total Requests
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-2xl font-bold">
                  {summary.total_requests.toLocaleString()}
                </span>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs text-muted-foreground">
                  Providers
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(summary.by_provider).map(([name, data]) => (
                    <Badge key={name} variant="outline" className="text-[10px]">
                      {name}: <CostBadge amount={data.cost} />
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Usage entries */}
        {entries.length === 0 ? (
          <EmptyState
            icon={TrendingUp}
            title="No usage data"
            description="Usage tracking will appear here as the system is used"
          />
        ) : (
          <div className="rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">Date</th>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">Provider</th>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">Model</th>
                  <th className="px-3 py-2 text-right font-semibold text-muted-foreground">Requests</th>
                  <th className="px-3 py-2 text-right font-semibold text-muted-foreground">Cost</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, i) => (
                  <tr key={i} className="border-b border-border last:border-0 hover:bg-muted/30">
                    <td className="px-3 py-1.5 font-mono">{entry.date}</td>
                    <td className="px-3 py-1.5">{entry.provider}</td>
                    <td className="px-3 py-1.5">{entry.model}</td>
                    <td className="px-3 py-1.5 text-right">{entry.requests}</td>
                    <td className="px-3 py-1.5 text-right">
                      <CostBadge amount={entry.cost} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
