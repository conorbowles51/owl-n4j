/** rec://<record_uid>[#<field_path>] citations to phone records (03 section 11.5). */
const UID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseRecordHref(href: string | undefined | null): { recordUid: string; fieldPath: string | null } | null {
  if (!href?.startsWith("rec://")) return null
  const rest = href.slice("rec://".length)
  const hash = rest.indexOf("#")
  const uid = (hash >= 0 ? rest.slice(0, hash) : rest).replace(/\/$/, "")
  if (!UID.test(uid)) return null
  let field: string | null = hash >= 0 ? rest.slice(hash + 1) : null
  if (field) {
    try {
      field = decodeURIComponent(field)
    } catch {
      /* keep it as written */
    }
  }
  return { recordUid: uid.toLowerCase(), fieldPath: field || null }
}

/** One phone record by id: the route finds its phone and opens the record panel. */
export function recordPath(caseId: string, recordUid: string, fieldPath?: string | null): string {
  return `/cases/${encodeURIComponent(caseId)}/records/${encodeURIComponent(recordUid)}${fieldPath ? `#${encodeURIComponent(fieldPath)}` : ""}`
}
