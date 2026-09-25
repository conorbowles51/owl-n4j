import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import {
  duplicateRowsLabel,
  duplicateStatementLabel,
  type DuplicateDocument,
} from "../lib/duplicate-format"
import {
  FinancialAccessContext,
  useFinancialAccess,
} from "../hooks/use-financial-access"
import { StatementSourceButton } from "./StatementSourceButton"

export function DuplicateDocumentContext({
  caseId,
  document,
  returnLabel = "Back to duplicate comparison",
}: {
  caseId: string
  document: DuplicateDocument
  returnLabel?: string
}) {
  const access = useFinancialAccess()
  const [opened, setOpened] = useState(false)
  const original = useRef<HTMLButtonElement>(null)
  return (
    <div className="space-y-2 text-sm">
      <p>{duplicateRowsLabel(document.rows_by_status)}</p>
      {document.statement_context.length > 0 ? (
        <ul aria-label="Saved statement periods" className="space-y-2">
          {document.statement_context.map((period) => (
            <li
              key={period.period_id}
              className="space-y-1 rounded border p-2 break-words"
            >
              <p>{duplicateStatementLabel(period)}</p>
              <FinancialAccessContext.Provider
                value={{ ...access, canEdit: false, canUpload: false }}
              >
                <StatementSourceButton
                  key={`${caseId}:${document.document_id}:${period.period_id}`}
                  caseId={caseId}
                  periodId={period.period_id}
                  sourceDocumentId={document.document_id}
                  label={`Inspect statement source · ${period.period_start || "unknown start"} to ${period.period_end || "unknown end"} · ${period.currency || "unknown currency"}`}
                  contextLabel={`${document.filename} · ${duplicateStatementLabel(period)}`}
                  returnLabel={returnLabel}
                />
              </FinancialAccessContext.Provider>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="text-muted-foreground">
            Saved statement account and period details are unavailable.
          </p>
          {document.evidence_file_id ? (
            <>
              <Button
                ref={original}
                variant="outline"
                size="sm"
                onClick={() => setOpened(true)}
              >
                Open original file
              </Button>
              <p className="text-xs text-muted-foreground">
                This opens the whole file; no saved statement period is
                available.
              </p>
              <DocumentViewer
                open={opened}
                onOpenChange={setOpened}
                onCloseAutoFocus={(event) => {
                  event.preventDefault()
                  original.current?.focus({ preventScroll: true })
                }}
                documentUrl={evidenceAPI.getFileUrl(document.evidence_file_id)}
                documentName={document.filename}
                navigationKey={`${caseId}:duplicate:${document.document_id}`}
                caseId={caseId}
                evidenceId={document.evidence_file_id}
              />
            </>
          ) : (
            <p className="text-xs text-muted-foreground">
              No registered original file is available in this case.
            </p>
          )}
        </>
      )}
    </div>
  )
}

export function DuplicateGroupContext({
  documents,
}: {
  documents: DuplicateDocument[]
}) {
  const contexts = [
    ...new Set(
      documents.flatMap((row) =>
        row.statement_context.map(duplicateStatementLabel)
      )
    ),
  ]
  const countsKnown = documents.every((row) => row.rows_by_status !== undefined)
  const rows = documents.reduce(
    (total, row) =>
      total +
      Object.values(row.rows_by_status || {}).reduce(
        (sum, value) => sum + value,
        0
      ),
    0
  )
  return (
    <span className="mt-1 block space-y-1 text-xs font-normal text-muted-foreground">
      {contexts.length ? (
        contexts.map((context) => (
          <span className="block break-words" key={context}>
            {context}
          </span>
        ))
      ) : (
        <span className="block">
          Saved statement account and period details are unavailable.
        </span>
      )}
      <span className="block">
        {countsKnown
          ? `${rows} stored rows across ${documents.length} copies`
          : "Some stored row counts are unavailable"}
      </span>
    </span>
  )
}
