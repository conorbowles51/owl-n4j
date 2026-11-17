/**
 * "Select all N" for a filtered file list (lx-corroselect C). The list shows 250 files a page; this reads every page of
 * the same filter so the selection is the whole result, never the page. A short read (the server stopped early) is
 * reported, not presented as whole.
 */
export interface FilePage {
  files: { id: string; original_filename?: string }[]
  file_total: number
}

export async function readWholeResult(
  fetchPage: (offset: number, limit: number) => Promise<FilePage>,
  pageSize = 250,
): Promise<{ files: { id: string; name?: string }[]; total: number; complete: boolean }> {
  const files: { id: string; name?: string }[] = []
  const seen = new Set<string>()
  let total = 0
  for (let offset = 0; ; offset += pageSize) {
    const page = await fetchPage(offset, pageSize)
    total = page.file_total
    for (const f of page.files) {
      if (!seen.has(f.id)) {
        seen.add(f.id)
        files.push({ id: f.id, name: f.original_filename })
      }
    }
    if (page.files.length === 0 || offset + pageSize >= total) break
  }
  return { files, total, complete: files.length >= total }
}
