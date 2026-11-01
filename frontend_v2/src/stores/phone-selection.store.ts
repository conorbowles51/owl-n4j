import { create } from "zustand"

/**
 * The phone selection store (07 4.2 item 7, 4.8, 6.2). Phone records are not graph nodes, so selection on phone
 * screens lives here, keyed by record id, and the side panel, the Notebook and Add to… read it. Nothing is cut
 * to a first few items: either a set of ids, or "the whole filtered result" stated with its total and scope.
 */

export interface WholeResult {
  total: number
  noun: string
  /** The scope in words, e.g. "between A and B, 1 Jan to 31 Mar, on 3 phones". */
  scope: string
  /** The scope as stored in the URL, so the server can resolve the same records. */
  scopeKey: string
}

interface PhoneSelectionState {
  caseId: string | null
  ids: string[]
  anchor: string | null
  focus: string | null
  whole: WholeResult | null
  setCase: (caseId: string) => void
  focusOn: (id: string | null) => void
  toggle: (id: string) => void
  /** Shift+click or Shift+J/K: everything between the anchor and `id` in the current order. */
  extendTo: (id: string, order: readonly string[]) => void
  selectWhole: (whole: WholeResult) => void
  clear: () => void
}

export const usePhoneSelection = create<PhoneSelectionState>((set, get) => ({
  caseId: null,
  ids: [],
  anchor: null,
  focus: null,
  whole: null,
  setCase: (caseId) => {
    if (get().caseId !== caseId) set({ caseId, ids: [], anchor: null, focus: null, whole: null })
  },
  focusOn: (id) => set({ focus: id }),
  toggle: (id) =>
    set((s) => ({
      whole: null,
      anchor: id,
      ids: s.ids.includes(id) ? s.ids.filter((x) => x !== id) : [...s.ids, id],
    })),
  extendTo: (id, order) =>
    set((s) => {
      const anchor = s.anchor ?? s.focus ?? id
      const a = order.indexOf(anchor)
      const b = order.indexOf(id)
      if (a < 0 || b < 0) return { ids: s.ids.includes(id) ? s.ids : [...s.ids, id], anchor: id, whole: null }
      const range = order.slice(Math.min(a, b), Math.max(a, b) + 1)
      const merged = [...s.ids]
      for (const x of range) if (!merged.includes(x)) merged.push(x)
      return { ids: merged, anchor, focus: id, whole: null }
    }),
  selectWhole: (whole) => set({ whole, ids: [], anchor: null }),
  clear: () => set({ ids: [], anchor: null, whole: null }),
}))

export function selectionCount(s: Pick<PhoneSelectionState, "ids" | "whole">): number {
  return s.whole ? s.whole.total : s.ids.length
}

/** The sentence every reader shows: "412 selected" or "All 186,787 messages selected". */
export function selectionSentence(s: Pick<PhoneSelectionState, "ids" | "whole">, noun = "records"): string {
  if (s.whole) return `All ${s.whole.total.toLocaleString("en-US")} ${s.whole.noun} selected`
  if (!s.ids.length) return "Nothing selected"
  return `${s.ids.length.toLocaleString("en-US")} ${s.ids.length === 1 ? noun.replace(/s$/, "") : noun} selected`
}

/** Key-triggered actions on more than this ask for confirmation first (07 4.9). */
export const CONFIRM_OVER = 5_000
