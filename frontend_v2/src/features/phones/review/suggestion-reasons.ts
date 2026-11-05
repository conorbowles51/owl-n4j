import { type IdentitySuggestion } from "./identities.api"

export const REASON_WORDS: Record<string, string> = {
  same_card: "listed together on one contact card",
  owner_accounts: "the phone's own account",
  dossier_contact: "a contact detail on this person's dossier",
  name_support: "the same name",
  financial_identifier: "an account identifier on a statement",
  name_only: "the same name only (nothing else links them)",
  number_change: "a possible number change, one stopping as the other starts",
}

export type LinkOrigin = "review" | "dossier" | "number_switching"

const ORIGIN_WORDS: Record<LinkOrigin, string> = {
  review: "on the review screen",
  dossier: "on Phone identities in Dossiers",
  number_switching: "on Number switching",
}

/** The standard reason a link stores (07 4.11): the screen and the reasons shown, as
 * services/phone/identity_decisions.standard_link_reason words them. */
export function standardReason(s: IdentitySuggestion | undefined, origin: LinkOrigin = "review") {
  const where = `Linked ${ORIGIN_WORDS[origin]}`
  const kinds = [...new Set((s?.reasons ?? []).map((r) => r.reason))].sort().map((k) => REASON_WORDS[k] ?? k)
  return kinds.length ? `${where} after seeing: ${kinds.join("; ")}` : where
}
