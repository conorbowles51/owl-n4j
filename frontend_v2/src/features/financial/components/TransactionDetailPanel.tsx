import { useState, useEffect } from "react"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { Transaction } from "../api"

interface TransactionDetailPanelProps {
  transaction: Transaction
  editable?: boolean
  onSave: (fields: {
    purpose?: string
    counterpartyDetails?: string
    notes?: string
  }) => void
}

export function TransactionDetailPanel({
  transaction,
  editable = true,
  onSave,
}: TransactionDetailPanelProps) {
  const [purpose, setPurpose] = useState(transaction.purpose || "")
  const [counterparty, setCounterparty] = useState(
    transaction.counterparty_details || ""
  )
  const [notes, setNotes] = useState(transaction.notes || "")

  useEffect(() => {
    setPurpose(transaction.purpose || "")
    setCounterparty(transaction.counterparty_details || "")
    setNotes(transaction.notes || "")
  }, [transaction.key, transaction.purpose, transaction.counterparty_details, transaction.notes])

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
    <div className="border-t border-border bg-muted/30 px-6 py-3">
      <div className="grid grid-cols-3 gap-4">
        {/* AI Summary */}
        {transaction.summary && (
          <div className="col-span-3">
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              AI Summary
            </label>
            <p className="text-xs text-muted-foreground italic">
              {transaction.summary}
            </p>
          </div>
        )}

        <div className="col-span-3 grid grid-cols-5 gap-3">
          <MetadataField label="Record Kind" value={transaction.financial_record_kind.replaceAll("_", " ")} />
          <MetadataField label="Evidence Strength" value={transaction.evidence_strength || "legacy"} />
          <MetadataField label="Source Type" value={transaction.evidence_source_type?.replaceAll("_", " ") || "legacy"} />
          <MetadataField label="Source File" value={transaction.source_filename || "Unavailable"} />
          <MetadataField label="Page" value={transaction.source_page ? String(transaction.source_page) : "Unknown"} />
        </div>

        {transaction.source_excerpt && (
          <div className="col-span-3">
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Source Excerpt
            </label>
            <p className="text-xs text-muted-foreground">{transaction.source_excerpt}</p>
          </div>
        )}

        {/* Purpose */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Purpose
          </label>
          <Input
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            onBlur={() => handleBlur("purpose", purpose, transaction.purpose)}
            disabled={!editable}
            className="h-7 text-xs"
            placeholder="Transaction purpose..."
          />
        </div>

        {/* Counterparty Details */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Counterparty Details
          </label>
          <Input
            value={counterparty}
            onChange={(e) => setCounterparty(e.target.value)}
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
        </div>

        {/* Notes */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Notes
          </label>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() => handleBlur("notes", notes, transaction.notes)}
            disabled={!editable}
            className="h-16 resize-none text-xs"
            placeholder="Investigation notes..."
          />
        </div>
      </div>
    </div>
  )
}

function MetadataField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      <p className="text-xs text-foreground">{value}</p>
    </div>
  )
}
