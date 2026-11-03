import type { TrayJob } from "@/components/ui/job-tray"
import type { DeriveBatch, DeriveBatchFacts } from "../api"

const n = (v: number) => v.toLocaleString("en-US")

/** What a batch leaves out, in words, or "" when it leaves nothing out. */
export function leftOutWords(f: DeriveBatchFacts): string {
  const parts: string[] = []
  if (f.left_out.already_read) parts.push(`${n(f.left_out.already_read)} already read or waiting`)
  if (f.left_out.not_in_production) parts.push(`${n(f.left_out.not_in_production)} not in the production`)
  if (f.left_out.empty_placeholder) parts.push(`${n(f.left_out.empty_placeholder)} empty placeholders`)
  if (f.left_out.uncategorised) parts.push(`${n(f.left_out.uncategorised)} the report gives no category (open one to have it read: its contents decide)`)
  return parts.length ? `Left out: ${parts.join(", ")}.` : ""
}

/** A batch as a job tray line (07 4.7): true counts from the server; time left from this batch's measured pace. */
export function batchJob(b: DeriveBatch, onCancel?: () => void): TrayJob {
  const verb = b.kind === "transcript" ? "Transcribing" : "Reading text in"
  const title = `${verb} ${n(b.total)} ${b.noun}${b.scope_words ? ` (${b.scope_words})` : ""}`
  const finished = b.done + b.failed
  const started = Date.parse(b.first_started_at ?? b.created_at)
  const step = b.failed ? `Read (${n(b.failed)} could not be read)` : "Read"
  const stopped = `${title}: stopped by request after ${n(finished)} of ${n(b.total)}; ${n(b.cancelled_count)} not started were removed; finished readings are kept`
  return {
    id: b.id,
    title: b.state === "cancelled" ? stopped : b.state === "done" && b.failed ? `${title}: ${n(b.failed)} could not be read` : title,
    state: b.state === "running" ? "running" : b.state === "cancelled" ? "failed" : "done",
    progress: { step, done: finished, total: b.total, unit: b.noun, startedAt: started, movedAt: Date.parse(b.last_finished_at ?? b.first_started_at ?? b.created_at) },
    onCancel,
    cancelWords: "readings not started are removed; finished ones are kept",
  }
}
