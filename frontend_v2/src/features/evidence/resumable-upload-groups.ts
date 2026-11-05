import { ApiError, fetchAPI } from "@/lib/api-client"
import type { EvidenceUploadOptions, UploadResponse } from "./api"
import { addFileCost, matchedWords, type MatchedFiles, type UploadProgress } from "./upload-progress"
import {
  randomUUID,
  setLocalUploadPaused,
  transferFile,
  uploadFingerprint,
  uploadSessionGuard,
  type UploadSession,
} from "./resumable-upload"

export interface UploadGroup {
  id: string
  case_id: string
  folder_id: string | null
  name: string
  kind: "folder" | "archive" | "files"
  status: "uploading" | "paused" | "dispatching" | "completed"
  replace_existing: boolean
  file_count: number
  staged_count: number
  size: number
  received_bytes: number
  members?: Member[]
  receipt: { file_ids: string[]; job_ids: string[]; message: string } | null
  /** While the server registers the selection (it answers ``complete`` before it is done for a large one). */
  registration?: Registration
}

/** Registration on the server (backend/routers/evidence_upload_groups.py read_registration). ``stopped`` (its server
 * process ended) and ``idle`` on a selection that is not registered mean nothing is registering it. */
export interface Registration {
  state: "idle" | "running" | "done" | "failed" | "stopped"
  phase?: RegistrationPhase
  done?: number
  total?: number
  error?: { status_code: number; detail: string }
}
export type RegistrationPhase = "starting" | "checking" | "phones" | "saving" | "queueing"
const endpoint = "/api/evidence-upload-groups"
/** The largest single file an upload group accepts (the server's limit: 2,048 parts of 4 MiB). */
export const MAX_FILE_BYTES = 8 * 1024 ** 3

export function tooLargeMessage(file: File, isArchive?: boolean) {
  const size = `${(file.size / 1024 ** 3).toFixed(1)} GB`
  return isArchive
    ? `This ZIP file is ${size}; one file can be at most 8 GB, so it was not uploaded. Unpack it and upload the report folder instead.`
    : `${file.name} is ${size}; one file can be at most 8 GB, so nothing was uploaded.`
}
type Active = {
  files: File[]
  paused: boolean
  completing: boolean
  /** Files being sent now (up to SEND_AT_ONCE). */
  memberIds: Set<string>
  /** Senders waiting for a paused selection to carry on. */
  waiting: Set<() => void>
  /** Paused by this tab's own Pause, so only this tab's Resume carries on. */
  pausedHere?: boolean
  promise: Promise<UploadGroup>
}
/** Files of one selection sent at once. Measured live over plain http (two A/B runs, slices interleaved): one at a
 * time 7.3 and 6.7 files/s, six at a time 11.4 and 12.4, four at a time 11.7 against 7.6. Four leaves two of the
 * browser's six connections to the host for the page itself. */
export const SEND_AT_ONCE = 4

/** Files of one part up to this size go many to a request; the server takes a batch of up to 1,000 one-part files
 * and 8 MiB (backend/routers/evidence_upload_groups.py BATCH_MAX_FILES, BATCH_MAX_BYTES). On a live 81,820-file phone
 * folder 98.7 % of the files are under 1 MiB and hold 6 % of its bytes; each cost three requests sent alone. */
export const BATCH_FILE_BYTES = 1024 * 1024
export const BATCH_MAX_FILES = 500
export const BATCH_MAX_BYTES = 4 * 1024 * 1024
const STAGED = new Set(["staged", "completed"])

/** ``modified``: the file's modified time when it was fingerprinted; a selection begun before it was kept has none. */
type Member = UploadSession & { path: string; modified?: number | null }
export const isBatchable = (member: Member) =>
  member.size <= BATCH_FILE_BYTES && member.size <= member.chunk_size

/** The next batch off the front of ``small``: up to BATCH_MAX_FILES files and BATCH_MAX_BYTES (always one file). */
export function takeBatch(small: Member[]) {
  const batch: Member[] = []
  let bytes = 0
  while (
    small.length &&
    batch.length < BATCH_MAX_FILES &&
    (!batch.length || bytes + small[0].size <= BATCH_MAX_BYTES)
  ) {
    const member = small.shift()!
    bytes += member.size
    batch.push(member)
  }
  return batch
}

