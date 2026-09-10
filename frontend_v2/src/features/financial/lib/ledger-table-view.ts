export interface LedgerTableView {
  search: string
  currency: string
  direction: string
  proof: string
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
