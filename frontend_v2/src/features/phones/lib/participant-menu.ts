import type { ParticipantLabelData } from "../schemas"

/**
 * Where the four actions of a participant label land (03 section 6.7). Pure, so each scope is tested. The other side
 * of a pair is the other party on the same row; with no identifier of its own (a phone's owner often has none), the
 * "between" reading with one person already means that person and the owner of each phone (PersonScope).
 */

type RowParties = { from: ParticipantLabelData | null; to: ParticipantLabelData[] }

const base = (caseId: string) => `/cases/${encodeURIComponent(caseId)}`

export function personPath(caseId: string, key: string): string {
  return `${base(caseId)}/conversations?${new URLSearchParams({ tab: "people", people: key }).toString()}`
}

/** The other party of the row: the sender for a recipient, the first recipient who is someone else for the sender. */
export function otherParty(row: RowParties, label: ParticipantLabelData): ParticipantLabelData | null {
  const same = (x: ParticipantLabelData) => x === label || (!!label.identity_key && x.identity_key === label.identity_key)
  if (row.from && !same(row.from)) return row.from
  return row.to.find((t) => !same(t)) ?? null
}

export function pairPath(caseId: string, key: string, other: ParticipantLabelData | null): string | null {
  if (!other) return null
  const otherKey = other.identity_key
  if (!otherKey && !other.is_owner) return null
  const people = otherKey && otherKey !== key ? [key, otherKey] : [key]
  return `${base(caseId)}/conversations?${new URLSearchParams({ tab: "people", people: people.join(","), mode: "between" }).toString()}`
}

/** People is the dossiers page; an identity with no person yet opens on Link to a person (07 J-7). */
export function peoplePath(caseId: string, key: string, linkedDossier: string | null): string {
  if (linkedDossier) return `${base(caseId)}/dossiers?${new URLSearchParams({ dossier: linkedDossier }).toString()}`
  return `${base(caseId)}/phone-review?${new URLSearchParams({ decision: "link_phone_identity", identity: key }).toString()}`
}
