/** The workbench's address: a page of a document, optionally with a search or a kept quote open. */
export function textWorkbenchHref(
  caseId: string,
  evidenceId: string,
  place: { page?: number | null; q?: string | null; passage?: string | null } = {}
): string {
  const params = new URLSearchParams()
  if (place.page) params.set("page", String(place.page))
  if (place.q) params.set("q", place.q)
  if (place.passage) params.set("passage", place.passage)
  const search = params.toString()
  return `/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/text${search ? `?${search}` : ""}`
}

/** The document a kept quote's target id names: `<file id>:<text version>:<start>:<end>`. */
export function passageDocument(targetId: string): string {
  return targetId.split(":")[0] ?? ""
}

/** The workbench address of a kept quote. */
export function passageHref(caseId: string, targetId: string, anchor?: Record<string, unknown>): string {
  const page = typeof anchor?.page_number === "number" ? anchor.page_number : null
  return textWorkbenchHref(caseId, passageDocument(targetId), { page, passage: targetId })
}

/** What read a kept quote, as stored on it. */
export function passageReaderWords(anchor?: Record<string, unknown>): string | null {
  const reader = anchor?.reader as { words?: unknown } | undefined
  return typeof reader?.words === "string" ? reader.words : null
}
