import type { LedgerTransaction } from "../api"
import { citationSchema } from "../lib/source-citation"
import { formatLedgerAmount } from "../lib/ledger-format"
import { CorrectionForm } from "./CorrectionForm"
import { TransactionNote } from "./TransactionNote"
import { SourceCustodyPanel } from "./SourceCustodyPanel"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { readLocator } from "../lib/locator"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { SourceAmountPanel } from "./SourceAmountPanel"

export function LedgerSourceDialog({
  caseId,
  transactionId,
  onClose,
  initialNoteOpen = false,
  onAdjudicate,
}: {
  caseId: string
  transactionId: string
  onClose: () => void
  initialNoteOpen?: boolean
  onAdjudicate?: (row: LedgerTransaction) => void
}) {
  const [replacement, setReplacement] = useState<string | null>(null)
  const [viewFile, setViewFile] = useState(false)
  const [assessAmount, setAssessAmount] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const source = useQuery({
    queryKey: ["ledger-source", caseId, transactionId],
    retry: false,
    queryFn: async () => {
      const data = citationSchema.parse(
        await fetchAPI(
          `/api/financial/ledger/${encodeURIComponent(transactionId)}/source?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (
        data.case_id !== caseId ||
        data.transaction_id !== transactionId ||
        (data.transaction &&
          (data.transaction.key !== transactionId ||
            data.transaction.case_id !== caseId ||
            data.transaction.source_document_id !== data.source_document_id)) ||
        (data.locator_state === "stored"
          ? !readLocator(data.locator).ok
          : data.locator !== null)
      )
        throw new Error(
          "Source citation is inconsistent. Reload the ledger before opening it."
        )
      return data
    },
  })
  const data = source.data
  const location = data ? readLocator(data.locator) : null
  const page =
    location?.ok && "page" in location.locator
      ? (location.locator.page ?? undefined)
      : undefined
  if (replacement)
    return (
      <LedgerSourceDialog
        key={replacement}
        caseId={caseId}
        transactionId={replacement}
        onClose={onClose}
        onAdjudicate={onAdjudicate}
      />
    )
  return (
    <>
      <Dialog
        open={!viewFile || source.isError}
        onOpenChange={(open) => !open && onClose()}
      >
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Transaction details</DialogTitle>
            <DialogDescription>
              Check the payment against its statement, record a note, or correct
              a value.
            </DialogDescription>
          </DialogHeader>
          {source.isPending && <p>Loading source citation…</p>}
          {source.isError && <p role="alert">{source.error.message}</p>}
          {data && !source.isError && (
            <>
              {data.transaction && (
                <section
                  className="rounded border p-3 space-y-2"
                  aria-label="Payment details"
                >
                  {data.transaction.account_label && (
                    <p className="text-sm">{data.transaction.account_label}</p>
                  )}
                  <h3 className="font-semibold">
                    {data.transaction.description || "No description recorded"}
                  </h3>
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt>Date</dt>
                      <dd>{data.transaction.ordering_date}</dd>
                    </div>
                    <div>
                      <dt>
                        {data.transaction.account_type === "credit_card"
                          ? data.transaction.direction === "credit"
                            ? "Card credit (reduces amount owed)"
                            : "Card charge (increases amount owed)"
                          : data.transaction.direction === "credit"
                            ? "Money in"
                            : "Money out"}
                      </dt>
                      <dd className="font-semibold">
                        {
                          formatLedgerAmount(
                            data.transaction.amount_minor,
                            data.transaction.currency
                          ).text
                        }{" "}
                        {data.transaction.currency}
                      </dd>
                    </div>
                    <div>
                      <dt>Paid by / paid to</dt>
                      <dd>
                        {data.transaction.counterparty_raw || "Not recorded"}
                      </dd>
                    </div>
                    <div>
                      <dt>Bank reference</dt>
                      <dd>
                        {data.transaction.bank_reference || "Not recorded"}
                      </dd>
                    </div>
                  </dl>
                  {data.transaction.ordering_date_context ===
                    "statement_end_ordering_only" && (
                    <p>
                      The statement end date is shown because a transaction date
                      was not recorded.
                    </p>
                  )}
                  {onAdjudicate &&
                    data.ledger_status === "admitted" &&
                    data.superseded_by_id === null && (
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (data.transaction) {
                            onClose()
                            onAdjudicate(data.transaction)
                          }
                        }}
                      >
                        Exclude from totals
                      </Button>
                    )}
                  {!correcting && (
                    <Button
                      variant="outline"
                      disabled={
                        data.ledger_status !== "admitted" ||
                        data.superseded_by_id !== null
                      }
                      onClick={() => setCorrecting(true)}
                    >
                      Correct a value
                    </Button>
                  )}
                  {correcting && (
                    <CorrectionForm
                      caseId={caseId}
                      transactionId={transactionId}
                      currency={data.transaction.currency}
                      initialRow={data.transaction}
                      initialDirection={
                        data.transaction.direction === "debit"
                          ? "debit"
                          : "credit"
                      }
                      onClose={() => {
                        setCorrecting(false)
                        void source.refetch()
                      }}
                    />
                  )}
                </section>
              )}
              <TransactionNote
                caseId={caseId}
                transactionId={transactionId}
                refId={data.ref_id}
                fileId={data.evidence_file_id}
                filename={data.filename}
                locator={data.locator}
                initialOpen={initialNoteOpen}
                transaction={data.transaction}
              />
              <details>
                <summary>File history and technical details</summary>
                <SourceCustodyPanel
                  caseId={caseId}
                  fileId={data.evidence_file_id}
                />
                <p className="text-sm text-muted-foreground">
                  {data.limitation}
                </p>
              </details>
              <p className="font-medium">
                {data.ref_id} · {data.filename}
              </p>
              {data.ledger_status === "superseded" && (
                <div className="space-y-2">
                  <p>This is the original transaction before correction.</p>
                  {data.superseded_by_id && (
                    <Button
                      variant="outline"
                      onClick={() => setReplacement(data.superseded_by_id)}
                    >
                      Open corrected transaction
                    </Button>
                  )}
                </div>
              )}
              {data.locator_state === "missing" && (
                <p>
                  No location was stored for this row. You can open the source
                  file.
                </p>
              )}
              {data.locator_state === "invalid" && (
                <p>
                  The stored location could not be read. You can open the source
                  file without a highlight.
                </p>
              )}
              {data.locator_state === "stored" && (
                <TransactionSourceHighlight
                  locatorPayload={data.locator}
                  sourceDocumentId={
                    data.filename.toLowerCase().endsWith(".pdf")
                      ? data.evidence_file_id
                      : undefined
                  }
                  valueLabel={data.ref_id}
                />
              )}
              <Button onClick={() => setViewFile(true)}>
                Open source file
              </Button>
              {assessAmount ? (
                <SourceAmountPanel
                  key={`${caseId}:${data.evidence_file_id}`}
                  caseId={caseId}
                  evidenceId={data.evidence_file_id}
                  onClose={() => setAssessAmount(false)}
                />
              ) : (
                <Button variant="outline" onClick={() => setAssessAmount(true)}>
                  Assess an amount in source text
                </Button>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
      {data && !source.isError && (
        <DocumentViewer
          open={viewFile}
          onOpenChange={setViewFile}
          documentUrl={evidenceAPI.getFileUrl(data.evidence_file_id)}
          documentName={data.filename}
          initialPage={page}
          navigationKey={`${caseId}:${transactionId}`}
        />
      )}
    </>
  )
}
