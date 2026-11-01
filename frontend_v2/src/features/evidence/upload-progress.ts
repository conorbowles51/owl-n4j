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
  /** Files finished in this phase, for a selection of many files (see {@link addFileCost}). */
  fit?: FileCostFit
}

/**
 * Running least-squares sums over the files finished in this phase: seconds = perFile + perByte x size. A phone
 * folder is tens of thousands of small files and a few large ones, so the time a file costs is not its bytes alone:
 * on a 43,123-file report (801 MB) hashing ran at 2 MB/s against 35 MB/s on 200 files, and a byte rate taken while
 * the large files went first promised 23 s for what took 402 s.
 */
export interface FileCostFit {
  n: number
  sx: number
  sy: number
  sxx: number
  sxy: number
}
/** Files that must have finished in this phase before a time left is given for a selection of many files. */
export const MIN_FILES_FOR_FIT = 20

export function addFileCost(fit: FileCostFit | undefined, size: number, seconds: number): FileCostFit {
  const f = fit ?? { n: 0, sx: 0, sy: 0, sxx: 0, sxy: 0 }
  return { n: f.n + 1, sx: f.sx + size, sy: f.sy + seconds, sxx: f.sxx + size * size, sxy: f.sxy + size * seconds }
}

/** perFile and perByte seconds from the fit, neither negative. */
export function fileCosts(f: FileCostFit) {
  const denom = f.n * f.sxx - f.sx * f.sx
  let perByte = denom > 0 ? (f.n * f.sxy - f.sx * f.sy) / denom : 0
  let perFile = (f.sy - perByte * f.sx) / f.n
  if (perByte < 0) [perByte, perFile] = [0, f.sy / f.n]
  if (perFile < 0) [perFile, perByte] = [0, f.sx > 0 ? f.sy / f.sx : 0]
  return { perFile, perByte }
}

/** The shortest measured interval before a rate is trusted. */
export const RATE_MIN_MS = 2000
/** The same words inside a sentence, after a count. */
export const FIRST_RUN_INLINE = "working out time left (first run of this step)"

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

/** Time left measured in this phase, or null while there is no measurement yet. A selection of many files uses the
 * per-file and per-byte costs of the files already finished here; a single file uses its byte rate. */
export function secondsLeft(p: UploadProgress, now: number): number | null {
  if (p.filesTotal > 1) {
    if (!p.fit || p.fit.n < MIN_FILES_FOR_FIT) return null
    const { perFile, perByte } = fileCosts(p.fit)
    return Math.max(0, p.filesTotal - p.filesDone) * perFile + Math.max(0, p.bytesTotal - p.bytesDone) * perByte
  }
  const elapsed = now - p.startedAt
  const moved = p.bytesDone - p.bytesAtStart
  if (elapsed < RATE_MIN_MS || moved <= 0) return null
  const rate = moved / (elapsed / 1000)
  return Math.max(0, p.bytesTotal - p.bytesDone) / rate
}

export function describeUploadProgress(p: UploadProgress, now: number): string {
  const left = secondsLeft(p, now)
  const time = left === null ? FIRST_RUN_INLINE : formatTimeLeft(left)
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
