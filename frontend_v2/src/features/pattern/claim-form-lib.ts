import type { Claim, ClaimCounterpart, ClaimKind, ClaimPlace, Subject, SubjectList } from "./api"

/** The statement form's values and how they map to a claim's fields (04 section 9.1). */
export const KIND_WORDS: Record<ClaimKind, string> = {
  inactive: "Not using the phone (for example asleep)", active: "Using the phone", at_place: "At a place",
  not_at_place: "Not at a place", with_subject: "With someone", apart_from_subject: "Apart from someone",
  no_contact: "No contact with someone", contact: "In contact with someone",
}

/** What each field a person still has to settle means, for "Settle before confirming". */
export const MISSING_WORDS: Record<string, string> = {
  window_start: "when it starts", window_end: "when it ends", window_zone: "the time zone the statement uses",
  place: "the place, as a routine place or a point", counterpart: "the other person",
}

export const isPlaceKind = (k: ClaimKind) => k === "at_place" || k === "not_at_place"
export const isSubjectKind = (k: ClaimKind) => k === "with_subject" || k === "apart_from_subject"
export const isContactKind = (k: ClaimKind) => k === "no_contact" || k === "contact"

export interface ClaimInput {
  kind: ClaimKind
  words: string
  start: string
  end: string
  zone: string
  tolerance: string
  lat: string
  lon: string
  radius: string
  clusterId: number | null
  placeLabel: string
  placeText: string
  counterpart: ClaimCounterpart | null
}

export const BLANK_INPUT: ClaimInput = { kind: "inactive", words: "", start: "", end: "", zone: "UTC", tolerance: "0",
  lat: "", lon: "", radius: "100", clusterId: null, placeLabel: "", placeText: "", counterpart: null }

const minuteUtc = (t: string | null) => t ? new Date(t).toISOString().slice(0, 16) : ""

export function inputFromClaim(c: Claim): ClaimInput {
  const p = c.place
  return { kind: c.kind, words: c.window_text ?? "", start: minuteUtc(c.window_start), end: minuteUtc(c.window_end),
    zone: c.window_zone ?? "", tolerance: String(c.activity?.tolerance_minutes ?? 0), lat: p?.lat != null ? String(p.lat) : "",
    lon: p?.lon != null ? String(p.lon) : "", radius: p?.radius_m != null ? String(p.radius_m) : "100",
    clusterId: p?.cluster_id ?? null, placeLabel: p?.label ?? "", placeText: p?.text ?? c.as_drafted?.place_text ?? "",
    counterpart: c.counterpart }
}

function placeField(v: ClaimInput): ClaimPlace | null {
  if (!isPlaceKind(v.kind)) return null
  const text = v.placeText.trim()
  if (v.lat.trim() && v.lon.trim()) {
    return { lat: Number(v.lat), lon: Number(v.lon), radius_m: Number(v.radius),
      ...(v.clusterId !== null ? { cluster_id: v.clusterId } : {}), ...(v.placeLabel ? { label: v.placeLabel } : {}), ...(text ? { text } : {}) }
  }
  return text ? { text } : null
}

/** The claim's fields for this input. The form's times are UTC (its labels say so), whatever zone the statement uses. */
export function fieldsFromInput(v: ClaimInput, activity?: Claim["activity"]): Record<string, unknown> {
  const toIso = (t: string) => t ? new Date(`${t}:00Z`).toISOString() : null
  const tolerance = Number(v.tolerance || 0)
  const rest = { ...(activity ?? {}) }
  delete rest.tolerance_minutes
  return { kind: v.kind, window_text: v.words || null, window_zone: v.zone || null, window_start: toIso(v.start), window_end: toIso(v.end),
    place: placeField(v), counterpart: isSubjectKind(v.kind) || isContactKind(v.kind) ? v.counterpart : null,
    activity: v.kind === "inactive" && tolerance !== 0 ? { ...rest, tolerance_minutes: tolerance } : Object.keys(rest).length ? rest : null }
}

function sameValue(key: string, a: unknown, b: unknown) {
  if ((key === "window_start" || key === "window_end") && a && b) return new Date(a as string).getTime() === new Date(b as string).getTime()
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

/** Only what the person changed, so an edit never rewrites a field it did not touch (a stored time with seconds, a place's words). */
export function changedFields(c: Claim, v: ClaimInput): Record<string, unknown> {
  const after = fieldsFromInput(v, c.activity)
  const before: Record<string, unknown> = fieldsFromInput(inputFromClaim(c), c.activity)
  return Object.fromEntries(Object.entries(after).filter(([k, x]) => !sameValue(k, before[k], x)))
}

export function subjectName(list: SubjectList | undefined, s: Subject): string | null {
  if (s.kind === "extraction") return list?.extractions.find((e) => e.extraction_id === s.extraction_id)?.label ?? null
  return list?.dossiers.find((d) => d.dossier_id === s.dossier_id)?.name ?? null
}

export function counterpartWords(cp: ClaimCounterpart | null, list?: SubjectList): string | null {
  if (!cp) return null
  if ("identity_ids" in cp) return cp.label || `${cp.identity_ids.length.toLocaleString("en-US")} chosen identit${cp.identity_ids.length === 1 ? "y" : "ies"}`
  return subjectName(list, cp) ?? (cp.kind === "dossier" ? "a person in this case" : "a phone in this case")
}

export function placeWords(p: ClaimPlace | null): string | null {
  if (!p) return null
  if (p.lat == null || p.lon == null) return p.text ? `not placed yet: "${p.text}"` : null
  const where = p.label || `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`
  return `${where}, within ${Math.round(p.radius_m ?? 0).toLocaleString("en-US")} m${p.cluster_id != null ? " (a routine place)" : ""}`
}

export function toleranceWords(c: Pick<Claim, "kind" | "activity">): string | null {
  const m = c.activity?.tolerance_minutes
  if (c.kind !== "inactive" || !m) return null
  return `use within ${m.toLocaleString("en-US")} minute${m === 1 ? "" : "s"} of the start or end is allowed`
}
