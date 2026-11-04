/** Who took part in an interview or statement, and who conducted it (police, a deposition, trial, an investigator). */
export type Participant = Record<string, unknown> | string

export const INTERVIEWED_BY_ROLE = "interviewed_by"

const nameOf = (p: Participant) => (typeof p === "string" ? p : String(p.name ?? ""))
const isInterviewer = (p: Participant) => typeof p !== "string" && p.role === INTERVIEWED_BY_ROLE

export function splitParticipants(list: Participant[] | undefined) {
  const people = (list ?? []).filter((p) => !isInterviewer(p))
  const interviewer = (list ?? []).find(isInterviewer)
  return {
    names: people.map(nameOf).filter(Boolean),
    interviewedBy: interviewer ? nameOf(interviewer) : "",
  }
}

/**
 * The participants to save: each typed name, keeping any existing record for that name whole (an edit never drops
 * what was stored with a person), then the interviewer as its own record when given.
 */
export function buildParticipants(namesText: string, interviewedBy: string, existing: Participant[] | undefined): Participant[] {
  const records = new Map<string, Participant>()
  for (const p of existing ?? []) if (!isInterviewer(p) && typeof p !== "string") records.set(nameOf(p), p)
  const names = namesText.split(",").map((n) => n.trim()).filter(Boolean)
  const out: Participant[] = names.map((name) => records.get(name) ?? name)
  const by = interviewedBy.trim()
  if (by) {
    const previous = (existing ?? []).find(isInterviewer)
    out.push(previous && typeof previous !== "string" ? { ...previous, name: by } : { name: by, role: INTERVIEWED_BY_ROLE })
  }
  return out
}
