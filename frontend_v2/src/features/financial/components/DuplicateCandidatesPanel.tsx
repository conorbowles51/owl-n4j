import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useDuplicateCandidates } from "../hooks/use-duplicate-candidates"
import {
  DuplicateDecisionForm,
  type DuplicateSelection,
} from "./DuplicateDecisionForm"
import { duplicateMatchLabel } from "../lib/duplicate-format"

export function DuplicateCandidatesPanel({
  caseId,
}: {
  caseId: string | undefined
}) {
  const [opened, setOpened] = useState(false)
  const [selection, setSelection] = useState<DuplicateSelection | null>(null)
  const { data, isPending, isError, error, isFetching, refetch } =
    useDuplicateCandidates(caseId, opened)
  return (
    <section
      aria-label="Duplicate candidates"
      className="space-y-3 rounded-lg border bg-card p-4"
    >
      <h2 className="text-sm font-semibold">Duplicate candidates</h2>
      <p className="text-xs text-muted-foreground">
        Compare financial documents already recorded in this case. Matching
        readings are candidates for review; this comparison does not exclude
        documents or change totals.
      </p>
      <p className="text-xs text-muted-foreground">
        Groups require matching account and period coverage. Different coverage
        is not grouped, even when files share the same bytes.
      </p>
      {!caseId ? (
        <p>Choose a case to compare documents.</p>
      ) : (
        <Button
          variant="outline"
          size="sm"
          disabled={isFetching}
          onClick={() => {
            if (opened) void refetch()
            else setOpened(true)
          }}
        >
          {opened ? "Refresh comparison" : "Compare documents"}
        </Button>
      )}
      {selection && (
        <DuplicateDecisionForm
          selection={selection}
          onClose={() => setSelection(null)}
        />
      )}
      {caseId &&
        opened &&
        (isError ? (
          <p role="alert">
            Comparison could not be completed. No results are shown.{" "}
            {error.message}
          </p>
        ) : isPending ? (
          <p role="status">Comparing stored documents...</p>
        ) : (
          data && (
            <>
              {isFetching && (
                <p role="status">
                  Refreshing; showing the last successful comparison.
                </p>
              )}
              <p>
                {data.compared} of {data.documents} financial documents
                compared. {data.skipped.length} not compared.
              </p>
              <p className="text-xs text-muted-foreground">
                Admitted and superseded documents are compared using all stored
                rows, including held-out rows, and balance observations. A
                matching reading is not proof that two exhibits are
                interchangeable. Row counts below describe stored statuses, not
                verified totals.
              </p>
              {data.groups.length === 0 ? (
                <p>No candidate groups found among the compared documents.</p>
              ) : (
                data.groups.map((group, index) => (
                  <details key={group.group_key}>
                    <summary className="cursor-pointer text-sm font-medium">
                      Candidate group {index + 1} · {group.members.length}{" "}
                      documents
                    </summary>
                    <ul className="mt-2 space-y-3">
                      {group.members.map((row) => (
                        <li
                          key={row.document_id}
                          className="rounded border p-3 text-sm"
                        >
                          <p className="font-medium break-all">
                            {row.filename}
                          </p>
                          <p>{duplicateMatchLabel(row.match)}</p>
                          <p>Document status: {row.status}</p>
                          <p className="text-xs break-all">
                            Document: {row.document_id}
                          </p>
                          {row.superseded_by_id && (
                            <p className="text-xs break-all">
                              Superseded by: {row.superseded_by_id}
                            </p>
                          )}
                          <p>
                            {Object.entries(row.rows_by_status)
                              .map(
                                ([status, count]) => `${count} ${status} rows`
                              )
                              .join(" · ") || "No stored rows"}
                          </p>
                          {row.status === "admitted" &&
                            group.members
                              .filter(
                                (other) =>
                                  other.document_id !== row.document_id &&
                                  other.status === "admitted" &&
                                  other.reading_fingerprint ===
                                    row.reading_fingerprint
                              )
                              .map((primary) => (
                                <Button
                                  key={primary.document_id}
                                  variant="outline"
                                  size="sm"
                                  disabled={!!selection || isFetching}
                                  onClick={() =>
                                    setSelection({
                                      caseId,
                                      document: row,
                                      primary,
                                    })
                                  }
                                >
                                  Exclude this copy; retain {primary.filename}
                                </Button>
                              ))}
                        </li>
                      ))}
                    </ul>
                  </details>
                ))
              )}
              {data.excluded_documents.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    Excluded documents ({data.excluded_documents.length})
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {data.excluded_documents.map((row) => (
                      <li
                        key={row.document_id}
                        className="flex items-center justify-between gap-2 text-sm"
                      >
                        <span>{row.filename}</span>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!!selection || isFetching}
                          onClick={() =>
                            setSelection({ caseId, document: row })
                          }
                        >
                          Restore {row.filename}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {data.skipped.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    Documents not compared ({data.skipped.length})
                  </summary>
                  <ul className="mt-2 space-y-2 text-sm">
                    {data.skipped.map((row) => (
                      <li key={row.document_id}>
                        {row.filename}: {row.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )
        ))}
    </section>
  )
}
