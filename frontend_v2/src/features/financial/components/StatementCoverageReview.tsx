import { useState } from "react"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import type { CoverageReview } from "../hooks/use-statement-coverage-review"

export function StatementCoverageReview({
  caseId,
  review,
  decision,
  change,
  canEdit,
  inBatch,
}: {
  inBatch: boolean
  caseId: string
  review: CoverageReview
  decision: { revision: string; reason: string }
  change: (value: { revision: string; reason: string }) => void
  canEdit: boolean
}) {
  const [file, setFile] = useState<CoverageReview["candidates"][number] | null>(
    null
  )
  if (!review.candidates.length) return null
  const checked = decision.revision === review.revision
  const decided = checked && !!decision.reason.trim()
  return (
    <section
      aria-label="Compare overlapping statements"
      className="rounded border border-amber-300 bg-amber-50/40 dark:bg-amber-950/20 p-3 space-y-3 text-sm"
    >
      <h3 className="font-semibold">
        {review.matching_statement
          ? decided
            ? "Possible duplicate statement — comparison recorded"
            : "Possible duplicate statement — import on hold"
          : "Another statement covers these dates"}
      </h3>
      <p>
        {review.matching_statement
          ? "A separate file matches the bank, full account number, account holder, currency and exact statement dates. Compare its original before adding another import. Matching details can also occur on a revised statement, so neither file is deleted."
          : "These files have overlapping dates for the same bank and account reference. A matching account ending or date range alone does not establish that the payments are duplicates."}
      </p>
      <ul className="space-y-2 max-h-64 overflow-y-auto">
        {review.candidates.map((other) => (
          <li
            key={`${other.file_id}:${other.statement_id}`}
            className="flex flex-wrap items-center justify-between gap-2 border rounded p-2 bg-background"
          >
            <div>
              <strong>{other.filename}</strong>
              <p>
                {other.period_start} to {other.period_end} ·{" "}
                {other.status === "imported"
                  ? "Already imported"
                  : "Awaiting import"}
                {other.matching_statement &&
                  " · Same account, holder, currency and period"}
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={() => setFile(other)}>
              Compare original PDF
            </Button>
          </li>
        ))}
      </ul>
      <p>
        {inBatch ? (
          <>
            If this is a copy, choose{" "}
            <strong>Don’t import this duplicate</strong> above or{" "}
            <strong>Leave unimported</strong> in the batch.
          </>
        ) : (
          <>
            If this is a copy, choose{" "}
            <strong>Don’t import this duplicate</strong> in the duplicate
            decision above.
          </>
        )}{" "}
        The file stays in Evidence. If it contains additional records, explain
        below why you need both statements.
      </p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          aria-label="I have compared these files and need to import this statement too"
          checked={checked}
          disabled={!canEdit}
          onChange={(e) =>
            change({
              revision: e.target.checked ? review.revision || "" : "",
              reason: decision.reason,
            })
          }
        />
        I have compared these files and need to import this statement too
      </label>
      {checked && (
        <label className="block">
          Why both statements are needed
          <textarea
            aria-label="Reason for importing overlapping statements"
            className="block w-full border rounded p-2 bg-background mt-1"
            maxLength={4096}
            disabled={!canEdit}
            value={decision.reason}
            onChange={(e) => change({ ...decision, reason: e.target.value })}
          />
        </label>
      )}
      {file && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={file.file_id}
          documentName={file.filename}
          initialPage={file.page_number ?? 1}
          documentUrl={evidenceAPI.getFileUrl(file.file_id)}
          navigationKey={`${caseId}:${file.file_id}`}
          open
          onOpenChange={(open) => {
            if (!open) setFile(null)
          }}
        />
      )}
    </section>
  )
}
