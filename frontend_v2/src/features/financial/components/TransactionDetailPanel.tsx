import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { Transaction } from "../api"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { formatEvidenceAmount } from "../lib/evidence-amounts"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"

interface TransactionDetailPanelProps {
  transaction: Transaction
  editable?: boolean
  onSave: (fields: {
    purpose?: string
    counterpartyDetails?: string
    notes?: string
  }) => void
}

interface TransactionDraft {
  sourceKey: string
  purpose: string
  counterparty: string
  notes: string
}

function amountValueLabel(transaction: Transaction): string {
  const formatted = formatEvidenceAmount(
    transaction.amount,
    transaction.currency
  )
  return `the ${formatted} amount`
}

const readingLabels = {
  documentary: "From a document",
  derived: "Calculated from other records",
  narrative: "Reported in text",
  unknown: "Not recorded",
}

function createTransactionDraft(transaction: Transaction): TransactionDraft {
  return {
    sourceKey: JSON.stringify([
      transaction.key,
      transaction.purpose ?? "",
      transaction.counterparty_details ?? "",
      transaction.notes ?? "",
    ]),
    purpose: transaction.purpose || "",
    counterparty: transaction.counterparty_details || "",
    notes: transaction.notes || "",
  }
}

export function TransactionDetailPanel({
  transaction,
  editable = true,
  onSave,
}: TransactionDetailPanelProps) {
  const [viewFile, setViewFile] = useState(false)
  const sourceDraft = createTransactionDraft(transaction)
  const [draft, setDraft] = useState(sourceDraft)
  const activeDraft =
    draft.sourceKey === sourceDraft.sourceKey ? draft : sourceDraft
  const { purpose, counterparty, notes } = activeDraft
  const updateDraft = (
    updates: Partial<Omit<TransactionDraft, "sourceKey">>
  ) => {
    setDraft((current) => ({
      ...(current.sourceKey === sourceDraft.sourceKey ? current : sourceDraft),
      ...updates,
    }))
  }

  const handleBlur = (
    field: "purpose" | "counterpartyDetails" | "notes",
    value: string,
    original: string | undefined
  ) => {
    if (value !== (original || "")) {
      onSave({ [field]: value })
    }
  }

  return (
    <section
      aria-label={`Record details for ${transaction.name || transaction.key}`}
      className="border-t border-border bg-muted/30 px-6 py-3"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* AI Summary */}
        {transaction.summary && (
          <div className="md:col-span-3">
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              AI Summary
            </label>
            <p className="text-xs text-muted-foreground italic">
              {transaction.summary}
            </p>
          </div>
        )}

        <div className="md:col-span-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <MetadataField
            label="Record type"
            value={transaction.financial_record_kind.replaceAll("_", " ")}
          />
          <MetadataField
            label="How recorded"
            value={
              transaction.evidence_strength
                ? readingLabels[transaction.evidence_strength]
                : "Not recorded"
            }
          />
          <MetadataField
            label="Source type"
            value={
              transaction.evidence_source_type?.replaceAll("_", " ") ||
              "Not recorded"
            }
          />
          <MetadataField
            label="Original file"
            value={transaction.source_filename || "Not recorded"}
          />
          <MetadataField
            label="Page"
            value={
              transaction.source_page
                ? String(transaction.source_page)
                : "Unknown"
            }
          />
          <MetadataField
            label="Recorded amount"
            value={formatEvidenceAmount(
              transaction.amount,
              transaction.currency
            )}
          />
        </div>

        {transaction.amount === null && transaction.raw_amount != null && (
          <div className="md:col-span-3 rounded border p-3 text-sm">
            <p>
              Amount needs review. The saved text could not be used as a numeric
              amount.
            </p>
            <p className="mt-1 whitespace-pre-wrap break-words">
              Saved amount text: {transaction.raw_amount || "(blank)"}
            </p>
            <p className="mt-1">
              Compare it with the original file, then select the amount in the
              record row to enter a correction if you can edit this case.
            </p>
          </div>
        )}
        {transaction.source_excerpt && (
          <div className="md:col-span-3">
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Source Excerpt
            </label>
            <p className="text-xs text-muted-foreground">
              {transaction.source_excerpt}
            </p>
          </div>
        )}

        {/* Source */}
        <div className="md:col-span-3">
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Source
          </label>
          <TransactionSourceHighlight
            locatorPayload={transaction.locator}
            sourceDocumentId={transaction.source_document_id}
            valueLabel={amountValueLabel(transaction)}
          />
          {transaction.source_document_id ? (
            <>
              <Button
                className="mt-3"
                variant="outline"
                onClick={() => setViewFile(true)}
              >
                Open original file
              </Button>
              <DocumentViewer
                open={viewFile}
                onOpenChange={setViewFile}
                documentUrl={evidenceAPI.getFileUrl(
                  transaction.source_document_id
                )}
                documentName={transaction.source_filename || "Original file"}
                initialPage={
                  transaction.source_page && transaction.source_page > 0
                    ? transaction.source_page
                    : 1
                }
                navigationKey={transaction.key}
                evidenceId={transaction.source_document_id}
              />
            </>
          ) : (
            <p className="mt-2 text-sm">
              The original file is not linked to this record. Open Evidence to
              find the source.
            </p>
          )}
        </div>

        {/* Purpose */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Purpose
          </label>
          {editable ? (
            <Input
              value={purpose}
              onChange={(e) => updateDraft({ purpose: e.target.value })}
              onBlur={() => handleBlur("purpose", purpose, transaction.purpose)}
              disabled={!editable}
              className="h-7 text-xs"
              placeholder="Transaction purpose..."
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap break-words">
              {purpose || "Not recorded"}
            </p>
          )}
        </div>

        {/* Counterparty Details */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Counterparty Details
          </label>
          {editable ? (
            <Input
              value={counterparty}
              onChange={(e) => updateDraft({ counterparty: e.target.value })}
              onBlur={() =>
                handleBlur(
                  "counterpartyDetails",
                  counterparty,
                  transaction.counterparty_details
                )
              }
              disabled={!editable}
              className="h-7 text-xs"
              placeholder="Counterparty info..."
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap break-words">
              {counterparty || "Not recorded"}
            </p>
          )}
        </div>

        {/* Notes */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Notes
          </label>
          {editable ? (
            <Textarea
              value={notes}
              onChange={(e) => updateDraft({ notes: e.target.value })}
              onBlur={() => handleBlur("notes", notes, transaction.notes)}
              disabled={!editable}
              className="h-16 resize-none text-xs"
              placeholder="Investigation notes..."
            />
          ) : (
            <p className="text-sm whitespace-pre-wrap break-words">
              {notes || "Not recorded"}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

function MetadataField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <p className="text-sm text-foreground break-words">{value}</p>
    </div>
  )
}
