import { useMediaQuery } from "@/hooks/use-media-query"
import { useFinancialDraft } from "../stores/financial-drafts"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
import { useFinancialAccess } from "../hooks/use-financial-access"
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
  investigation?: boolean
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
  investigation = false,
}: {
  caseId: string | undefined
  onAdjudicate: (row: LedgerTransaction) => void
  investigation?: boolean
  heldOut?: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const [params, setParams] = useInvestigationScope(caseId)
  const [selected, setSelected] = useState<LedgerTransaction | null>(null)
  const wide = useMediaQuery("(min-width: 1280px)")
  const [source, setSource] = useFinancialDraft<{
    caseId: string
    transactionId: string
    note?: boolean
  } | null>(
    caseId || "none",
    `open-payment:${heldOut ? "excluded" : investigation ? "investigation" : "ledger"}`,
    null
  )
  const Panel = heldOut ? QuarantinePanel : LedgerPanel
  return (
    <div className="space-y-3">
      {caseId && !heldOut && (
        <>
          {investigation ? (
            <WorkspaceScope caseId={caseId} />
          ) : (
            <InvestigationFilters
              key={JSON.stringify(params)}
              caseId={caseId}
              initialParams={params}
              onApply={setParams}
            />
          )}
          {!investigation && (
            <LedgerSummaryPanel
              caseId={caseId}
              params={params}
              population="working"
              compact
            />
          )}
        </>
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
      <div
        className={
          source && investigation && wide
            ? "grid grid-cols-[minmax(0,1.2fr)_minmax(370px,0.8fr)] gap-4 items-start"
            : ""
        }
      >
        <div className="min-w-0">
          <Panel
            splitAmounts
            investigation={investigation}
            caseId={caseId}
            params={heldOut ? undefined : params}
            onAdjudicate={canEdit ? onAdjudicate : undefined}
            onCorrect={!canEdit || selected ? undefined : setSelected}
            onNote={
              canEdit
                ? (row) =>
                    caseId &&
                    setSource({ caseId, transactionId: row.key, note: true })
                : undefined
            }
            onSource={(row) =>
              caseId && setSource({ caseId, transactionId: row.key })
            }
          />
        </div>
        {source && source.caseId === caseId && (
          <LedgerSourceDialog
            inline={investigation && wide}
            key={`${source.caseId}:${source.transactionId}`}
            caseId={source.caseId}
            transactionId={source.transactionId}
            initialNoteOpen={source.note}
            onAdjudicate={canEdit ? onAdjudicate : undefined}
            onClose={() => setSource(null)}
          />
        )}
      </div>
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
