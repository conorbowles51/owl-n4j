import { useState } from "react"
import { useInvestigationScope } from "../stores/investigation-scope"
import { RequestedCoveragePanel } from "./RequestedCoveragePanel"
import { LedgerTrendsPanel } from "./LedgerTrendsPanel"
import { LedgerSummaryPanel } from "./LedgerSummaryPanel"
import { LedgerExportButton } from "./LedgerExportButton"
import { InvestigationFilters } from "./InvestigationFilters"
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
  const [params, setParams] = useInvestigationScope(caseId)
  const [selected, setSelected] = useState<LedgerTransaction | null>(null)
  const [source, setSource] = useState<{
    caseId: string
    transactionId: string
    note?: boolean
  } | null>(null)
  const Panel = heldOut ? QuarantinePanel : LedgerPanel
  return (
    <div className="space-y-3">
      {caseId && !heldOut && (
        <>
          <InvestigationFilters
            key={JSON.stringify(params)}
            caseId={caseId}
            initialParams={params}
            onApply={setParams}
          />
          <LedgerSummaryPanel
            caseId={caseId}
            params={params}
            population="working"
            compact
          />
        </>
      )}
      {source && source.caseId === caseId && (
        <LedgerSourceDialog
          key={`${source.caseId}:${source.transactionId}`}
          caseId={source.caseId}
          transactionId={source.transactionId}
          initialNoteOpen={source.note}
          onClose={() => setSource(null)}
        />
      )}
      {selected && caseId && (
        <CorrectionForm
          key={`${caseId}:${selected.key}`}
          caseId={caseId}
          transactionId={selected.key}
          currency={selected.currency}
          initialRow={selected}
          initialDirection={selected.direction === "debit" ? "debit" : "credit"}
          onClose={() => setSelected(null)}
        />
      )}
      <Panel
        splitAmounts
        caseId={caseId}
        params={heldOut ? undefined : params}
        onAdjudicate={onAdjudicate}
        onCorrect={selected ? undefined : setSelected}
        onNote={(row) =>
          caseId && setSource({ caseId, transactionId: row.key, note: true })
        }
        onSource={(row) =>
          caseId && setSource({ caseId, transactionId: row.key })
        }
      />
      {caseId && !heldOut && (
        <details className="rounded border p-3">
          <summary className="cursor-pointer font-medium">
            Reports, balance coverage and verification details
          </summary>
          <div className="space-y-3 pt-3">
            <LedgerExportButton caseId={caseId} params={params} />
            <RequestedCoveragePanel caseId={caseId} params={params} />
            <LedgerSummaryPanel caseId={caseId} params={params} />
            <LedgerTrendsPanel
              caseId={caseId}
              params={params}
              population="working"
            />
          </div>
        </details>
      )}
    </div>
  )
}
