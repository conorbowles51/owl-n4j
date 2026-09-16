import { useStatementRegister } from "../hooks/use-statement-register"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
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
  const { canUpload } = useFinancialAccess()
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const [error, setError] = useState("")
  const [reading, setReading] = useState<Record<string, boolean>>({})
  const queue = useStatementUploads((state) => state.queues[scope])
  const selected = useStatementWorkspace(
    (state) => state.selections[scope]?.fileId
  )
  const { files, imports } = useStatementRegister(
    caseId,
    !!queue?.running,
    queue?.items.flatMap((item) =>
      item.status === "Reading queued" && item.fileId ? [item.fileId] : []
    ) ?? []
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
      ?.filter((file) =>
        file.original_filename.toLowerCase().includes(search.toLowerCase())
      )
      .filter((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        return (
          status === "all" ||
          (status === "imported" && !!saved?.current_transactions) ||
          (status === "review" &&
            imports.data &&
            !imports.data.truncated &&
            !saved?.current_transactions) ||
          (status === "attention" &&
            ["failed", "unprocessed"].includes(file.status))
        )
      }) ?? []
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
      </div>
      {canUpload && (
        <p className="text-xs text-muted-foreground">
          Up to 20 PDFs per selection. Keep the browser tab open while uploads
          finish. Each statement is reviewed and confirmed separately.
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
      {register && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label>
            Show files{" "}
            <select
              className="rounded border bg-background p-2"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All files</option>
              <option value="imported">With imported payments</option>
              <option value="review">Without imported payments</option>
              <option value="attention">Reading failed or not started</option>
            </select>
          </label>
          {files.data && (
            <span>
              {files.data.length} uploaded PDFs ·{" "}
              {imports.data?.files.filter(
                (file) => file.current_transactions > 0
              ).length ?? "…"}{" "}
              with imported payments
            </span>
          )}
        </div>
      )}
      {files.isPending && <p role="status">Loading statement files…</p>}
      {files.isError && <p role="alert">{files.error.message}</p>}
      {visibleFiles.map((file) => {
        const saved = imports.data?.files.find(
          (item) => item.evidence_file_id === file.id
        )
        return (
          <div key={file.id} className="space-y-1">
            <button
              type="button"
              aria-pressed={selected === file.id}
              disabled={file.status !== "processed"}
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
              <span className="block text-xs">
                {saved?.wire_review_count
                  ? `${saved.wire_review_count} saved wire ${saved.wire_review_count === 1 ? "review" : "reviews"}`
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
            {canUpload && ["unprocessed", "failed"].includes(file.status) && (
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
          No files match these filters. Clear the filename search or choose All
          files.
        </p>
      )}
      {files.data?.length === 0 && (
        <p>No PDFs have been uploaded to this case.</p>
      )}
    </section>
  )
}
