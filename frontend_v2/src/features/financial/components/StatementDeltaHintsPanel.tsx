import { useState } from "react"
import { Button } from "@/components/ui/button"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { correctionMoney } from "../lib/correction-contract"
import type { StatementDeltaHints } from "../lib/statement-delta-hints"

export function StatementDeltaHintsPanel({
  caseId,
  currency,
  hints,
}: {
  caseId: string
  currency: string
  hints: StatementDeltaHints
}) {
  const [source, setSource] = useState<string | null>(null),
    [page, setPage] = useState(0)
  if (!hints.available)
    return <p>Discrepancy leads unavailable: {hints.reason}</p>
  if (hints.difference_minor === "0") return null
  return (
    <section
      aria-label="Statement discrepancy leads"
      className="space-y-2 rounded border p-3"
    >
      <h5 className="font-medium">Amounts worth checking</h5>
      <p>{hints.limitation}</p>
      <p>
        {hints.rows_checked} current admitted rows checked against the
        difference of {correctionMoney(hints.difference_minor, currency)}.
      </p>
      {!hints.candidates.length && (
        <p>No checked row amount provides a simple arithmetic explanation.</p>
      )}
      {hints.candidates.slice(page * 10, page * 10 + 10).map((c) => (
        <div key={c.transaction_id} className="rounded border p-2">
          <p>
            {c.ref_id}: {correctionMoney(c.amount_minor, currency)}{" "}
            {c.direction}
          </p>
          <p>{c.explanation}</p>
          <Button onClick={() => setSource(c.transaction_id)}>
            Inspect lead {c.ref_id}
          </Button>
        </div>
      ))}
      {hints.candidates.length > 10 && (
        <div className="flex items-center gap-2">
          <Button disabled={!page} onClick={() => setPage((p) => p - 1)}>
            Previous leads
          </Button>
          <span>
            Leads {page * 10 + 1}–
            {Math.min(page * 10 + 10, hints.candidates.length)} of{" "}
            {hints.candidates.length}
          </span>
          <Button
            disabled={(page + 1) * 10 >= hints.candidates.length}
            onClick={() => setPage((p) => p + 1)}
          >
            Next leads
          </Button>
        </div>
      )}
      {hints.signatures.map((s) => (
        <p key={s.kind}>{s.explanation}</p>
      ))}
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
