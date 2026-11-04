/** The Conversations view for one phone over the time its positions were in the area (07 XF-6). */
export function areaConversationsHref(caseId: string, extractionId: string, from: string | null, to: string | null) {
  const q = new URLSearchParams({ phones: extractionId })
  if (from) q.set("from", from)
  if (to) q.set("to", to)
  q.set("notime", "0")
  return `/cases/${encodeURIComponent(caseId)}/conversations?${q.toString()}`
}

