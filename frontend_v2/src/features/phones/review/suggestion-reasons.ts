import { type IdentitySuggestion } from "./identities.api"

export const REASON_WORDS: Record<string, string> = {
  same_card: "listed together on one contact card",
  owner_accounts: "the phone's own account",
  dossier_contact: "a contact detail on this person's dossier",
  name_support: "the same name",
  financial_identifier: "an account identifier on a statement",
}

/** The standard reason a link stores (07 4.11): built from the reasons shown. */
export function standardReason(s: IdentitySuggestion | undefined) {
  const kinds = [...new Set((s?.reasons ?? []).map((r) => r.reason))].sort().map((k) => REASON_WORDS[k] ?? k)
  return kinds.length ? `Linked on the review screen after seeing: ${kinds.join("; ")}` : "Linked on the review screen"
}
