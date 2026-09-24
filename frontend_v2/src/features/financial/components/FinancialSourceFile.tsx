import { Link } from "react-router-dom"
import type { StatementFile } from "../hooks/use-statement-register"
import { FinancialFileAction } from "./FinancialFileAction"

/** A source may contain financial evidence without being a PDF statement. */
export function FinancialSourceFile({
  caseId,
  file,
  importedPayments = 0,
}: {
  caseId: string
  file: StatementFile
  importedPayments?: number
}) {
  const legacyOffice = /\.(xls|doc)$/i.test(file.original_filename)
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
        {legacyOffice
          ? " This reader requires XLS to be converted to XLSX or CSV, and DOC to DOCX or PDF. Keep the original as evidence."
          : " Use the file’s processing controls in Evidence to read its contents or check progress. Reader support depends on the format."}
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <Link
          className="text-sm underline"
          to={`/cases/${caseId}/evidence?file=${encodeURIComponent(file.id)}&from=financial`}
        >
          Open source in Evidence
        </Link>
        <FinancialFileAction caseId={caseId} file={file} />
      </div>
    </article>
  )
}
