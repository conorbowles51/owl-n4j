import { useMemo } from "react"
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import type { Transaction, FinancialCategory } from "../api"
import {
  getFinancialDateTimestamp,
  isValidFinancialDate,
  parseFinancialDate,
} from "../lib/date-utils"

const CHART_COLORS = [
  "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]

export type FinancialChartGrouping = "daily" | "weekly" | "monthly"

interface FinancialChartsProps {
  transactions: Transaction[]
  categories: FinancialCategory[]
  groupingOverride?: "auto" | FinancialChartGrouping
}

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(0)}`
}

function detectGrouping(transactions: Transaction[]): FinancialChartGrouping {
  const dates = transactions
    .map((t) => getFinancialDateTimestamp(t.date))
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b)
  if (dates.length < 2) return "daily"
  const span = (dates[dates.length - 1] - dates[0]) / (1000 * 60 * 60 * 24)
  if (span > 60) return "monthly"
  if (span > 14) return "weekly"
  return "daily"
}

function getGroupKey(date: Date, grouping: FinancialChartGrouping): string {
  if (grouping === "monthly") {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
  }
  if (grouping === "weekly") {
    const d = new Date(date)
    d.setDate(d.getDate() - d.getDay())
    return d.toISOString().slice(0, 10)
  }
  return date.toISOString().slice(0, 10)
}

export function FinancialCharts({
  transactions,
  categories,
  groupingOverride = "auto",
}: FinancialChartsProps) {
  const datedTransactions = useMemo(
    () => transactions.filter((tx) => isValidFinancialDate(tx.date)),
    [transactions]
  )

  const categoryColorMap = useMemo(
    () => new Map(categories.map((c) => [c.name, c.color])),
    [categories]
  )

  const grouping = useMemo(() => {
    if (groupingOverride !== "auto") {
      return groupingOverride
    }
    return detectGrouping(datedTransactions)
  }, [datedTransactions, groupingOverride])

  // Stacked bar chart data: volume by period by category
  const volumeData = useMemo(() => {
    const groups = new Map<string, Record<string, number>>()
    const allCats = new Set<string>()

    for (const tx of datedTransactions) {
      const parsedDate = parseFinancialDate(tx.date)
      if (!parsedDate) continue
      const key = getGroupKey(parsedDate, grouping)
      if (!groups.has(key)) groups.set(key, {})
      const group = groups.get(key)!
      const cat = tx.category || "Uncategorized"
      allCats.add(cat)
      group[cat] = (group[cat] || 0) + Math.abs(tx.amount)
    }

    const sorted = Array.from(groups.entries()).sort(([a], [b]) =>
      a.localeCompare(b)
    )

    return {
      data: sorted.map(([period, vals]) => ({ period, ...vals })),
      categories: Array.from(allCats),
    }
  }, [datedTransactions, grouping])

  // Donut chart data: count by category
  const categoryData = useMemo(() => {
    const counts = new Map<string, number>()
    for (const tx of transactions) {
      const cat = tx.category || "Uncategorized"
      counts.set(cat, (counts.get(cat) || 0) + 1)
    }
    return Array.from(counts.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
  }, [transactions])

  const chartWidth = useMemo(
    () => Math.max(900, volumeData.data.length * 72),
    [volumeData.data.length]
  )

  if (transactions.length === 0) return null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs">
            Volume Over Time ({grouping})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {volumeData.data.length > 0 ? (
            <div className="overflow-x-auto pb-2">
              <BarChart width={chartWidth} height={340} data={volumeData.data}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 10 }}
                  stroke="hsl(var(--muted-foreground))"
                />
                <YAxis
                  tick={{ fontSize: 10 }}
                  stroke="hsl(var(--muted-foreground))"
                  tickFormatter={formatCurrency}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: 11,
                  }}
                  formatter={(value) =>
                    formatCurrency(
                      typeof value === "number" ? value : Number(value) || 0
                    )
                  }
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {volumeData.categories.map((cat, i) => (
                  <Bar
                    key={cat}
                    dataKey={cat}
                    stackId="volume"
                    fill={
                      categoryColorMap.get(cat) ||
                      CHART_COLORS[i % CHART_COLORS.length]
                    }
                  />
                ))}
              </BarChart>
            </div>
          ) : (
            <div className="flex h-[340px] items-center justify-center text-center text-xs text-muted-foreground">
              No valid dated transactions available for the time chart.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs">Category Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={categoryData}
                cx="50%"
                cy="50%"
                innerRadius={45}
                outerRadius={75}
                paddingAngle={2}
                dataKey="value"
              >
                {categoryData.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={
                      categoryColorMap.get(entry.name) ||
                      CHART_COLORS[i % CHART_COLORS.length]
                    }
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  fontSize: 11,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          {/* Legend below chart */}
          <div className="mt-2 flex flex-wrap gap-2">
            {categoryData.map((entry, i) => (
              <div key={entry.name} className="flex items-center gap-1">
                <div
                  className="size-2 rounded-full"
                  style={{
                    backgroundColor:
                      categoryColorMap.get(entry.name) ||
                      CHART_COLORS[i % CHART_COLORS.length],
                  }}
                />
                <span className="text-[10px] text-muted-foreground">
                  {entry.name} ({entry.value})
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
