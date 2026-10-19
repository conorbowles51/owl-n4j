import { useState } from "react"
import type { SummaryContribution } from "../lib/summary-contributions"
import { Button } from "@/components/ui/button"
import { correctionMoney } from "../lib/correction-contract"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

export function SummaryContributions({
  caseId,
  currency,
  rows,
  direction,
  onClose,
}: {
  caseId: string
  currency: string
  rows: SummaryContribution[]
  direction: "credit" | "debit" | "all"
  onClose: () => void
}) {
  const [page, setPage] = useState(0)
  const [source, setSource] = useState<string | null>(null)
  const selected = rows.filter(
    (r) =>
      r.currency === currency &&
      (direction === "all" || r.direction === direction)
  )
  return (
    <section
      aria-label={`${currency} contributing readings`}
      className="space-y-2 rounded border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold">
          {currency} ·{" "}
          {direction === "all"
            ? "Net posting"
            : direction === "credit"
              ? "Credit"
              : "Debit"}{" "}
          sources
        </h4>
        <Button variant="ghost" onClick={onClose}>
          Close contributing readings
        </Button>
      </div>
      <p>
        {selected.length} contributing readings. Amounts and classifications
        were captured with this total. Ordering dates may differ from printed
        dates.
      </p>
      {selected.length === 0 ? (
        <p>No readings contribute to this side of the total.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left">Reading</th>
                  <th className="text-left">Ordering date</th>
                  <th className="text-left">Direction</th>
                  <th className="text-right">Amount</th>
                  <th>Row / source class</th>
                  <th>Original</th>
                </tr>
              </thead>
              <tbody>
                {selected.slice(page * 25, (page + 1) * 25).map((row) => (
                  <tr key={row.transaction_id} className="border-t">
                    <td>{row.ref_id}</td>
                    <td>{row.ordering_date ?? "Unknown"}</td>
                    <td>{row.direction}</td>
                    <td className="text-right tabular-nums">
                      {correctionMoney(row.amount_minor, currency)}
                    </td>
                    <td className="text-center">
                      {row.proof_class.toUpperCase()} /{" "}
                      {row.source_proof_class.toUpperCase()}
                    </td>
                    <td>
                      <Button
                        variant="outline"
                        onClick={() => setSource(row.transaction_id)}
                        aria-label={`Open source ${row.ref_id}`}
                      >
                        View source
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous contributing readings
            </Button>
            <span>
              {page * 25 + 1}–{Math.min((page + 1) * 25, selected.length)} of{" "}
              {selected.length}
            </span>
            <Button
              variant="outline"
              disabled={(page + 1) * 25 >= selected.length}
              onClick={() => setPage((p) => p + 1)}
            >
              Next contributing readings
            </Button>
          </div>
        </>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </section>
  )
}
