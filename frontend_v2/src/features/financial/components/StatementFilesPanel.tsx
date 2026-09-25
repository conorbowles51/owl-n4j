import { StatementRecoveryPanel } from "./StatementRecoveryPanel"
import { FinancialSourceAudit } from "./FinancialSourceAudit"
import { ReadyStatementPeriods } from "./ReadyStatementPeriods"
import { ResumableUploadsPanel } from "@/features/evidence/components/ResumableUploadsPanel"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { FinancialRemovalAction } from "./FinancialRemovalAction"
import {
  useStatementRegister,
  groupStatementReadings,
  usesPdfStatementReader,
} from "../hooks/use-statement-register"
import { FinancialSourceFile } from "./FinancialSourceFile"
import { FinancialFileAction } from "./FinancialFileAction"
import { EvidenceFinancialPicker } from "./EvidenceFinancialPicker"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { fetchAPI } from "@/lib/api-client"
import { newReviewId } from "../lib/statement-review-id"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialStore } from "../stores/financial.store"
import { useStatementWorkspace } from "../stores/statement-workspace"
import {
  uploadStatementFiles,
  useStatementUploads,
} from "../stores/statement-upload-queue"

export function StatementFilesPanel({
  caseId,
  register = false,
  onOpen,
  removalMode = false,
  onFinishRemoval,
  active = true,
}: {
  caseId: string
  register?: boolean
  onOpen?: () => void
  removalMode?: boolean
  onFinishRemoval?: () => void
  active?: boolean
}) {
  const { canUpload, canEdit } = useFinancialAccess()
  const navigate = useNavigate()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const resultsHeading = useRef<HTMLHeadingElement>(null)
  const [filterAction, setFilterAction] = useState(0)
  const [removed, setRemoved] = useState(false)
  const sourceReview = useRef<HTMLDivElement>(null)
  const [auditFilter, setAuditFilter] = useState<{
    caseId: string
    fileId: string
    filename: string
  } | null>(null)
  const [visibilityResult, setVisibilityResult] = useState<{
    caseId: string
    filename: string
    removed: boolean
  } | null>(null)
  const visibilityNotice = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (visibilityResult?.caseId !== caseId) return
    visibilityNotice.current?.focus()
    visibilityNotice.current?.scrollIntoView({ block: "nearest" })
  }, [visibilityResult, caseId])
  const [error, setError] = useState("")
  const [reading, setReading] = useState<Record<string, boolean>>({})
  const [selection, setSelection] = useState<{ scope: string; ids: string[] }>({
    scope,
    ids: [],
  })
  const [preparing, setPreparing] = useState(false)
  const batchRequest = useRef<{ selection: string; id: string } | null>(null)
  const queue = useStatementUploads((state) => state.queues[scope])
  const queuedReadings = new Set(
    queue?.items.flatMap((item) =>
      item.status === "Reading queued" && item.fileId ? [item.fileId] : []
    ) ?? []
  )
  const selected = useStatementWorkspace(
    (state) => state.selections[scope]?.fileId
  )
  const reviewOpen = useStatementWorkspace(
    (state) => state.selections[scope]?.open ?? false
  )
  const showResults = (value: string, clearSearch = false) => {
    setStatus(value)
    if (clearSearch) setSearch("")
    setFilterAction((previous) => previous + 1)
  }
  useEffect(() => {
    if (!filterAction || reviewOpen || !register || removalMode) return
    const frame = requestAnimationFrame(() => {
      resultsHeading.current?.focus({ preventScroll: true })
      resultsHeading.current?.scrollIntoView({ block: "start" })
    })
    return () => cancelAnimationFrame(frame)
  }, [filterAction, reviewOpen, register, removed, removalMode])
  const openStatement = (fileId: string, statementId?: string) => {
    if (statementId !== undefined)
      useStatementWorkspace
        .getState()
        .setReviewChoice(`${scope}:${fileId}`, { statementId, currency: "" })
    useStatementWorkspace.getState().select(scope, fileId)
    useFinancialStore.getState().setMainView("statements")
    useFinancialStore.getState().setMode("transactions")
    onOpen?.()
  }
  const { files, imports } = useStatementRegister(
    caseId,
    !!queue?.running,
    queue?.items.flatMap((item) =>
      item.status === "Reading queued" && item.fileId ? [item.fileId] : []
    ) ?? [],
    true,
    active
  )
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["statement-import-files", caseId],
    })
  }
  const findAuditFile = async (fileId: string) => {
    const refreshed = await files.refetch()
    if (refreshed.isError)
      throw Error(
        "The file list could not be refreshed. Try again before changing this source."
      )
    const match = groupStatementReadings(refreshed.data || []).find(
      (file) =>
        file.id === fileId ||
        file.readingVersions.some((version) => version.id === fileId)
    )
    if (!match)
      throw Error(
        "This source is no longer in the Financial file list. Refresh source review to check its current location."
      )
    setAuditFilter({
      caseId,
      fileId: match.id,
      filename: match.original_filename,
    })
    setRemoved(match.financial_removed)
    setSearch("")
    setStatus("all")
    setFilterAction((value) => value + 1)
  }
  const readStatement = async (fileId: string) => {
    if (!canUpload) return
    setReading((current) => ({ ...current, [fileId]: true }))
    setError("")
    try {
      const result = z
        .object({ job_ids: z.array(z.string()) })
        .parse(await evidenceAPI.preparePdfReview(caseId, fileId))
      if (result.job_ids.length !== 1)
        throw Error("No reading job was returned.")
    } catch (failure) {
      setError(
        `${failure instanceof Error ? failure.message : "Reading could not start."} Refresh files to check its status before trying again. Your uploaded PDF is retained.`
      )
    } finally {
      await files.refetch()
      setReading((current) => ({ ...current, [fileId]: false }))
    }
  }
  const visibleFiles =
    files.data
      ?.filter(
        (file) => file.financial_removed === (removalMode ? false : removed)
      )
      ?.filter((file) =>
        file.original_filename.toLowerCase().includes(search.toLowerCase())
      )
      .filter(
        (file) =>
          auditFilter?.caseId !== caseId ||
          file.id === auditFilter.fileId ||
          file.readingVersions.some(
            (version) => version.id === auditFilter.fileId
          )
      )
      .filter((file) => !removalMode || usesPdfStatementReader(file))
      .filter((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        return (
          removalMode ||
          removed ||
          status === "all" ||
          (status === "ready" && !!saved?.available_periods) ||
          (status === "duplicates" && !!saved?.ignored_periods) ||
          (status === "checks" &&
            (!!saved?.periods_with_checks || !!saved?.incomplete_count)) ||
          (status === "pending" &&
            (!!saved?.pending_periods ||
              ["processing", "queued"].includes(file.status))) ||
          (status === "imported" &&
            (!!saved?.current_transactions || !!saved?.periods.length)) ||
          (status === "review" &&
            imports.data &&
            !imports.data.truncated &&
            !saved?.current_transactions &&
            !saved?.periods.length) ||
          (status === "attention" &&
            ["failed", "unprocessed"].includes(file.status))
        )
      }) ?? []
  const readyCount = (imports.data?.files ?? [])
    .filter((item) =>
      files.data?.some(
        (file) => file.id === item.evidence_file_id && !file.financial_removed
      )
    )
    .reduce((total, file) => total + (file.available_periods || 0), 0)
  const visibleReadyCount = visibleFiles.reduce(
    (total, file) =>
      total +
      (imports.data?.files.find((item) => item.evidence_file_id === file.id)
        ?.available_periods || 0),
    0
  )
  const selectedIds = (selection.scope === scope ? selection.ids : []).filter(
    (id) =>
      files.data?.some(
        (file) =>
          file.id === id &&
          !file.financial_removed &&
          usesPdfStatementReader(file)
      )
  )
  const selectableFiles = visibleFiles.filter(usesPdfStatementReader)
  const hiddenSelected = selectedIds.filter(
    (id) => !visibleFiles.some((file) => file.id === id)
  ).length
  const selectFiles = (ids: string[]) => setSelection({ scope, ids })
  const prepareSelected = async () => {
    if (!canEdit || !canUpload || preparing || !selectedIds.length) return
    const snapshot = JSON.stringify([scope, [...selectedIds].sort()])
    if (batchRequest.current?.selection !== snapshot)
      batchRequest.current = { selection: snapshot, id: newReviewId() }
    setPreparing(true)
    setError("")
    try {
      const batch = z.object({ id: z.string(), case_id: z.string() }).parse(
        await fetchAPI(
          `/api/financial/statement-import/batches?case_id=${caseId}`,
          {
            method: "POST",
            body: {
              request_id: batchRequest.current.id,
              file_ids: selectedIds,
              folder_ids: [],
            },
          }
        )
      )
      if (batch.case_id !== caseId)
        throw Error("The batch belongs to another case.")
      void client.invalidateQueries({ queryKey: ["financial-batches", caseId] })
      navigate(
        `/cases/${caseId}/financial?view=statements&batch=${encodeURIComponent(batch.id)}`
      )
    } catch (failure) {
      setError(
        `${failure instanceof Error ? failure.message : "Preparation could not start."} Your selection is kept. Retry to check the same request.`
      )
    } finally {
      setPreparing(false)
    }
  }
  return (
    <section
      aria-label="Statement files"
      className={register ? "space-y-4" : "h-full overflow-auto p-3 space-y-3"}
    >
      {!removalMode && register && (
        <StatementRecoveryPanel
          key={caseId}
          caseId={caseId}
          active={active}
          onReview={(fileId) => {
            useStatementWorkspace.getState().select(scope, fileId)
            useFinancialStore.getState().setMainView("statements")
            useFinancialStore.getState().setMode("transactions")
            onOpen?.()
          }}
        />
      )}
      <h2 className="font-semibold">
        {removalMode
          ? "Remove imports or start again"
          : register
            ? "Files in Financial"
            : "Statement files"}
      </h2>
      <p className="text-sm text-muted-foreground">
        {removalMode
          ? "Select the PDFs you want to remove. The next screen shows exactly which statements and transactions will be affected. You can remove the imports, or remove them and process the same PDFs afresh."
          : canUpload
            ? "Upload PDFs together, then select a ready file to open it in the statement viewer."
            : "Select a ready file to open its original PDF and extracted statement."}{" "}
        {!removalMode &&
          "Supported wire reports and deposit receipts open their own review."}
        {!removalMode &&
          " Financial sources can also be CSV, spreadsheets, Word documents, images or other formats. Use Choose from Evidence to select relevant content; each source opens with its available reader."}
      </p>
      {register && !removalMode && (
        <div
          ref={sourceReview}
          tabIndex={-1}
          className="scroll-mt-24 focus:outline-none"
        >
          <FinancialSourceAudit
            key={caseId}
            caseId={caseId}
            onFindFile={findAuditFile}
          />
        </div>
      )}
      {removalMode && (
        <p className="text-sm">
          Original PDFs, case notes, findings and import history are retained.
          No new case is needed.
        </p>
      )}
      {canUpload && (
        <input
          ref={input}
          type="file"
          multiple
          accept="application/pdf,.pdf"
          aria-label="Statement PDFs"
          className="hidden"
          onChange={(event) => {
            if (!canUpload) return
            const selectedFiles = Array.from(event.target.files ?? [])
            event.target.value = ""
            setError("")
            void uploadStatementFiles(
              selectedFiles,
              caseId,
              owner,
              refresh
            ).catch((error) => setError(error.message))
          }}
        />
      )}
      <div className={removalMode ? "hidden" : "flex flex-wrap gap-2"}>
        <EvidenceFinancialPicker caseId={caseId} />
        {canUpload && (
          <Button
            disabled={queue?.running}
            onClick={() => input.current?.click()}
          >
            Upload PDFs
          </Button>
        )}
        <Button
          variant="outline"
          onClick={() => {
            void files.refetch()
            void imports.refetch()
          }}
        >
          Refresh files
        </Button>
        <Button
          variant="outline"
          aria-pressed={removed}
          onClick={() => {
            setRemoved(!removed)
            setStatus("all")
            setSearch("")
          }}
        >
          {removed
            ? "Back to financial files"
            : `Removed files (${files.data?.filter((file) => file.financial_removed).length ?? 0})`}
        </Button>
      </div>
      {visibilityResult?.caseId === caseId && (
        <div
          ref={visibilityNotice}
          tabIndex={-1}
          role="status"
          className="rounded border bg-card p-3 text-sm space-y-2"
        >
          <p>
            {visibilityResult.filename}{" "}
            {visibilityResult.removed
              ? "removed from Financial. The original and saved reviews are retained."
              : "restored to Financial with its saved reviews."}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setRemoved(visibilityResult.removed)
              setStatus("all")
              setSearch("")
            }}
          >
            {visibilityResult.removed
              ? "View removed files"
              : "View financial files"}
          </Button>
        </div>
      )}
      {removed && !removalMode && (
        <p className="text-sm">
          These files were removed from Financial. Their originals remain in
          Evidence. Restore a file to review it here again.
        </p>
      )}
      {!removed && !removalMode && canEdit && (
        <p className="text-xs text-muted-foreground">
          Remove from Financial hides a file and keeps its Evidence, corrections
          and batch reviews. To withdraw saved transactions, use Remove imports…
          and review the affected records first.
        </p>
      )}
      {canUpload && !removalMode && (
        <p className="text-xs text-muted-foreground">
          Up to 20 PDFs per selection. Pause or resume uploads here. If the
          browser closes, reselect the same files to send only missing parts.
          Uploaded PDFs are retained in Evidence. If reading has not started,
          use Choose from Evidence to send the retained PDF for review.
        </p>
      )}
      {canUpload && <ResumableUploadsPanel caseId={caseId} financialContext active={active} />}
      {error && <p role="alert">{error}</p>}
      {queue && (
        <div aria-live="polite" className="space-y-2">
          {queue.items
            .filter(
              (item) =>
                !item.fileId ||
                !files.data?.some(
                  (file) =>
                    file.id === item.fileId && file.status === "processed"
                )
            )
            .map((item, index) => (
              <div
                key={index}
                className="rounded border p-2 text-sm break-words"
              >
                <strong>{item.name}</strong>
                <p>{item.status}</p>
                {item.error && <p className="text-destructive">{item.error}</p>}
              </div>
            ))}
        </div>
      )}
      <input
        aria-label="Search statement files"
        placeholder="Search filenames"
        className="w-full rounded border bg-background p-2"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      {register && !removed && !removalMode && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label>
            Show files{" "}
            <select
              className="rounded border bg-background p-2"
              value={status}
              onChange={(e) => showResults(e.target.value)}
            >
              <option value="all">All files</option>
              <option value="ready">Ready to import</option>
              <option value="checks">Checks to review</option>
              <option value="duplicates">Ignored duplicates</option>
              <option value="pending">Reading or importing</option>
              <option value="imported">With imported statements</option>
              <option value="review">Without imported statements</option>
              <option value="attention">Reading failed or not started</option>
            </select>
          </label>
          {files.data && (
            <span>
              {files.data.filter((file) => !file.financial_removed).length}{" "}
              files in Financial ·{" "}
              {imports.data?.files.filter(
                (file) =>
                  file.current_transactions > 0 || file.periods.length > 0
              ).length ?? "…"}{" "}
              with imported statements
            </span>
          )}
        </div>
      )}
      {files.isPending && <p role="status">Loading statement files…</p>}
      {register && !removed && !removalMode && imports.data && (
        <section
          aria-label="Statement work remaining"
          className="rounded border p-3 space-y-2"
        >
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              aria-pressed={status === "ready"}
              onClick={() => showResults("ready", true)}
            >
              Show {readyCount} statement{" "}
              {readyCount === 1 ? "period" : "periods"} ready to import
            </Button>
            <Button
              variant="outline"
              aria-pressed={status === "checks"}
              onClick={() => showResults("checks", true)}
            >
              Show{" "}
              {
                imports.data.files.filter(
                  (f) => f.periods_with_checks || f.incomplete_count
                ).length
              }{" "}
              files with checks to review
            </Button>
            <Button
              variant="outline"
              aria-pressed={status === "pending"}
              onClick={() => showResults("pending", true)}
            >
              Show{" "}
              {imports.data.files.reduce(
                (n, f) => n + (f.pending_periods || 0),
                0
              )}{" "}
              statement imports pending
            </Button>
            <Button variant="ghost" onClick={() => showResults("all", true)}>
              Show all files
            </Button>
          </div>
          <p className="text-sm">
            Open a matching file below to review its statements or import ready
            payments. A saved statement can still have checks; reading and
            importing are separate steps.
          </p>
          {imports.data.truncated && (
            <p role="status">
              This case has more records than the current summary can display.
              Counts are partial; use the file search to review the remaining
              files.
            </p>
          )}
        </section>
      )}
      {files.isError && <p role="alert">{files.error.message}</p>}
      {imports.isError && (
        <div role="alert">
          Statement import status could not be loaded.{" "}
          <Button variant="outline" onClick={() => void imports.refetch()}>
            Retry import status
          </Button>
        </div>
      )}
      {register && (!removed || removalMode) && canEdit && (
        <section
          aria-label="Selected statement files"
          className="rounded border bg-card p-3 space-y-2"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span>
              {selectedIds.length} {selectedIds.length === 1 ? "file" : "files"}{" "}
              selected
              {hiddenSelected ? ` · ${hiddenSelected} hidden by filters` : ""}
            </span>
            <Button
              variant="outline"
              disabled={preparing || !selectableFiles.length}
              onClick={() =>
                selectFiles([
                  ...new Set([
                    ...selectedIds,
                    ...selectableFiles.map((file) => file.id),
                  ]),
                ])
              }
            >
              Select all {selectableFiles.length} shown{" "}
              {selectableFiles.length === 1 ? "file" : "files"}
            </Button>
            <Button
              variant="ghost"
              disabled={preparing || !selectedIds.length}
              onClick={() => selectFiles([])}
            >
              Clear selection
            </Button>
            {!removalMode && (
              <Button
                disabled={
                  !canUpload ||
                  preparing ||
                  !selectedIds.length ||
                  files.isError
                }
                onClick={() => void prepareSelected()}
              >
                {preparing
                  ? "Preparing statements…"
                  : `Prepare statements from ${selectedIds.length} ${selectedIds.length === 1 ? "file" : "files"}`}
              </Button>
            )}
            {!removalMode && (
              <BulkStatementDetails
                caseId={caseId}
                fileIds={selectedIds}
                onSaved={refresh}
              />
            )}
            <FinancialRemovalAction
              caseId={caseId}
              fileIds={selectedIds}
              label={
                selectedIds.length
                  ? `Review removal of ${selectedIds.length} selected ${selectedIds.length === 1 ? "file" : "files"}`
                  : "Select files to remove"
              }
              onRemoved={() => selectFiles([])}
            />
            {removalMode && (
              <Button variant="outline" onClick={onFinishRemoval}>
                Back to files
              </Button>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {removalMode
              ? "Tick individual files below or select all shown files, then review the removal. Nothing is removed until you confirm."
              : "Select PDFs to edit account details across their statements, prepare them together or remove their imports. Other sources have their own review and removal actions. Edit account details lets you choose the individual periods before saving."}
          </p>
        </section>
      )}
      {register && !removalMode && auditFilter?.caseId === caseId && (
        <div className="rounded border p-3 text-sm space-y-2">
          <p>Showing source selected for review: {auditFilter.filename}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAuditFilter(null)
                setFilterAction((value) => value + 1)
              }}
            >
              Clear source filter
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAuditFilter(null)
                sourceReview.current?.focus()
                sourceReview.current?.scrollIntoView({ block: "start" })
              }}
            >
              Back to source review
            </Button>
          </div>
        </div>
      )}
      {register && !removalMode && (
        <div className="space-y-1">
          <h3
            ref={resultsHeading}
            tabIndex={-1}
            className="font-semibold scroll-mt-24 focus:outline-none"
            aria-live="polite"
          >
            {removed
              ? `Removed files · ${visibleFiles.length} matching files`
              : status === "ready"
                ? `Ready to import · ${visibleReadyCount} statement ${visibleReadyCount === 1 ? "period" : "periods"} in ${visibleFiles.length} ${visibleFiles.length === 1 ? "file" : "files"}`
                : `${visibleFiles.length} matching files`}
          </h3>
          {status === "ready" && (
            <p className="text-sm">
              Choose Review and import beside a statement to check its source
              and confirm the import. Your list stays here when you return. Use
              the file selection controls above to review several PDFs together.
            </p>
          )}
        </div>
      )}
      {visibleFiles.map((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        const allPreparedIgnored =
          !!saved?.ignored_periods &&
          saved.ignored_periods === saved.prepared_periods &&
          !saved.current_transactions &&
          !saved.periods.length
        if (!usesPdfStatementReader(file))
          return (
            <FinancialSourceFile
              key={file.id}
              caseId={caseId}
              file={file}
              importedPayments={saved?.current_transactions}
              onVisibilityChanged={(removed) =>
                setVisibilityResult({
                  caseId,
                  filename: file.original_filename,
                  removed,
                })
              }
            />
          )
        return (
          <div
            key={file.id}
            className="rounded-lg border bg-card p-3 space-y-2"
          >
            {register && (!removed || removalMode) && canEdit && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label={`Select ${file.original_filename}`}
                  checked={selectedIds.includes(file.id)}
                  disabled={preparing}
                  onChange={(event) =>
                    selectFiles(
                      event.target.checked
                        ? [...selectedIds, file.id]
                        : selectedIds.filter((id) => id !== file.id)
                    )
                  }
                />
                {removalMode
                  ? `Select ${file.original_filename}`
                  : "Select file"}
              </label>
            )}
            <button
              type="button"
              aria-pressed={selected === file.id}
              aria-label={
                register
                  ? `${removalMode ? "Imported file" : "Review"} ${file.original_filename}`
                  : undefined
              }
              disabled={removalMode || removed || file.status !== "processed"}
              className={
                register
                  ? `grid w-full gap-2 rounded p-2 text-left text-sm md:grid-cols-[minmax(220px,1fr)_minmax(220px,1fr)] ${removalMode ? "" : "hover:bg-accent disabled:opacity-60"}`
                  : "block w-full rounded border p-3 text-left text-sm hover:bg-accent aria-pressed:border-primary aria-pressed:bg-accent disabled:opacity-60"
              }
              onClick={() => openStatement(file.id)}
            >
              <span className="block break-words font-medium">
                {file.original_filename}
                {file.readingVersions.length > 1 && (
                  <span className="block text-xs text-muted-foreground">
                    One PDF · {file.readingVersions.length} retained reading
                    versions
                  </span>
                )}
              </span>
              <span
                className="finance-badge"
                data-finance-tone={
                  file.status === "failed"
                    ? "debit"
                    : saved?.current_transactions ||
                        saved?.periods.length ||
                        saved?.wire_review_count
                      ? "info"
                      : "review"
                }
              >
                {removed
                  ? "Removed from Financial"
                  : allPreparedIgnored
                    ? "Duplicate - Ignored by system"
                    : saved?.wire_review_count
                      ? `${saved.wire_review_count} saved wire ${saved.wire_review_count === 1 ? "review" : "reviews"}`
                      : saved?.incomplete_count
                        ? `${saved.current_transactions} usable transactions · ${saved.incomplete_count} incomplete records to check`
                        : saved?.periods.length && !saved.current_transactions
                          ? `Statement saved · ${saved.periods.length} recorded ${saved.periods.length === 1 ? "period" : "periods"} · no payments`
                          : saved
                            ? `${saved.current_transactions} imported payments · ${saved.periods.length} recorded ${saved.periods.length === 1 ? "period" : "periods"}`
                            : file.status === "processed"
                              ? imports.data && !imports.data.truncated
                                ? "PDF read · payments not yet imported"
                                : "Ready to open"
                              : file.status === "unprocessed" &&
                                  queuedReadings.has(file.id)
                                ? "Reading queued — waiting for progress"
                                : file.status}
              </span>
              {saved?.prepared_periods !== undefined && (
                <span className="block text-sm">
                  {saved.periods.length} of{" "}
                  {Math.max(saved.prepared_periods, saved.periods.length)}{" "}
                  statement periods saved
                  {saved.available_periods
                    ? ` · ${saved.available_periods} available to import`
                    : ""}
                  {saved.pending_periods
                    ? ` · ${saved.pending_periods} imports pending`
                    : ""}
                  {saved.periods_with_checks
                    ? ` · ${saved.periods_with_checks} periods have checks to review`
                    : ""}
                  {saved.ignored_periods
                    ? ` · ${saved.ignored_periods} duplicate ${saved.ignored_periods === 1 ? "period" : "periods"} ignored`
                    : ""}
                </span>
              )}
              {saved?.periods.slice(0, 2).map((period) => (
                <span key={period.id} className="block text-xs mt-1">
                  {period.account_label} ·{" "}
                  {period.start || "Start not recorded"} to{" "}
                  {period.end || "End not recorded"}
                  {period.source_status !== "admitted"
                    ? " · source excluded"
                    : ""}
                </span>
              ))}
              {(saved?.periods.length ?? 0) > 2 && (
                <span className="text-xs">
                  {removalMode
                    ? `All ${saved!.periods.length} periods will be included in the removal preview.`
                    : `${saved!.periods.length - 2} more periods in this PDF. Open the file to choose a period.`}
                </span>
              )}
              {!!saved?.receipt_review_count && (
                <p>
                  {saved.receipt_review_count} saved receipt{" "}
                  {saved.receipt_review_count === 1 ? "review" : "reviews"}
                </p>
              )}
              {saved && !saved.wire_review_count && !removalMode && (
                <span className="block text-xs mt-1">Review statement →</span>
              )}
              {file.created_at && (
                <span className="block text-xs text-muted-foreground">
                  Added {new Date(file.created_at).toLocaleString()} ·{" "}
                  {file.id.slice(-6)}
                </span>
              )}
            </button>
            {!!saved?.duplicate_dispositions.length &&
              !removalMode &&
              !removed && (
                <details className="rounded border p-2 text-sm">
                  <summary className="cursor-pointer font-medium">
                    Duplicate decisions · evidence retained
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {saved.duplicate_dispositions.map(
                      ({ statement_id, decision }) => (
                        <li
                          key={statement_id || "file"}
                          className="space-y-1 rounded border p-2"
                        >
                          <p className="font-medium">
                            {decision.current && decision.status === "ignored"
                              ? "Duplicate - Ignored by system"
                              : decision.label}
                          </p>
                          <p>{decision.reason}</p>
                          {decision.retained && (
                            <p className="break-words">
                              Retained source: {decision.retained.filename}
                            </p>
                          )}
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={file.status !== "processed"}
                            onClick={() =>
                              openStatement(file.id, statement_id || "")
                            }
                          >
                            Review duplicate decision
                          </Button>
                        </li>
                      )
                    )}
                  </ul>
                </details>
              )}
            {status === "ready" &&
              !removed &&
              !removalMode &&
              file.status === "processed" &&
              (saved?.ready_periods.length ? (
                <ReadyStatementPeriods
                  periods={saved.ready_periods}
                  canEdit={canEdit}
                  onReview={(statementId) =>
                    openStatement(file.id, statementId)
                  }
                />
              ) : (
                <Button
                  variant="outline"
                  onClick={() => openStatement(file.id)}
                >
                  {canEdit ? "Review and import" : "Review statement"}
                </Button>
              ))}
            {!removalMode && (
              <FinancialFileAction
                caseId={caseId}
                file={file}
                onVisibilityChanged={(removed) =>
                  setVisibilityResult({
                    caseId,
                    filename: file.original_filename,
                    removed,
                  })
                }
                imported={
                  !!saved?.periods.length || !!saved?.current_transactions
                }
              />
            )}
            {!!saved?.wire_review_count && (
              <a
                className="inline-block underline text-sm"
                href={`/cases/${caseId}/financial?view=findings`}
              >
                Open saved wire reviews in Findings
              </a>
            )}
            {!!saved?.receipt_review_count && (
              <a
                className="inline-block underline text-sm"
                href={`/cases/${caseId}/financial?view=findings`}
              >
                Open saved receipt reviews in Findings
              </a>
            )}
            {!removed &&
              canUpload &&
              ["unprocessed", "failed"].includes(file.status) && (
                <Button
                  variant="outline"
                  disabled={
                    reading[file.id] ||
                    queue?.running ||
                    (file.status === "unprocessed" &&
                      queuedReadings.has(file.id))
                  }
                  aria-label={`${file.status === "failed" ? "Retry reading" : "Read statement"}: ${file.original_filename}`}
                  onClick={() => void readStatement(file.id)}
                >
                  {reading[file.id]
                    ? "Starting reading…"
                    : file.status === "failed"
                      ? "Retry reading"
                      : "Read statement"}
                </Button>
              )}
            {file.readingVersions.length > 1 && (
              <details className="text-sm">
                <summary className="cursor-pointer">
                  Reading history ({file.readingVersions.length} versions of
                  this PDF)
                </summary>
                <p className="text-xs text-muted-foreground">
                  These are retained readings of one source, not additional
                  uploaded statements. Opening a reading does not import it.
                </p>
                <ul className="mt-2 max-h-48 overflow-auto">
                  {file.readingVersions.map((version) => (
                    <li key={version.id}>
                      <Button
                        size="sm"
                        variant="link"
                        disabled={
                          version.status !== "processed" ||
                          version.financial_removed
                        }
                        onClick={() => {
                          useStatementWorkspace
                            .getState()
                            .select(scope, version.id)
                          useFinancialStore.getState().setMainView("statements")
                          onOpen?.()
                        }}
                      >
                        {version.id === file.id
                          ? "Current reading"
                          : "Earlier reading"}{" "}
                        ·{" "}
                        {version.created_at
                          ? new Date(version.created_at).toLocaleString()
                          : version.id.slice(0, 8)}{" "}
                        ·{" "}
                        {version.financial_removed
                          ? "Removed from Financial"
                          : version.status}
                      </Button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )
      })}
      {register && imports.data?.truncated && (
        <p role="alert">
          Import status is incomplete. Open individual files to check every
          recorded period.
        </p>
      )}
      {imports.isError && (
        <p className="text-xs">
          Import status could not be loaded. Open a file to check its saved
          import.
        </p>
      )}
      {!files.isError && !!files.data?.length && visibleFiles.length === 0 && (
        <p>
          {removed
            ? "No removed files match this search."
            : "No files match these filters. Clear the filename search or check Removed files."}
        </p>
      )}
      {files.data?.length === 0 && (
        <p>
          No files have been added to Financial. Upload statements or choose
          financial sources from Evidence.
        </p>
      )}
    </section>
  )
}
