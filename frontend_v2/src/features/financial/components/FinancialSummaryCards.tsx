import { useMemo } from "react"
import type { Transaction, FinancialDatasetMode } from "../api"
import {
  formatEvidenceCents,
  summarizeEvidenceAmounts,
} from "../lib/evidence-amounts"

interface FinancialSummaryCardsProps {
  transactions: Transaction[]
  mode: FinancialDatasetMode
}

export function FinancialSummaryCards({
  transactions,
}: FinancialSummaryCardsProps) {
  const groups = useMemo(
    () => summarizeEvidenceAmounts(transactions),
    [transactions]
  )
  const names = new Set(
    transactions
      .flatMap((record) => [record.from_entity, record.to_entity])
      .map((entity) => entity?.key || entity?.name)
      .filter(Boolean)
  ).size
  return (
    <section
      aria-label="Other evidence totals"
      className="space-y-2 border-b px-4 py-3 text-sm"
    >
      <p>
        <strong>{transactions.length.toLocaleString()} records</strong> in this
        view · {names.toLocaleString()} recorded names
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              {[
                "Currency",
                "Records",
                "Positive amounts",
                "Negative amounts",
                "Sum of amounts",
              ].map((label) => (
                <th key={label} className="p-2 text-left">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.currency} className="border-t">
                <td className="p-2">{group.currency}</td>
                <td className="p-2">{group.count.toLocaleString()}</td>
                {[
                  group.positive,
                  group.negative,
                  group.positive + group.negative,
                ].map((value, index) => (
                  <td key={index} className="p-2 font-mono">
                    {group.incomplete
                      ? "Not totalled"
                      : formatEvidenceCents(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Amounts stay in their recorded currencies. Missing currencies or amounts
        that cannot be totalled exactly are not added together. These sums are
        not account balances.
      </p>
    </section>
  )
}
