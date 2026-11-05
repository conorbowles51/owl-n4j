import type { ReactNode } from "react"
import { CheckCircle2, CircleAlert, Loader } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { type ProgressState } from "@/components/ui/progress-panel"
import { timeLeft } from "@/components/ui/progress-time"
import { cn } from "@/lib/cn"
import { trayLabel } from "./job-tray-label"

/**
 * The header job tray (07 4.7): every long job in words with time left, updated every second from the server's
 * published progress, with a notice and a link when it is done. Intake, interpretation, re-reading, export,
 * transcription, thumbnails, Together, approach runs, bulk collect and agent phone tool calls all report here.
 */
export interface TrayJob {
  id: string
  /** What the job is, e.g. "Getting C3 ready" or "Export: messages between A and B". */
  title: string
  state: "running" | "done" | "failed" | "cancelled"
  progress: ProgressState
  /** Where the result or the job's card is. */
  href?: string
  /** What came of it, said after "Done.": what it holds or what was left out. */
  note?: string
  /** Why it stopped, named. */
  error?: string
  /** What is kept if it is cancelled, when it can be cancelled. */
  onCancel?: () => void
  cancelWords?: string
}

export function JobLine({ job, now }: { job: TrayJob; now: number }) {
  const p = job.progress
  const Icon = job.state === "done" ? CheckCircle2 : job.state === "failed" ? CircleAlert : Loader
  return (
    <li className="flex flex-col gap-0.5 border-b py-2 last:border-b-0" data-job={job.id}>
      <span className="flex items-center gap-2 font-medium">
        <Icon className={cn("size-4 shrink-0", job.state === "failed" && "text-status-error")} aria-hidden />
        {job.title}
      </span>
      <span className="text-sm">
        {job.state === "done"
          ? `Done.${job.note ? ` ${job.note}` : ""}`
          : job.state === "cancelled"
            ? job.note ?? "Cancelled."
          : job.state === "failed"
            ? `${p.step} stopped.${job.error ? ` ${job.error}` : ""}${job.note ? ` ${job.note}` : ""}${p.failed ? ` Reference: ${p.failed.referenceId}.` : ""}`
            : `${p.step}${p.done !== undefined && p.total !== undefined ? `: ${p.done.toLocaleString("en-US")} of ${p.total.toLocaleString("en-US")}${p.unit ? ` ${p.unit}` : ""}` : ""}, ${timeLeft(p, now)}`}
      </span>
      <span className="flex gap-3 text-sm">
        {job.href && (
          <a className="underline underline-offset-2" href={job.href}>
            {job.state === "done" ? "Open the result" : "Open"}
          </a>
        )}
        {job.state === "running" && job.onCancel && (
          <button type="button" className="underline underline-offset-2" onClick={job.onCancel}>
            Cancel{job.cancelWords ? ` (${job.cancelWords})` : ""}
          </button>
        )}
      </span>
    </li>
  )
}

export function JobTray({ jobs, now, defaultOpen, footer }: { jobs: TrayJob[]; now: number; defaultOpen?: boolean; footer?: ReactNode }) {
  return (
    <Popover defaultOpen={defaultOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label={trayLabel(jobs)}>
          {trayLabel(jobs)}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-h-[70vh] w-96 overflow-auto" aria-label="Jobs">
        {jobs.length === 0 ? (
          <p className="text-sm">No jobs are running. Long work such as adding a phone or an export appears here.</p>
        ) : (
          <ul aria-label="Jobs">{jobs.map((j) => <JobLine key={j.id} job={j} now={now} />)}</ul>
        )}
        {footer}
      </PopoverContent>
    </Popover>
  )
}
