/** Words for the Graph's People in contact panel (lx-graphclarity B). */
const fmt = (n: number) => n.toLocaleString("en-US")
const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`

/** A pair's contact in words, zero counts left out: "43 messages and 4 calls", "1 email". */
export function contactWords(messages: number, calls: number, emails: number): string {
  const parts = [
    messages ? plural(messages, "message", "messages") : "",
    calls ? plural(calls, "call", "calls") : "",
    emails ? plural(emails, "email", "emails") : "",
  ].filter(Boolean)
  if (!parts.length) return "No contact"
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`
}

/** The closed panel's one line: what it holds and what it is for. */
export function contactSummary(n: number): string {
  return n === 1
    ? "2 people on the phones messaged, called or emailed each other. See how often"
    : `${fmt(n)} pairs of people on the phones messaged, called or emailed each other. See who and how often`
}
