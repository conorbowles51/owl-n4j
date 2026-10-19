import { ApiError } from "@/lib/api-client"
import {
  UNADMITTED_FILES_ERROR,
  type HeldFile,
  type UnadmittedFilesRefusal,
} from "../api"

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

const nullableString = (value: unknown) =>
  value === null || typeof value === "string"

/** Reject the whole envelope if any file is unreadable; never quietly drop a hold. */
export function readAdmissionRefusal(
  error: unknown
): UnadmittedFilesRefusal | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 409 ||
    !record(error.data)
  )
    return null
  const detail = error.data.detail
  if (
    !record(detail) ||
    detail.error !== UNADMITTED_FILES_ERROR ||
    typeof detail.message !== "string" ||
    !Array.isArray(detail.held) ||
    !detail.held.length
  )
    return null
  const held: HeldFile[] = []
  const ids = new Set<string>()
  for (const file of detail.held) {
    if (
      !record(file) ||
      typeof file.file_id !== "string" ||
      !file.file_id ||
      ids.has(file.file_id) ||
      !nullableString(file.file_name) ||
      typeof file.route_outcome !== "string" ||
      !nullableString(file.detected_format) ||
      !Array.isArray(file.claimants) ||
      !file.claimants.every((item: unknown) => typeof item === "string")
    )
      return null
    ids.add(file.file_id)
    held.push(file as unknown as HeldFile)
  }
  return { error: UNADMITTED_FILES_ERROR, message: detail.message, held }
}

export interface AdmissionReading {
  canProcess: boolean
  decisionRecorded: boolean
  message: string
  reason: string | null
  reasonLabel: string
  routeOutcome: string | null
  detectedFormat: string | null
  claimants: string[]
}

/** A 200 can be a refusal. Unknown or contradictory answers never enable a send. */
export function readFileAdmission(
  value: unknown,
  fileId: string
): AdmissionReading {
  const invalid: AdmissionReading = {
    canProcess: false,
    decisionRecorded: false,
    message:
      "The admission response could not be verified. Nothing was sent. Check the decision history before trying again.",
    reason: null,
    reasonLabel: "System response",
    routeOutcome: null,
    detectedFormat: null,
    claimants: [],
  }
  if (!record(value)) return invalid
  // Refresh the history even for a contradictory response that may have written a decision.
  const decisionRecorded =
    value.admitted === true || typeof value.adjudication_id === "string"
  const base = { ...invalid, decisionRecorded }
  if (
    value.file_id !== fileId ||
    typeof value.outcome !== "string" ||
    typeof value.admitted !== "boolean" ||
    !nullableString(value.reason) ||
    !nullableString(value.route_outcome) ||
    !nullableString(value.detected_format) ||
    !Array.isArray(value.claimants) ||
    !value.claimants.every((x: unknown) => typeof x === "string")
  )
    return base
  const details = {
    ...base,
    reason: value.reason as string | null,
    routeOutcome: value.route_outcome as string | null,
    detectedFormat: value.detected_format as string | null,
    claimants: value.claimants as string[],
  }
  if (
    value.outcome === "admitted" &&
    value.admitted &&
    value.routed_to === "document_pipeline" &&
    typeof value.adjudication_id === "string" &&
    value.adjudication_id.length > 0
  ) {
    return {
      ...details,
      canProcess: true,
      message: "Decision recorded. This file has not been sent for processing.",
      reasonLabel: "Your recorded reason",
    }
  }
  if (
    value.outcome === "nothing_to_override" &&
    !value.admitted &&
    value.adjudication_id === null &&
    value.routed_to === "held"
  ) {
    return {
      ...details,
      canProcess: true,
      message:
        "The file is no longer held. No decision was recorded. It has not been sent for processing.",
    }
  }
  if (
    value.outcome === "refused" &&
    !value.admitted &&
    value.adjudication_id === null
  ) {
    return {
      ...details,
      message: "The decision was refused. Nothing was sent.",
    }
  }
  return {
    ...details,
    message: `Unverified admission outcome: ${value.outcome}. Nothing was sent. Check the decision history before trying again.`,
  }
}