/** One request: a JSON line naming each file and its size, then the files' bytes back to back. The server checks
 * every file against its SHA-256 and answers for each one. */
export function sendBatch(groupId: string, files: { member: Member; file: File }[]) {
  const head = JSON.stringify({ files: files.map(({ member }) => ({ id: member.id, size: member.size })) }) + "\n"
  return fetchAPI<{ files: { id: string; status: UploadSession["status"]; error?: string }[] }>(
    `${endpoint}/${groupId}/files`,
    {
      method: "PUT",
      body: new Blob([head, ...files.map(({ file }) => file)]),
      headers: { "Content-Type": "application/octet-stream" },
    }
  )
}

function setPaused(transfer: Active, paused: boolean) {
  transfer.paused = paused
  for (const id of transfer.memberIds) setLocalUploadPaused(id, paused)
  if (!paused) {
    const waiting = [...transfer.waiting]
    transfer.waiting.clear()
    for (const wake of waiting) wake()
  }
}

async function whilePaused(transfer: Active) {
  while (transfer.paused) await new Promise<void>((resolve) => transfer.waiting.add(resolve))
}
const active = new Map<string, Active>()
const relativePath = (file: File, kind: UploadGroup["kind"]) =>
  kind === "folder" ? file.webkitRelativePath || file.name : file.name
export const listUploadGroups = (caseId: string) =>
  fetchAPI<UploadGroup[]>(`${endpoint}?case_id=${caseId}`).then((groups) => {
    followServer(groups)
    return groups
  })

/** A release pauses open uploads and resumes them when it is done. A selection this tab is sending follows that:
 * paused on the server, it stops; uploading again, it carries on (seen live: the tab otherwise stayed asleep after
 * the resume, with the upload saying it was sending). A pause made with this tab's Pause waits for its Resume. */
export function followServer(groups: UploadGroup[]) {
  for (const group of groups) {
    const transfer = active.get(group.id)
    if (!transfer || transfer.completing || transfer.pausedHere) continue
    if (group.status === "paused") setPaused(transfer, true)
    else if (group.status === "uploading") setPaused(transfer, false)
  }
}
export const hasLocalUploadGroup = (id: string) => active.has(id)
export const isCompletingUploadGroup = (id: string) =>
  active.get(id)?.completing ?? false

export const DISCARD_CONFIRM =
  "Discard this upload? The parts saved so far are removed from the server. Nothing from this selection is in Evidence yet."

/** Abandon a selection that has registered nothing (the server refuses once its files are evidence). A transfer
 * running in this tab is stopped first. */
export async function discardUploadGroup(id: string) {
  const transfer = active.get(id)
  if (transfer?.completing)
    throw new Error("Files have arrived and are being registered, so this upload can no longer be discarded.")
  if (transfer) setPaused(transfer, true)
  const result = await fetchAPI<{ id: string; status: "discarded"; file_count: number; saved_count: number }>(
    `${endpoint}/${id}/discard`,
    { method: "POST" }
  )
  active.delete(id)
  return result
}

export async function pauseUploadGroup(id: string) {
  const transfer = active.get(id)
  if (transfer?.completing)
    throw new Error(
      "Files have arrived. Registration is finishing and will be retained if you leave."
    )
  if (transfer) {
    transfer.pausedHere = true
    setPaused(transfer, true)
  }
  try {
    return await fetchAPI<UploadGroup>(`${endpoint}/${id}/pause`, {
      method: "POST",
    })
  } catch (error) {
    if (transfer) {
      transfer.pausedHere = false
      setPaused(transfer, false)
    }
    throw error
  }
}

const isSaved = (member: Member) => STAGED.has(member.status)

/** A member the server holds and verified, and a chosen file that is the same one by name and size, with the same
 * modified time where the selection kept it. Only such a file goes without being read: the member keeps the hash its
 * bytes were saved and verified with, and this file gets no hash at all. A file with another modified time is read. */
const matchesSaved = (member: Member, file: File) =>
  isSaved(member) &&
  file.size === member.size &&
  (member.modified == null || member.modified === file.lastModified)

