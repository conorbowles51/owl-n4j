import { useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import type { StatementFile } from "../hooks/use-statement-register"
import { FinancialFileAction } from "./FinancialFileAction"
import { isSpreadsheetName } from "../lib/spreadsheet-layout"
import { SendToLedgerDialog } from "./SendToLedgerDialog"

/** A source may contain financial evidence without being a PDF statement. */
export function FinancialSourceFile({
  caseId,
  file,
  importedPayments = 0,
  onVisibilityChanged,
}: {
  caseId: string
  file: StatementFile
  importedPayments?: number
  onVisibilityChanged?: (removed: boolean) => void
}) {
  const legacyOffice = /\.doc$/i.test(file.original_filename)
  const spreadsheet = isSpreadsheetName(file.original_filename)
  const { canEdit } = useFinancialAccess()
  const [reading, setReading] = useState(false)
  return (
    <article
      aria-label={`Financial source ${file.original_filename}`}
      className="rounded-lg border bg-card p-4 space-y-3"
    >
      <h3 className="font-medium break-words">{file.original_filename}</h3>
      <p className="text-sm">
        {file.financial_removed
          ? "Removed from Financial"
          : `Source selected for Financial · Evidence processing: ${file.status}`}
        {importedPayments > 0 ? ` · ${importedPayments} imported payments` : ""}
      </p>
      <p className="text-sm text-muted-foreground">
        Review the original content in Evidence. Adding this source to Financial
        does not import transactions.
        {spreadsheet
          ? " If it is a bank or payment-app statement, choose Read as a statement to check which column holds the date and the money, and every line, before anything is added."
          : legacyOffice
            ? " This reader requires DOC to be converted to DOCX or PDF. Keep the original as evidence."
            : " Use the file’s processing controls in Evidence to read its contents or check progress. Reader support depends on the format."}
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <Link
          className="text-sm underline"
          to={`/cases/${caseId}/evidence?file=${encodeURIComponent(file.id)}&from=financial`}
        >
          Open source in Evidence
        </Link>
        {spreadsheet && canEdit && !file.financial_removed && (
          <Button
            variant="outline"
            size="sm"
            data-testid="read-spreadsheet-statement"
            onClick={() => setReading(true)}
          >
            Read as a statement
          </Button>
        )}
        <FinancialFileAction
          caseId={caseId}
          file={file}
          onVisibilityChanged={onVisibilityChanged}
        />
      </div>
      {reading && (
        <SendToLedgerDialog
          caseId={caseId}
          fileId={file.id}
          fileName={file.original_filename}
          open
          onClose={() => setReading(false)}
        />
      )}
    </article>
  )
}
