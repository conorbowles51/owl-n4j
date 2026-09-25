export function StatementRowCorrectionStatus({
  rowId,
  original,
  reviewed,
  saved,
  saving,
  newer,
  failed,
  pendingChecks,
  checksError,
  canImport,
  problems,
}: {
  rowId: string
  original: string
  reviewed: string
  saved: boolean
  saving: boolean
  newer: boolean
  failed: boolean
  pendingChecks: boolean
  checksError: boolean
  canImport: boolean
  problems: string[]
}) {
  return (
    <div
      role="note"
      aria-label={`Balance correction ${rowId}`}
      className="rounded border bg-background p-2 text-sm font-sans space-y-1"
    >
      <p className="text-muted-foreground">
        Original reading: <q>{original}</q>. Retained for comparison.
      </p>
      <p className="font-medium">Reviewed balance: {reviewed}</p>
      <p>
        {saved
          ? "Row correction saved to the case."
          : saving
            ? newer
              ? "New row edits are not included in the save in progress."
              : "Saving this row with all review progress…"
            : failed
              ? "Save not confirmed. Keep these edits and retry Save progress."
              : "Row changes are not yet saved to the case."}
      </p>
      <p className="text-muted-foreground">
        {pendingChecks
          ? "Checking the current review…"
          : checksError
            ? "Current checks are unavailable. Saving progress does not confirm reconciliation."
            : canImport
              ? "Current statement checks allow import."
              : problems.length
                ? `Still needs review: ${problems.join(" ")}`
                : "The statement still needs review before import. See the current checks above."}
      </p>
    </div>
  )
}
