/** Group names and kinds, and recent queries kept for this tab only (03 section 11.4). */
export const GROUP_NAMES: Record<string, string> = {
  messages: "Messages",
  calls: "Calls",
  emails: "Emails",
  people: "People and identifiers",
  records: "Other phone records",
  documents: "Documents and transcripts",
  machine_text: "Machine-generated text",
  payments: "Payments",
  production_numbers: "Production numbers",
}

/** The Conversations kinds behind each phone group, so "Show all" opens the same list the total counts. */
export const GROUP_KINDS: Record<string, string[]> = {
  messages: ["message", "chat_activity"],
  calls: ["call", "voicemail"],
  emails: ["email"],
}

const KEY = "loupe.search.recent"

/** Recent queries live in sessionStorage only and go when the tab closes; storage can be refused, so every access
 * is wrapped. */
export function recentQueries(): string[] {
  try {
    const v = JSON.parse(window.sessionStorage.getItem(KEY) ?? "[]")
    return Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, 8) : []
  } catch {
    return []
  }
}

export function rememberQuery(q: string) {
  if (!q.trim()) return
  try {
    const next = [q, ...recentQueries().filter((x) => x !== q)].slice(0, 8)
    window.sessionStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* storage refused: nothing is kept */
  }
}

/** The areas of the search by meaning, in the words a person uses. */
export const MEANING_AREAS: Record<string, string> = {
  phone_text: "Phone messages",
  ledger: "Payments",
  accounts: "Accounts",
  judgements: "Judgement calls",
  trails: "Saved money groups",
  statement_pages: "Statement pages",
  casework: "Notes, findings and theories",
  timeline: "Timeline",
  parties: "People and names on the phones",
  transcripts: "Transcripts and image text",
  documents: "Documents",
}
export const MEANING_WHY: Record<string, string> = { meaning: "by meaning", words: "by words", both: "by meaning and words" }