/** What a pick of ``files`` needs against a selection's members: the saved ones it matches without reading them, and
 * those that must be read (the files still to send, and any saved file that no longer matches). */
function planResume(members: Member[], files: File[], kind: UploadGroup["kind"]) {
  const byPath = new Map(members.map((member) => [member.path, member]))
  const matched: MatchedFiles = { files: 0, bytes: 0, byTime: true }
  const toRead: File[] = []
  for (const file of files) {
    const member = byPath.get(relativePath(file, kind))
    if (member && matchesSaved(member, file)) {
      matched.files++
      matched.bytes += member.size
      if (member.modified == null) matched.byTime = false
    } else toRead.push(file)
  }
  return { byPath, matched, toRead }
}

type Fingerprint = Awaited<ReturnType<typeof uploadFingerprint>>

/** Reads ``files`` once each into ``read`` (path to fingerprint), telling ``onProgress`` how far it has come. */
async function readFiles(
  files: File[],
  kind: UploadGroup["kind"],
  read: Map<string, Fingerprint>,
  onProgress?: (progress: UploadProgress) => void,
  matched?: MatchedFiles
) {
  if (!files.length) return
  const hashed: UploadProgress = {
    phase: "hashing",
    filesDone: 0,
    filesTotal: files.length,
    bytesDone: 0,
    bytesTotal: files.reduce((sum, file) => sum + file.size, 0),
    startedAt: Date.now(),
    bytesAtStart: 0,
    kind,
    matched,
  }
  onProgress?.({ ...hashed })
  for (const file of files) {
    const began = performance.now()
    read.set(
      relativePath(file, kind),
      await uploadFingerprint(file, (bytes) => {
        hashed.bytesDone += bytes
        onProgress?.({ ...hashed })
      })
    )
    hashed.fit = addFileCost(hashed.fit, file.size, (performance.now() - began) / 1000)
    hashed.filesDone++
    onProgress?.({ ...hashed })
  }
}

/** ``verified``: path to SHA-256 of files the caller fingerprinted in this same selection and matched against this
 *  group's members; those are not read a second time. ``matched``: the saved files the caller matched without
 *  reading them. */
export async function resumeUploadGroup(
  id: string,
  files?: File[],
  onProgress?: (progress: UploadProgress) => void,
  verified?: ReadonlyMap<string, string>,
  matched?: MatchedFiles
): Promise<UploadGroup> {
  const checkSession = uploadSessionGuard()
  const state = await fetchAPI<UploadGroup>(`${endpoint}/${id}`)
  if (state.status === "completed") return state
  const attached = active.get(id)
  if (attached) {
    if (state.status === "paused")
      await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
    attached.pausedHere = false
    setPaused(attached, false)
    return attached.promise
  }
  const members = state.members || []
  const needed = members.filter((member) => !isSaved(member))
  const plan = planResume(members, files || [], state.kind)
  if (needed.length && !files?.length)
    throw new Error(
      "Reselect the original files, folder or archive. Uploaded files and chunks are already saved."
    )
  const shown = matched ?? (files?.length && !verified ? plan.matched : undefined)
  // Validate the remaining selection before resuming any bytes. Already verified members can be absent: they do not
  // have to be uploaded again. A saved file that was chosen and no longer matches is read like the rest.
  const selected = new Map((files || []).map((file) => [relativePath(file, state.kind), file]))
  const changed = (member: Member) =>
    new Error(`The original file ${member.path} is missing or has changed. Saved upload data has not changed.`)
  const toCheck = members.filter((member) => {
    const file = selected.get(member.path)
    return !(isSaved(member) && (!file || matchesSaved(member, file)))
  })
  for (const member of toCheck)
    if (selected.get(member.path)?.size !== member.size) throw changed(member)
  const read = new Map<string, Fingerprint>()
  await readFiles(
    toCheck.filter((member) => !verified?.has(member.path)).map((member) => selected.get(member.path)!),
    state.kind,
    read,
    onProgress,
    shown
  )
  for (const member of toCheck)
    if ((verified?.get(member.path) ?? read.get(member.path)?.sha256) !== member.sha256) throw changed(member)
  checkSession()
  if (state.status === "paused")
    await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
  return runGroup(state, files || [], onProgress, shown)
}

