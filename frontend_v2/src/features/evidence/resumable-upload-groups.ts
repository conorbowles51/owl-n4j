import { fetchAPI } from "@/lib/api-client"
import type { EvidenceUploadOptions, UploadResponse } from "./api"
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
  memberId?: string
  wake?: () => void
  promise: Promise<UploadGroup>
}
const active = new Map<string, Active>()
const relativePath = (file: File, kind: UploadGroup["kind"]) =>
  kind === "folder" ? file.webkitRelativePath || file.name : file.name
export const listUploadGroups = (caseId: string) =>
  fetchAPI<UploadGroup[]>(`${endpoint}?case_id=${caseId}`)
export const hasLocalUploadGroup = (id: string) => active.has(id)
export const isCompletingUploadGroup = (id: string) =>
  active.get(id)?.completing ?? false

export async function pauseUploadGroup(id: string) {
  const transfer = active.get(id)
  if (transfer?.completing)
    throw new Error(
      "Files have arrived. Registration is finishing and will be retained if you leave."
    )
  if (transfer) {
    transfer.paused = true
    if (transfer.memberId) setLocalUploadPaused(transfer.memberId, true)
  }
  try {
    return await fetchAPI<UploadGroup>(`${endpoint}/${id}/pause`, {
      method: "POST",
    })
  } catch (error) {
    if (transfer) {
      transfer.paused = false
      transfer.wake?.()
      if (transfer.memberId) setLocalUploadPaused(transfer.memberId, false)
    }
    throw error
  }
}

export async function resumeUploadGroup(
  id: string,
  files?: File[]
): Promise<UploadGroup> {
  const checkSession = uploadSessionGuard()
  const state = await fetchAPI<UploadGroup>(`${endpoint}/${id}`)
  if (state.status === "completed") return state
  const attached = active.get(id)
  if (attached) {
    if (state.status === "paused")
      await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
    attached.paused = false
    attached.wake?.()
    if (attached.memberId) setLocalUploadPaused(attached.memberId, false)
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
  return runGroup(state, files || [])
}

function runGroup(state: UploadGroup, files: File[]) {
  const checkSession = uploadSessionGuard()
  const prior = active.get(state.id)
  if (prior) return prior.promise
  const transfer: Active = {
    files,
    paused: false,
    completing: false,
    promise: null as unknown as Promise<UploadGroup>,
  }
  active.set(state.id, transfer)
  transfer.promise = (async () => {
    const selected = new Map(
      files.map((file) => [relativePath(file, state.kind), file])
    )
    for (const member of state.members || []) {
      if (member.status === "staged" || member.status === "completed") continue
      while (transfer.paused)
        await new Promise<void>((resolve) => {
          transfer.wake = resolve
        })
      const file = selected.get(member.path)
      checkSession()
      if (!file)
        throw new Error(`Reselect ${member.path} to finish this selection.`)
      transfer.memberId = member.id
      await transferFile(member, file)
      transfer.memberId = undefined
    }
    while (transfer.paused)
      await new Promise<void>((resolve) => {
        transfer.wake = resolve
      })
    transfer.completing = true
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
  const manifest = []
  for (const file of files)
    manifest.push({
      path: relativePath(file, kind),
      size: file.size,
      ...(await uploadFingerprint(file)),
    })
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
      group.replace_existing === !!options.replaceExisting &&
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
        replace_existing: !!options.replaceExisting,
        members: manifest,
      },
    }))
  checkSession()
  const result = prior
    ? await resumeUploadGroup(group.id, files)
    : await runGroup(group, files)
  if (!result.receipt)
    throw new Error(
      "The selection is saved. Finish registration from upload activity."
    )
  // The evidence queries refresh from the committed receipt; no 20,000-file
  // fan-out is needed just to reconstruct an upload acknowledgement.
  return {
    files: [],
    file_ids: result.receipt.file_ids,
    job_ids: result.receipt.job_ids,
    message: result.receipt.message,
  }
}
