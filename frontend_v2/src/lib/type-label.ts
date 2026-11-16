/**
 * The readable name of a graph node type, for everything the Graph shows (legend, type filter, node badges).
 * The Graph reads types lowercased ("financialtransaction"), so the word breaks are restored here: one mapping for
 * the types the case database has, and for any other type a split into known words, never a run-together name.
 */
const KNOWN: Record<string, string> = {
  financialtransaction: "Financial transaction",
  financialstatementperiod: "Statement period",
  financialinstrument: "Financial instrument",
  financialaccount: "Financial account",
  financialparty: "Financial party",
  physicalevidence: "Physical evidence",
  phoneidentity: "Phone identity",
  phoneextraction: "Phone extraction",
  phonecall: "Phone call",
  phonereport: "Phone report",
  phonenumber: "Phone number",
  phonegroup: "Phone group",
  celltower: "Cell tower",
  wirelessnetwork: "Wireless network",
  deviceevent: "Device event",
  appsession: "App session",
  searcheditem: "Searched item",
  visitedpage: "Visited page",
  digitalaccount: "Digital account",
  networkidentifier: "Network identifier",
  cyberidentity: "Online identity",
  legalaction: "Legal action",
  deleteditem: "Deleted item",
  realestatepurchase: "Real estate purchase",
}

// words an unknown run-together type is split into, longest first
const WORDS = [
  "communication", "organization", "transaction", "identifier", "instrument", "extraction", "statement", "evidence",
  "financial", "identity", "location", "physical", "property", "document", "purchase", "wireless", "searched",
  "deleted", "digital", "account", "network", "address", "company", "invoice", "payment", "session", "message",
  "meeting", "vehicle", "visited", "website", "transfer", "person", "period", "report", "device", "wallet", "crypto",
  "number", "social", "action", "estate", "legal", "media", "phone", "group", "party", "event", "email", "asset",
  "cyber", "tower", "check", "money", "item", "page", "cell", "call", "bank", "card", "real", "case", "app",
].sort((a, b) => b.length - a.length)

function split(word: string): string[] | null {
  if (!word) return []
  for (const w of WORDS) {
    if (word.startsWith(w)) {
      const rest = split(word.slice(w.length))
      if (rest) return [w, ...rest]
    }
  }
  return null
}

const sentence = (words: string[]) => {
  const s = words.filter(Boolean).join(" ").toLowerCase()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function typeLabel(type: string): string {
  const raw = (type ?? "").trim()
  if (!raw) return "Other"
  const flat = raw.replace(/[\s_-]+/g, "").toLowerCase()
  if (KNOWN[flat]) return KNOWN[flat]
  // camelCase, snake_case or spaced words keep their own breaks
  if (/[a-z][A-Z]|[\s_-]/.test(raw)) return sentence(raw.replace(/([a-z])([A-Z])/g, "$1 $2").split(/[\s_-]+/))
  return sentence(split(flat) ?? [flat])
}

/** The plural for counts in sentences ("all 12 phone identities"). */
export function typeLabelPlural(type: string): string {
  const one = typeLabel(type).toLowerCase()
  if (/person$/.test(one)) return `${one.slice(0, -6)}people`
  if (/(s|x|ch|sh)$/.test(one)) return `${one}es`
  if (/[^aeiou]y$/.test(one)) return `${one.slice(0, -1)}ies`
  if (/evidence$/.test(one)) return one
  return `${one}s`
}
