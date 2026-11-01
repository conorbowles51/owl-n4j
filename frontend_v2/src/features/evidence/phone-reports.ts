import { fetchAPI } from "@/lib/api-client"

/** Phone reports of a case and Replace / Retire (01 section 10.7): types, the API and the rules the panel shows. */

export interface PhoneReport {
  id: string
  case_id: string
  label: string
  standing: "pending" | "active" | "superseded"
  capture_state: string
  record_count: number | null
  file_count: number | null
  created_at: string | null
  captured_at: string | null
  extracted_from: string | null
  extracted_to: string | null
  supersedes_id: string | null
  superseded_at: string | null
  superseded_reason: string | null
  superseded_by: string | null
  replaced_by_id: string | null
  possible_same_device: { extraction_id: string; name: string | null }[]
}

const READ_IN_FULL = ["captured", "captured_incomplete"]

export const phoneReportsKey = (caseId: string) => ["phone-extractions", caseId]

export const phoneReportsAPI = {
  list: (caseId: string) => fetchAPI<PhoneReport[]>(`/api/phone-extractions?case_id=${encodeURIComponent(caseId)}`),
  supersede: (newId: string, previousId: string, reason: string) =>
    fetchAPI<PhoneReport[]>(`/api/phone-extractions/${newId}/supersede`, {
      method: "POST",
      body: { previous_id: previousId, reason },
    }),
}

export const day = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" }) : ""

/** The consequence shown before Replace or Retire runs (01 section 10.7 step 3). */
export function consequenceText(older: PhoneReport) {
  const when = older.extracted_from
    ? `extracted ${day(older.extracted_from)}`
    : `read into the case ${day(older.captured_at || older.created_at)}`
  return `${older.label} (${when}) will be retired. Its records stay readable and marked as from a replaced report.`
}

export function isUsable(report: PhoneReport) {
  return report.standing === "active" && READ_IN_FULL.includes(report.capture_state)
}

/** Replace on the newer report names each older report the capture flagged as the same phone and still in use. */
export function replaceTargets(report: PhoneReport, all: PhoneReport[]) {
  if (!isUsable(report)) return []
  const ids = new Set(report.possible_same_device.map((p) => p.extraction_id))
  return all.filter((other) => ids.has(other.id) && other.id !== report.id && other.standing === "active")
}

/** Retire on an older report asks which report replaces it: any other report in use that was read in full. */
export function retireCandidates(report: PhoneReport, all: PhoneReport[]) {
  if (report.standing !== "active") return []
  return all.filter((other) => other.id !== report.id && isUsable(other))
}

