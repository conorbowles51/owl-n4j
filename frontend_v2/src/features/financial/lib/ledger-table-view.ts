export interface LedgerTableView {
  profile_id?: string
  profile_group?: string
  from_names?: string[]
  to_names?: string[]
  perspective_names?: string[]
  analysis_group?: string
  analysis_period?: string
  analysis_direction?: "credit" | "debit"
  analysis_categories?: string[]
  flow_party?: string
  flow_kind?: string
  category?: string
  account_id?: string
  account_holder?: string
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
      Object.entries(view).every(
        ([key, value]) => JSON.stringify(parsed[key]) === JSON.stringify(value)
      )
    )
  } catch {
    return false
  }
}