function runGroup(
  state: UploadGroup,
  files: File[],
  onProgress?: (progress: UploadProgress) => void,
  matched?: MatchedFiles
) {
  const checkSession = uploadSessionGuard()
  const prior = active.get(state.id)
  if (prior) return prior.promise
  const transfer: Active = {
    files,
    paused: false,
    completing: false,
    memberIds: new Set(),
    waiting: new Set(),
    promise: null as unknown as Promise<UploadGroup>,
  }
  active.set(state.id, transfer)
  transfer.promise = (async () => {
    const selected = new Map(
      files.map((file) => [relativePath(file, state.kind), file])
    )
    const sent: UploadProgress = {
      phase: "sending",
      filesDone: 0,
      filesTotal: state.file_count,
      bytesDone: state.received_bytes,
      bytesTotal: state.size,
      startedAt: Date.now(),
      bytesAtStart: state.received_bytes,
      kind: state.kind,
      matched,
    }
    const queue = (state.members || []).filter((member) => {
      if (!isSaved(member)) return true
      sent.filesDone++
      return false
    })
    onProgress?.({ ...sent })
    // Small files of one part go many to a request; larger files go in resumable chunks as before.
    const small = queue.filter((member) => isBatchable(member))
    const large = queue.filter((member) => !isBatchable(member))
    // Several files are sent at once, so a file's own time overstates its cost; the time left is fitted on the
    // interval between one file finishing and the next (a batch's interval is shared by its files).
    let lastFinish = performance.now()
    let failure: unknown = null
    const finished = (done: { size: number }[]) => {
      const now = performance.now()
      for (const item of done) sent.fit = addFileCost(sent.fit, item.size, (now - lastFinish) / 1000 / done.length)
      lastFinish = now
      sent.filesDone += done.length
      onProgress?.({ ...sent })
    }
    const sendSmall = async () => {
      const batch = takeBatch(small)
      let retried = false
      for (;;) {
        await whilePaused(transfer)
        checkSession()
        const missing = batch.find((member) => !selected.has(member.path))
        if (missing) throw new Error(`Reselect ${missing.path} to finish this selection.`)
        try {
          const saved = await sendBatch(
            state.id,
            batch.map((member) => ({ member, file: selected.get(member.path)! }))
          )
          const refused = saved.files.filter((item) => item.error)
          const done = batch.filter((member) =>
            saved.files.some((item) => item.id === member.id && STAGED.has(item.status))
          )
          sent.bytesDone += done.reduce((sum, member) => sum + member.size, 0)
          finished(done)
          if (refused.length) {
            const member = batch.find((item) => item.id === refused[0].id)
            throw new Error(
              `${member?.path ?? "A file"} does not match the fingerprint taken when it was chosen, so it was not saved. Select the original folder again; files already saved are kept.`
            )
          }
          return
        } catch (error) {
          if (error instanceof Error && /does not match the fingerprint/.test(error.message)) throw error
          // A pause (this tab's, or a release's) refuses the batch: wait for the resume and send it again. A lost
          // answer is retried once: the server keeps a file it already saved and answers for it unchanged.
          // The selection's own status says whether it is paused (a file's may already read staged); the list
          // also lets this tab follow the server (followServer) at once rather than at the next poll.
          const groups = await listUploadGroups(state.case_id).catch(() => null)
          if (groups?.find((group) => group.id === state.id)?.status === "paused" || transfer.paused) {
            if (!transfer.paused) setPaused(transfer, true)
            continue
          }
          if (retried) throw error
          retried = true
        }
      }
    }
    const sendLarge = async (member: UploadSession & { path: string }) => {
      const file = selected.get(member.path)
      checkSession()
      if (!file) throw new Error(`Reselect ${member.path} to finish this selection.`)
      transfer.memberIds.add(member.id)
      try {
        await transferFile(member, file, (bytes) => {
          sent.bytesDone += bytes
          onProgress?.({ ...sent })
        })
      } finally {
        transfer.memberIds.delete(member.id)
      }
      finished([member])
    }
    const sender = async () => {
      for (;;) {
        await whilePaused(transfer)
        if (failure !== null || (!small.length && !large.length)) return
        try {
          if (small.length) await sendSmall()
          else await sendLarge(large.shift()!)
        } catch (error) {
          failure ??= error
          return
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(SEND_AT_ONCE, queue.length) }, sender))
    if (failure !== null) throw failure
    await whilePaused(transfer)
    transfer.completing = true
    const registering = (done: number, registrationPhase?: RegistrationPhase) =>
      onProgress?.({
        ...sent,
        phase: "registering",
        bytesDone: sent.bytesTotal,
        filesDone: done,
        filesTotal: state.file_count,
        registrationPhase,
      })
    registering(0)
    checkSession()
    return await registerGroup(state.id, (step) => registering(step.done ?? 0, step.phase))
  })().finally(() => active.delete(state.id))
  return transfer.promise
}

