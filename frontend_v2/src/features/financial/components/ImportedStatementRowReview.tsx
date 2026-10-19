import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { SavedStatementPayments } from "./SavedStatementPayments"

/** Original row IDs can change between readings. Never guess a ledger match. */
export function ImportedStatementRowReview({
  caseId,
  sourceId,
  hasIncomplete,
  page,
  issues,
  onShowSource,
}: {
  caseId: string
  sourceId: string
  hasIncomplete: boolean
  page: number
  issues: string[]
  onShowSource: () => void
}) {
  const { canEdit } = useFinancialAccess()
  const [open, setOpen] = useState(false)
  const destination = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    destination.current?.focus({ preventScroll: true })
    destination.current?.scrollIntoView({ block: "nearest" })
  }, [open])
  return (
    <div className="space-y-2 text-sm">
      {issues.map((issue, index) => (
        <p key={index}>Original extraction flag: {issue}</p>
      ))}
      <p>
        This statement has already been imported. Compare this original reading
        on page {page} with the saved records below. Corrections belong to the
        saved payment; the original text stays unchanged.
      </p>
      {!canEdit && <p>You have view-only access to this case.</p>}
      <Button
        ref={trigger}
        size="sm"
        variant="outline"
        aria-expanded={open}
        onClick={() => {
          onShowSource()
          setOpen(true)
        }}
      >
        {canEdit ? "Review or fix saved records" : "View saved records"}
      </Button>
      {open && (
        <div
          ref={destination}
          tabIndex={-1}
          role="region"
          aria-label="Saved records for this flagged reading"
          className="rounded border p-3 space-y-3"
        >
          <p>
            Only this saved statement is shown. Match the date, description and
            source before editing. If the payment is missing, review any
            incomplete records or use Add a missed transaction after checking
            the original.
          </p>
          <Button
            size="sm"
            variant="outline"
            className="sticky top-0 z-10 bg-background"
            onClick={() => {
              setOpen(false)
              trigger.current?.focus({ preventScroll: true })
              trigger.current?.scrollIntoView({ block: "nearest" })
            }}
          >
            Return to original row
          </Button>
          <SavedStatementPayments
            caseId={caseId}
            sourceId={sourceId}
            hasIncomplete={hasIncomplete}
            initiallyOpen
          />
        </div>
      )}
    </div>
  )
}
