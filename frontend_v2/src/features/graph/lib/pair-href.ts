/** Where a pair's edge opens: Conversations, Between A and B, with the same direct, copies-collapsed scope the edge
 * is counted with (07 J-3, a Graph edge start). */
export function pairConversationsHref(caseId: string, a: string, b: string, window?: { from: string; to: string } | null): string {
  const q = new URLSearchParams({ tab: "people", people: `${a},${b}`, mode: "between" })
  // the Graph time slider's window (03 14.3, R-3): Conversations counts the same window, records with a time only
  if (window) { q.set("from", window.from); q.set("to", window.to); q.set("notime", "0") }
  return `/cases/${encodeURIComponent(caseId)}/conversations?${q.toString()}`
}
