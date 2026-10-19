import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { ApiError, fetchAPI } from "@/lib/api-client"
import {
  financialSourceAuditDetail,
  financialSourceAuditList,
  type FinancialSourceAuditGroup,
} from "../lib/financial-source-audit"

type Props = { caseId: string; onFindFile: (fileId: string) => Promise<void> }
const PAGE_SIZE = 50
const TEXT_SIZE = 4000
const dateLabel = (value: string) => new Date(value).toLocaleString()

/** Inspector only: opening this panel never reads files again or changes them. */
export function FinancialSourceAudit(props: Props) {
  const [open, setOpen] = useState(false)
  return (
    <section
      aria-label="Review Financial sources"
      className="rounded-lg border bg-card p-3 space-y-3"
    >
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "Hide source review" : "Review Financial sources"}
      </Button>
      {open && <AuditInventory key={props.caseId} {...props} />}
    </section>
  )
}

function AuditInventory({ caseId, onFindFile }: Props) {
  const [visibility, setVisibility] = useState("visible")
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [navigation, setNavigation] = useState(0)
  const [finding, setFinding] = useState<string | null>(null)
  const [error, setError] = useState("")
  const heading = useRef<HTMLHeadingElement>(null)
  const [original, setOriginal] = useState<{
    id: string
    filename: string
  } | null>(null)
  const query = useQuery({
    queryKey: ["financial-source-audit", caseId, visibility, offset],
    retry: false,
    queryFn: async ({ signal }) => {
      const result = financialSourceAuditList.parse(
        await fetchAPI(
          `/api/financial/source-audit?${new URLSearchParams({ case_id: caseId, visibility, offset: String(offset), limit: String(PAGE_SIZE) })}`,
          { signal }
        )
      )
      if (
        result.case_id !== caseId ||
        result.offset !== offset ||
        result.limit !== PAGE_SIZE
      )
        throw Error("The source review did not match this case or page.")
      return result
    },
  })
  useEffect(() => {
    if (!navigation || !query.data) return
    heading.current?.focus()
    heading.current?.scrollIntoView({ block: "nearest" })
  }, [navigation, query.data])
  const move = (next: number) => {
    setExpanded(null)
    setOffset(next)
    setNavigation((n) => n + 1)
  }
  const find = async (group: FinancialSourceAuditGroup) => {
    setFinding(group.root_file_id)
    setError("")
    try {
      await onFindFile(group.current_file_id)
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "This file could not be located. Refresh the file list and try again."
      )
    } finally {
      setFinding(null)
    }
  }
  const data = query.data
  return (
    <div className="space-y-3 text-sm">
      <p>
        Inspect the contents and how a source entered Financial before deciding
        whether it belongs here. File type does not determine financial
        relevance. This review changes nothing.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1">
          Sources to review
          <select
            aria-label="Sources to review"
            className="rounded border bg-background p-2"
            value={visibility}
            onChange={(event) => {
              setVisibility(event.target.value)
              move(0)
            }}
          >
            <option value="visible">Currently in Financial</option>
            <option value="hidden">Removed from Financial</option>
            <option value="all">All retained Financial sources</option>
          </select>
        </label>
        <Button
          variant="outline"
          size="sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh source review
        </Button>
      </div>
      {query.isPending && <p role="status">Loading source review…</p>}
      {query.isError && (
        <p role="alert">
          {query.error instanceof ApiError
            ? query.error.message
            : "Source review could not be loaded for this case. Refresh source review to try again."}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p>
            {data.summary.groups.toLocaleString()} source files ·{" "}
            {data.summary.visible.toLocaleString()} in Financial ·{" "}
            {data.summary.hidden.toLocaleString()} removed ·{" "}
            {data.summary.active_work.toLocaleString()} with active work ·{" "}
            {data.summary.without_retained_text.toLocaleString()} without stored
            text
          </p>
          <p className="text-muted-foreground">
            {data.summary.protected.toLocaleString()} sources have recorded
            selections, work or history to preserve. These records are not a
            financial classification; missing text does not mean a source is
            non-financial. Counts include retained history.
          </p>
          <h3
            ref={heading}
            tabIndex={-1}
            className="font-medium scroll-mt-24 focus:outline-none"
          >
            {data.total
              ? `Sources ${offset + 1}–${Math.min(offset + data.groups.length, data.total)} of ${data.total}`
              : "No sources match this view"}
          </h3>
          <ul
            aria-label="Financial sources for inspection"
            className="divide-y rounded border"
          >
            {data.groups.map((group) => (
              <li key={group.root_file_id} className="p-3 space-y-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1 basis-full sm:basis-auto">
                    <h4 className="font-medium break-words">
                      {group.filename}
                    </h4>
                    <p className="text-muted-foreground">
                      {group.visibility === "hidden"
                        ? "Removed from Financial"
                        : "In Financial"}{" "}
                      · {group.version_count} retained{" "}
                      {group.version_count === 1 ? "reading" : "readings"}
                      {group.active_work ? " · Work queued or active" : ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      aria-expanded={expanded === group.root_file_id}
                      onClick={() =>
                        setExpanded(
                          expanded === group.root_file_id
                            ? null
                            : group.root_file_id
                        )
                      }
                    >
                      {expanded === group.root_file_id
                        ? "Close details"
                        : "Inspect source"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={finding !== null}
                      onClick={() => void find(group)}
                    >
                      {finding === group.root_file_id
                        ? "Finding file…"
                        : "Find in files"}
                    </Button>
                  </div>
                </div>
                <p>
                  {group.provenance.explicit_selection
                    ? "Selected for Financial by an investigator."
                    : group.provenance.enrollment_recorded
                      ? "Added to Financial; who selected it was not recorded."
                      : "No explicit investigator selection is recorded."}
                  {group.provenance.batch_count
                    ? ` Referenced by ${group.provenance.batch_count} processing ${group.provenance.batch_count === 1 ? "batch" : "batches"}.`
                    : ""}
                </p>
                <p>
                  {group.provenance.saved_period_count} saved statement periods
                  · {group.provenance.payment_count} saved payments ·{" "}
                  {group.provenance.saved_review_storage_count
                    ? "Saved reviews present"
                    : "No saved reviews recorded"}{" "}
                  · {group.provenance.note_count} note links{" "}
                  <span className="text-muted-foreground">
                    (including retained history)
                  </span>
                </p>
                {expanded === group.root_file_id && (
                  <SourceDetails
                    key={group.root_file_id}
                    caseId={caseId}
                    group={group}
                    onOpenOriginal={setOriginal}
                  />
                )}
              </li>
            ))}
          </ul>
          <div
            role="group"
            aria-label="Source review pages"
            className="flex flex-wrap items-center gap-2"
          >
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || query.isFetching}
              onClick={() => move(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous sources
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= data.total || query.isFetching}
              onClick={() => move(offset + PAGE_SIZE)}
            >
              Next sources
            </Button>
          </div>
        </>
      )}
      {original && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={original.id}
          documentName={original.filename}
          documentUrl={evidenceAPI.getFileUrl(original.id)}
          open
          onOpenChange={(open) => {
            if (!open) setOriginal(null)
          }}
        />
      )}
    </div>
  )
}

