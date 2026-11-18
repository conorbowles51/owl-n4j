import { useSyncExternalStore } from "react"

/**
 * "Show these records" (lx-leads C): while a lead is open, its records are highlighted in Conversations, the map and
 * the timeline. Closing the lead clears them. In-page only: nothing is stored.
 */
interface Shown {
  leadId: string
  title: string
  refs: Set<string>
  /** Where the bar's links go: the lead's case and its days, so the marked records are on screen. */
  caseId?: string
  period?: { from?: string; to?: string }
}

let shown: Shown | null = null
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

export function showLeadRecords(leadId: string, title: string, refs: string[],
                                where: { caseId?: string; period?: { from?: string; to?: string } } = {}): void {
  shown = { leadId, title, refs: new Set(refs), ...where }
  emit()
}

export function clearLeadRecords(leadId?: string): void {
  if (!shown || (leadId && shown.leadId !== leadId)) return
  shown = null
  emit()
}

export function getShownLead(): Shown | null {
  return shown
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useShownLead(): Shown | null {
  return useSyncExternalStore(subscribe, getShownLead, getShownLead)
}

/** True when the record (by "type:id", or a bare record uid) belongs to the shown lead. */
export function isShownRef(s: Shown | null, ref: string | null | undefined): boolean {
  if (!s || !ref) return false
  return s.refs.has(ref) || s.refs.has(`phone_record:${ref}`) || s.refs.has(`financial_transaction:${ref}`)
}

export function useIsShown(ref: string | null | undefined): boolean {
  return isShownRef(useShownLead(), ref)
}

export const SHOWN_CLASS = "ring-2 ring-amber-400 bg-amber-50 dark:bg-amber-400/10"
