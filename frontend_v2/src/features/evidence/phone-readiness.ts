import { formatBytesOf, RATE_MIN_MS } from "./upload-progress"

/**
 * The words, counts and measured rates behind the phone readiness card (07 J-1 step 3, J-1a): every stage in words, true counts, time left from
 * the measured rate of this step, the stall rule of 4.7, and Cancel saying what is kept.
 */

export const PHONE_STEPS = [
  { key: "checking", label: "Checking the report", stages: ["verifying_container", "detecting", "counting"] },
  { key: "reading", label: "Reading records", stages: ["capturing"] },
  { key: "checking_complete", label: "Checking nothing is missing", stages: ["reconciling", "indexing_files"] },
] as const

/** 07 4.7: intake stages start at 30 s; reversed once per-step rates are measured. */
export const PHONE_STALL_SECONDS = 30

export const CANCEL_KEEPS =
  "Cancel stops the reading. The upload, its fingerprints and its evidence entry are kept, and the report can be read again. What was read so far is removed."

const OUTCOME_WORDS: Record<string, string> = {
  match: "match the report's fingerprint",
  missing: "are listed in the report but not in the production",
  empty_placeholder: "are empty placeholders for files the production did not include",
  size_mismatch: "are a different size from the report's description",
  mismatch: "do not match the report's fingerprint",
  no_hash: "have no fingerprint in the report to check",
  no_local_path: "have no location in the production",
}
const OUTCOME_ORDER = ["match", "missing", "empty_placeholder", "size_mismatch", "mismatch", "no_hash", "no_local_path"]

export const n = (value: number | undefined) => (value ?? 0).toLocaleString("en-US")

export function stepIndex(stage: string | undefined) {
  if (!stage) return 0
  if (stage === "finishing" || stage === "completed") return PHONE_STEPS.length
  const i = PHONE_STEPS.findIndex((step) => (step.stages as readonly string[]).includes(stage))
  return i < 0 ? 0 : i
}

/** The quantity a stage is measured by: [done, total, unit]. */
export function measureOf(stage: string | undefined, counts: Record<string, number> | undefined) {
  const c = counts || {}
  if (stage === "indexing_files" && c.files_total !== undefined)
    return [c.files_checked ?? 0, c.files_total, "files"] as const
  // within one document the entries compared so far; across several, the documents (entries restart per document)
  if (stage === "reconciling" && c.entries_total !== undefined && c.documents_total === 1)
    return [c.entries_checked ?? 0, c.entries_total, "entries"] as const
  if (stage === "reconciling" && c.documents_total !== undefined)
    return [c.documents_done ?? 0, c.documents_total, "documents"] as const
  if (c.bytes_total !== undefined) return [c.bytes_read ?? 0, c.bytes_total, "bytes"] as const
  return null
}

export function stepText(stage: string | undefined, counts: Record<string, number> | undefined) {
  const c = counts || {}
  const m = measureOf(stage, counts)
  switch (stage) {
    case "verifying_container":
      return m ? `Checking the report's fingerprints: ${formatBytesOf(m[0], m[1])}` : "Checking the report's fingerprints"
    case "detecting":
      return "Finding the report documents"
    case "counting":
      return m ? `Counting every element: ${formatBytesOf(m[0], m[1])}` : "Counting every element"
    case "capturing":
      return `${n(c.records)} records and ${n(c.files)} files read` + (m ? ` (${formatBytesOf(m[0], m[1])})` : "")
    case "reconciling": {
      const docs = c.documents_total ?? 0
      const doc = docs > 1 ? `document ${n((c.documents_done ?? 0) + ((c.documents_done ?? 0) < docs ? 1 : 0))} of ${n(docs)}` : ""
      const entries = c.entries_total !== undefined ? `${n(c.entries_checked)} of ${n(c.entries_total)} entries` : ""
      const where = [doc, entries].filter(Boolean).join(", ")
      return where ? `Comparing every element with the report: ${where}` : docs ? "Comparing every element with the report: document 1 of 1" : "Comparing every element with the report"
    }
    case "indexing_files":
      return m ? `Checking the files: ${n(m[0])} of ${n(m[1])}` : "Checking the files"
    default:
      return ""
  }
}

/** changedAt is 0 until a change is seen in this browser; the first observation is not a change. */
type Sample = { stage: string; t0: number; v0: number; last: number; lastValue: string; changedAt: number }
const samples = new Map<string, Sample>()

/** Rate of this step as measured in this browser: the first observation of the stage and the latest. */
export function observe(jobId: string, stage: string, counts: Record<string, number> | undefined, now: number) {
  const m = measureOf(stage, counts)
  const value = JSON.stringify([stage, counts || {}])
  let s = samples.get(jobId)
  if (!s || s.stage !== stage) {
    s = { stage, t0: now, v0: m ? m[0] : 0, last: now, lastValue: value, changedAt: 0 }
    samples.set(jobId, s)
  } else if (s.lastValue !== value) {
    s.lastValue = value
    s.changedAt = now
  }
  s.last = now
  let left: number | null = null
  if (m && now - s.t0 >= RATE_MIN_MS && m[0] > s.v0) {
    const rate = (m[0] - s.v0) / ((now - s.t0) / 1000)
    left = Math.max(0, m[1] - m[0]) / rate
  }
  return { left, changedAt: s.changedAt, firstSeen: s.t0 }
}

export function outcomeLines(outcomes: Record<string, number> | undefined) {
  if (!outcomes) return []
  return OUTCOME_ORDER.filter((k) => outcomes[k]).map(
    (k) => `${n(outcomes[k])} ${outcomes[k] === 1 ? "file" : "files"} ${OUTCOME_WORDS[k]}`
  )
}
