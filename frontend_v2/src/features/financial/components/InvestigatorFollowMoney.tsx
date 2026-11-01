import { MoneyFlowExplorer } from "./MoneyFlowExplorer"
import { CategoryFlowDiagram } from "./CategoryFlowDiagram"
import { Disclosure } from "./Disclosure"
import { InfoTip } from "./InfoTip"
import { ReviewedMoneyTrails } from "./ReviewedMoneyTrails"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useEffect, useMemo, useState } from "react"
import {
  ArrowRight,
  GitCompareArrows,
  Network,
  Search,
  Route,
  CalendarDays,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import {
  useFinancialStore,
  type FinancialMainView,
} from "../stores/financial.store"
import { nearbyPayments } from "../lib/investigator-workspace"
import { connectionGroupsInSteps, type PanelGroup, type PanelTotal } from "../lib/overview-panels"
import { formatLedgerAmount } from "../lib/ledger-format"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  InvestigationReadState,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { PaymentComparison } from "./PaymentComparison"

export function MoneyConnections({
  rows,
  onOpen,
}: {
  rows: LedgerTransaction[]
  onOpen: (ids: string[], title: string) => void
}) {
  // Grouped once per row list, not on every render: on d5b330d1 (27,926 payments) grouping the profiles took about
  // 0.7 s of main thread per render, and the Overview renders as each of its requests lands (browser profile,
  // 2026-10-31). The inputs are the same array while the answer and categories are (useInvestigatorPayments).
  // The grouping runs in its own task after the page has drawn, not inside the render that first shows the
  // payments: together they held the main thread 1.0-1.2 s on d5b330d1 Follow money (live long-task trace,
  // 2026-10-31 23:05), longer than the page may sit without redrawing. Until it is done, and again for a new row
  // list, the panel says what it is doing; figures for an older row list are never shown for the new one.
  // The chosen currency group and page live here, not in the view, so they are kept while a new row list is grouped
  // (the view is not drawn then), as they were when the grouping ran inside the render.
  const choice = useState("")
  const pageChoice = useState(0)
  // The grouping itself runs in steps that give the browser a turn (connectionGroupsInSteps): in one piece it held
  // the main thread 0.6 s on d5b330d1 with the host idle and 1.2-1.6 s with it busy (2026-11-01). The line below says
  // which step it is on, from the true count of steps.
  const [grouped, setGrouped] = useState<{ rows: LedgerTransaction[]; groups: PanelGroup[] } | null>(null)
  const [step, setStep] = useState<{ rows: LedgerTransaction[]; done: number; total: number } | null>(null)
  // A grouping that fails says so for this row list and offers to run it again; it never sits on "Grouping…".
  const [failure, setFailure] = useState<{ rows: LedgerTransaction[]; message: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const failed = failure?.rows === rows ? failure.message : null
  useEffect(() => {
    if (grouped?.rows === rows || failed !== null) return
    const signal = { cancelled: false }
    const timer = setTimeout(() => {
      connectionGroupsInSteps(rows, (done, total) => setStep({ rows, done, total }), signal).then(
        (groups) => {
          if (groups && !signal.cancelled) setGrouped({ rows, groups })
        },
        (error: unknown) => {
          if (!signal.cancelled) setFailure({ rows, message: error instanceof Error ? error.message : String(error) })
        }
      )
    }, 0)
    return () => {
      signal.cancelled = true
      clearTimeout(timer)
    }
  }, [rows, grouped, failed, attempt])
  if (grouped?.rows !== rows && failed !== null)
    return (
      <section className="rounded-xl border bg-card p-5 space-y-2" aria-label="Recorded payment connections">
        <h3 className="font-semibold text-lg">Who paid in, and where payments went</h3>
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-destructive">
          <span>
            Grouping {rows.length.toLocaleString("en-US")} {rows.length === 1 ? "payment" : "payments"} by name and
            account failed: {failed}. No figures are shown for this panel.
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setFailure(null)
              setStep(null)
              setAttempt((n) => n + 1)
            }}
          >
            Try again
          </Button>
        </div>
      </section>
    )
  if (grouped?.rows !== rows)
    return (
      <section
        className="rounded-xl border bg-card p-5 space-y-2"
        aria-label="Recorded payment connections"
      >
        <h3 className="font-semibold text-lg">Who paid in, and where payments went</h3>
        <p role="status" className="text-sm text-muted-foreground">
          Grouping {rows.length.toLocaleString("en-US")} {rows.length === 1 ? "payment" : "payments"} by name and account…
          {step?.rows === rows && ` step ${step.done} of ${step.total}`}
        </p>
      </section>
    )
  return (
    <MoneyConnectionsView
      payments={rows.length}
      groups={grouped.groups}
      onOpen={onOpen}
      choice={choice}
      pageChoice={pageChoice}
    />
  )
}

