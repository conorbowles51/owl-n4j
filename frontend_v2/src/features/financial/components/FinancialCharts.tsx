import { useMemo, useState } from "react"
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
import { evidenceAmountCents, evidenceCurrency } from "../lib/evidence-amounts"
import type { Transaction, FinancialCategory } from "../api"
import {
  getFinancialDateTimestamp,
  isValidFinancialDate,
} from "../lib/date-utils"

const CHART_COLORS = [
  "#b41624",
  "#5571c8",
  "#2c8197",
  "#c25778",
  "#8060a9",
  "#bc4e78",
  "#26869e",
  "#6f8b45",
  "#c4653f",
  "#655fc0",
]

import {
  buildEvidenceVolumeData,
  type FinancialChartGrouping,
} from "../lib/evidence-chart-data"
export type { FinancialChartGrouping } from "../lib/evidence-chart-data"

interface FinancialChartsProps {
  transactions: Transaction[]
  categories: FinancialCategory[]
  groupingOverride?: "auto" | FinancialChartGrouping
}

function formatCurrency(value: number, currency: string): string {
  return `${value.toLocaleString("en-IE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
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

function CurrencyFinancialCharts({
  currency,
  transactions,
  categories,
  groupingOverride = "auto",
}: FinancialChartsProps & { currency: string }) {
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

  const volumeData = useMemo(
    () => buildEvidenceVolumeData(datedTransactions, grouping),
    [datedTransactions, grouping]
  )

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
            Recorded amount sizes by date ({currency}, {grouping})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {volumeData.tooLarge ? (
            <p className="text-sm">
              These totals are too large to plot accurately. Use the record list
              or download the report.
            </p>
          ) : volumeData.data.length > 0 ? (
            <div className="overflow-x-auto pb-2">
              <BarChart width={chartWidth} height={340} data={volumeData.data}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 10 }}
                  stroke="hsl(var(--muted-foreground))"
                />
                <YAxis
                  width={75}
                  tick={{ fontSize: 10 }}
                  stroke="hsl(var(--muted-foreground))"
                  tickFormatter={(value: number) =>
                    value.toLocaleString("en-IE", {
                      notation:
                        Math.abs(value) >= 1000000 ? "compact" : "standard",
                      maximumFractionDigits: 2,
                    })
                  }
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
                      typeof value === "number" ? value : Number(value) || 0,
                      currency
                    )
                  }
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {volumeData.categories.map((cat, i) => (
                  <Bar
                    key={cat}
                    dataKey={`category_${i}`}
                    name={cat}
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
              No records with valid dates are available for this chart.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs">
            Records by category ({currency})
          </CardTitle>
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

export function FinancialCharts(props: FinancialChartsProps) {
  const [choice, setChoice] = useState("")
  const currencies = [
    ...new Set(
      props.transactions
        .map((row) => evidenceCurrency(row.currency))
        .filter((currency): currency is string => currency !== null)
    ),
  ].sort()
  const active = currencies.includes(choice) ? choice : currencies[0]
  const available = props.transactions.filter(
    (row) =>
      evidenceCurrency(row.currency) === active &&
      evidenceAmountCents(row.amount) !== null
  )
  const excluded = props.transactions.filter(
    (row) =>
      evidenceCurrency(row.currency) === null ||
      evidenceAmountCents(row.amount) === null
  ).length
  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        Chart currency
        <select
          aria-label="Chart currency"
          value={active || ""}
          disabled={!currencies.length}
          onChange={(event) => setChoice(event.target.value)}
          className="rounded border p-2"
        >
          {!currencies.length && <option value="">No recorded currency</option>}
          {currencies.map((currency) => (
            <option key={currency}>{currency}</option>
          ))}
        </select>
      </label>
      <p className="text-sm">
        {available.length} {available.length === 1 ? "record" : "records"} in{" "}
        {active || "a recorded currency"}. The date chart adds amount sizes, so
        -150 contributes 150. It does not show an account balance or establish
        money paid in or out.
      </p>
      {excluded > 0 && (
        <p className="text-sm">
          {excluded}{" "}
          {excluded === 1
            ? "record has a missing currency or an amount"
            : "records have missing currencies or amounts"}{" "}
          that cannot be plotted exactly. They remain in Transactions.
        </p>
      )}
      {active && (
        <CurrencyFinancialCharts
          {...props}
          transactions={available}
          currency={active}
        />
      )}
    </div>
  )
}
