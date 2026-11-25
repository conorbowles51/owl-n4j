import type { RelationMember } from "@/features/relations/api"
import type { Scope } from "@/features/corroborate/api"
import { addPart } from "@/features/corroborate/selection-store"

/**
 * Corroborate from anywhere (lx-leads C): one action on any selection opens the Corroborate panel over the current
 * page. A plain function: it only sends a window event, so any screen can call it, and calling it before the panel
 * has loaded is safe (the panel reads the last request when it mounts).
 */
export interface CorroborateRequest {
  caseId: string
  /** The screen it came from, in words: "Conversations", "the map" ... */
  screen: string
  /** What was chosen, in words: "1 message", "Kell and Okafor" ... */
  label: string
  members: RelationMember[]
  /** Store person keys ("person:<id>"), for "Leads already here". */
  people?: string[]
  period?: { from: string; to: string }
  /** Chosen items Corroborate cannot read yet, by type: named in the panel, never dropped without a word. */
  skipped?: { type: string; count: number }[]
  /** The list's own time scope, handed to the full question menu. */
  scope?: Scope
  /** The page it was asked from (set by openCorroborate): the panel shows only there, never on another page. */
  path?: string
}

export const CORROBORATE_OPEN = "loupe-corroborate-open"
let last: CorroborateRequest | null = null

export function openCorroborate(request: CorroborateRequest, opts: { keep?: boolean } = {}): void {
  // The choice also joins the case-wide selection (lx-corroselect), so gathering across screens keeps working.
  if (opts.keep !== false && request.members.length)
    addPart(request.caseId, { screen: request.screen, label: request.label, members: request.members, skipped: request.skipped ?? [] })
  const asked = { ...request, path: request.path ?? window.location.pathname }
  // kept only until a panel takes it: a panel already showing takes it from the event (and clears it), so a panel
  // mounted later (another page) never opens by itself with an old request
  last = asked
  window.dispatchEvent(new CustomEvent<CorroborateRequest>(CORROBORATE_OPEN, { detail: asked }))
}

/** The request sent before the panel mounted, once, and only on the page it was asked from. */
export function takePendingCorroborate(): CorroborateRequest | null {
  const r = last
  last = null
  return r && (!r.path || r.path === window.location.pathname) ? r : null
}

export function clearPendingCorroborate(): void {
  last = null
}
