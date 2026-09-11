import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { newReviewId } from "../lib/statement-review-id"

const receiptSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  job_id: z.string(),
})
const recoverySchema = z.object({
  requestId: z.string().uuid(),
  receipt: receiptSchema.nullable(),
})

export function ReprocessStatement({
  caseId,
  fileId,
  onReady,
}: {
  caseId: string
  fileId: string
  onReady: (id: string) => void
}) {
  const owner = useAuthStore((state) => state.user?.id || state.user?.username)
  const storageKey = owner
    ? `loupe-statement-reprocessing:${owner}:${caseId}:${fileId}`
    : null
  const [saved] = useState(() => {
    try {
      const raw = storageKey && sessionStorage.getItem(storageKey)
      if (!raw) return null
      const recovered = recoverySchema.parse(JSON.parse(raw))
      if (
        recovered.receipt &&
        (recovered.receipt.case_id !== caseId ||
          recovered.receipt.evidence_file_id === fileId)
      )
        return null
      return recovered
    } catch {
      return null
    }
  })
  const [requestId] = useState(() => saved?.requestId ?? newReviewId())
  const [receipt, setReceipt] = useState(saved?.receipt ?? null)
  const [storageFailed, setStorageFailed] = useState(false)
  function remember(value: z.infer<typeof receiptSchema> | null) {
    if (!storageKey) return
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ requestId, receipt: value })
      )
    } catch {
      setStorageFailed(true)
    }
  }
  const delivered = useRef(false)
  const start = useMutation({
    retry: false,
    mutationFn: async () => {
      remember(receipt)
      const result = receiptSchema.parse(
        await fetchAPI(
          `/api/financial/statement-import/${fileId}/reprocess?${new URLSearchParams({ case_id: caseId })}`,
          { method: "POST", body: { request_id: requestId } }
        )
      )
      if (result.case_id !== caseId || result.evidence_file_id === fileId)
        throw Error("The new reading does not match this case.")
      remember(result)
      setReceipt(result)
      return result
    },
  })
  const job = useQuery({
    queryKey: ["statement-reprocessing", caseId, receipt?.job_id],
    enabled: !!receipt,
    retry: false,
    queryFn: async () => {
      const result = z
        .object({
          id: z.string(),
          case_id: z.string(),
          job_type: z.string(),
          status: z.string(),
          quality_report: z.record(z.string(), z.unknown()).optional(),
        })
        .parse(
          await fetchAPI(
            `/api/evidence/engine/jobs/${encodeURIComponent(receipt!.job_id)}`
          )
        )
      if (
        result.id !== receipt!.job_id ||
        result.case_id !== caseId ||
        result.job_type !== "pdf_review"
      )
        throw Error("The preparation result does not match this statement.")
      return result
    },
    refetchInterval: (q) =>
      q.state.error ||
      ["completed", "failed"].includes(q.state.data?.status ?? "")
        ? false
        : 2000,
  })
  const ready =
    job.data?.status === "completed" &&
    job.data.quality_report?.preparation_mode === "pdf_review"
  useEffect(() => {
    if (ready && receipt && !saved?.receipt && !delivered.current) {
      delivered.current = true
      onReady(receipt.evidence_file_id)
    }
  }, [ready, receipt, onReady, saved])
  return (
    <details className="border rounded p-3" open={!!receipt || !!saved}>
      <summary>Read the statement again</summary>
      <p className="text-sm my-2">
        Use this if the extraction missed information. A new reading will open
        for review. Existing transactions stay in use until you confirm their
        replacement. Finish or record any unsaved corrections before starting.
      </p>
      <Button
        variant="outline"
        disabled={
          start.isPending || (!!receipt && job.data?.status !== "failed")
        }
        onClick={() => start.mutate()}
      >
        {start.isPending ? "Starting new reading…" : "Reprocess statement"}
      </Button>
      {receipt && (
        <p role="status">
          New reading:{" "}
          {job.data?.status.replaceAll("_", " ") ?? "checking progress"}
        </p>
      )}
      {ready && receipt && (
        <Button onClick={() => onReady(receipt.evidence_file_id)}>
          Open new reading
        </Button>
      )}
      {(start.isError || job.isError) && (
        <p role="alert">{start.error?.message || job.error?.message}</p>
      )}
      {saved && !receipt && !start.isPending && (
        <p role="status">
          A previous request was interrupted. Resume it using Reprocess
          statement; the same request will be checked without creating another
          version.
        </p>
      )}
      {storageFailed && (
        <p role="alert">
          This browser could not save processing progress. Keep this page open
          until the new reading is ready.
        </p>
      )}
      {job.isError && (
        <Button onClick={() => void job.refetch()}>Check progress again</Button>
      )}
      {job.data?.status === "failed" && (
        <p role="alert">
          The new reading failed. Your previous import is unchanged. Check the
          file in Evidence for the processing error.
        </p>
      )}
    </details>
  )
}
