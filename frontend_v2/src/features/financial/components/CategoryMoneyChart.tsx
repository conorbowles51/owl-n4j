import { categoryAmounts } from "../lib/category-amounts"
import { useFinancialDraft } from "../stores/financial-drafts"
import type { LedgerTransaction } from "../api"
import { usePaymentCategory } from "../hooks/use-payment-categories"
import { chartRatio } from "../lib/investigator-workspace"
import { formatLedgerAmount } from "../lib/ledger-format"
import { PaymentSet } from "./InvestigationWorkspaceParts"
import { Button } from "@/components/ui/button"

export function CategoryMoneyChart({
  caseId,
  rows,
}: {
  caseId: string
  rows: LedgerTransaction[]
}) {
  const groups = categoryAmounts(rows)
  const [, setCategory] = usePaymentCategory(caseId)
  const [selected, setSelected] = useFinancialDraft<string | null>(
    caseId,
    "category-chart-selection",
    null
  )
  const [page, setPage] = useFinancialDraft(caseId, "category-chart-page", 0)
  const index = Math.min(page, Math.max(0, Math.ceil(groups.length / 12) - 1))
  const key = (group: (typeof groups)[number]) =>
    JSON.stringify([group.currency, group.card, group.category])
  const selectedGroup = groups.find((group) => key(group) === selected)
  const money = (value: bigint, currency: string) =>
    `${formatLedgerAmount(String(value), currency).text} ${currency}`
  return (
    <section
      className="rounded-xl border bg-card p-4 space-y-4"
      aria-label="Money by category"
    >
      <div>
        <h3 className="font-semibold">Money by category</h3>
        <p className="text-sm text-muted-foreground">
          Compare incoming and outgoing amounts. Select a category to see its
          transactions.
        </p>
      </div>
      {groups.slice(index * 12, (index + 1) * 12).map((group) => {
        const peers = groups.filter(
          (other) =>
            other.currency === group.currency && other.card === group.card
        )
        const maximum = peers.reduce(
          (max, other) =>
            other.credit > max || other.debit > max
              ? other.credit > other.debit
                ? other.credit
                : other.debit
              : max,
          1n
        )
        return (
          <div key={key(group)} className="space-y-1">
            <button
              className="font-medium underline text-left"
              onClick={() => setSelected(key(group))}
            >
              {group.category} · {group.currency}
              {group.card ? " · credit cards" : ""}
            </button>
            {(["credit", "debit"] as const).map((direction) => (
              <div
                key={direction}
                className="grid grid-cols-[7rem_1fr_minmax(8rem,auto)] items-center gap-3 text-sm"
              >
                <span>
                  {direction === "credit"
                    ? group.card
                      ? "Card credits"
                      : "Money in"
                    : group.card
                      ? "Card charges"
                      : "Money out"}
                </span>
                <div className="h-3 rounded bg-muted">
                  <div
                    className="h-3 rounded"
                    style={{
                      width: `${chartRatio(group[direction], maximum) * 100}%`,
                      backgroundColor: `var(--finance-${direction})`,
                    }}
                  />
                </div>
                <span className="tabular-nums text-right">
                  {money(group[direction], group.currency)}
                </span>
              </div>
            ))}
          </div>
        )
      })}
      {!groups.length && (
        <p>No transactions match the selected accounts, dates and category.</p>
      )}
      {groups.length > 12 && (
        <div className="flex gap-3 items-center">
          <Button
            variant="outline"
            disabled={!index}
            onClick={() => setPage(index - 1)}
          >
            Previous categories
          </Button>
          <span>
            {index * 12 + 1} to {Math.min((index + 1) * 12, groups.length)} of{" "}
            {groups.length}
          </span>
          <Button
            variant="outline"
            disabled={(index + 1) * 12 >= groups.length}
            onClick={() => setPage(index + 1)}
          >
            Next categories
          </Button>
        </div>
      )}
      {selectedGroup && (
        <div className="space-y-3">
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => setCategory(selectedGroup.category)}
            >
              Use this category across financial views
            </Button>
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Close category transactions
            </Button>
          </div>
          <PaymentSet
            caseId={caseId}
            rows={selectedGroup.rows}
            title={`${selectedGroup.category} transactions`}
          />
        </div>
      )}
    </section>
  )
}
