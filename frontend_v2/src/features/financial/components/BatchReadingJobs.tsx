import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useJobs } from "@/features/evidence/hooks/use-jobs"
import { JobCard } from "@/features/evidence/components/JobCard"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceJob } from "@/types/evidence.types"

export function BatchReadingJobs({
  caseId,
  jobIds,
  canEdit,
}: {
  caseId: string
  jobIds: string[]
  canEdit: boolean
}) {
  const client = useQueryClient()
  const jobs = useJobs(jobIds.length ? caseId : undefined, true)
  const control = useMutation({
    mutationFn: ({
      job,
      action,
    }: {
      job: EvidenceJob
      action: "pause" | "resume"
    }) =>
      fetchAPI(
        `/api/evidence/engine/jobs/${job.id}/${action}?case_id=${caseId}`,
        { method: "POST" }
      ),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
    },
  })
  if (!jobIds.length) return null
  const readings =
    jobs.data?.filter(
      (job) => jobIds.includes(job.id) && job.job_type === "pdf_review"
    ) ?? []
  return (
    <details className="rounded border p-3">
      <summary>PDF reading jobs · pause or resume a reading</summary>
      <p className="my-2 text-sm text-muted-foreground">
        These readings have their own saved progress. Pausing batch preparation
        stops new statements and imports after the current statement finishes.
        Readings already running continue until you pause them here. A reading
        may be used by another financial batch; its pause applies there too. AI
        ingestion is separate.
      </p>
      {jobs.isError && (
        <p role="alert">
          Reading progress is unavailable. Refresh this page to try again; saved
          batch progress is retained.
        </p>
      )}
      {jobs.isPending && <p role="status">Loading PDF reading progress…</p>}
      {control.isError && <p role="alert">{control.error.message}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        {readings.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            controlScope="reading group"
            controlling={control.isPending}
            onPause={
              canEdit
                ? (selected) =>
                    control.mutate({ job: selected, action: "pause" })
                : undefined
            }
            onResume={
              canEdit
                ? (selected) =>
                    control.mutate({ job: selected, action: "resume" })
                : undefined
            }
          />
        ))}
      </div>
      {jobs.isSuccess && !readings.length && (
        <p>
          No separate financial PDF reading is running for these files. Any
          general evidence processing is shown in Evidence.
        </p>
      )}
    </details>
  )
}
