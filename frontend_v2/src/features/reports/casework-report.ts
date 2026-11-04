import type { PrivilegeMarking } from "@/features/cases/snapshots-api"

export type CaseworkSection = "findings" | "theories" | "notes"

export const SECTION_LABELS: Record<CaseworkSection, string> = {
  findings: "Findings, with their linked evidence",
  theories: "Theories",
  notes: "Notes",
}

export const DEFAULT_SECTIONS: CaseworkSection[] = ["findings", "theories", "notes"]

export function moveSection(order: CaseworkSection[], index: number, delta: -1 | 1): CaseworkSection[] {
  const target = index + delta
  if (target < 0 || target >= order.length) return order
  const next = [...order]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

export async function downloadCaseworkReport(caseId: string, sections: CaseworkSection[], marking: PrivilegeMarking) {
  const token = localStorage.getItem("authToken")
  const response = await fetch(`/api/workspace/${encodeURIComponent(caseId)}/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    credentials: "include",
    body: JSON.stringify({ sections, privilege_marking: marking }),
  })
  if (!response.ok) {
    const detail = await response.json().then((b) => b?.detail).catch(() => null)
    throw new Error(typeof detail === "string" ? detail : `Report not produced (${response.status})`)
  }
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")
  const filename = match?.[1] ?? "casework-report.pdf"
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return filename
}

