export interface LedgerTableView {
  source_document_id?: string
  import_batch_id?: string
  import_batch_revision?: string
  search: string
  currency: string
  direction: string
  proof: string
  minimum_minor?: string
  maximum_minor?: string
  sort: string
}
export function sameTableView(header: string | null, view?: LedgerTableView) {
  if (!view) return !header
  try {
    const parsed = JSON.parse(header ?? "null")
    return (
      parsed !== null &&
      Object.entries(view).every(([key, value]) => parsed[key] === value)
    )
  } catch {
    return false
  }
}
