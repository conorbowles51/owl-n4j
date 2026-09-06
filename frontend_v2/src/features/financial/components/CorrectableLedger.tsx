import { useState } from "react"
import type { LedgerTransaction } from "../api"
import { CorrectionForm } from "./CorrectionForm"
import { LedgerPanel } from "./LedgerPanel"

export function CorrectableLedger({
  caseId,
  onAdjudicate,
}: {
  caseId: string | undefined
  onAdjudicate: (row: LedgerTransaction) => void
}) {
  const [selected, setSelected] = useState<LedgerTransaction | null>(null)
  return (
    <div className="space-y-3">
      {selected && caseId && (
        <CorrectionForm
          key={`${caseId}:${selected.key}`}
          caseId={caseId}
          transactionId={selected.key}
          currency={selected.currency}
          initialDirection={selected.direction === "debit" ? "debit" : "credit"}
          onClose={() => setSelected(null)}
        />
      )}
      <LedgerPanel
        caseId={caseId}
        onAdjudicate={onAdjudicate}
        onCorrect={selected ? undefined : setSelected}
      />
    </div>
  )
}
