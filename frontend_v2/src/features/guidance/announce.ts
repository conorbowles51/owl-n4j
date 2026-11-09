import { create } from "zustand"
import { nextSteps, type ActionFacts, type NextStepsCard } from "./next-steps"

/**
 * The one call a screen makes when an action completes: `announce(caseId, facts)`. The card waits in this store until
 * the person acts on it or dismisses it; NextStepsHost shows it where they are. Small on purpose: screens import it
 * without the host's code.
 */
export interface Announced extends NextStepsCard {
  id: string
  caseId: string
  at: number
}

const KEEP = 6
let counter = 0

interface NextStepsState {
  cards: Announced[]
  add: (card: Announced) => void
  dismiss: (id: string) => void
  clear: (caseId: string) => void
}

export const useNextSteps = create<NextStepsState>((set) => ({
  cards: [],
  add: (card) =>
    set((s) => ({
      // the same action announced twice in a row (a refetch, a second tab event) is one card
      cards: [card, ...s.cards.filter((c) => !(c.caseId === card.caseId && c.title === card.title))].slice(0, KEEP),
    })),
  dismiss: (id) => set((s) => ({ cards: s.cards.filter((c) => c.id !== id) })),
  clear: (caseId) => set((s) => ({ cards: s.cards.filter((c) => c.caseId !== caseId) })),
}))

/** Shows the next steps for a completed action; returns the card, or null when no step would lead anywhere. */
export function announce(caseId: string | null | undefined, facts: ActionFacts): Announced | null {
  caseId = caseId || caseOnScreen()
  if (!caseId) return null
  const card = nextSteps(caseId, facts)
  if (!card) return null
  counter += 1
  const out = { ...card, id: `${Date.now()}-${counter}`, caseId, at: Date.now() }
  useNextSteps.getState().add(out)
  return out
}

/** The case in the address bar, for a component that does not hold the case id itself. */
export function caseOnScreen(): string | null {
  const m = /^\/cases\/([^/?#]+)/.exec(window.location.pathname)
  return m ? decodeURIComponent(m[1]) : null
}