function SourceDetails({
  caseId,
  group,
  onOpenOriginal,
}: {
  caseId: string
  group: FinancialSourceAuditGroup
  onOpenOriginal: (source: { id: string; filename: string }) => void
}) {
  const [fileId, setFileId] = useState(group.current_file_id)
  const [offset, setOffset] = useState(0)
  const excerptHeading = useRef<HTMLHeadingElement>(null)
  const query = useQuery({
    queryKey: ["financial-source-audit-detail", caseId, fileId, offset],
    retry: false,
    queryFn: async ({ signal }) => {
      const result = financialSourceAuditDetail.parse(
        await fetchAPI(
          `/api/financial/source-audit/${encodeURIComponent(fileId)}?${new URLSearchParams({ case_id: caseId, text_offset: String(offset), text_limit: String(TEXT_SIZE) })}`,
          { signal }
        )
      )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        result.group.root_file_id !== group.root_file_id ||
        result.text_excerpt.evidence_file_id !== fileId ||
        result.text_excerpt.offset !== offset
      )
        throw Error(
          "The stored text did not match this case and source reading."
        )
      return result
    },
  })
  useEffect(() => {
    if (offset && query.data) excerptHeading.current?.focus()
  }, [offset, query.data])
  const data = query.data
  const version = data?.versions.find(
    (version) => version.evidence_file_id === fileId
  )
  return (
    <div className="border-t pt-3 space-y-3">
      {!!group.protection_reasons.length && (
        <div>
          <h5 className="font-medium">Work and history to preserve</h5>
          <ul className="list-disc pl-5">
            {group.protection_reasons.map((reason) => (
              <li key={reason.code}>{reason.message}</li>
            ))}
          </ul>
        </div>
      )}
      {!!group.provenance.recognized_readers.length && (
        <p>
          Previous reader records:{" "}
          {group.provenance.recognized_readers
            .map((name) => name.replace(/[_-]+/g, " "))
            .join(", ")}
          . These describe previous processing, not a new content check.
        </p>
      )}
      <div className="flex flex-wrap gap-3 items-center">
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            onOpenOriginal({
              id: fileId,
              filename: version?.filename || group.filename,
            })
          }
        >
          Open original
        </Button>
        <Link
          className="underline"
          target="_blank"
          rel="noopener noreferrer"
          to={`/cases/${encodeURIComponent(caseId)}/evidence?file=${encodeURIComponent(group.root_file_id)}&from=financial`}
        >
          Open in Evidence
        </Link>
      </div>
      {query.isPending && <p role="status">Loading stored source details…</p>}
      {query.isError && (
        <div role="alert">
          <p>
            {query.error instanceof ApiError
              ? query.error.message
              : "Stored source details could not be verified for this file. Try again or open the original."}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
          >
            Retry source details
          </Button>
        </div>
      )}
      {data && (
        <>
          <label className="grid gap-1">
            Source reading
            <select
              aria-label="Source reading"
              className="rounded border bg-background p-2 w-full min-w-0"
              value={fileId}
              onChange={(event) => {
                setFileId(event.target.value)
                setOffset(0)
              }}
            >
              {!version && (
                <option value={fileId}>
                  {group.filename} · current reading
                </option>
              )}
              {data.versions.map((version, index) => (
                <option
                  key={version.evidence_file_id}
                  value={version.evidence_file_id}
                >
                  {index + 1}. {version.filename} ·{" "}
                  {version.created_at
                    ? dateLabel(version.created_at)
                    : "date unavailable"}{" "}
                  · {version.status}
                </option>
              ))}
            </select>
          </label>
          {data.versions_truncated && (
            <p>
              Only the first 100 retained readings are listed. Open the source
              in Evidence to inspect its full history.
            </p>
          )}
          {version?.selected_at && (
            <p>
              Financial selection recorded {dateLabel(version.selected_at)}
              {version.selected_by
                ? " by an investigator"
                : "; actor unavailable"}
              .
            </p>
          )}
          {data.source_summary && (
            <div>
              <h5 className="font-medium">Stored source summary</h5>
              <p className="whitespace-pre-wrap break-words">
                {data.source_summary}
              </p>
              {data.source_summary_truncated && (
                <p className="text-muted-foreground">
                  First 1,500 characters of the stored summary.
                </p>
              )}
            </div>
          )}
          <div>
            <h5 ref={excerptHeading} tabIndex={-1} className="font-medium">
              Stored text excerpt
            </h5>
            {data.text_excerpt.available ? (
              <>
                <p className="text-muted-foreground">
                  {version?.filename || group.filename} · characters{" "}
                  {Math.min(offset + 1, data.text_excerpt.total_characters)}–
                  {Math.min(
                    offset + TEXT_SIZE,
                    data.text_excerpt.total_characters
                  )}{" "}
                  of {data.text_excerpt.total_characters}. Character positions
                  are not PDF page numbers; check the original for page layout.
                </p>
                <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-xs font-sans">
                  {data.text_excerpt.text}
                </pre>
                <div
                  role="group"
                  aria-label="Stored text pages"
                  className="mt-2 flex flex-wrap gap-2"
                >
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={offset === 0 || query.isFetching}
                    onClick={() => setOffset(Math.max(0, offset - TEXT_SIZE))}
                  >
                    Previous text
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.text_excerpt.truncated || query.isFetching}
                    onClick={() => setOffset(offset + TEXT_SIZE)}
                  >
                    Next text
                  </Button>
                </div>
              </>
            ) : (
              <p>
                No stored text is available for this reading. Its financial
                relevance is unknown from this view. Inspect the original;
                opening this review does not start processing.
              </p>
            )}
          </div>
          <p className="text-muted-foreground">{data.limitation}</p>
        </>
      )}
    </div>
  )
}
