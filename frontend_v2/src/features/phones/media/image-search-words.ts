import type { TrayJob } from "@/components/ui/job-tray"
import type { ImageIndexFacts, ImageIndexJob } from "../api"

const n = (v: number) => v.toLocaleString("en-US")
const pl = (v: number, one: string, many: string) => `${n(v)} ${v === 1 ? one : many}`

/** Why an image could not be indexed, in words, by the server's reason code. */
export const REASON_WORDS: Record<string, string> = {
  heic: "stored as HEIC, which this server cannot open",
  not_image: "not a picture",
  unreadable: "damaged or in a format this server cannot open",
  too_large: "too large to open",
  empty: "no bytes",
  not_in_production: "not readable from the production",
  no_model: "the model was not installed",
  stopped: "stopped twice",
  timeout: "took too long",
  error: "could not be indexed",
}

const byReason = (r: Record<string, number>) =>
  Object.entries(r).filter(([, v]) => v > 0).map(([k, v]) => `${n(v)} ${REASON_WORDS[k] ?? k}`).join(", ")

/** Every image indexing leaves out, with its reason, or "" when it leaves nothing out. */
export function imageLeftOutWords(f: ImageIndexFacts): string {
  const parts: string[] = []
  const l = f.left_out
  if (f.indexed) parts.push(`${n(f.indexed)} already indexed`)
  if (f.waiting) parts.push(`${n(f.waiting)} waiting`)
  if (l.not_in_population) parts.push(`${n(l.not_in_population)} not sent or received, not from a camera or screenshot folder`)
  if (l.not_in_production) parts.push(`${n(l.not_in_production)} not in the production`)
  if (l.empty_placeholder) parts.push(`${n(l.empty_placeholder)} empty placeholders`)
  if (l.could_not_open) parts.push(`${n(l.could_not_open)} could not be opened (${byReason(l.could_not_open_by_reason)})`)
  return parts.length ? `Left out of ${pl(f.images, "image", "images")}: ${parts.join(", ")}.` : ""
}

/** How much of the case a search covers, so a partial index is never read as the whole case. */
export function coverageWords(f: ImageIndexFacts): string {
  const notYet = f.eligible + f.waiting
  const unable = f.left_out.not_in_production + f.left_out.empty_placeholder + f.left_out.could_not_open
  const parts = [`${pl(f.indexed, "file is", "files are")} indexed (${pl(f.indexed_contents, "distinct picture", "distinct pictures")})`]
  if (notYet) parts.push(`${pl(notYet, "image is", "images are")} not indexed yet`)
  if (unable) parts.push(`${pl(unable, "image", "images")} cannot be indexed`)
  if (f.left_out.not_in_population) parts.push(`${pl(f.left_out.not_in_population, "image is", "images are")} outside the search (not sent or received, not from a camera)`)
  return `${parts.join("; ")}.`
}

/** An indexing job as a job tray line (07 4.7): true counts from the server; time left from its measured pace. */
export function indexJob(j: ImageIndexJob, onCancel?: () => void): TrayJob {
  const title = `Indexing ${pl(j.total, "image", "images")} for search by description`
  const finished = j.done + j.failed
  const failedWords = j.failed ? `${n(j.failed)} could not be indexed (${byReason(j.failed_by_reason)})` : ""
  const stopped = `${title}: stopped by request after ${n(finished)} of ${n(j.total)}; ${n(j.cancelled_count)} not started were removed; indexed images are kept`
  return {
    id: j.id,
    title: j.state === "cancelled" ? stopped : j.state === "done" && j.failed ? `${title}: ${failedWords}` : title,
    state: j.state === "running" ? "running" : j.state === "cancelled" ? "failed" : "done",
    progress: {
      step: j.failed ? `Indexed (${failedWords})` : "Indexed",
      done: finished, total: j.total, unit: j.noun,
      startedAt: Date.parse(j.first_started_at ?? j.created_at),
      movedAt: Date.parse(j.last_finished_at ?? j.first_started_at ?? j.created_at),
    },
    onCancel,
    cancelWords: "images not started are removed; indexed ones are kept",
  }
}
