import { fetchAPI } from "@/lib/api-client"
import { JOB_STARTED_EVENT } from "@/lib/job-started"
import type { TrayJob } from "@/components/ui/job-tray"
import { stepText } from "@/features/evidence/phone-readiness"

/** The header job tray's one list (GET /api/phones/jobs, 07 section 4.7): a reload keeps it, because the server does. */
export interface ServerJob {
  id: string
  kind: string
  title: string
  state: "running" | "done" | "failed" | "cancelled"
  step: string
  done: number | null
  total: number | null
  unit: string | null
  started_at: string | null
  moved_at: string | null
  ended_at: string | null
  note: string | null
  error: string | null
  reference: string | null
  href: string | null
  stage?: string | null
  counts?: Record<string, number>
}

export interface JobList {
  case_id: string
  items: ServerJob[]
  older_finished: number
  unavailable: string[]
  active: boolean
  read_at: string
}

/** How often one tab asks while a job runs. An idle tab asks not at all; the line ticks each second on its own. */
export const JOB_POLL_MS = 5_000
/** A read this recent is not repeated when a person changes screen or comes back to the tab. */
export const JOB_FRESH_MS = 30_000

export const jobsQueryKey = (caseId: string) => ["phone-jobs", caseId]

export const getJobs = (caseId: string) => fetchAPI<JobList>(`/api/phones/jobs?case_id=${encodeURIComponent(caseId)}`)

const at = (iso: string | null, fallback: number) => (iso ? Date.parse(iso) : fallback)

/** One server row as a tray line. Intake's step and counts use the readiness card's own words. */
export function trayJob(j: ServerJob, now: number): TrayJob {
  const startedAt = at(j.started_at, now)
  const step = j.kind === "intake" && j.stage ? stepText(j.stage, j.counts) : j.step
  return {
    id: j.id,
    title: j.title,
    state: j.state,
    href: j.href ?? undefined,
    note: j.note ?? undefined,
    error: j.error ?? undefined,
    progress: {
      step,
      done: j.done ?? undefined,
      total: j.total ?? undefined,
      unit: j.unit ?? undefined,
      startedAt,
      movedAt: at(j.moved_at, startedAt),
      failed: j.state === "failed" && j.reference ? { what: j.title, referenceId: j.reference } : null,
    },
  }
}

/** Jobs that were running on the last read and are finished now: each gets its notice once. */
export function justFinished(before: ReadonlySet<string>, items: ServerJob[]): ServerJob[] {
  return items.filter((j) => j.state !== "running" && before.has(j.id))
}

/**
 * A bulk add in parts (07 6.4): the links go through their own routes and this row keeps the true counts, so the tray
 * still shows it after a reload, and says how many went if the page closes. A failed report never stops the add.
 */
export async function trackBulkAdd(caseId: string, targetWords: string, noun: string, total: number) {
  const run = await fetchAPI<{ id: string }>("/api/phones/jobs/collect", {
    method: "POST",
    body: { case_id: caseId, target_words: targetWords, noun, total },
  }).catch(() => null)
  window.dispatchEvent(new Event(JOB_STARTED_EVENT))
  const report = (sent: number, r: { added: number; skipped: number; refused: number; refusedReason?: string }, finished: boolean, error: string | null) =>
    run
      ? fetchAPI(`/api/phones/jobs/collect/${run.id}`, {
          method: "POST",
          body: { case_id: caseId, sent, added: r.added, skipped: r.skipped, refused: r.refused, refused_reason: r.refusedReason ?? null, finished, error },
        }).catch(() => undefined)
      : Promise.resolve(undefined)
  return report
}