/** How often the page asks how far registration has come. */
export const REGISTRATION_POLL_MS = 2000
/** How long the page keeps asking through failed requests (a server restart) before it gives up. */
export const REGISTRATION_UNREACHABLE_MS = 5 * 60 * 1000
/** Times a registration that stopped on the server (a restart) is started again before the page gives up. */
export const REGISTRATION_RESTARTS = 3
export const REGISTRATION_STOPPED =
  "Registration stopped on the server more than once. Choose Finish registration to try again; files will not be uploaded again."

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Registers a selection whose files are all saved and resolves with its receipt. The server answers ``complete``
 * at once for a large selection and registers it in the background, so no request timeout bounds a selection's
 * size; the page asks how far it has come until the receipt is there, and starts it again when it stopped (a
 * server restart leaves no half-registered selection: its rows and receipt commit together). */
export async function registerGroup(
  id: string,
  onStep?: (registration: Registration) => void,
  wait: (ms: number) => Promise<void> = pause
): Promise<UploadGroup> {
  const start = async (): Promise<UploadGroup> => {
    // The server holds this answer up to 25 s; the count moves meanwhile.
    const whileWaiting = setInterval(() => {
      void fetchAPI<UploadGroup>(`${endpoint}/${id}/registration`)
        .then((now) => {
          if (now.registration?.state === "running") onStep?.(now.registration)
        })
        .catch(() => {})
    }, REGISTRATION_POLL_MS)
    try {
      return await fetchAPI<UploadGroup>(`${endpoint}/${id}/complete`, { method: "POST", timeout: 2 * 60 * 1000 })
    } catch (error) {
      // A refusal (a file that changed, a paused selection) is the answer; a lost answer is not.
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) throw error
      const now = await fetchAPI<UploadGroup>(`${endpoint}/${id}/registration`).catch(() => null)
      if (now?.status === "completed" || now?.registration?.state === "running") return now
      throw error
    } finally {
      clearInterval(whileWaiting)
    }
  }
  let answer = await start()
  let restarts = 0
  let unreachableSince: number | null = null
  for (;;) {
    if (answer.status === "completed") return answer
    const registration = answer.registration
    if (registration?.state === "failed")
      throw new Error(
        registration.error?.detail ||
          "Registration stopped with an error. Choose Finish registration to try again; files will not be uploaded again."
      )
    if (registration?.state === "running") onStep?.(registration)
    else {
      // Nothing is registering it now (stopped, or done while its receipt was still being written): start it again.
      if (restarts++ >= REGISTRATION_RESTARTS) throw new Error(REGISTRATION_STOPPED)
      answer = await start()
      continue
    }
    await wait(REGISTRATION_POLL_MS)
    try {
      answer = await fetchAPI<UploadGroup>(`${endpoint}/${id}/registration`)
      unreachableSince = null
    } catch (error) {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) throw error
      unreachableSince ??= Date.now()
      if (Date.now() - unreachableSince > REGISTRATION_UNREACHABLE_MS) throw error
    }
  }
}

