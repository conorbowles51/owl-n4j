import { useState } from "react"
import type { LedgerTransaction } from "../api"
import { chartRatio, paymentGroup } from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import {
  activitySeries,
  amountGroupName,
  filterAnalysis,
  type AnalysisFilters,
} from "../lib/transaction-analysis"

const CATEGORY_PAGE_SIZE = 8
const MONTH_PAGE_SIZE = 12
const shortMonth = (value: string) =>
  `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(value.slice(5, 7)) - 1]} ${value.slice(2, 4)}`
const point = (radius: number, angle: number) =>
  `${70 + radius * Math.cos(angle)},${70 + radius * Math.sin(angle)}`
function ringSlice(start: number, end: number) {
  // Two arcs per side also draw the one-category, full-circle case correctly.
  const middle = (start + end) / 2
  return `M${point(64, start)} A64,64 0 0 1 ${point(64, middle)} A64,64 0 0 1 ${point(64, end)} L${point(43, end)} A43,43 0 0 0 ${point(43, middle)} A43,43 0 0 0 ${point(43, start)} Z`
}

export function TransactionFilterCharts({
  rows,
  filters,
  onChange,
}: {
  rows: LedgerTransaction[]
  filters: AnalysisFilters
  onChange: (value: Partial<AnalysisFilters>) => void
}) {
  const [categorySearch, setCategorySearch] = useState("")
  const [categoryPage, setCategoryPage] = useState(0)
  const [monthPage, setMonthPage] = useState(0)
  const counts = new Map<string, number>()
  rows.forEach((r) =>
    counts.set(paymentGroup(r), (counts.get(paymentGroup(r)) || 0) + 1)
  )
  const groups = [...counts]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([g]) => g)
  const group = groups.includes(filters.analysisGroup)
    ? filters.analysisGroup
    : groups[0] || ""
  const groupRows = rows.filter((r) => paymentGroup(r) === group)
  const money = (value: bigint) =>
    `${formatLedgerAmount(value.toString(), group.split(":")[0]).text} ${group.split(":")[0]}`
  // Each chart responds to the other chart's selection while retaining its own
  // alternatives, so choosing another month/category remains possible.
  const monthData = activitySeries(
    filterAnalysis(groupRows, {
      ...filters,
      analysisGroup: group,
      analysisPeriod: "",
      analysisDirection: "",
    })
  )
  const categoryData = activitySeries(
    filterAnalysis(groupRows, {
      ...filters,
      analysisGroup: group,
      analysisCategories: [],
    })
  )
  const matched = filterAnalysis(groupRows, {
    ...filters,
    analysisGroup: group,
  }).length
  const allCategories = [
    ...new Set(groupRows.map((r) => r.category || "Uncategorized")),
  ].sort()
  const color = (category: string) =>
    `hsl(${(allCategories.indexOf(category) * 137.508 + 160) % 360} 54% 43%)`
  const mi = Math.min(
    monthPage,
    Math.max(0, Math.ceil(monthData.months.length / MONTH_PAGE_SIZE) - 1)
  )
  const months = monthData.months.slice(
    mi * MONTH_PAGE_SIZE,
    (mi + 1) * MONTH_PAGE_SIZE
  )
  const maximum = months.reduce(
    (m, r) => (r.credit + r.debit > m ? r.credit + r.debit : m),
    0n
  )
  const categories = categoryData.categories.filter((c) =>
    c.category.toLowerCase().includes(categorySearch.toLowerCase())
  )
  const ci = Math.min(
    categoryPage,
    Math.max(0, Math.ceil(categories.length / CATEGORY_PAGE_SIZE) - 1)
  )
  const categoryVolume = categoryData.categories.reduce(
    (sum, c) => sum + c.credit + c.debit,
    0n
  )
  let angle = -Math.PI / 2
  const slices = categoryData.categories.map((c) => {
    const start = angle
    angle += chartRatio(c.credit + c.debit, categoryVolume) * Math.PI * 2
    return { ...c, start, end: angle }
  })
  const selectCategory = (category: string) =>
    onChange({
      analysisGroup: group,
      analysisCategories: filters.analysisCategories.includes(category)
        ? filters.analysisCategories.filter((c) => c !== category)
        : [...filters.analysisCategories, category],
    })
  const selectMonth = (
    month: string,
    direction: AnalysisFilters["analysisDirection"] = ""
  ) => {
    const selected =
      filters.analysisGroup === group &&
      filters.analysisPeriod === month &&
      filters.analysisDirection === direction
    onChange({
      analysisGroup: group,
      analysisPeriod: selected ? "" : month,
      analysisDirection: selected ? "" : direction,
    })
    setCategoryPage(0)
  }
  const directionName = (direction: "credit" | "debit") =>
    group.endsWith(":card")
      ? direction === "credit"
        ? "Card credits"
        : "Card charges"
      : direction === "credit"
        ? "Money in"
        : "Money out"
  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <label>
          Chart currency and account type{" "}
          <select
            aria-label="Chart currency and account type"
            className="ml-2 rounded border bg-background p-1"
            value={group}
            onChange={(e) => {
              onChange({
                analysisGroup: e.target.value,
                analysisPeriod: "",
                analysisDirection: "",
                analysisCategories: [],
              })
              setMonthPage(0)
              setCategoryPage(0)
              setCategorySearch("")
            }}
          >
            {groups.map((g) => (
              <option key={g} value={g}>
                {amountGroupName(g)}
              </option>
            ))}
          </select>
        </label>
        <span>
          {matched.toLocaleString()} matching transactions in this chart group.
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Click a coloured bar segment for its month and direction, a month label
        for both directions, or a category slice or list entry. Selections
        filter the totals, names, money flow and transactions below. Click again
        or remove a filter chip to clear a selection.
      </p>
      {!groupRows.length ? (
        <p>No transactions to chart.</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <section className="min-w-0" aria-label="Monthly transaction volume">
            <h4 className="text-sm font-medium">
              Monthly volume · {amountGroupName(group)}
            </h4>
            <p className="text-xs text-muted-foreground">
              Responds to selected categories.{" "}
              {maximum > 0n
                ? `Scale for displayed months: 0 to ${money(maximum)}.`
                : "No recorded volume in these months."}{" "}
              No currency conversion.
            </p>
            <div
              className="mt-2 flex gap-1 overflow-x-auto border-b pb-1"
              style={{ height: 194 }}
            >
              {months.map((m) => (
                <div
                  key={m.month}
                  className={`flex min-w-12 flex-1 flex-col justify-end rounded-t px-1 ${filters.analysisPeriod === m.month && filters.analysisGroup === group ? "bg-primary/10 ring-1 ring-inset ring-primary" : ""}`}
                >
                  <div
                    className="mx-auto flex w-full max-w-10 flex-col-reverse"
                    style={{
                      height: Math.max(
                        m.count ? 12 : 0,
                        chartRatio(m.credit + m.debit, maximum) * 140
                      ),
                    }}
                  >
                    {(["credit", "debit"] as const)
                      .filter((d) => m[d] > 0n)
                      .map((d) => {
                        const selected =
                          filters.analysisGroup === group &&
                          filters.analysisPeriod === m.month &&
                          filters.analysisDirection === d
                        return (
                          <button
                            key={d}
                            type="button"
                            aria-label={`${m.month}: ${directionName(d)} ${money(m[d])}`}
                            aria-pressed={selected}
                            title={`${m.month} · ${directionName(d)}: ${money(m[d])}. Click to filter.`}
                            className="w-full min-h-[6px] cursor-pointer border-0 p-0 transition-opacity hover:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                            style={{
                              height: `${chartRatio(m[d], m.credit + m.debit) * 100}%`,
                              background: `var(--finance-${d})`,
                              opacity:
                                filters.analysisDirection && !selected
                                  ? 0.4
                                  : 1,
                              boxShadow: selected
                                ? "inset 0 0 0 2px var(--foreground)"
                                : undefined,
                            }}
                            onClick={() => selectMonth(m.month, d)}
                          />
                        )
                      })}
                  </div>
                  <button
                    type="button"
                    className="mt-1 whitespace-nowrap rounded py-1 text-[11px] hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
                    aria-label={`${m.month}: ${m.count} transactions, credits ${money(m.credit)}, debits ${money(m.debit)}`}
                    aria-pressed={
                      filters.analysisPeriod === m.month &&
                      filters.analysisGroup === group &&
                      !filters.analysisDirection
                    }
                    onClick={() => selectMonth(m.month)}
                  >
                    {shortMonth(m.month)}
                  </button>
                </div>
              ))}
            </div>
            {monthData.months.length > MONTH_PAGE_SIZE && (
              <div
                className="mt-2 flex items-center justify-between gap-2 text-xs"
                aria-label="Month pages"
              >
                <button
                  className="rounded border px-2 py-1 disabled:opacity-40"
                  disabled={!mi}
                  onClick={() => setMonthPage(mi - 1)}
                >
                  Previous months
                </button>
                <span>
                  {months[0]?.month} to {months.at(-1)?.month} ·{" "}
                  {mi * MONTH_PAGE_SIZE + 1}–
                  {Math.min(
                    (mi + 1) * MONTH_PAGE_SIZE,
                    monthData.months.length
                  )}{" "}
                  of {monthData.months.length} months
                </span>
                <button
                  className="rounded border px-2 py-1 disabled:opacity-40"
                  disabled={
                    (mi + 1) * MONTH_PAGE_SIZE >= monthData.months.length
                  }
                  onClick={() => setMonthPage(mi + 1)}
                >
                  Next months
                </button>
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <span style={{ color: "var(--finance-credit)" }}>
                ● {directionName("credit")}
              </span>
              <span style={{ color: "var(--finance-debit)" }}>
                ● {directionName("debit")}
              </span>
              {monthData.undated > 0 && (
                <button
                  className="underline"
                  onClick={() =>
                    onChange({
                      analysisGroup: group,
                      analysisPeriod:
                        filters.analysisPeriod === "undated" ? "" : "undated",
                      analysisDirection: "",
                    })
                  }
                >
                  {monthData.undated} transactions without a printed date
                </button>
              )}
            </div>
            {monthData.omittedEmptyMonths && (
              <p className="text-xs text-muted-foreground">
                Only months with dated matching transactions are shown. Missing
                months do not mean zero activity.
              </p>
            )}
          </section>
          <section className="min-w-0" aria-label="Category distribution">
            <h4 className="text-sm font-medium">
              Category distribution · {amountGroupName(group)}
            </h4>
            <p className="text-xs text-muted-foreground">
              Responds to the selected month and direction. Share of total
              volume, with exact amounts in the list.
            </p>
            <div className="mt-2 flex flex-wrap items-start gap-3 sm:flex-nowrap">
              <svg
                viewBox="0 0 140 140"
                className="h-36 w-36 shrink-0"
                role="group"
                aria-label="Filter by category slices"
              >
                <circle
                  cx="70"
                  cy="70"
                  r="53.5"
                  fill="none"
                  stroke="var(--muted)"
                  strokeWidth="21"
                />
                {slices
                  .filter((c) => c.credit + c.debit > 0n)
                  .map((c) => (
                    <path
                      key={c.category}
                      d={ringSlice(c.start, c.end)}
                      fill={color(c.category)}
                      stroke={
                        filters.analysisCategories.includes(c.category)
                          ? "var(--foreground)"
                          : "var(--card)"
                      }
                      strokeWidth={
                        filters.analysisCategories.includes(c.category)
                          ? 2
                          : 0.5
                      }
                      opacity={
                        filters.analysisCategories.length &&
                        !filters.analysisCategories.includes(c.category)
                          ? 0.4
                          : 1
                      }
                      role="button"
                      tabIndex={0}
                      aria-label={`Filter category ${c.category}: ${c.count} transactions, ${money(c.credit + c.debit)}`}
                      aria-pressed={filters.analysisCategories.includes(
                        c.category
                      )}
                      className="cursor-pointer transition-opacity hover:opacity-75 focus-visible:outline-none focus-visible:stroke-primary focus-visible:stroke-[3px]"
                      onClick={() => selectCategory(c.category)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault()
                          selectCategory(c.category)
                        }
                      }}
                    >
                      <title>
                        {c.category}: {money(c.credit + c.debit)}. Click to
                        filter.
                      </title>
                    </path>
                  ))}
                <text
                  x="70"
                  y="67"
                  textAnchor="middle"
                  className="fill-foreground text-[16px] font-semibold pointer-events-none"
                >
                  {categoryData.categories.length}
                </text>
                <text
                  x="70"
                  y="84"
                  textAnchor="middle"
                  className="fill-muted-foreground text-[10px] pointer-events-none"
                >
                  categories
                </text>
              </svg>
              <div
                className="min-w-0 flex-1 text-xs"
                role="group"
                aria-label="Category list"
              >
                <input
                  aria-label="Search chart categories"
                  placeholder={`Search all ${categoryData.categories.length} categories…`}
                  value={categorySearch}
                  onChange={(e) => {
                    setCategorySearch(e.target.value)
                    setCategoryPage(0)
                  }}
                  className="mb-1 w-full rounded border bg-background px-2 py-1.5"
                />
                {categories
                  .slice(ci * CATEGORY_PAGE_SIZE, (ci + 1) * CATEGORY_PAGE_SIZE)
                  .map((c) => (
                    <button
                      key={c.category}
                      aria-label={`Category: ${c.category} (${c.count}), ${money(c.credit + c.debit)}`}
                      aria-pressed={filters.analysisCategories.includes(
                        c.category
                      )}
                      className={`flex w-full items-center justify-between gap-2 rounded p-1.5 text-left hover:bg-muted ${filters.analysisCategories.includes(c.category) ? "bg-primary/10" : ""}`}
                      onClick={() => selectCategory(c.category)}
                    >
                      <span>
                        <span style={{ color: color(c.category) }}>● </span>
                        {c.category}{" "}
                        <span className="text-muted-foreground">
                          ({c.count})
                        </span>
                      </span>
                      <span className="whitespace-nowrap tabular-nums">
                        {money(c.credit + c.debit)}
                      </span>
                    </button>
                  ))}
                {!categories.length && (
                  <p className="py-3">
                    No categories match this search and scope.
                  </p>
                )}
                <div
                  className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t pt-2"
                  aria-label="Category pages"
                >
                  <button
                    className="rounded border px-2 py-1 disabled:opacity-40"
                    disabled={!ci}
                    onClick={() => setCategoryPage(ci - 1)}
                  >
                    Previous categories
                  </button>
                  <span>
                    {categories.length ? ci * CATEGORY_PAGE_SIZE + 1 : 0}–
                    {Math.min((ci + 1) * CATEGORY_PAGE_SIZE, categories.length)}{" "}
                    of {categories.length}
                    {categorySearch
                      ? ` matching (${categoryData.categories.length} total)`
                      : " categories"}
                  </span>
                  <button
                    className="rounded border px-2 py-1 disabled:opacity-40"
                    disabled={
                      (ci + 1) * CATEGORY_PAGE_SIZE >= categories.length
                    }
                    onClick={() => setCategoryPage(ci + 1)}
                  >
                    Next categories
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
