import { fetchAPI } from "@/lib/api-client"
import type { EvidenceUploadOptions, UploadResponse } from "./api"
import { addFileCost, type UploadProgress } from "./upload-progress"
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
  members?: (UploadSession & { path: string })[]
  receipt: { file_ids: string[]; job_ids: string[]; message: string } | null
}
const endpoint = "/api/evidence-upload-groups"
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

export async function resumeUploadGroup(
  id: string,
  files?: File[],
  onProgress?: (progress: UploadProgress) => void
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
  const needed = (state.members || []).filter(
    (m) => m.status !== "staged" && m.status !== "completed"
  )
  if (needed.length) {
    if (!files?.length)
      throw new Error(
        "Reselect the original files, folder or archive. Uploaded files and chunks are already saved."
      )
    const selected = new Map(
      files.map((file) => [relativePath(file, state.kind), file])
    )
    // Validate the remaining selection before resuming any bytes. Already
    // verified members can be absent: they do not have to be uploaded again.
    for (const member of needed) {
      const file = selected.get(member.path)
      if (
        !file ||
        file.size !== member.size ||
        (await uploadFingerprint(file)).sha256 !== member.sha256
      )
        throw new Error(
          `The original file ${member.path} is missing or has changed. Saved upload data has not changed.`
        )
    }
  }
  checkSession()
  if (state.status === "paused")
    await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
  return runGroup(state, files || [], onProgress)
}

function runGroup(
  state: UploadGroup,
  files: File[],
  onProgress?: (progress: UploadProgress) => void
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
    }
    onProgress?.({ ...sent })
    const queue = (state.members || []).filter((member) => {
      if (member.status !== "staged" && member.status !== "completed") return true
      sent.filesDone++
      return false
    })
    // Several files are sent at once, so a file's own time overstates its cost; the time left is fitted on the
    // interval between one file finishing and the next.
    let lastFinish = performance.now()
    let failure: unknown = null
    const sender = async () => {
      for (;;) {
        await whilePaused(transfer)
        const member = failure === null ? queue.shift() : undefined
        if (!member) return
        const file = selected.get(member.path)
        try {
          checkSession()
          if (!file)
            throw new Error(`Reselect ${member.path} to finish this selection.`)
          transfer.memberIds.add(member.id)
          await transferFile(member, file, (bytes) => {
            sent.bytesDone += bytes
            onProgress?.({ ...sent })
          })
        } catch (error) {
          failure ??= error
          return
        } finally {
          transfer.memberIds.delete(member.id)
        }
        const now = performance.now()
        sent.fit = addFileCost(sent.fit, file.size, (now - lastFinish) / 1000)
        lastFinish = now
        sent.filesDone++
        onProgress?.({ ...sent })
      }
    }
    await Promise.all(Array.from({ length: Math.min(SEND_AT_ONCE, queue.length) }, sender))
    if (failure !== null) throw failure
    await whilePaused(transfer)
    transfer.completing = true
    onProgress?.({ ...sent, phase: "registering", bytesDone: sent.bytesTotal })
    checkSession()
    try {
      return await fetchAPI<UploadGroup>(`${endpoint}/${state.id}/complete`, {
        method: "POST",
        timeout: 60 * 60 * 1000,
      })
    } catch (error) {
      const receipt = await fetchAPI<UploadGroup>(
        `${endpoint}/${state.id}`
      ).catch(() => null)
      if (receipt?.status === "completed") return receipt
      throw error
    }
  })().finally(() => active.delete(state.id))
  return transfer.promise
}

export async function uploadFolderOrArchive(
  caseId: string,
  files: File[],
  options: EvidenceUploadOptions,
  selectionKind?: "files"
): Promise<UploadResponse> {
  const checkSession = uploadSessionGuard()
  if (!files.length) throw new Error("Select files to upload.")
  const kind = selectionKind || (options.isArchive ? "archive" : "folder")
  const onProgress = options.onProgress
  const hashed: UploadProgress = {
    phase: "hashing",
    filesDone: 0,
    filesTotal: files.length,
    bytesDone: 0,
    bytesTotal: files.reduce((sum, file) => sum + file.size, 0),
    startedAt: Date.now(),
    bytesAtStart: 0,
    kind,
  }
  onProgress?.({ ...hashed })
  const manifest = []
  for (const file of files) {
    const began = performance.now()
    manifest.push({
      path: relativePath(file, kind),
      size: file.size,
      ...(await uploadFingerprint(file, (bytes) => {
        hashed.bytesDone += bytes
        onProgress?.({ ...hashed })
      })),
    })
    hashed.fit = addFileCost(hashed.fit, file.size, (performance.now() - began) / 1000)
    hashed.filesDone++
    onProgress?.({ ...hashed })
  }
  const name =
    kind === "files"
      ? `Selected files (${files.length})`
      : kind === "archive"
        ? files[0].name
        : relativePath(files[0], kind).split("/")[0]
  const pending = await listUploadGroups(caseId)
  let prior: UploadGroup | undefined
  for (const candidate of pending.filter(
    (group) =>
      group.kind === kind &&
      group.name === name &&
      group.folder_id === (options.folderId || null) &&
      !group.replace_existing &&
      group.file_count === files.length
  )) {
    const full = await fetchAPI<UploadGroup>(`${endpoint}/${candidate.id}`)
    if (
      manifest.every((item) =>
        full.members?.some(
          (m) =>
            m.path === item.path &&
            m.sha256 === item.sha256 &&
            m.size === item.size
        )
      )
    ) {
      prior = full
      break
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
    ? await resumeUploadGroup(group.id, files, onProgress)
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
    message: result.receipt.message,
  }
}
