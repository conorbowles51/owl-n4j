import { useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useFinancialStore } from "../stores/financial.store"
import { useStatementWorkspace } from "../stores/statement-workspace"
import {
  uploadStatementFiles,
  useStatementUploads,
} from "../stores/statement-upload-queue"

const listing = z.object({
  files: z.array(
    z.object({
      id: z.string(),
      case_id: z.string(),
      original_filename: z.string(),
      status: z.string(),
      created_at: z.string().optional(),
    })
  ),
})

export function StatementFilesPanel({ caseId }: { caseId: string }) {
  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const scope = `${owner}:${caseId}`
  const client = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [search, setSearch] = useState("")
  const [error, setError] = useState("")
  const queue = useStatementUploads((state) => state.queues[scope])
  const selected = useStatementWorkspace(
    (state) => state.selections[scope]?.fileId
  )
  const files = useQuery({
    queryKey: ["statement-import-files", caseId],
    queryFn: async () => {
      const result = listing.parse(
        await fetchAPI(
          `/api/evidence?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (result.files.some((file) => file.case_id !== caseId))
        throw Error("The returned file list belongs to another case.")
      return result.files.filter((file) =>
        file.original_filename.toLowerCase().endsWith(".pdf")
      )
    },
    refetchInterval: (query) =>
      queue?.running ||
      query.state.data?.some((file) =>
        ["processing", "unprocessed", "queued"].includes(file.status)
      )
        ? 3000
        : false,
  })
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["statement-import-files", caseId],
    })
  }
  return (
    <section
      aria-label="Statement files"
      className="h-full overflow-auto p-3 space-y-3"
    >
      <h2 className="font-semibold">Statement files</h2>
      <p className="text-sm text-muted-foreground">
        Upload PDFs together, then select a ready file to open it in the
        statement viewer.
      </p>
      <input
        ref={input}
        type="file"
        multiple
        accept="application/pdf,.pdf"
        aria-label="Statement PDFs"
        className="hidden"
        onChange={(event) => {
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
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={queue?.running}
          onClick={() => input.current?.click()}
        >
          Upload statements
        </Button>
        <Button variant="outline" onClick={() => void files.refetch()}>
          Refresh files
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Up to 20 PDFs per selection. Keep the browser tab open while uploads
        finish. Each statement is reviewed and confirmed separately.
      </p>
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
      {files.isPending && <p role="status">Loading statement files…</p>}
      {files.isError && <p role="alert">{files.error.message}</p>}
      {files.data
        ?.filter((file) =>
          file.original_filename.toLowerCase().includes(search.toLowerCase())
        )
        .map((file) => (
          <button
            key={file.id}
            type="button"
            aria-pressed={selected === file.id}
            disabled={file.status !== "processed"}
            className="block w-full rounded border p-3 text-left text-sm hover:bg-accent aria-pressed:border-primary aria-pressed:bg-accent disabled:opacity-60"
            onClick={() => {
              useStatementWorkspace.getState().select(scope, file.id)
              useFinancialStore.getState().setMainView("transactions")
              useFinancialStore.getState().setMode("transactions")
            }}
          >
            <span className="block break-words font-medium">
              {file.original_filename}
            </span>
            <span className="block text-xs">
              {file.status === "processed" ? "Ready to review" : file.status}
            </span>
            {file.created_at && (
              <span className="block text-xs text-muted-foreground">
                Added {new Date(file.created_at).toLocaleString()} ·{" "}
                {file.id.slice(-6)}
              </span>
            )}
          </button>
        ))}
      {files.data?.length === 0 && (
        <p>No PDFs have been uploaded to this case.</p>
      )}
    </section>
  )
}
