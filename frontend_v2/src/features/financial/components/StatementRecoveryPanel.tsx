import { useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"

const recoverySchema = z.object({
  run: z
    .object({ id: z.string(), status: z.string(), release: z.string() })
    .nullable(),
  total: z.number(),
  added: z.number().default(0),
  counts: z.record(z.string(), z.number()),
  items: z.array(
    z.object({
      id: z.string(),
      file_id: z.string(),
      review_file_id: z.string().optional(),
      filename: z.string(),
      status: z.string(),
      message: z.string().optional(),
      added: z.number(),
      sections: z
        .array(
          z.object({
            statement_id: z.string().nullable().optional(),
            status: z.string(),
            message: z.string(),
            added: z.number(),
          })
        )
        .optional(),
    })
  ),
})

export function StatementRecoveryPanel({
  caseId,
  onReview,
}: {
  caseId: string
  onReview: (fileId: string) => void
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const query = useQuery({
    queryKey: ["financial-deployment-recovery", caseId, offset],
    queryFn: async () =>
      recoverySchema.parse(
        await fetchAPI(
          `/api/financial/statement-import/deployment-recovery?case_id=${caseId}&offset=${offset}`
        )
      ),
    refetchInterval: (query) =>
      !query.state.data?.run || query.state.data.run.status === "running"
        ? 5000
        : false,
  })
  const recovered = query.data?.added ?? 0
  useEffect(() => {
    if (!recovered) return
    // Refresh saved counts and Transactions without resetting an open editor.
    for (const key of [
      "statement-import-status",
      "statement-import-files",
      "financial-ledger",
    ]) {
      void client.invalidateQueries({ queryKey: [key, caseId] })
    }
  }, [recovered, caseId, client])
  const act = async (action: string) => {
    setBusy(true)
    setError("")
    try {
      await fetchAPI(
        `/api/financial/statement-import/deployment-recovery/${action}?case_id=${caseId}`,
        { method: "POST" }
      )
      await client.invalidateQueries({
        queryKey: ["financial-deployment-recovery", caseId],
      })
      await client.invalidateQueries({
        queryKey: ["statement-import-files", caseId],
      })
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The recovery action could not be confirmed. Refresh its status before retrying."
      )
    } finally {
      setBusy(false)
    }
  }
  if (query.isError)
    return (
      <p role="alert" className="text-sm">
        Statement recovery status could not be loaded.{" "}
        <button className="underline" onClick={() => void query.refetch()}>
          Retry recovery status
        </button>
      </p>
    )
  const data = query.data
  if (!data?.run) return null
  const pending =
    (data.counts.pending ?? 0) +
    (data.counts.waiting ?? 0) +
    (data.counts.reading ?? 0)
  const label =
    data.run.status === "complete"
      ? "Finished checking"
      : data.run.status === "paused"
        ? "Paused"
        : "Checking previous statements"
  return (
    <section
      aria-label="Recovery of previous statements"
      className="rounded-lg border bg-card p-3 space-y-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Recovery of previous statements</h3>
        {canEdit && data.run.status !== "complete" && (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() =>
              void act(data.run!.status === "paused" ? "resume" : "pause")
            }
          >
            {busy
              ? "Saving…"
              : data.run.status === "paused"
                ? "Resume recovery"
                : "Pause recovery"}
          </Button>
        )}
      </div>
      <p role="status" className="text-sm">
        {label} · {data.total - pending} of {data.total} files checked ·{" "}
        {data.counts.review ?? 0} need review
      </p>
      <p className="text-sm text-muted-foreground">
        This one-time check uses the improved statement reader. Verified missing
        payments are added to existing imports. Your saved payments, edits and
        notes stay in place. New imports and uncertain matches need your review.
      </p>
      {error && <p role="alert">{error}</p>}
      {recovered > 0 && (
        <p className="text-sm font-medium">
          {recovered} recovered{" "}
          {recovered === 1 ? "payment is" : "payments are"} saved in
          Transactions.
        </p>
      )}
      <details>
        <summary className="cursor-pointer text-sm font-medium">
          Review recovery results
        </summary>
        <ul className="divide-y mt-2">
          {data.items.map((item) => (
            <li key={item.id} className="py-3 space-y-2">
              <div className="flex flex-wrap gap-2 items-start justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium break-words">
                    {item.filename}
                  </p>
                  <p className="text-sm">
                    {item.message || "Waiting to check this source."}
                  </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {item.filename.toLowerCase().endsWith(".pdf") ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        onReview(item.review_file_id || item.file_id)
                      }
                    >
                      Open statement
                    </Button>
                  ) : (
                    <a
                      className="underline text-sm"
                      href={`/cases/${caseId}/evidence?file=${encodeURIComponent(item.file_id)}&from=financial`}
                    >
                      Open source in Evidence
                    </a>
                  )}
                  {canEdit && item.status === "review" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => void act(`items/${item.id}/retry`)}
                    >
                      Retry recovery
                    </Button>
                  )}
                </div>
              </div>
              {item.sections
                ?.filter((section) => section.status === "review")
                .map((section, index) => (
                  <p
                    key={section.statement_id || index}
                    className="text-sm text-muted-foreground"
                  >
                    {section.message}
                  </p>
                ))}
            </li>
          ))}
        </ul>
        {data.total > 50 && (
          <div className="flex gap-2 items-center mt-2">
            <Button
              variant="outline"
              disabled={offset === 0 || query.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous recovery results
            </Button>
            <span className="text-sm">
              {offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}
            </span>
            <Button
              variant="outline"
              disabled={offset + 50 >= data.total || query.isFetching}
              onClick={() => setOffset(offset + 50)}
            >
              Next recovery results
            </Button>
          </div>
        )}
      </details>
    </section>
  )
}