/** The connections panel from its figures: worked out from every payment (MoneyConnections) or answered by the
 * server for the Overview (GET /ledger-overview-panels), the same figures either way. */
export function MoneyConnectionsView({
  payments: paymentCount,
  groups: figures,
  onOpen,
  choice,
  pageChoice,
}: {
  payments: number
  groups: PanelGroup[]
  onOpen: (ids: string[], title: string) => void
  /** The chosen group and page, when the caller keeps them (MoneyConnections). */
  choice?: [string, (value: string) => void]
  pageChoice?: [number, (value: number) => void]
}) {
  const groups = figures.map((item) => item.group)
  const ownChoice = useState("")
  const ownPage = useState(0)
  const [requestedGroup, setGroup] = choice ?? ownChoice
  const group = groups.includes(requestedGroup) ? requestedGroup : groups[0]
  const current = figures.find((item) => item.group === group)
  const [requestedPage, setPage] = pageChoice ?? ownPage
  const visibleNames = current?.names ?? []
  const page = Math.min(
    requestedPage,
    Math.max(0, Math.ceil(visibleNames.length / 6) - 1)
  )
  const list = visibleNames.slice(page * 6, (page + 1) * 6)
  const card = group?.endsWith(":card")
  const unnamed = current?.unnamed ?? []
  const unnamedCount = unnamed.reduce((sum, item) => sum + item.keys.length, 0)
  const totalLabel = (total: PanelTotal | undefined) => {
    if (total === null || total === undefined) return "Amount needs checking"
    return `${formatLedgerAmount(total, group?.split(":")[0] || "").text} ${group?.split(":")[0]}`
  }
  return (
    <section
      className="rounded-xl border bg-card p-5 space-y-4"
      aria-label="Recorded payment connections"
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-lg">
            Who paid in, and where payments went
          </h3>
          <p className="text-sm text-muted-foreground">
            Select a connection to read its payments and original statements.
          </p>
        </div>
        {groups.length > 1 && (
          <select
            aria-label="Connection currency and account type"
            className="rounded border bg-background p-2 text-sm"
            value={group}
            onChange={(e) => {
              setGroup(e.target.value)
              setPage(0)
            }}
          >
            {groups.map((value) => (
              <option key={value} value={value}>
                {value.split(":")[0]}{" "}
                {value.endsWith(":card") ? "cards" : "bank accounts"}
              </option>
            ))}
          </select>
        )}
      </div>
      {!!paymentCount && (
        <div className="rounded-lg border bg-muted/20 p-3 space-y-2 text-sm">
          <p>
            This is a summary of independent transactions for{" "}
            {group?.split(":")[0]} {card ? "credit cards" : "bank accounts"}.
            Left:{" "}
            {totalLabel(current?.credit_total)}{" "}
            in credits. Right:{" "}
            {totalLabel(current?.debit_total)}{" "}
            in debits. Totals include the unidentified counterparties listed
            below.
          </p>
          <p>
            The arrows show the direction of each payment into or out of these
            accounts. They do not connect a particular receipt to a withdrawal.
            A bank appearing on both sides may reflect different interest, fee
            or transfer entries; open its payments to see the descriptions.
            Choose a tracing concept above to test how receipts could relate to
            later payments.
          </p>
        </div>
      )}
      {!paymentCount ? (
        <p>No imported payments in this scope.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr_auto_1fr] items-center">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {card ? "Credits recorded from" : "Paid in by"}
            </p>
            {list.map((profile) => {
              const payments = profile.credit
              return (
                payments.keys.length > 0 && (
                  <button
                    key={profile.id}
                    onClick={() =>
                      onOpen(
                        payments.keys,
                        `Payments from ${profile.name}`
                      )
                    }
                    className="finance-tint block w-full rounded-lg border p-3 text-left"
                    data-finance-tone="credit"
                  >
                    <strong className="block text-sm break-words">
                      {profile.name}
                    </strong>
                    {payments.suggested && (
                      <span className="block text-xs text-muted-foreground">
                        Includes names suggested from descriptions
                      </span>
                    )}
                    <span className="finance-amount text-xs">
                      {payments.keys.length} payments · {totalLabel(payments.total)}
                    </span>
                  </button>
                )
              )
            })}
            {!list.some((profile) => profile.credit.keys.length > 0) && (
              <p className="text-sm text-muted-foreground">
                No incoming payments for these names
              </p>
            )}
          </div>
          <ArrowRight
            className="text-muted-foreground hidden lg:block"
            aria-hidden="true"
          />
          <div
            className="finance-tint rounded-lg border-2 p-4 space-y-2"
            data-finance-tone="info"
          >
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Accounts in the case
            </p>
            {(current?.accounts ?? []).map((account) => (
                <button
                  key={account.id}
                  className="block text-left text-sm font-semibold hover:underline break-words"
                  onClick={() =>
                    onOpen(account.keys, account.name)
                  }
                >
                  {account.name}
                </button>
              ))}
          </div>
          <ArrowRight
            className="text-muted-foreground hidden lg:block"
            aria-hidden="true"
          />
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {card ? "Charges recorded to" : "Paid out to"}
            </p>
            {list.map((profile) => {
              const payments = profile.debit
              return (
                payments.keys.length > 0 && (
                  <button
                    key={profile.id}
                    onClick={() =>
                      onOpen(
                        payments.keys,
                        `Payments to ${profile.name}`
                      )
                    }
                    className="finance-tint block w-full rounded-lg border p-3 text-left"
                    data-finance-tone="debit"
                  >
                    <strong className="block text-sm break-words">
                      {profile.name}
                    </strong>
                    {payments.suggested && (
                      <span className="block text-xs text-muted-foreground">
                        Includes names suggested from descriptions
                      </span>
                    )}
                    <span className="finance-amount text-xs">
                      {payments.keys.length} payments · {totalLabel(payments.total)}
                    </span>
                  </button>
                )
              )
            })}
            {!list.some((profile) => profile.debit.keys.length > 0) && (
              <p className="text-sm text-muted-foreground">
                No outgoing payments for these names
              </p>
            )}
          </div>
        </div>
      )}
      {visibleNames.length > 6 && (
        <div className="flex gap-3 items-center text-sm">
          <Button
            variant="outline"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            Previous names
          </Button>
          <span>
            {page * 6 + 1} to {Math.min(visibleNames.length, (page + 1) * 6)} of{" "}
            {visibleNames.length} names
          </span>
          <Button
            variant="outline"
            disabled={(page + 1) * 6 >= visibleNames.length}
            onClick={() => setPage(page + 1)}
          >
            Next names
          </Button>
        </div>
      )}
      {unnamedCount > 0 && (
        <section
          aria-label="Payments without identified counterparties"
          className="rounded-lg border bg-muted/20 p-4 space-y-3"
        >
          <h4 className="font-semibold">
            {unnamedCount} payments without an identified counterparty
          </h4>
          <p className="text-sm text-muted-foreground">
            These payments remain in the totals. They are grouped below by their
            descriptions, not treated as one person or company. Open a group to
            inspect its references and source statements.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {unnamed.map((item) => (
              <button
                key={`${item.direction}:${item.kind}`}
                className="rounded border bg-background p-3 text-left hover:bg-muted/50"
                onClick={() =>
                  onOpen(
                    item.keys,
                    item.label
                  )
                }
              >
                <strong className="block text-sm">{item.label}</strong>
                <span className="block text-sm">
                  {item.keys.length}{" "}
                  {item.keys.length === 1 ? "payment" : "payments"} ·{" "}
                  {totalLabel(item.total)} ·{" "}
                  {card
                    ? item.direction === "credit"
                      ? "Card credits"
                      : "Card charges"
                    : item.direction === "credit"
                      ? "Money in"
                      : "Money out"}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {item.reason}
                </span>
                <span className="mt-2 block text-xs font-medium text-primary">
                  View payments and references →
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
      <p className="text-xs text-muted-foreground">
        Names include statement readings, investigator edits and suggestions
        from descriptions. Open a payment to check its name source. These
        connections do not establish ownership or show that one receipt funded a
        later payment.
      </p>
    </section>
  )
}

export function InvestigatorFollowMoney({ caseId }: { caseId: string }) {
  const data = useInvestigatorPayments(caseId)
  const [view, setView] = useFinancialDraft(
    caseId,
    "investigator-follow-money",
    { days: 7, page: 0 }
  )
  const comparisons = useMemo(
    () => nearbyPayments(data.rows, view.days),
    [data.rows, view.days]
  )
  const [open, setOpen] = useState<{ ids: string[]; title: string } | null>(
    null
  )
  const setMainView = useFinancialStore((state) => state.setMainView)
  const page = Math.min(
    view.page,
    Math.max(0, Math.ceil(comparisons.length / 20) - 1)
  )
  return (
    <div className="space-y-5 p-5">
      <WorkspaceHeading
        title="Follow money"
        description="Compare related movements and record the evidence for any connection you identify."
      />
      <WorkspaceScope caseId={caseId} />
      <MoneyTrailReview caseId={caseId} />
      <InvestigationReadState data={data}>
        <CategoryFlowDiagram
          caseId={caseId}
          rows={data.rows}
          onOpen={(ids, title) => setOpen({ ids, title })}
          onTrace={() => setMainView("tracing")}
        />
        <div id="follow-money-tables" className="scroll-mt-4" />
        <ReviewedMoneyTrails caseId={caseId} rows={data.rows} />
        <MoneyFlowExplorer
          caseId={caseId}
          rows={data.rows}
          onOpen={(ids, title) => setOpen({ ids, title })}
          overview={
            <MoneyConnections
              rows={data.rows}
              onOpen={(ids, title) => setOpen({ ids, title })}
            />
          }
        />
        <Disclosure label={`Adjacent payments · timing comparisons (${comparisons.length})`}>
          <section className="rounded-xl border bg-card p-5 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">
                  Receipts followed by an outgoing payment
                </h3>
                <p className="text-sm text-muted-foreground">
                  {comparisons.length} comparisons to examine in the selected
                  accounts and dates.
                </p>
              </div>
              <label className="text-sm">
                Maximum gap
                <select
                  className="block rounded border bg-background p-2"
                  value={view.days}
                  onChange={(e) =>
                    setView({ days: Number(e.target.value), page: 0 })
                  }
                >
                  {[1, 3, 7, 14, 30].map((days) => (
                    <option key={days} value={days}>
                      {days} days
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="text-sm">
              A starting point for review, not a confirmed transfer.
              <InfoTip text={`Each comparison uses adjacent dated payments in the same bank account and currency. A receipt is followed by a payment within ${view.days} days. This is a starting point for review, not a confirmed transfer. Credit card entries and unknown payment dates are not compared.`} />
            </p>
            {!!comparisons.length && (
              <Button
                variant="outline"
                onClick={() =>
                  setOpen({
                    ids: [
                      ...new Set(
                        comparisons.flatMap((pair) => [
                          pair.incoming.key,
                          pair.outgoing.key,
                        ])
                      ),
                    ],
                    title: "All payments in these comparisons",
                  })
                }
              >
                Compare all supporting payments
              </Button>
            )}
            <div className="overflow-x-auto">
              <table
                className="finance-table w-full text-sm"
                aria-label="Receipts and subsequent payments"
              >
                <thead className="text-left bg-muted/30">
                  <tr>
                    <th className="p-3">Receipt</th>
                    <th className="p-3">Later outgoing payment</th>
                    <th className="p-3">Gap</th>
                    <th className="p-3">Amount difference</th>
                    <th className="p-3">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.slice(page * 20, (page + 1) * 20).map((pair) => (
                    <tr
                      key={`${pair.incoming.key}:${pair.outgoing.key}`}
                      className="border-t align-top"
                    >
                      <td className="p-3">
                        <strong
                          className="finance-amount"
                          data-finance-tone="credit"
                        >
                          {
                            formatLedgerAmount(
                              pair.incoming.amount_minor,
                              pair.incoming.currency
                            ).text
                          }{" "}
                          {pair.incoming.currency}
                        </strong>
                        <p>{pair.incoming.ordering_date}</p>
                        <p className="text-xs text-muted-foreground">
                          {(pair.incoming.from_name ??
                            pair.incoming.counterparty_raw) ||
                            "Name not identified"}
                        </p>
                      </td>
                      <td className="p-3">
                        <strong
                          className="finance-amount"
                          data-finance-tone="debit"
                        >
                          {
                            formatLedgerAmount(
                              pair.outgoing.amount_minor,
                              pair.outgoing.currency
                            ).text
                          }{" "}
                          {pair.outgoing.currency}
                        </strong>
                        <p>{pair.outgoing.ordering_date}</p>
                        <p className="text-xs text-muted-foreground">
                          {(pair.outgoing.to_name ??
                            pair.outgoing.counterparty_raw) ||
                            "Name not identified"}
                        </p>
                      </td>
                      <td className="p-3">
                        {pair.days} days
                        {pair.days === 0 && (
                          <p className="text-xs">Same-day order unconfirmed</p>
                        )}
                      </td>
                      <td className="p-3">
                        {
                          formatLedgerAmount(
                            String(pair.difference),
                            pair.incoming.currency
                          ).text
                        }{" "}
                        {pair.incoming.currency}
                      </td>
                      <td className="p-3">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setOpen({
                              ids: [pair.incoming.key, pair.outgoing.key],
                              title: "Receipt and subsequent payment",
                            })
                          }
                        >
                          Compare payments
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!comparisons.length && (
              <p className="rounded border p-4 text-sm">
                No adjacent receipt/payment pairs meet these settings. Change
                the gap or accounts, or select payments yourself in
                Transactions.
              </p>
            )}
            {comparisons.length > 20 && (
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  disabled={!page}
                  onClick={() => setView({ ...view, page: page - 1 })}
                >
                  Previous comparisons
                </Button>
                <span>
                  {page * 20 + 1} to{" "}
                  {Math.min(comparisons.length, (page + 1) * 20)} of{" "}
                  {comparisons.length}
                </span>
                <Button
                  variant="outline"
                  disabled={(page + 1) * 20 >= comparisons.length}
                  onClick={() => setView({ ...view, page: page + 1 })}
                >
                  Next comparisons
                </Button>
              </div>
            )}
          </section>
        </Disclosure>
      </InvestigationReadState>
      <section className="space-y-3">
        <h3 className="text-lg font-semibold">Continue the investigation</h3>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(
            [
              [
                "transfers",
                "Compare transfers",
                "Compare a payment out of one account with a receipt into another.",
                GitCompareArrows,
              ],
              [
                "patterns",
                "Look for repeated activity",
                "Search for repeated amounts, split payments and other defined patterns.",
                Search,
              ],
              [
                "posting-graph",
                "Explore payment connections",
                "Open the payments connecting accounts and recorded names.",
                Network,
              ],
              [
                "tracing",
                "Test where funds could have gone",
                "Calculate a possible route using an explicit opening amount and method.",
                Route,
              ],
              [
                "case-context",
                "Compare with case events",
                "Place payments beside other dated evidence in this case.",
                CalendarDays,
              ],
            ] as const
          ).map(([key, label, explanation, Icon]) => (
            <button
              key={key}
              className="rounded-lg border bg-card p-4 text-left hover:border-primary"
              onClick={() =>
                useFinancialStore
                  .getState()
                  .setMainView(key as FinancialMainView)
              }
            >
              <Icon size={19} className="text-primary mb-3" />
              <strong className="block text-sm">{label}</strong>
              <p className="mt-1 text-sm text-muted-foreground">
                {explanation}
              </p>
            </button>
          ))}
        </div>
      </section>
      {open && (
        <PaymentComparison
          caseId={caseId}
          ids={open.ids}
          title={open.title}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}
import { MoneyTrailReview } from "./MoneyTrailReview"
