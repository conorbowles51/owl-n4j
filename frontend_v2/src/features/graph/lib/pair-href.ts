/** Where a pair's edge opens: Conversations, Between A and B, with the same direct, copies-collapsed scope the edge
 * is counted with (07 J-3, a Graph edge start). */
export function pairConversationsHref(caseId: string, a: string, b: string): string {
  const q = new URLSearchParams({ tab: "people", people: `${a},${b}`, mode: "between" })
  return `/cases/${encodeURIComponent(caseId)}/conversations?${q.toString()}`
}
