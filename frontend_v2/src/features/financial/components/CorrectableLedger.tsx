import { useState } from "react"
import type { LedgerTransaction } from "../api"
import { CorrectionForm } from "./CorrectionForm"
import { LedgerPanel } from "./LedgerPanel"
import { QuarantinePanel } from "./QuarantinePanel"

export function CorrectableLedger({
  caseId,
  onAdjudicate,
  heldOut = false,
}: {
  caseId: string | undefined
  onAdjudicate: (row: LedgerTransaction) => void
  heldOut?: boolean
}) {
  const [selected, setSelected] = useState<LedgerTransaction | null>(null)
  const Panel = heldOut ? QuarantinePanel : LedgerPanel
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
      <Panel
        caseId={caseId}
        onAdjudicate={onAdjudicate}
        onCorrect={selected ? undefined : setSelected}
      />
    </div>
  )
}
