/** Where a phone address with a query lands (07 4.13): a thread or record in Conversations, a person on its people tab. */
export function phoneQueryTarget(caseId: string, search: string): string | null {
  const q = new URLSearchParams(search)
  const base = `/cases/${encodeURIComponent(caseId)}/conversations`
  const thread = q.get("thread")
  if (thread) return `${base}?thread=${encodeURIComponent(thread)}`
  const record = q.get("record")
  if (record) return `${base}?record=${encodeURIComponent(record)}`
  const identity = q.get("identity")
  if (identity) return `${base}?tab=people&people=${encodeURIComponent(identity)}`
  const selection = q.get("selection")
  if (selection) return `${base}?selection=${encodeURIComponent(selection)}`
  return null
}
