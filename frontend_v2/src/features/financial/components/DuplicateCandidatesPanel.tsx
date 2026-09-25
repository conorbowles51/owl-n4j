import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { useEffect, useRef, useState } from "react"
import { CrossCaseDuplicatePanel } from "./CrossCaseDuplicatePanel"
import { Button } from "@/components/ui/button"
import { useDuplicateCandidates } from "../hooks/use-duplicate-candidates"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  DuplicateDecisionForm,
  type DuplicateSelection,
} from "./DuplicateDecisionForm"
import { duplicateMatchLabel } from "../lib/duplicate-format"
import {
  DuplicateDocumentContext,
  DuplicateGroupContext,
} from "./DuplicateDocumentContext"

type Props = {
  caseId: string | undefined
  autoLoad?: boolean
  showCrossCase?: boolean
}

export function DuplicateCandidatesPanel(props: Props) {
  return (
    <DuplicateCandidatesCasePanel key={props.caseId || "no-case"} {...props} />
  )
}

function DuplicateCandidatesCasePanel({
  caseId,
  autoLoad = false,
  showCrossCase = true,
}: Props) {
  const { canEdit, ready } = useFinancialAccess()
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [groupPage, setGroupPage] = useState(0)
  const [hashPage, setHashPage] = useState(0)
  const [opened, setOpened] = useState(autoLoad)
  const [selection, setSelection] = useState<DuplicateSelection | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const selectionOrigin = useRef<{
    button: HTMLElement
    group: HTMLElement | null
  } | null>(null)
  useEffect(() => {
    if (selection || !selectionOrigin.current) return
    const { button, group } = selectionOrigin.current
    const target =
      button.isConnected && !button.matches(":disabled")
        ? button
        : group?.isConnected
          ? group
          : heading.current
    target?.focus({ preventScroll: true })
    target?.scrollIntoView({ block: "center" })
    selectionOrigin.current = null
  }, [selection])
  const openDecision = (value: DuplicateSelection, button: HTMLElement) => {
    selectionOrigin.current = {
      button,
      group: button.closest("details")?.querySelector("summary") || null,
    }
    setSelection(value)
  }
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
      <h2 ref={heading} tabIndex={-1} className="text-sm font-semibold">
        Duplicate candidates
      </h2>
      <p className="text-xs text-muted-foreground">
        Find statements that may have been imported twice. Open each source,
        then choose which copy to keep. This comparison does not exclude
        documents or change totals.
      </p>
      {ready && !canEdit && (
        <p className="text-xs text-muted-foreground">
          You can compare statements and open their originals. Changing which
          copies count in Transactions requires permission to edit this case.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Statements are grouped when their recorded accounts and dates match.
        Files with the same contents but different recorded accounts or dates
        are listed separately.
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
      {caseId && showCrossCase && (
        <CrossCaseDuplicatePanel key={caseId} caseId={caseId} />
      )}
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
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer">What was compared</summary>
                <p className="mt-2">
                  The comparison includes original transaction values, balances
                  and rows previously excluded or corrected. Open the originals
                  to check whether either file contains additional information
                  before excluding a copy.
                </p>
                {data.stored_rows_in_case !== undefined && (
                  <p>{data.stored_rows_in_case} saved rows in this case.</p>
                )}
              </details>
              {data.source_hash_groups.length > 0 && (
                <section aria-label="Matching original files across recorded periods">
                  <h3 className="font-medium">
                    Same original file, different statement details
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    These copies have different or missing recorded accounts or
                    statement periods. Open a group to compare the saved details
                    and sources.
                  </p>
                  {data.source_hash_groups
                    .slice(visibleHashPage * 10, visibleHashPage * 10 + 10)
                    .map((group, index) => (
                      <details key={group.sha256_at_ingestion}>
                        <summary>
                          Original file group {visibleHashPage * 10 + index + 1}{" "}
                          · {group.members.length} documents
                          <DuplicateGroupContext documents={group.members} />
                        </summary>
                        <details className="my-2 text-xs text-muted-foreground">
                          <summary>File matching details</summary>
                          <p>{group.limitation}</p>
                          <p className="break-all">
                            Recorded SHA-256: {group.sha256_at_ingestion}
                          </p>
                        </details>
                        <ul>
                          {group.members.map((row) => (
                            <li
                              key={row.document_id}
                              className="my-2 break-words"
                            >
                              {row.filename} · {row.status}
                              <br />
                              Document: {row.document_id}
                              <DuplicateDocumentContext
                                caseId={caseId}
                                document={row}
                              />
                              {!row.statement_context.length &&
                                !row.evidence_file_id &&
                                row.source_transaction_id && (
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
                    <div className="flex flex-wrap items-center gap-2">
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
                    <details
                      key={group.group_key}
                      className="rounded border p-3"
                    >
                      <summary className="cursor-pointer text-sm font-medium">
                        Candidate group {visibleGroupPage * 10 + index + 1} ·{" "}
                        {group.members.length} documents
                        <DuplicateGroupContext documents={group.members} />
                      </summary>
                      <ul className="mt-2 grid items-start gap-3 lg:grid-cols-2">
                        {group.members.map((row, memberIndex) => (
                          <li
                            key={row.document_id}
                            aria-label={`Copy ${memberIndex + 1}: ${row.filename}`}
                            className="min-w-0 space-y-2 rounded border p-3 text-sm"
                          >
                            <p className="font-medium break-all">
                              {row.filename}
                            </p>
                            {!row.statement_context.length &&
                              !row.evidence_file_id &&
                              row.source_transaction_id && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  aria-label={`View source for ${row.filename}`}
                                  onClick={() =>
                                    setSourceId(row.source_transaction_id!)
                                  }
                                >
                                  View source
                                </Button>
                              )}
                            <DuplicateDocumentContext
                              caseId={caseId}
                              document={row}
                              returnLabel={`Back to candidate group ${visibleGroupPage * 10 + index + 1}`}
                            />
                            <p>{duplicateMatchLabel(row.match)}</p>
                            <p>
                              {row.status === "admitted"
                                ? Object.values(row.rows_by_status).every(
                                    (count) => count === 0
                                  )
                                  ? "Saved statement · no transactions"
                                  : "Included in Transactions"
                                : "Excluded from Transactions"}
                            </p>
                            {row.superseded_by_id && (
                              <p className="break-words">
                                Retained copy:{" "}
                                {group.members.find(
                                  (member) =>
                                    member.document_id === row.superseded_by_id
                                )?.filename ?? "See document identifiers"}
                              </p>
                            )}
                            <details className="text-xs break-all">
                              <summary className="cursor-pointer">
                                Document identifiers
                              </summary>
                              <p>Document: {row.document_id}</p>
                              {row.superseded_by_id && (
                                <p>Retained document: {row.superseded_by_id}</p>
                              )}
                            </details>
                            {canEdit &&
                              row.status === "admitted" &&
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
                                    onClick={(event) =>
                                      openDecision(
                                        {
                                          caseId,
                                          document: row,
                                          primary,
                                        },
                                        event.currentTarget
                                      )
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
                <div className="flex flex-wrap items-center gap-2">
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
                        className="space-y-2 rounded border p-3 text-sm"
                      >
                        <p className="font-medium break-words">
                          {row.filename}
                        </p>
                        <DuplicateDocumentContext
                          caseId={caseId}
                          document={row}
                        />
                        {canEdit && (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!!selection || isFetching}
                            onClick={(event) =>
                              openDecision(
                                { caseId, document: row },
                                event.currentTarget
                              )
                            }
                          >
                            Restore {row.filename}
                          </Button>
                        )}
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
                        <p>
                          {row.filename}: {row.reason}
                        </p>
                        <DuplicateDocumentContext
                          caseId={caseId}
                          document={row}
                        />
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
