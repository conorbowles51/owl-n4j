import { useState } from "react"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { LedgerFilters } from "./LedgerFilters"
import type { LedgerTransaction } from "../api"
import { CorrectionForm } from "./CorrectionForm"
import { LedgerPanel } from "./LedgerPanel"
import { QuarantinePanel } from "./QuarantinePanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

export function CorrectableLedger(props: {
  caseId: string | undefined
  onAdjudicate: (row: LedgerTransaction) => void
  heldOut?: boolean
}) {
  return (
    <CorrectableLedgerContent
      key={`${props.caseId}:${props.heldOut}`}
      {...props}
    />
  )
}

function CorrectableLedgerContent({
  caseId,
  onAdjudicate,
  heldOut = false,
}: {
  caseId: string | undefined
  onAdjudicate: (row: LedgerTransaction) => void
  heldOut?: boolean
}) {
  const [params, setParams] = useState<LedgerQueryParams>({})
  const [selected, setSelected] = useState<LedgerTransaction | null>(null)
  const [source, setSource] = useState<{
    caseId: string
    transactionId: string
  } | null>(null)
  const Panel = heldOut ? QuarantinePanel : LedgerPanel
  return (
    <div className="space-y-3">
      {caseId && !heldOut && (
        <LedgerFilters caseId={caseId} onApply={setParams} />
      )}
      {source && source.caseId === caseId && (
        <LedgerSourceDialog
          key={`${source.caseId}:${source.transactionId}`}
          caseId={source.caseId}
          transactionId={source.transactionId}
          onClose={() => setSource(null)}
        />
      )}
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
        params={heldOut ? undefined : params}
        onAdjudicate={onAdjudicate}
        onCorrect={selected ? undefined : setSelected}
        onSource={(row) =>
          caseId && setSource({ caseId, transactionId: row.key })
        }
      />
    </div>
  )
}
