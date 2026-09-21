import { FinancialRemovalAction } from "./FinancialRemovalAction"
import { useStatementRegister } from "../hooks/use-statement-register"
import { FinancialFileAction } from "./FinancialFileAction"
import { EvidenceFinancialPicker } from "./EvidenceFinancialPicker"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useRef, useState } from "react"
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
}: {
  caseId: string
  register?: boolean
  onOpen?: () => void
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
  const [removed, setRemoved] = useState(false)
  const [error, setError] = useState("")
  const [reading, setReading] = useState<Record<string, boolean>>({})
  const [selection, setSelection] = useState<{ scope: string; ids: string[] }>({
    scope,
    ids: [],
  })
  const [preparing, setPreparing] = useState(false)
  const batchRequest = useRef<{ selection: string; id: string } | null>(null)
  const queue = useStatementUploads((state) => state.queues[scope])
  const selected = useStatementWorkspace(
    (state) => state.selections[scope]?.fileId
  )
  const { files, imports } = useStatementRegister(
    caseId,
    !!queue?.running,
    queue?.items.flatMap((item) =>
      item.status === "Reading queued" && item.fileId ? [item.fileId] : []
    ) ?? [],
    true
  )
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["statement-import-files", caseId],
    })
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
      ?.filter((file) => file.financial_removed === removed)
      ?.filter((file) =>
        file.original_filename.toLowerCase().includes(search.toLowerCase())
      )
      .filter((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        return (
          removed ||
          status === "all" ||
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
  const selectedIds = (selection.scope === scope ? selection.ids : []).filter(
    (id) =>
      files.data?.some((file) => file.id === id && !file.financial_removed)
  )
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
      <h2 className="font-semibold">
        {register ? "Files in this case" : "Statement files"}
      </h2>
      <p className="text-sm text-muted-foreground">
        {canUpload
          ? "Upload PDFs together, then select a ready file to open it in the statement viewer."
          : "Select a ready file to open its original PDF and extracted statement."}{" "}
        Supported wire reports and deposit receipts open their own review.
      </p>
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
      <div className="flex flex-wrap gap-2">
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
      {removed && (
        <p className="text-sm">
          These files were removed from Financial. Their originals remain in
          Evidence. Restore a file to review it here again.
        </p>
      )}
      {canUpload && (
        <p className="text-xs text-muted-foreground">
          Up to 20 PDFs per selection. Keep the browser tab open while uploads
          finish. Select files below to prepare their statements together, or
          open one file for individual review.
        </p>
      )}
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
      {register && !removed && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label>
            Show files{" "}
            <select
              className="rounded border bg-background p-2"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All files</option>
              <option value="imported">With imported statements</option>
              <option value="review">Without imported statements</option>
              <option value="attention">Reading failed or not started</option>
            </select>
          </label>
          {files.data && (
            <span>
              {files.data.filter((file) => !file.financial_removed).length} PDFs
              in Financial ·{" "}
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
      {files.isError && <p role="alert">{files.error.message}</p>}
      {register && !removed && canEdit && (
        <section
          aria-label="Prepare selected statement files"
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
              disabled={preparing || !visibleFiles.length}
              onClick={() =>
                selectFiles([
                  ...new Set([
                    ...selectedIds,
                    ...visibleFiles.map((file) => file.id),
                  ]),
                ])
              }
            >
              Select all {visibleFiles.length} shown{" "}
              {visibleFiles.length === 1 ? "file" : "files"}
            </Button>
            <Button
              variant="ghost"
              disabled={preparing || !selectedIds.length}
              onClick={() => selectFiles([])}
            >
              Clear selection
            </Button>
            <Button
              disabled={
                !canUpload || preparing || !selectedIds.length || files.isError
              }
              onClick={() => void prepareSelected()}
            >
              {preparing
                ? "Preparing statements…"
                : `Prepare statements from ${selectedIds.length} ${selectedIds.length === 1 ? "file" : "files"}`}
            </Button>
            <FinancialRemovalAction
              caseId={caseId}
              fileIds={selectedIds}
              label={`Remove ${selectedIds.length} selected files / imports`}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            All recognised accounts and periods go into one batch. Import them
            together there; you can return to reading issues later. Existing
            imports are recognised.
          </p>
        </section>
      )}
      {visibleFiles.map((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        return (
          <div key={file.id} className="space-y-1">
            {register && !removed && canEdit && (
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
                Select for preparation or removal
              </label>
            )}
            <button
              type="button"
              aria-pressed={selected === file.id}
              disabled={removed || file.status !== "processed"}
              className={
                register
                  ? "grid w-full gap-3 rounded-lg border bg-card p-4 text-left text-sm hover:bg-accent aria-pressed:border-primary disabled:opacity-60 md:grid-cols-[minmax(220px,1fr)_minmax(220px,1fr)]"
                  : "block w-full rounded border p-3 text-left text-sm hover:bg-accent aria-pressed:border-primary aria-pressed:bg-accent disabled:opacity-60"
              }
              onClick={() => {
                useStatementWorkspace.getState().select(scope, file.id)
                useFinancialStore.getState().setMainView("statements")
                useFinancialStore.getState().setMode("transactions")
                onOpen?.()
              }}
            >
              <span className="block break-words font-medium">
                {file.original_filename}
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
                  : saved?.wire_review_count
                    ? `${saved.wire_review_count} saved wire ${saved.wire_review_count === 1 ? "review" : "reviews"}`
                    : saved?.incomplete_count
                      ? `${saved.current_transactions} usable transactions · ${saved.incomplete_count} incomplete records to check`
                      : saved?.periods.length && !saved.current_transactions
                        ? `Statement saved · ${saved.periods.length} recorded ${saved.periods.length === 1 ? "period" : "periods"} · no payments`
                        : saved
                          ? `${saved.current_transactions} imported payments · ${saved.periods.length} recorded periods`
                          : file.status === "processed"
                            ? imports.data && !imports.data.truncated
                              ? "Ready to review"
                              : "Ready to open"
                            : file.status}
              </span>
              {saved?.periods
                .slice(0, register ? undefined : 3)
                .map((period) => (
                  <span key={period.id} className="block text-xs mt-1">
                    {period.account_label} ·{" "}
                    {period.start || "Start not recorded"} to{" "}
                    {period.end || "End not recorded"}
                    {period.source_status !== "admitted"
                      ? " · source excluded"
                      : ""}
                  </span>
                ))}
              {!!saved?.receipt_review_count && (
                <p>
                  {saved.receipt_review_count} saved receipt{" "}
                  {saved.receipt_review_count === 1 ? "review" : "reviews"}
                </p>
              )}
              {saved && !saved.wire_review_count && (
                <span className="block text-xs mt-1">
                  Open to review this file and any other statement periods.
                </span>
              )}
              {file.created_at && (
                <span className="block text-xs text-muted-foreground">
                  Added {new Date(file.created_at).toLocaleString()} ·{" "}
                  {file.id.slice(-6)}
                </span>
              )}
            </button>
            <FinancialFileAction
              caseId={caseId}
              file={file}
              imported={
                !!saved?.periods.length || !!saved?.current_transactions
              }
            />
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
                  disabled={reading[file.id] || queue?.running}
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
        <p>No PDFs have been uploaded to this case.</p>
      )}
    </section>
  )
}
