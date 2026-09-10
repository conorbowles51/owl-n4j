import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { useState } from "react"
import { CrossCaseDuplicatePanel } from "./CrossCaseDuplicatePanel"
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
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [groupPage, setGroupPage] = useState(0)
  const [hashPage, setHashPage] = useState(0)
  const [opened, setOpened] = useState(false)
  const [selection, setSelection] = useState<DuplicateSelection | null>(null)
  const { data, isPending, isError, error, isFetching, refetch } =
    useDuplicateCandidates(caseId, opened)
  const visibleGroupPage = Math.min(
    groupPage,
    Math.max(0, Math.ceil((data?.groups.length ?? 0) / 10) - 1)
  )
  const visibleHashPage = Math.min(
    hashPage,
    Math.max(0, Math.ceil((data?.source_hash_groups.length ?? 0) / 10) - 1)
  )
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
        Reading groups require matching account and period coverage. Matching
        ingestion hashes with different or missing coverage are shown separately
        for source review.
      </p>
      {!caseId ? (
        <p>Choose a case to compare documents.</p>
      ) : (
        <Button
          variant="outline"
          size="sm"
          disabled={isFetching}
          onClick={() => {
            setGroupPage(0)
            setHashPage(0)
            if (opened) void refetch()
            else setOpened(true)
          }}
        >
          {opened ? "Refresh comparison" : "Compare documents"}
        </Button>
      )}
      {caseId && <CrossCaseDuplicatePanel key={caseId} caseId={caseId} />}
      {sourceId && caseId && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={sourceId}
          onClose={() => setSourceId(null)}
        />
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
              {data.stored_rows_in_case !== undefined && (
                <p>
                  {data.stored_rows_in_case} stored readings in this case were
                  counted for the comparison limit.
                </p>
              )}
              {data.source_hash_groups.length > 0 && (
                <section aria-label="Matching source hashes across coverage">
                  <h3 className="font-medium">
                    Same source hash, different or missing recorded coverage
                  </h3>
                  {data.source_hash_groups
                    .slice(visibleHashPage * 10, visibleHashPage * 10 + 10)
                    .map((group) => (
                      <details key={group.sha256_at_ingestion}>
                        <summary>
                          {group.members.length} documents ·{" "}
                          {group.sha256_at_ingestion.slice(0, 12)}…
                        </summary>
                        <p>{group.limitation}</p>
                        <p className="break-all">
                          Recorded SHA-256: {group.sha256_at_ingestion}
                        </p>
                        <ul>
                          {group.members.map((row) => (
                            <li
                              key={row.document_id}
                              className="my-2 break-words"
                            >
                              {row.filename} · {row.status}
                              <br />
                              Document: {row.document_id}
                              {row.source_transaction_id && (
                                <Button
                                  onClick={() =>
                                    setSourceId(row.source_transaction_id!)
                                  }
                                >
                                  Inspect source for document{" "}
                                  {row.document_id.slice(0, 8)}
                                </Button>
                              )}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ))}
                  {data.source_hash_groups.length > 10 && (
                    <div className="flex items-center gap-2">
                      <Button
                        disabled={!visibleHashPage}
                        onClick={() => setHashPage(visibleHashPage - 1)}
                      >
                        Previous source matches
                      </Button>
                      <span>
                        Source groups {visibleHashPage * 10 + 1}–
                        {Math.min(
                          visibleHashPage * 10 + 10,
                          data.source_hash_groups.length
                        )}{" "}
                        of {data.source_hash_groups.length}
                      </span>
                      <Button
                        disabled={
                          (visibleHashPage + 1) * 10 >=
                          data.source_hash_groups.length
                        }
                        onClick={() => setHashPage(visibleHashPage + 1)}
                      >
                        Next source matches
                      </Button>
                    </div>
                  )}
                </section>
              )}
              {data.groups.length === 0 ? (
                <p>No candidate groups found among the compared documents.</p>
              ) : (
                data.groups
                  .slice(visibleGroupPage * 10, visibleGroupPage * 10 + 10)
                  .map((group, index) => (
                    <details key={group.group_key}>
                      <summary className="cursor-pointer text-sm font-medium">
                        Candidate group {visibleGroupPage * 10 + index + 1} ·{" "}
                        {group.members.length} documents
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
              {data.groups.length > 10 && (
                <div className="flex items-center gap-2">
                  <Button
                    disabled={!visibleGroupPage}
                    onClick={() => setGroupPage(visibleGroupPage - 1)}
                  >
                    Previous reading groups
                  </Button>
                  <span>
                    Reading groups {visibleGroupPage * 10 + 1}–
                    {Math.min(visibleGroupPage * 10 + 10, data.groups.length)}{" "}
                    of {data.groups.length}
                  </span>
                  <Button
                    disabled={(visibleGroupPage + 1) * 10 >= data.groups.length}
                    onClick={() => setGroupPage(visibleGroupPage + 1)}
                  >
                    Next reading groups
                  </Button>
                </div>
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
