import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { LedgerPanel } from "./LedgerPanel"
import { CorrectionForm } from "./CorrectionForm"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { SavedStatementRecovery } from "./SavedStatementRecovery"

/** The saved-record recovery path lives inside the statement's review. */
export function SavedStatementPayments({
  caseId,
  sourceId,
  hasIncomplete,
}: {
  caseId: string
  sourceId: string
  hasIncomplete: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const [open, setOpen] = useState(false)
  const [correcting, setCorrecting] = useState<LedgerTransaction | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const editor = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!correcting) return
    editor.current?.focus({ preventScroll: true })
    editor.current?.scrollIntoView({ block: "center" })
  }, [correcting])
  return (
    <section className="space-y-3" aria-label="Review saved statement payments">
      <p className="text-sm">
        Correct saved payments here, beside their source. The extraction shown
        further down is a new reading for comparison; editing it would require a
        reviewed replacement.
      </p>
      <Button
        variant="outline"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open
          ? "Close saved payment review"
          : "Review or correct saved payments"}
      </Button>
      {canEdit && (
        <SavedStatementRecovery caseId={caseId} sourceId={sourceId} />
      )}
      {open && (
        <div className="space-y-3">
          {hasIncomplete && (
            <ImportedRecordsPanel
              caseId={caseId}
              params={{ sourceDocumentId: sourceId }}
              onOpen={setSource}
            />
          )}
          {correcting && (
            <div ref={editor} tabIndex={-1}>
              <CorrectionForm
                key={correcting.key}
                caseId={caseId}
                transactionId={correcting.key}
                currency={correcting.currency}
                initialRow={correcting}
                initialDirection={
                  correcting.direction === "debit" ? "debit" : "credit"
                }
                onClose={() => setCorrecting(null)}
              />
            </div>
          )}
          <LedgerPanel
            caseId={caseId}
            params={{ sourceDocumentId: sourceId }}
            onCorrect={canEdit ? setCorrecting : undefined}
            onSource={(row) => setSource(row.key)}
            splitAmounts
          />
          {source && (
            <LedgerSourceDialog
              caseId={caseId}
              transactionId={source}
              onClose={() => setSource(null)}
              inline
              allowNearby={false}
            />
          )}
        </div>
      )}
    </section>
  )
}
