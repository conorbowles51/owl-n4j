import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { LedgerTransaction } from "../api"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { LedgerPanel } from "./LedgerPanel"
import { CorrectionForm } from "./CorrectionForm"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { SavedStatementRecovery } from "./SavedStatementRecovery"
import { AddSavedStatementPayment } from "./AddSavedStatementPayment"

/** The saved-record recovery path lives inside the statement's review. */
export function SavedStatementPayments({
  caseId,
  sourceId,
  hasIncomplete,
  initiallyOpen = false,
}: {
  caseId: string
  sourceId: string
  hasIncomplete: boolean
  initiallyOpen?: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const [open, setOpen] = useState(initiallyOpen)
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
        Review saved payments here, beside their source. Original extraction
        flags are retained for comparison and do not show whether a saved
        payment has since been corrected. Choose the matching saved record to
        inspect its current values.
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
        <AddSavedStatementPayment
          caseId={caseId}
          sourceId={sourceId}
          onSaved={(id) => {
            setOpen(true)
            setSource(id)
          }}
        />
      )}
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
            independentFilters
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
