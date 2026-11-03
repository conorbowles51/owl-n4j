/** Where a keyword list's total for one phone, term and group opens: every hit of that search on that phone, each
 * opening the record in context (03 section 11.2; 07 J-6 step 3). */
export function hitsPath(caseId: string, term: string, group: string, phone: string, exact: boolean) {
  const p = new URLSearchParams({ q: term, group, phones: phone })
  if (exact) p.set("exact", "1")
  return `/cases/${encodeURIComponent(caseId)}/search?${p}`
}
