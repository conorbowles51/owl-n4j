import { useState, useEffect } from "react"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import type { Transaction } from "../api"

interface TransactionDetailPanelProps {
  transaction: Transaction
  onSave: (fields: {
    purpose?: string
    counterpartyDetails?: string
    notes?: string
  }) => void
}

export function TransactionDetailPanel({
  transaction,
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

        {/* Purpose */}
        <div>
          <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Purpose
          </label>
          <Input
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            onBlur={() => handleBlur("purpose", purpose, transaction.purpose)}
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
            className="h-16 resize-none text-xs"
            placeholder="Investigation notes..."
          />
        </div>
      </div>
    </div>
  )
}
