import { sha256 } from "@noble/hashes/sha2.js"
import { bytesToHex } from "@noble/hashes/utils.js"
import { fetchAPI } from "@/lib/api-client"
import type { EvidenceFile } from "@/types/evidence.types"
import type { UploadResponse } from "./api"

export interface UploadSession {
  id: string
  case_id: string
  folder_id: string | null
  filename: string
  size: number
  sha256: string
  chunk_size: number
  received: number[]
  status: "uploading" | "paused" | "staged" | "completed"
  evidence_id: string | null
  group_id?: string | null
}
const CHUNK_SIZE = 4 * 1024 * 1024
const transfers = new Map<
  string,
  {
    file: File
    paused: boolean
    wake?: () => void
    promise: Promise<UploadSession>
  }
>()
const endpoint = "/api/evidence-upload-sessions"

export function uploadSessionGuard() {
  const token = localStorage.getItem("authToken")
  return () => {
    if (localStorage.getItem("authToken") !== token)
      throw new Error(
        "The signed-in session changed. Received upload data is retained. Sign in and resume from upload activity."
      )
  }
}

export async function uploadFingerprint(file: File) {
  const whole = sha256.create()
  const chunks: string[] = []
  for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
    const bytes = new Uint8Array(
      await file.slice(offset, offset + CHUNK_SIZE).arrayBuffer()
    )
    whole.update(bytes)
    chunks.push(bytesToHex(sha256(bytes)))
  }
  return { sha256: bytesToHex(whole.digest()), chunks }
}

export const listUploads = (caseId: string) =>
  fetchAPI<UploadSession[]>(`${endpoint}?case_id=${caseId}`)
export const hasLocalUploadFile = (id: string) => transfers.has(id)
export function setLocalUploadPaused(id: string, paused: boolean) {
  const transfer = transfers.get(id)
  if (transfer) {
    transfer.paused = paused
    if (!paused) transfer.wake?.()
  }
}

export async function pauseUpload(id: string) {
  const transfer = transfers.get(id)
  if (transfer) transfer.paused = true
  try {
    return await fetchAPI<UploadSession>(`${endpoint}/${id}/pause`, {
      method: "POST",
    })
  } catch (error) {
    if (transfer) {
      transfer.paused = false
      transfer.wake?.()
    }
    throw error
  }
}

export async function resumeUpload(
  id: string,
  file?: File
): Promise<UploadSession> {
  const checkSession = uploadSessionGuard()
  const current = transfers.get(id)
  if (current) {
    await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
    current.paused = false
    current.wake?.()
    return current.promise
  }
  if (!file)
    throw new Error(
      "Reselect the original file to resume. Uploaded chunks are already saved."
    )
  const saved = await fetchAPI<UploadSession>(`${endpoint}/${id}`)
  const fingerprint = await uploadFingerprint(file)
  checkSession()
  if (file.size !== saved.size || fingerprint.sha256 !== saved.sha256)
    throw new Error(
      "This is a different file. Select the original file; saved upload data has not changed."
    )
  await fetchAPI(`${endpoint}/${id}/resume`, { method: "POST" })
  checkSession()
  return transferFile(saved, file)
}

export function transferFile(session: UploadSession, file: File) {
  const checkSession = uploadSessionGuard()
  const existing = transfers.get(session.id)
  if (existing) return existing.promise
  const transfer = {
    file,
    paused: false,
    wake: undefined as (() => void) | undefined,
    promise: null as unknown as Promise<UploadSession>,
  }
  transfers.set(session.id, transfer)
  transfer.promise = (async () => {
    let state = await fetchAPI<UploadSession>(`${endpoint}/${session.id}`)
    if (state.status === "completed" || state.status === "staged") return state
    for (let index = 0; index < Math.ceil(file.size / CHUNK_SIZE); index++) {
      if (state.received.includes(index)) continue
      while (transfer.paused)
        await new Promise<void>((resolve) => {
          transfer.wake = resolve
        })
      checkSession()
      const chunk = file.slice(index * CHUNK_SIZE, (index + 1) * CHUNK_SIZE)
      try {
        state = await fetchAPI<UploadSession>(
          `${endpoint}/${session.id}/chunks/${index}`,
          {
            method: "PUT",
            body: chunk,
            headers: { "Content-Type": "application/octet-stream" },
          }
        )
      } catch (error) {
        state = await fetchAPI<UploadSession>(`${endpoint}/${session.id}`)
        if (state.received.includes(index)) continue // Lost acknowledgement.
        if (state.status === "paused" || transfer.paused) {
          transfer.paused = true
          index--
          continue
        }
        throw error
      }
    }
    for (;;) {
      while (transfer.paused)
        await new Promise<void>((resolve) => {
          transfer.wake = resolve
        })
      checkSession()
      try {
        return await fetchAPI<UploadSession>(
          `${endpoint}/${session.id}/complete`,
          { method: "POST" }
        )
      } catch (error) {
        // The server may have committed before the acknowledgement was lost.
        const receipt = await fetchAPI<UploadSession>(
          `${endpoint}/${session.id}`
        ).catch(() => null)
        if (receipt?.status === "completed" || receipt?.status === "staged")
          return receipt
        if (receipt?.status === "paused" || transfer.paused) {
          transfer.paused = true
          continue
        }
        throw error
      }
    }
  })().finally(() => transfers.delete(session.id))
  return transfer.promise
}

export async function uploadOrdinaryFiles(
  caseId: string,
  files: File[],
  folderId?: string
): Promise<UploadResponse> {
  const checkSession = uploadSessionGuard()
  const records: EvidenceFile[] = []
  for (const file of files) {
    const fingerprint = await uploadFingerprint(file)
    const pending = await listUploads(caseId)
    const prior = pending.find(
      (item) =>
        item.sha256 === fingerprint.sha256 &&
        item.filename === file.name &&
        item.folder_id === (folderId || null)
    )
    // A random id belongs to this transfer, not the file hash: intentional
    // separately uploaded originals remain distinct.
    const id = prior?.id ?? randomUUID()
    checkSession()
    const session = await fetchAPI<UploadSession>(endpoint, {
      method: "POST",
      body: {
        id,
        case_id: caseId,
        folder_id: folderId || null,
        filename: file.name,
        size: file.size,
        ...fingerprint,
      },
    })
    const result = prior
      ? await resumeUpload(id, file)
      : await transferFile(session, file)
    if (!result.evidence_id)
      throw new Error(
        "Upload is saved but evidence registration has not completed. Resume to finish."
      )
    records.push(
      await fetchAPI<EvidenceFile>(`/api/evidence/${result.evidence_id}`)
    )
  }
  return {
    files: records,
    message: `Uploaded ${records.length} file(s). Select Process to start ingestion.`,
  }
}

export function randomUUID() {
  // crypto.randomUUID is unavailable on Loupe's current HTTP origin.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = bytesToHex(bytes)
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
