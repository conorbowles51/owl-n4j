export function phonesEntryActive(pathname: string, caseId: string): boolean {
  const base = `/cases/${caseId}/`
  if (!pathname.startsWith(base)) return false
  const rest = pathname.slice(base.length)
  return /^(phones(\/|$)|conversations(\/|$)|phone-)/.test(rest) && !rest.startsWith("phones-prototype")
}
