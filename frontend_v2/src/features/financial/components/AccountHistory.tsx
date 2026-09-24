import { useMemo, useState, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import {
  accountColor,
  historyMonths,
  historyResponse,
  type HistoryPeriod,
} from "../lib/account-history"
import { currencyMinorUnits, formatLedgerAmount } from "../lib/ledger-format"
import { useInvestigationScope } from "../stores/investigation-scope"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { StatementSourceButton } from "./StatementSourceButton"
import { PaymentSet } from "./InvestigationWorkspaceParts"

export function AccountHistory({
  caseId,
  accountId,
}: {
  caseId: string
  accountId?: string
}) {
  const [scope] = useInvestigationScope(caseId)
  const [metric, setMetric] = useState("count")
  const [selected, setSelected] = useState<string | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const selectMonth = (month: string | null) => {
    setSelected(month)
    if (month)
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        })
        detailRef.current?.focus({ preventScroll: true })
      })
  }
  const [paymentPeriod, setPaymentPeriod] = useState<HistoryPeriod | null>(null)
  const params = new URLSearchParams()
  if (accountId || scope.accountId)
    params.set("account_id", accountId || scope.accountId!)
  if (!accountId) {
    scope.accountIds?.forEach((id) => params.append("account_ids", id))
    scope.accountHolders?.forEach((holder) =>
      params.append("account_holders", holder)
    )
  }
  if (scope.startDate) params.set("start_date", scope.startDate)
  if (scope.endDate) params.set("end_date", scope.endDate)
  const query = useQuery({
    queryKey: ["financial-account-history", caseId, params.toString()],
    retry: false,
    queryFn: async () => {
      const data = historyResponse.parse(
        await fetchAPI(`${candidateUrl("account-history", caseId)}&${params}`)
      )
      if (data.case_id !== caseId)
        throw new Error(
          "Account history belongs to a different case. Reload the view."
        )
      return data
    },
  })
  const prepared = useMemo(() => {
    try {
      return {
        months: historyMonths(
          query.data?.groups || [],
          scope.startDate,
          scope.endDate
        ),
        error: "",
      }
    } catch (e) {
      return {
        months: [],
        error:
          e instanceof Error ? e.message : "Could not prepare account history.",
      }
    }
  }, [query.data, scope.startDate, scope.endDate])
  const groups = query.data?.groups || []
  const units = [
    ...new Set(groups.map((g) => `${g.currency}:${g.balance_kind}`)),
  ]
  const number = (v: string | null, currency: string) =>
    v === null ? null : Number(v) / 10 ** (currencyMinorUnits(currency) ?? 2)
  const format = (v: string | null, currency: string) =>
    v === null
      ? "Not available"
      : formatLedgerAmount(v, currency).text + " " + currency
  const active = prepared.months.find((m) => m.month === selected)
  return (
    <section
      aria-label="Account balances and activity"
      className="min-w-0 w-full max-w-full rounded border p-4 space-y-4"
    >
      <div className="flex flex-wrap justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">
            Account balances and activity
          </h3>
          <p className="text-sm text-muted-foreground">
            Compare activity with the balance left in each account, including
            periods with no transactions. Accounts and dates above apply here.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          Refresh account history
        </Button>
      </div>
      {query.isPending && (
        <p role="status">Loading statements and their saved payments…</p>
      )}
      {query.isError && <p role="alert">{query.error.message}</p>}
      {prepared.error && <p role="alert">{prepared.error}</p>}
      {query.isSuccess && !groups.length && (
        <p>
          No saved statement periods match these accounts and dates. Prepared
          statements stay in review until they can be reconciled.
        </p>
      )}
      {groups.length > 8 && (
        <p role="status">
          {groups.length} account/currency series match. Select up to eight
          using Accounts and dates to make the comparison readable. All matching
          statement periods remain in the list below.
        </p>
      )}
      {!!groups.length && (
        <>
          <label className="text-sm">
            Activity measure{" "}
            <select
              aria-label="Activity measure"
              className="border rounded p-2 ml-2 bg-background"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              <option value="count">Transaction count</option>
              <option value="credit_minor">Credits / money in</option>
              <option value="debit_minor">Debits / money out</option>
            </select>
          </label>
          <p className="text-xs text-muted-foreground">
            A gap means missing or unverified evidence, not zero activity.
            Balances are points at statement end dates; they are not added
            together or carried across missing months. For credit cards,
            balances show amounts owed, debits are charges and credits reduce
            the amount owed. Select a month below to inspect its statements.
          </p>
          {groups.length <= 8 &&
            !prepared.error &&
            units.map((unit) => {
              const series = groups.filter(
                (g) => `${g.currency}:${g.balance_kind}` === unit
              )
              const points = prepared.months.map((m) => ({
                month: m.month,
                ...Object.fromEntries(
                  series.flatMap((g) => {
                    const v = m.values.find((v) => v.key === g.key)!
                    return [
                      [`${g.key}-balance`, number(v.closing_minor, g.currency)],
                      [
                        `${g.key}-activity`,
                        metric === "count"
                          ? v.count
                          : number(
                              v[metric as "credit_minor" | "debit_minor"],
                              g.currency
                            ),
                      ],
                    ]
                  })
                ),
              }))
              return (
                <div key={unit} className="space-y-3 border rounded p-3">
                  <h4 className="font-semibold">
                    {series[0].currency} ·{" "}
                    {series[0].balance_kind === "liability"
                      ? "Credit card amounts owed"
                      : "Bank account balances"}
                  </h4>
                  <p className="text-sm">
                    Closing balances · points at the last statement end in each
                    month
                  </p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis width={80} />
                        <Tooltip />
                        <Legend />
                        {series.map((g) => (
                          <Line
                            key={g.key}
                            name={g.label}
                            dataKey={`${g.key}-balance`}
                            stroke={accountColor(g.key)}
                            connectNulls={false}
                            dot={{ r: 4 }}
                            type="stepAfter"
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-sm">
                    {metric === "count"
                      ? "Number of dated transactions"
                      : metric === "credit_minor"
                        ? "Credits"
                        : "Debits"}{" "}
                    · per month
                  </p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis width={80} />
                        <Tooltip />
                        <Legend />
                        {series.map((g) => (
                          <Bar
                            key={g.key}
                            name={g.label}
                            dataKey={`${g.key}-activity`}
                            fill={accountColor(g.key)}
                            onClick={(_, index) =>
                              selectMonth(points[index].month)
                            }
                          />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )
            })}
          <div
            className="flex flex-wrap gap-2"
            aria-label="Inspect activity month"
          >
            {prepared.months.map((m) => (
              <Button
                key={m.month}
                size="sm"
                variant={selected === m.month ? "primary" : "outline"}
                onClick={() =>
                  selectMonth(selected === m.month ? null : m.month)
                }
              >
                {m.month}
              </Button>
            ))}
          </div>
          {active && (
            <div
              className="border rounded p-3 space-y-2"
              role="region"
              aria-label={`${active.month} activity details`}
              ref={detailRef}
              tabIndex={-1}
            >
              <h4 className="font-semibold">{active.month}</h4>
              {groups.map((g) => {
                const v = active.values.find((v) => v.key === g.key)!
                return (
                  <p key={g.key}>
                    <strong style={{ color: accountColor(g.key) }}>
                      {g.label}
                    </strong>
                    : {v.state} ·{" "}
                    {v.count === null
                      ? "Activity unknown"
                      : `${v.count} dated transactions`}{" "}
                    · Closing balance {format(v.closing_minor, g.currency)}
                    {v.closing_date ? ` at ${v.closing_date}` : ""}
                  </p>
                )
              })}
            </div>
          )}
          <details key={selected || "all"} open={!!active}>
            <summary className="cursor-pointer font-semibold">
              Statement periods and exact balances (
              {groups.reduce((n, g) => n + g.periods.length, 0)})
            </summary>
            <div className="overflow-auto max-h-[55vh]">
              <table className="text-sm w-full">
                <thead className="sticky top-0 bg-background">
                  <tr>
                    {[
                      "Account",
                      "Statement period",
                      "Opening",
                      "Closing",
                      "Activity",
                      "Review",
                      "Source and payments",
                    ].map((h) => (
                      <th className="text-left p-2" key={h}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {groups.flatMap((g) =>
                    g.periods
                      .filter(
                        (p) =>
                          !active ||
                          active.values
                            .find((v) => v.key === g.key)
                            ?.periods.some((v) => v.id === p.id)
                      )
                      .map((p) => (
                        <tr className="border-t" key={p.id}>
                          <td className="p-2">
                            <span style={{ color: accountColor(g.key) }}>
                              ●{" "}
                            </span>
                            {g.label} · {g.currency}
                          </td>
                          <td className="p-2">
                            {p.start || "Start missing"} →{" "}
                            {p.end || "End missing"}
                          </td>
                          <td className="p-2 whitespace-nowrap">
                            {format(p.opening_minor, g.currency)}
                          </td>
                          <td className="p-2 whitespace-nowrap">
                            {format(p.closing_minor, g.currency)}
                          </td>
                          <td className="p-2">
                            {p.status === "confirmed_no_activity"
                              ? "No activity confirmed"
                              : `${p.transaction_count} saved transactions`}
                            {p.undated_count > 0 &&
                              ` · ${p.undated_count} dates unprinted`}
                          </td>
                          <td className="p-2">
                            {p.status === "needs_review"
                              ? "Needs review — saved readings retained"
                              : p.status === "confirmed_no_activity"
                                ? "Confirmed quiet period"
                                : "Reconciled"}
                          </td>
                          <td className="p-2 space-y-2">
                            <StatementSourceButton
                              caseId={caseId}
                              periodId={p.id}
                              sourceDocumentId={p.source_document_id}
                              label="Open statement"
                            />
                            {p.transaction_count > 0 && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setPaymentPeriod(p)}
                              >
                                View {p.transaction_count} payments
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
      <Dialog
        open={!!paymentPeriod}
        onOpenChange={(open) => {
          if (!open) setPaymentPeriod(null)
        }}
      >
        <DialogContent className="sm:max-w-[95vw] max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Payments in this statement</DialogTitle>
            <DialogDescription>
              {paymentPeriod?.filename} · {paymentPeriod?.start} to{" "}
              {paymentPeriod?.end}. Close to return to the same account
              comparison.
            </DialogDescription>
          </DialogHeader>
          {paymentPeriod && (
            <PeriodPayments caseId={caseId} period={paymentPeriod} />
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
function PeriodPayments({
  caseId,
  period,
}: {
  caseId: string
  period: HistoryPeriod
}) {
  const query = useLedgerTransactions(caseId, {
    sourceDocumentId: period.source_document_id,
  })
  if (query.isPending) return <p role="status">Loading saved payments…</p>
  if (query.isError)
    return (
      <div role="alert">
        {query.error.message}
        <Button onClick={() => void query.refetch()}>Retry payments</Button>
      </div>
    )
  if (
    query.data.case_id !== caseId ||
    query.data.transactions.length !== query.data.total
  )
    return (
      <p role="alert">
        Not all payments were returned. Close and reopen this statement to
        retry.
      </p>
    )
  return (
    <PaymentSet
      caseId={caseId}
      rows={query.data.transactions}
      title="Saved statement payments"
    />
  )
}
