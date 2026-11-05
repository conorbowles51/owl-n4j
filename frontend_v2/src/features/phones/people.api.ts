import { fetchAPI } from "@/lib/api-client"

/** People across phones (03 section 10.4; 07 4.5): the Phone identities list, a dossier's panel, scope presets. */
export interface RegistryItem {
  identity_key: string
  kind: string
  subkind: string | null
  value_display: string | null
  names: { phone_label: string | null; extraction_id: string; name: string; basis: string }[]
  person: { id: string; display_name: string | null } | null
  event_count: number
  phones: { extraction_id: string; phone_label: string; events: number }[]
  first_contact: string | null
  last_contact: string | null
  can_be_a_person: boolean
}

export interface Registry {
  case_id: string
  items: RegistryItem[]
  total: number
  next_cursor: number | null
  in_case: number
  linked_in_case: number
}

export interface RegistryParams {
  q?: string
  phone?: string
  linked?: boolean
  cursor?: number
  limit?: number
}

export interface PanelPhone {
  extraction_id: string
  label: string
  names: { name: string; value_display: string | null; basis: string; contact_created: string | null; contact_modified: string | null }[]
  total: number
  first_contact: string | null
  last_contact: string | null
  kinds: { kind: string; directions: { direction: string; events: number }[] }[]
  conversations_href: string
}

export interface PanelDecision {
  id: string
  decision: string
  reason: string
  reason_kind: string
  actor: string | null
  at: string | null
  identity_key: string
  value_display: string | null
}

export interface DossierPhones {
  case_id: string
  dossier: { id: string; name: string; type: string }
  identities: { identity_key: string; kind: string; value_display: string | null; events: number; phones: number; conversations_href: string }[]
  phones: PanelPhone[]
  total: number
  conversations_href: string | null
  suggested_identities: number
  review_href: string
  phones_in_case: number
  history: PanelDecision[]
  history_total: number
  expected_revision: string | null
}

export interface ScopePerson {
  dossier_id: string
  name: string
  identity_keys: string[]
  owned_phones: string[]
  appears_on: string[]
}

export const peopleAPI = {
  registry: (caseId: string, p: RegistryParams = {}) => {
    const q = new URLSearchParams({ case_id: caseId, limit: String(p.limit ?? 50), cursor: String(p.cursor ?? 0) })
    if (p.q?.trim()) q.set("q", p.q.trim())
    if (p.phone) q.set("phone", p.phone)
    if (p.linked !== undefined) q.set("linked", String(p.linked))
    return fetchAPI<Registry>(`/api/phones/identities?${q}`, { read: true })
  },
  dossierPhones: (caseId: string, dossierId: string) =>
    fetchAPI<DossierPhones>(`/api/phones/people/${encodeURIComponent(dossierId)}/phones?case_id=${encodeURIComponent(caseId)}`, { read: true }),
  scopeIdentities: (caseId: string, phones: string[]) => {
    const q = new URLSearchParams({ case_id: caseId })
    if (phones.length) q.set("phones", phones.join(","))
    return fetchAPI<{ total: number }>(`/api/phones/scope-identities?${q}`, { read: true })
  },
  scopePresets: (caseId: string) =>
    fetchAPI<{ case_id: string; people: ScopePerson[] }>(`/api/phones/scope-presets?case_id=${encodeURIComponent(caseId)}`, { read: true }),
}

export const dayOf = (iso: string | null) => (iso ? iso.slice(0, 10) : "not recorded")

/** A count's link: the phone's list for this person, narrowed to one channel and direction. */
export function countHref(href: string, kind: string, direction: string) {
  return `${href}&kinds=${encodeURIComponent(kind)}&directions=${encodeURIComponent(direction)}`
}
