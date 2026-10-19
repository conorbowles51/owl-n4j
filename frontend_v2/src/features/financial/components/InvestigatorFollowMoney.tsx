import { MoneyFlowExplorer } from "./MoneyFlowExplorer"
import { ReviewedMoneyTrails } from "./ReviewedMoneyTrails"
import { useInvestigatorPayments } from "../hooks/use-investigator-payments"
import { useMemo, useState } from "react"
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
import {
  nearbyPayments,
  minorAmount,
  paymentProfiles,
  paymentGroup,
} from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import { useFinancialDraft } from "../stores/financial-drafts"
import {
  InvestigationReadState,
  WorkspaceHeading,
  WorkspaceScope,
} from "./InvestigationWorkspaceParts"
import { PaymentComparison } from "./PaymentComparison"
import {
  unidentifiedGroups,
  unidentifiedPayment,
} from "../lib/unidentified-payments"

export function MoneyConnections({
  rows,
  onOpen,
}: {
  rows: LedgerTransaction[]
  onOpen: (ids: string[], title: string) => void
}) {
  const names = paymentProfiles(
    rows.filter((row) => !unidentifiedPayment(row))
  ).filter((profile) => profile.kind === "name")
  const accounts = paymentProfiles(rows).filter(
    (profile) => profile.kind === "account"
  )
  const groups = [...new Set(rows.map(paymentGroup))].sort()
  const [requestedGroup, setGroup] = useState("")
  const group = groups.includes(requestedGroup) ? requestedGroup : groups[0]
  const [requestedPage, setPage] = useState(0)
  const visibleNames = names.filter((profile) =>
    profile.rows.some((row) => paymentGroup(row) === group)
  )
  const page = Math.min(
    requestedPage,
    Math.max(0, Math.ceil(visibleNames.length / 6) - 1)
  )
  const list = visibleNames.slice(page * 6, (page + 1) * 6)
  const card = group?.endsWith(":card")
  const unnamed = unidentifiedGroups(
    rows.filter((row) => paymentGroup(row) === group)
  )
  const unnamedCount = unnamed.reduce((sum, item) => sum + item.rows.length, 0)
  const totalLabel = (payments: LedgerTransaction[]) => {
    const amounts = payments.map((row) => minorAmount(row.amount_minor))
    if (amounts.some((value) => value === null)) return "Amount needs checking"
    return `${formatLedgerAmount(amounts.reduce<bigint>((sum, value) => sum + value!, 0n).toString(), group?.split(":")[0] || "").text} ${group?.split(":")[0]}`
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
      {!!rows.length && (
        <div className="rounded-lg border bg-muted/20 p-3 space-y-2 text-sm">
          <p>
            This is a summary of independent transactions for{" "}
            {group?.split(":")[0]} {card ? "credit cards" : "bank accounts"}.
            Left:{" "}
            {totalLabel(
              rows.filter(
                (r) => paymentGroup(r) === group && r.direction === "credit"
              )
            )}{" "}
            in credits. Right:{" "}
            {totalLabel(
              rows.filter(
                (r) => paymentGroup(r) === group && r.direction === "debit"
              )
            )}{" "}
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
      {!rows.length ? (
        <p>No imported payments in this scope.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr_auto_1fr] items-center">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {card ? "Credits recorded from" : "Paid in by"}
            </p>
            {list.map((profile) => {
              const payments = profile.rows.filter(
                (row) =>
                  paymentGroup(row) === group && row.direction === "credit"
              )
              return (
                payments.length > 0 && (
                  <button
                    key={profile.id}
                    onClick={() =>
                      onOpen(
                        payments.map((row) => row.key),
                        `Payments from ${profile.name}`
                      )
                    }
                    className="finance-tint block w-full rounded-lg border p-3 text-left"
                    data-finance-tone="credit"
                  >
                    <strong className="block text-sm break-words">
                      {profile.name}
                    </strong>
                    {payments.some(
                      (row) =>
                        row.label_sources?.from_name?.source === "description"
                    ) && (
                      <span className="block text-xs text-muted-foreground">
                        Includes names suggested from descriptions
                      </span>
                    )}
                    <span className="finance-amount text-xs">
                      {payments.length} payments · {totalLabel(payments)}
                    </span>
                  </button>
                )
              )
            })}
            {!list.some((profile) =>
              profile.rows.some(
                (row) =>
                  paymentGroup(row) === group && row.direction === "credit"
              )
            ) && (
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
            {accounts
              .filter((account) =>
                account.rows.some((row) => paymentGroup(row) === group)
              )
              .map((account) => (
                <button
                  key={account.id}
                  className="block text-left text-sm font-semibold hover:underline break-words"
                  onClick={() =>
                    onOpen(
                      account.rows
                        .filter((row) => paymentGroup(row) === group)
                        .map((row) => row.key),
                      account.name
                    )
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
              const payments = profile.rows.filter(
                (row) =>
                  paymentGroup(row) === group && row.direction === "debit"
              )
              return (
                payments.length > 0 && (
                  <button
                    key={profile.id}
                    onClick={() =>
                      onOpen(
                        payments.map((row) => row.key),
                        `Payments to ${profile.name}`
                      )
                    }
                    className="finance-tint block w-full rounded-lg border p-3 text-left"
                    data-finance-tone="debit"
                  >
                    <strong className="block text-sm break-words">
                      {profile.name}
                    </strong>
                    {payments.some(
                      (row) =>
                        row.label_sources?.to_name?.source === "description"
                    ) && (
                      <span className="block text-xs text-muted-foreground">
                        Includes names suggested from descriptions
                      </span>
                    )}
                    <span className="finance-amount text-xs">
                      {payments.length} payments · {totalLabel(payments)}
                    </span>
                  </button>
                )
              )
            })}
            {!list.some((profile) =>
              profile.rows.some(
                (row) =>
                  paymentGroup(row) === group && row.direction === "debit"
              )
            ) && (
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
                    item.rows.map((row) => row.key),
                    item.label
                  )
                }
              >
                <strong className="block text-sm">{item.label}</strong>
                <span className="block text-sm">
                  {item.rows.length}{" "}
                  {item.rows.length === 1 ? "payment" : "payments"} ·{" "}
                  {totalLabel(item.rows)} ·{" "}
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
        <details>
          <summary className="cursor-pointer font-medium">
            Adjacent payments · timing comparisons
          </summary>
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
              Each comparison uses adjacent dated payments in the same bank
              account and currency. A receipt is followed by a payment within{" "}
              {view.days} days. This is a starting point for review, not a
              confirmed transfer. Credit card entries and unknown payment dates
              are not compared.
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
        </details>
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
