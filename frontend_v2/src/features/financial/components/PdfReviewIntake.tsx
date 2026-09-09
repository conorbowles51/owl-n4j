import { evidenceAPI } from "@/features/evidence/api"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
const uploadAnswer = z.object({
  files: z.array(
    z.object({
      id: z.string(),
      case_id: z.string(),
      original_filename: z.string(),
      engine_job_id: z.string().nullable().optional(),
      status: z.string(),
    })
  ),
})
const started = z.object({
  job_ids: z.array(z.string()).nullable().optional(),
  message: z.string().optional(),
})
const jobAnswer = z.object({
  id: z.string(),
  case_id: z.string(),
  status: z.string(),
  job_type: z.string(),
  quality_report: z.record(z.string(), z.unknown()).optional(),
})
export function PdfReviewIntake({
  caseId,
  onReady,
}: {
  caseId: string
  onReady: () => void
}) {
  const [file, setFile] = useState<File | null>(null),
    [fileId, setFileId] = useState<string | null>(null),
    [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("")
  const [showExisting, setShowExisting] = useState(false)
  const existing = useQuery({
    queryKey: ["financial-candidates", caseId, "uploaded-pdfs"],
    enabled: showExisting,
    retry: false,
    queryFn: async () => {
      const result = uploadAnswer.parse(
        await fetchAPI(
          `/api/evidence?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (result.files.some((f) => f.case_id !== caseId))
        throw Error("Uploaded files belong to another case.")
      return result.files.filter((f) =>
        f.original_filename.toLowerCase().endsWith(".pdf")
      )
    },
  })
  const job = useQuery({
    queryKey: ["financial-candidates", caseId, "prepare-pdf", jobId],
    enabled: !!jobId,
    retry: false,
    queryFn: async () => {
      const result = jobAnswer.parse(
        await fetchAPI(
          `/api/evidence/engine/jobs/${encodeURIComponent(jobId!)}`
        )
      )
      if (
        result.id !== jobId ||
        result.case_id !== caseId ||
        result.job_type !== "pdf_review"
      )
        throw Error("Preparation result does not match this PDF review job.")
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
  const running = !!jobId && !ready && job.data?.status !== "failed"
  const prepare = async () => {
    if ((!file && !fileId) || busy) return
    setBusy(true)
    setError("")
    try {
      let id = fileId
      if (!id) {
        const body = new FormData()
        body.append("case_id", caseId)
        body.append("files", file!)
        const result = uploadAnswer.parse(
          await fetchAPI("/api/evidence/upload", {
            method: "POST",
            body,
            timeout: 120000,
          })
        )
        if (
          result.files.length !== 1 ||
          result.files[0].original_filename !== file!.name ||
          result.files[0].case_id !== caseId
        )
          throw Error("Upload did not return the selected PDF.")
        id = result.files[0].id
        setFileId(id)
      }
      const result = started.parse(
        await evidenceAPI.preparePdfReview(caseId, id)
      )
      if (result.job_ids?.length !== 1)
        throw Error(
          result.message ||
            "No preparation job was started. Check this file in Evidence."
        )
      setJobId(result.job_ids[0])
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "PDF preparation could not be started."
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      aria-label="Prepare PDF for review"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">Add a PDF for review</h3>
      <p>
        Prepare its text and page locations locally, then choose and review
        possible transaction rows. This does not run AI analysis, verify
        transactions or add them to totals.
      </p>
      <Button
        variant="outline"
        disabled={busy || running}
        onClick={() => {
          setShowExisting(true)
          if (showExisting) void existing.refetch()
        }}
      >
        Find uploaded PDFs
      </Button>
      {existing.isError && <p role="alert">{existing.error.message}</p>}
      {showExisting &&
        existing.data?.map((f) => (
          <Button
            key={f.id}
            variant="outline"
            disabled={
              busy ||
              running ||
              f.status === "processed" ||
              f.status === "processing"
            }
            onClick={() => {
              setFile(null)
              setFileId(f.id)
              setJobId(null)
              setError("")
            }}
          >
            Use uploaded PDF: {f.original_filename} ({f.status})
          </Button>
        ))}
      {showExisting && (
        <p>
          Already processed files can be opened through Choose PDF rows. Active
          processing is shown in Evidence.
        </p>
      )}
      <label className="block">
        PDF document{" "}
        <input
          aria-label="PDF document"
          type="file"
          accept="application/pdf,.pdf"
          disabled={busy || running}
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null)
            setFileId(null)
            setJobId(null)
            setError("")
          }}
        />
      </label>
      <Button
        disabled={(!file && !fileId) || busy || running || ready}
        onClick={() => void prepare()}
      >
        {busy ? "Uploading and preparing…" : "Prepare PDF for review"}
      </Button>
      {fileId && <p>Uploaded evidence reference: {fileId}</p>}
      {jobId && (
        <p role="status">
          Preparation:{" "}
          {job.isPending
            ? "checking progress"
            : (job.data?.status.replaceAll("_", " ") ?? "status unavailable")}
          .
        </p>
      )}
      {(error || job.isError) && (
        <p role="alert">
          {error || job.error?.message} Check Evidence before uploading again;
          an interrupted request may already have been accepted.
        </p>
      )}
      {job.isError && (
        <Button variant="outline" onClick={() => void job.refetch()}>
          Check preparation again
        </Button>
      )}
      {job.data?.status === "failed" && (
        <p role="alert">
          Preparation failed. Check the file and processing details in Evidence.
          No transactions were admitted.
        </p>
      )}
      {ready && (
        <>
          <p>
            Source ready for review. Some pages may have no selectable table;
            this does not mean they contain no transactions.
          </p>
          <Button onClick={onReady}>Choose prepared PDF rows</Button>
        </>
      )}
    </section>
  )
}
