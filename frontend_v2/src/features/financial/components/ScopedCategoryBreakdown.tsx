import { categoryTone } from "../lib/category-palette"
import { type CategoryTotal, useScopedCategoryTotals } from "../lib/category-totals"
import { formatLedgerAmount } from "../lib/ledger-format"

/** "Where the money went by category" for one account, statement or person: a table per currency, every number as text. */
export function CategoryBreakdownTable({
  title,
  rows,
  pending,
  error,
  onRetry,
}: {
  title: string
  rows: CategoryTotal[] | undefined
  pending?: boolean
  error?: string | null
  onRetry?: () => void
}) {
  const currencies = [...new Set((rows ?? []).map((row) => row.currency))]
  return (
    <section className="space-y-2 rounded-lg border p-3" aria-label={title}>
      <h4 className="font-semibold">{title}</h4>
      {pending && <p role="status">Adding up categories…</p>}
      {error && (
        <p role="alert" className="text-sm">
          Category totals could not be loaded. {error}{" "}
          {onRetry && (
            <button type="button" className="underline" onClick={onRetry}>
              Try again
            </button>
          )}
        </p>
      )}
      {rows && !rows.length && <p className="text-sm text-muted-foreground">No payments in this scope.</p>}
      {currencies.map((currency) => (
        <table key={currency} className="w-full text-sm" aria-label={`${title} · ${currency}`}>
          <thead>
            <tr className="border-b text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <th className="py-1 pr-2">Category · {currency}</th>
              <th className="py-1 pr-2 text-right">Money in</th>
              <th className="py-1 pr-2 text-right">Money out</th>
              <th className="py-1 text-right">Payments</th>
            </tr>
          </thead>
          <tbody>
            {rows!
              .filter((row) => row.currency === currency)
              .map((row) => (
                <tr key={row.category} className="border-b last:border-0">
                  <th className="py-1 pr-2 text-left font-medium">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        aria-hidden="true"
                        className={`size-2.5 rounded-full ${row.category === "Uncategorized" ? "border border-dashed border-muted-foreground" : ""}`}
                        style={row.category === "Uncategorized" ? undefined : { background: categoryTone(row.category).dot }}
                      />
                      {row.category}
                    </span>
                  </th>
                  <td className="py-1 pr-2 text-right tabular-nums text-[#12784a]">
                    {formatLedgerAmount(row.moneyIn.toString(), currency).text}
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums">
                    {formatLedgerAmount(row.moneyOut.toString(), currency).text}
                  </td>
                  <td className="py-1 text-right tabular-nums">{row.count}</td>
                </tr>
              ))}
          </tbody>
        </table>
      ))}
    </section>
  )
}

export function ScopedCategoryBreakdown({
  caseId,
  title,
  scope,
}: {
  caseId: string
  title: string
  scope: { account_ids?: string[]; source_document_ids?: string[] }
}) {
  const totals = useScopedCategoryTotals(caseId, scope)
  return (
    <CategoryBreakdownTable
      title={title}
      rows={totals.data}
      pending={totals.isPending}
      error={totals.isError ? totals.error.message : null}
      onRetry={() => void totals.refetch()}
    />
  )
}
