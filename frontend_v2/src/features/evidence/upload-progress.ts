/**
 * Upload progress in words (07 J-1 steps 1 and 2, and 4.7): true counts, and a time left that comes only from the
 * rate measured in this step. Before a rate exists the text says so; no figure is invented.
 */
export type UploadPhase = "hashing" | "sending" | "registering"

export interface UploadProgress {
  phase: UploadPhase
  filesDone: number
  filesTotal: number
  bytesDone: number
  bytesTotal: number
  /** ms since epoch when this phase started, and the bytes already done then (a resumed send). */
  startedAt: number
  bytesAtStart: number
  kind: "folder" | "archive" | "files"
}

/** The shortest measured interval before a rate is trusted. */
export const RATE_MIN_MS = 2000
export const FIRST_RUN_TEXT = "Working out time left (first run of this step)"

const n = (value: number) => value.toLocaleString("en-US")

export function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${n(bytes)} bytes`
}

/** "2.1 of 6.4 GB": both amounts in the unit of the total (07 J-1a step 2). */
export function formatBytesOf(done: number, total: number) {
  const [unit, size] =
    total >= 1024 ** 3 ? ["GB", 1024 ** 3] : total >= 1024 ** 2 ? ["MB", 1024 ** 2] : total >= 1024 ? ["KB", 1024] : ["bytes", 1]
  const show = (v: number) => (size >= 1024 ** 2 ? (v / size).toFixed(1) : n(Math.round(v / size)))
  return `${show(done)} of ${show(total)} ${unit}`
}

export function formatTimeLeft(seconds: number) {
  if (seconds < 60) return `about ${Math.max(1, Math.round(seconds))} s left`
  if (seconds < 3600) return `about ${Math.round(seconds / 60)} min left`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return `about ${h} h ${m} min left`
}

/** Time left from this phase's measured byte rate, or null while no rate is measured yet. */
export function secondsLeft(p: UploadProgress, now: number): number | null {
  const elapsed = now - p.startedAt
  const moved = p.bytesDone - p.bytesAtStart
  if (elapsed < RATE_MIN_MS || moved <= 0) return null
  const rate = moved / (elapsed / 1000)
  return Math.max(0, p.bytesTotal - p.bytesDone) / rate
}

export function describeUploadProgress(p: UploadProgress, now: number): string {
  const left = secondsLeft(p, now)
  const time = left === null ? FIRST_RUN_TEXT : formatTimeLeft(left)
  if (p.phase === "hashing")
    return p.filesTotal > 1
      ? `Checking files before upload: ${n(p.filesDone)} of ${n(p.filesTotal)}, ${time}`
      : `Checking the file before upload: ${formatBytesOf(p.bytesDone, p.bytesTotal)}, ${time}`
  if (p.phase === "sending") {
    const again =
      p.kind === "folder"
        ? "choose the same folder again to continue"
        : p.kind === "archive"
          ? "choose the same file again to continue"
          : "choose the same files again to continue"
    return `Sending ${formatBytesOf(p.bytesDone, p.bytesTotal)}, ${time}. If this tab closes, ${again}.`
  }
  return p.filesTotal > 1
    ? `All ${n(p.filesTotal)} files arrived. Saving them to the case and checking for phone reports.`
    : "The file arrived. Saving it to the case and checking for a phone report."
}

export function percentOf(p: UploadProgress) {
  if (p.phase === "registering") return 100
  return p.bytesTotal > 0 ? Math.min(99, Math.floor((p.bytesDone / p.bytesTotal) * 100)) : 0
}