export async function uploadFolderOrArchive(
  caseId: string,
  files: File[],
  options: EvidenceUploadOptions,
  selectionKind?: "files"
): Promise<UploadResponse> {
  const checkSession = uploadSessionGuard()
  if (!files.length) throw new Error("Select files to upload.")
  // the server takes one file of at most MAX_FILE_BYTES (backend/routers/evidence_upload_groups.py Member.size); say so
  // before the whole selection is hashed, never after
  const tooLarge = files.find((file) => file.size > MAX_FILE_BYTES)
  if (tooLarge) throw new Error(tooLargeMessage(tooLarge, options.isArchive && !selectionKind))
  const kind = selectionKind || (options.isArchive ? "archive" : "folder")
  const onProgress = options.onProgress
  const name =
    kind === "files"
      ? `Selected files (${files.length})`
      : kind === "archive"
        ? files[0].name
        : relativePath(files[0], kind).split("/")[0]
  const sameSelection = (groups: UploadGroup[]) =>
    groups.filter(
      (group) =>
        group.kind === kind &&
        group.name === name &&
        group.folder_id === (options.folderId || null) &&
        !group.replace_existing &&
        group.file_count === files.length
    )
  const fetchGroup = (id: string) => fetchAPI<UploadGroup>(`${endpoint}/${id}`)
  const read = new Map<string, Fingerprint>()
  const unread = (list: File[]) => list.filter((file) => !read.has(relativePath(file, kind)))
  let prior: UploadGroup | undefined
  let matched: MatchedFiles | undefined
  // Carrying on a selection: its saved files are matched by name and size before anything is read (a fresh page read
  // every file of a phone folder first: 5 h 52 min on 81,820 files, 54,018 of them already saved and verified). Only
  // the files still to send are read, and they must be the ones this selection was fingerprinted from.
  for (const candidate of sameSelection(await listUploadGroups(caseId))) {
    const full = await fetchGroup(candidate.id)
    const plan = planResume(full.members || [], files, kind)
    const member = (file: File) => plan.byPath.get(relativePath(file, kind))
    if (!files.every((file) => member(file)?.size === file.size)) continue
    await readFiles(unread(plan.toRead), kind, read, onProgress, plan.matched)
    if (plan.toRead.every((file) => read.get(relativePath(file, kind))?.sha256 === member(file)?.sha256)) {
      prior = full
      matched = plan.matched
      break
    }
  }
  let manifest: (Fingerprint & { path: string; size: number; modified: number })[] = []
  if (!prior) {
    await readFiles(unread(files), kind, read, onProgress)
    manifest = files.map((file) => {
      const path = relativePath(file, kind)
      return { path, size: file.size, modified: file.lastModified, ...read.get(path)! }
    })
    // Every file is read now, so a selection begun meanwhile (another tab) is known by its fingerprints.
    for (const candidate of sameSelection(await listUploadGroups(caseId))) {
      const full = await fetchGroup(candidate.id)
      const members = new Map((full.members || []).map((member) => [member.path, member]))
      if (
        manifest.every((item) => {
          const member = members.get(item.path)
          return member?.sha256 === item.sha256 && member?.size === item.size
        })
      ) {
        prior = full
        break
      }
    }
  }
  checkSession()
  const group =
    prior ||
    (await fetchAPI<UploadGroup>(endpoint, {
      method: "POST",
      body: {
        id: randomUUID(),
        case_id: caseId,
        folder_id: options.folderId || null,
        name,
        kind,
        // Replacing a phone report is an explicit action on its extraction, never part of an upload (01 4.2).
        replace_existing: false,
        members: manifest,
      },
    }))
  checkSession()
  const result = prior
    ? // the files read above matched this group's members: do not read them again
      await resumeUploadGroup(
        group.id,
        files,
        onProgress,
        new Map([...read].map(([path, fingerprint]) => [path, fingerprint.sha256])),
        matched
      )
    : await runGroup(group, files, onProgress)
  if (!result.receipt)
    throw new Error(
      "The selection is saved. Finish registration from upload activity."
    )
  // The evidence queries refresh from the committed receipt; no per-file
  // fan-out is needed just to reconstruct an upload acknowledgement.
  return {
    files: [],
    file_ids: result.receipt.file_ids,
    job_ids: result.receipt.job_ids,
    message: matched?.files ? `${result.receipt.message} ${matchedWords(matched)}` : result.receipt.message,
  }
}
