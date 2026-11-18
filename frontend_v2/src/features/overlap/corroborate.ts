import { openCorroborate, type CorroborateRequest } from "@/features/leads/open"

export type CorroborateAsk = CorroborateRequest

/**
 * "Corroborate this" from an overlap view: lx-leads' Corroborate panel opens over the page with these records (they
 * also join the case-wide Corroborate selection). Nothing is saved until a question is asked there.
 */
export function askCorroborate(ask: CorroborateAsk) {
  openCorroborate(ask)
}
