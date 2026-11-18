import type { RelationMember } from "@/features/relations/api"
import { addPart } from "@/features/corroborate/selection-store"

export interface CorroborateAsk {
  caseId: string
  screen: string
  label: string
  members: RelationMember[]
  people?: string[]
  period?: { from: string; to: string }
}

/**
 * "Corroborate this" from an overlap view: the records join the Corroborate selection (the tray every screen
 * shares), and the Leads panel is asked to open over the page with them (lx-leads' "loupe-corroborate-open"
 * event, the same one its openCorroborate sends). Nothing is saved until a question is asked there.
 */
export function askCorroborate(ask: CorroborateAsk) {
  addPart(ask.caseId, { screen: ask.screen, label: ask.label, members: ask.members, skipped: [] })
  window.dispatchEvent(new CustomEvent("loupe-corroborate-open", { detail: ask }))
}
