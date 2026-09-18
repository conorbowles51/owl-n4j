import { CategoryMoneyChart } from "./CategoryMoneyChart"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  chartRatio,
  minorAmount,
  paymentDay,
  paymentGroup,
  paymentPeriods,
} from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import {
  InvestigationReadState,
  PaymentSet,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { useStatementRegister } from "../hooks/use-statement-register"
import { PaymentComparison } from "./PaymentComparison"

export function InvestigatorTrends({ caseId }: { caseId: string }) {
  const data = useInvestigatorPayments(caseId)
  const register = useStatementRegister(caseId)
  const [view, setView] = useFinancialDraft(caseId, "investigator-trends", {
    group: "",
    granularity: "month" as "month" | "day",
    metric: "amount",
    page: 0,
    selected: "",
  })
  const [compare, setCompare] = useState<string[] | null>(null)
  const groups = [...new Set(data.rows.map(paymentGroup))].sort()
  const group = groups.includes(view.group) ? view.group : groups[0] || ""
  const [currency, kind] = group.split(":")
  const rows = useMemo(
    () => data.rows.filter((row) => paymentGroup(row) === group),
    [data.rows, group]
  )
  const accounts = new Set(rows.map((row) => row.account_id))
  const coverage =
    register.imports.data?.files
      .flatMap((file) => file.periods)
      .filter(
        (period) =>
          accounts.has(period.account_id) && period.source_status === "admitted"
      ) ?? []
  const rowDates = rows.flatMap((row) =>
    paymentDay(row) ? [paymentDay(row)!] : []
  )
  const first =
    data.params.startDate ||
    [
      ...coverage.flatMap((period) => (period.start ? [period.start] : [])),
      ...rowDates,
    ].sort()[0]
  const last =
    data.params.endDate ||
    [
      ...coverage.flatMap((period) => (period.end ? [period.end] : [])),
      ...rowDates,
    ]
      .sort()
      .at(-1)
  const periods = useMemo(
    () => paymentPeriods(rows, view.granularity, first, last),
    [rows, view.granularity, first, last]
  )
  const size = view.granularity === "month" ? 12 : 31
  const page = Math.min(
    view.page,
    Math.max(0, Math.ceil(periods.length / size) - 1)
  )
  const visible = periods.slice(page * size, (page + 1) * size)
  const selected = periods.find((period) => period.date === view.selected)
  const selectedIndex = selected ? periods.indexOf(selected) : -1
  const prior = periods[selectedIndex - 1]
  const metric =
    view.metric === "balance" && accounts.size !== 1 ? "amount" : view.metric
  const unknownDates = rows.filter((row) => !paymentDay(row)).length
  const label = (date: string) =>
    new Date(`${date}T00:00:00Z`).toLocaleDateString("en-GB", {
      timeZone: "UTC",
      month: "short",
      ...(view.granularity === "day"
        ? { day: "numeric" }
        : { year: "2-digit" }),
    })
  const values = visible.map((period) => {
    if (metric === "count")
      return [
        BigInt(period.rows.filter((row) => row.direction === "credit").length),
        BigInt(period.rows.filter((row) => row.direction === "debit").length),
      ]
    if (metric === "balance") {
      const recorded = period.rows
        .filter((row) => minorAmount(row.running_balance_minor) !== null)
        .sort(
          (a, b) =>
            a.ordering_date.localeCompare(b.ordering_date) ||
            a.row_index - b.row_index
        )
      return [
        recorded.length
          ? minorAmount(recorded.at(-1)!.running_balance_minor)!
          : null,
        null,
      ]
    }
    return [period.credit, period.debit]
  })
  let maximum = 1n,
    minimum = 0n
  for (const pair of values)
    for (const value of pair)
      if (value !== null) {
        if (value > maximum) maximum = value
        if (value < minimum) minimum = value
      }
  const y = (value: bigint) =>
    248 - chartRatio(value - minimum, maximum - minimum) * 200
  const baseline = y(0n)
  const amount = (value: bigint) =>
    metric === "count"
      ? String(value)
      : `${formatLedgerAmount(String(value), currency).text} ${currency}`
  const step = 840 / Math.max(1, visible.length)
  const covered = (start: string, end: string) =>
    [...accounts].every((id) =>
      coverage.some(
        (period) =>
          period.account_id === id &&
          period.start &&
          period.end &&
          period.start <= start &&
          period.end >= end
      )
    )
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="Trends"
        description="See when activity changed, then open the payments behind the change."
      />
      <WorkspaceScope caseId={caseId} />
      <InvestigationReadState data={data}>
        <div
          className="finance-panel rounded-xl border p-5 space-y-4"
          data-finance-tone="info"
        >
          <div className="flex flex-wrap justify-between items-end gap-4">
            <div>
              <h3 className="font-semibold text-lg">
                {metric === "balance"
                  ? "Recorded balance over time"
                  : metric === "count"
                    ? "Number of payments over time"
                    : kind === "card"
                      ? "Card charges and credits over time"
                      : "Money in and out over time"}
              </h3>
              <p className="text-sm text-muted-foreground">
                {first || "No dated payments"}
                {last ? ` to ${last}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-3 text-sm">
              <label>
                Amounts
                <select
                  aria-label="Trend currency and account type"
                  className="block rounded border bg-background p-2"
                  value={group}
                  onChange={(e) =>
                    setView({
                      ...view,
                      group: e.target.value,
                      page: 0,
                      selected: "",
                    })
                  }
                >
                  {groups.map((value) => (
                    <option key={value} value={value}>
                      {value.split(":")[0]} ·{" "}
                      {value.endsWith(":card")
                        ? "credit cards"
                        : "bank accounts"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Interval
                <select
                  className="block rounded border bg-background p-2"
                  value={view.granularity}
                  onChange={(e) =>
                    setView({
                      ...view,
                      granularity: e.target.value as "month" | "day",
                      page: 0,
                      selected: "",
                    })
                  }
                >
                  <option value="month">Monthly</option>
                  <option value="day">Daily</option>
                </select>
              </label>
              <label>
                Show
                <select
                  className="block rounded border bg-background p-2"
                  value={metric}
                  onChange={(e) => setView({ ...view, metric: e.target.value })}
                >
                  <option value="amount">Amounts</option>
                  <option value="count">Payment count</option>
                  <option value="balance" disabled={accounts.size !== 1}>
                    Recorded balance (one account)
                  </option>
                </select>
              </label>
            </div>
          </div>
          {visible.length ? (
            <>
              <div className="overflow-x-auto">
                <svg
                  viewBox="0 0 1000 295"
                  className="w-full min-w-[700px]"
                  role="group"
                  aria-label="Chronological payment chart"
                >
                  {[0, 1, 2, 3, 4].map((tick) => {
                    const value =
                      minimum + ((maximum - minimum) * BigInt(tick)) / 4n
                    return (
                      <g key={tick}>
                        <line
                          x1="150"
                          x2="990"
                          y1={y(value)}
                          y2={y(value)}
                          stroke="currentColor"
                          opacity="0.12"
                        />
                        <text
                          x="140"
                          y={y(value) + 4}
                          textAnchor="end"
                          fontSize="11"
                          fill="currentColor"
                        >
                          {amount(value)}
                        </text>
                      </g>
                    )
                  })}
                  {visible.map((period, index) => {
                    const x = 150 + index * step + step / 2
                    return (
                      <g
                        key={period.date}
                        role="button"
                        tabIndex={0}
                        aria-label={`${label(period.date)}: ${period.rows.length} imported payments. Open period`}
                        onClick={() =>
                          setView({ ...view, selected: period.date })
                        }
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault()
                            setView({ ...view, selected: period.date })
                          }
                        }}
                        className="cursor-pointer focus:outline-primary"
                      >
                        <rect
                          x={x - step / 2 + 1}
                          y="25"
                          width={step - 2}
                          height="232"
                          fill={
                            selected?.date === period.date
                              ? "var(--finance-info)"
                              : "transparent"
                          }
                          opacity="0.15"
                        />
                        {metric === "balance"
                          ? values[index][0] !== null && (
                              <>
                                <circle
                                  cx={x}
                                  cy={y(values[index][0]!)}
                                  r="5"
                                  fill="var(--finance-info)"
                                />
                                {index > 0 && values[index - 1][0] !== null && (
                                  <line
                                    x1={x - step}
                                    x2={x}
                                    y1={y(values[index - 1][0]!)}
                                    y2={y(values[index][0]!)}
                                    stroke="var(--finance-info)"
                                    strokeWidth="2"
                                  />
                                )}
                                <title>{`${label(period.date)}: ${amount(values[index][0]!)}. Last printed balance in this interval.`}</title>
                              </>
                            )
                          : values[index].map((value, direction) => (
                              <rect
                                key={direction}
                                x={x + (direction ? 1 : -step * 0.32)}
                                y={y(value ?? 0n)}
                                width={step * 0.3}
                                height={Math.max(
                                  value ? 2 : 0,
                                  baseline - y(value ?? 0n)
                                )}
                                rx="2"
                                fill={
                                  direction
                                    ? "var(--finance-debit)"
                                    : "var(--finance-credit)"
                                }
                              >
                                <title>{`${label(period.date)}: ${direction ? "debit" : "credit"} ${amount(value ?? 0n)}`}</title>
                              </rect>
                            ))}
                        {!period.rows.length && (
                          <text
                            x={x}
                            y={baseline - 5}
                            textAnchor="middle"
                            fontSize="13"
                            fill="currentColor"
                          >
                            ·
                          </text>
                        )}
                        <text
                          x={x}
                          y="278"
                          textAnchor="middle"
                          fontSize={visible.length > 20 ? "9" : "12"}
                          fill="currentColor"
                        >
                          {label(period.date)}
                        </text>
                      </g>
                    )
                  })}
                </svg>
              </div>
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                {metric === "balance" ? (
                  <span>
                    Each point is the last printed balance in that interval. A
                    gap means no balance was recorded.
                  </span>
                ) : (
                  <>
                    <span className="flex items-center gap-2">
                      <i className="w-3 h-3 rounded-sm bg-[var(--finance-credit)]" />
                      {kind === "card" ? "Card credits" : "Money in"}
                    </span>
                    <span className="flex items-center gap-2">
                      <i className="w-3 h-3 rounded-sm bg-[var(--finance-debit)]" />
                      {kind === "card" ? "Card charges" : "Money out"}
                    </span>
                  </>
                )}
                <span>Select a date to inspect its payments.</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Empty intervals mean no imported payments, not confirmed
                inactivity.{" "}
                {register.imports.isError
                  ? "Statement coverage could not be checked."
                  : "Select an interval to check its recorded statement dates."}
                {unknownDates > 0 &&
                  ` ${unknownDates} payments have no known payment date and are omitted from this chart.`}
                {kind === "card" &&
                  " Card charges increase the amount owed; credits reduce it."}
              </p>
              {periods.length > size && (
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    disabled={!page}
                    onClick={() => setView({ ...view, page: page - 1 })}
                  >
                    Earlier dates
                  </Button>
                  <span className="text-sm">
                    {visible[0].date} to {visible.at(-1)!.end}
                  </span>
                  <Button
                    variant="outline"
                    disabled={(page + 1) * size >= periods.length}
                    onClick={() => setView({ ...view, page: page + 1 })}
                  >
                    Later dates
                  </Button>
                </div>
              )}
              <details>
                <summary className="cursor-pointer text-sm">
                  Read the chart values as a table
                </summary>
                <div className="overflow-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left">
                        <th>Period</th>
                        <th>
                          {metric === "balance" ? "Recorded balance" : "Credit"}
                        </th>
                        {metric !== "balance" && <th>Debit</th>}
                        <th>Payments</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((period, index) => (
                        <tr key={period.date} className="border-t">
                          <td>
                            <button
                              className="underline p-2"
                              onClick={() =>
                                setView({ ...view, selected: period.date })
                              }
                            >
                              {label(period.date)}
                            </button>
                          </td>
                          <td>
                            {values[index][0] === null
                              ? "Not recorded"
                              : amount(values[index][0]!)}
                          </td>
                          {metric !== "balance" && (
                            <td>{amount(values[index][1] ?? 0n)}</td>
                          )}
                          <td>{period.rows.length}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </>
          ) : (
            <p className="py-8 text-center text-muted-foreground">
              No dated payments in this scope. Import a statement or change the
              accounts and dates.
            </p>
          )}
        </div>
        <CategoryMoneyChart caseId={caseId} rows={rows} />
        {selected && (
          <section className="rounded-xl border bg-card p-5 space-y-4">
            <div className="flex flex-wrap justify-between gap-3">
              <div>
                <h3 className="font-semibold text-lg">
                  {label(selected.date)}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {selected.date} to {selected.end} · {selected.rows.length}{" "}
                  imported payments
                </p>
              </div>
              {prior && !!(selected.rows.length + prior.rows.length) && (
                <Button
                  variant="outline"
                  onClick={() =>
                    setCompare(
                      [...prior.rows, ...selected.rows].map((row) => row.key)
                    )
                  }
                >
                  Compare with {label(prior.date)}
                </Button>
              )}
            </div>
            <p className="text-sm">
              {register.imports.isError || register.imports.data?.truncated
                ? "Coverage could not be fully checked."
                : covered(selected.date, selected.end)
                  ? "Recorded statement dates cover this interval for the accounts shown. This does not independently confirm that every payment was read."
                  : "Full statement coverage is not recorded for every account in this interval. Check Statements & accounts for missing periods."}
            </p>
            {selected.unreadable > 0 && (
              <p role="alert">
                {selected.unreadable} amounts could not be totalled. Open their
                original records.
              </p>
            )}
            <PaymentSet
              key={`${group}:${selected.date}`}
              caseId={caseId}
              rows={selected.rows}
              title={`Payments in ${label(selected.date)}`}
            />
          </section>
        )}
        {compare && (
          <PaymentComparison
            caseId={caseId}
            ids={compare}
            onClose={() => setCompare(null)}
          />
        )}
      </InvestigationReadState>
    </div>
  )
}
