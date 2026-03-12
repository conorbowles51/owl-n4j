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

const CHART_COLORS = [
  "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]

interface FinancialChartsProps {
  transactions: Transaction[]
  categories: FinancialCategory[]
}

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(0)}`
}

type Grouping = "daily" | "weekly" | "monthly"

function detectGrouping(transactions: Transaction[]): Grouping {
  if (transactions.length < 2) return "daily"
  const dates = transactions.map((t) => new Date(t.date).getTime()).sort((a, b) => a - b)
  const span = (dates[dates.length - 1] - dates[0]) / (1000 * 60 * 60 * 24)
  if (span > 60) return "monthly"
  if (span > 14) return "weekly"
  return "daily"
}

function getGroupKey(date: Date, grouping: Grouping): string {
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
}: FinancialChartsProps) {
  const categoryColorMap = useMemo(
    () => new Map(categories.map((c) => [c.name, c.color])),
    [categories]
  )

  const grouping = useMemo(() => detectGrouping(transactions), [transactions])

  // Stacked bar chart data: volume by period by category
  const volumeData = useMemo(() => {
    const groups = new Map<string, Record<string, number>>()
    const allCats = new Set<string>()

    for (const tx of transactions) {
      const key = getGroupKey(new Date(tx.date), grouping)
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
  }, [transactions, grouping])

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

  if (transactions.length === 0) return null

  return (
    <div className="grid grid-cols-2 gap-4 border-b border-border px-4 py-3">
      {/* Volume Over Time */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs">
            Volume Over Time ({grouping})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={volumeData.data}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="period"
                tick={{ fontSize: 9 }}
                stroke="hsl(var(--muted-foreground))"
              />
              <YAxis
                tick={{ fontSize: 9 }}
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
                formatter={(value: number) => formatCurrency(value)}
              />
              <Legend wrapperStyle={{ fontSize: 9 }} />
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
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Category Distribution */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs">Category Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
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
