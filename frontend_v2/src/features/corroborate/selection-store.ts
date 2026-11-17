import { useSyncExternalStore } from "react"
import type { RelationMember } from "@/features/relations/api"

/**
 * The case-wide selection for Corroborate (lx-corroselect B). It follows the investigator across screens and reloads
 * until cleared, holds any mix of record types, and each part is one chip: its screen, its words and its whole count.
 * The count is always the whole set (members de-duplicated), never a page. It is the draft of a `case_selections`
 * group: on Corroborate it is frozen there (kind relation_query), so there is one store of record, not two.
 * It uses only localStorage and plain arrays (the site runs on plain http: no crypto.randomUUID).
 */
export interface SelectionPart {
  id: string
  /** The screen it came from, in words: "the map", "the graph", "the ledger" ... */
  screen: string
  label: string
  members: RelationMember[]
  /** Chosen items the analysis cannot read yet, by type; named to the person, never dropped silently. */
  skipped: { type: string; count: number }[]
  /** Left out because the paste matched nothing, kept so the chip can say so. */
  unmatched?: string[]
}

export type NewPart = Omit<SelectionPart, "id"> & { id?: string }

const KEY = (caseId: string) => `loupeCorroSelection:${caseId}`
const EVENT = "loupe-corro-selection"
const memory = new Map<string, string>()
const memoryOnly = new Set<string>()
const EMPTY: SelectionPart[] = []
const parsed = new Map<string, { raw: string; parts: SelectionPart[] }>()
let counter = 0

function readRaw(caseId: string): string {
  try {
    const stored = localStorage.getItem(KEY(caseId))
    // Storage that refused the last write holds the older copy; the in-page copy is newer then.
    return stored ?? (memoryOnly.has(caseId) ? (memory.get(caseId) ?? "[]") : "[]")
  } catch {
    return memory.get(caseId) ?? "[]"
  }
}

export function getSelection(caseId: string): SelectionPart[] {
  const raw = readRaw(caseId)
  const hit = parsed.get(caseId)
  if (hit && hit.raw === raw) return hit.parts
  let parts: SelectionPart[]
  try {
    const v = JSON.parse(raw)
    parts = Array.isArray(v) ? v : EMPTY
  } catch {
    parts = EMPTY
  }
  parsed.set(caseId, { raw, parts })
  return parts
}

/** Returns false when the browser would not keep it; the selection then lives until the page closes, and says so. */
function write(caseId: string, parts: SelectionPart[]): boolean {
  const raw = JSON.stringify(parts)
  memory.set(caseId, raw)
  let kept = true
  try {
    if (parts.length) localStorage.setItem(KEY(caseId), raw)
    else localStorage.removeItem(KEY(caseId))
    memoryOnly.delete(caseId)
  } catch {
    kept = false
    memoryOnly.add(caseId)
  }
  window.dispatchEvent(new Event(EVENT))
  return kept
}

export function addPart(caseId: string, part: NewPart): { id: string; kept: boolean; added: number } {
  const have = new Set(selectionMembers(getSelection(caseId)).map((m) => `${m.type}:${m.id}`))
  const added = part.members.filter((m) => !have.has(`${m.type}:${m.id}`)).length
  const id = part.id ?? `p${Date.now().toString(36)}${(counter++).toString(36)}`
  const kept = write(caseId, [...getSelection(caseId).filter((p) => p.id !== id), { ...part, id }])
  return { id, kept, added }
}

export function removePart(caseId: string, id: string) {
  write(caseId, getSelection(caseId).filter((p) => p.id !== id))
}

export function clearSelection(caseId: string) {
  write(caseId, [])
}

/** Every member once, in the order chosen. */
export function selectionMembers(parts: SelectionPart[]): RelationMember[] {
  const seen = new Set<string>()
  const out: RelationMember[] = []
  for (const p of parts)
    for (const m of p.members) {
      const k = `${m.type}:${m.id}`
      if (!seen.has(k)) {
        seen.add(k)
        out.push(m)
      }
    }
  return out
}

/** The whole set, de-duplicated across parts. */
export function selectionCount(parts: SelectionPart[]): number {
  return selectionMembers(parts).length
}

export function useSelection(caseId: string | undefined): SelectionPart[] {
  return useSyncExternalStore(
    (l) => {
      window.addEventListener(EVENT, l)
      window.addEventListener("storage", l)
      return () => {
        window.removeEventListener(EVENT, l)
        window.removeEventListener("storage", l)
      }
    },
    () => (caseId ? getSelection(caseId) : EMPTY),
    () => EMPTY,
  )
}
