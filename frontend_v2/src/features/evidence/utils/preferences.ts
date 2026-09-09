export interface EvidenceSort {
  sort_by: "name" | "date"
  sort_direction: "asc" | "desc"
}
interface Preferences {
  sortBy: EvidenceSort["sort_by"]
  sortDirection: EvidenceSort["sort_direction"]
  nameWidth: number | null
}
const key = "evidence-preferences-v1"
export function readEvidencePreferences(): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "{}")
    return {
      sortBy: value.sortBy === "date" ? "date" : "name",
      sortDirection: value.sortDirection === "desc" ? "desc" : "asc",
      nameWidth:
        typeof value.nameWidth === "number" && Number.isFinite(value.nameWidth)
          ? Math.max(180, Math.min(1600, value.nameWidth))
          : null,
    }
  } catch {
    return { sortBy: "name", sortDirection: "asc", nameWidth: null }
  }
}
export function saveEvidencePreferences({
  sortBy,
  sortDirection,
  nameWidth,
}: Preferences) {
  try {
    localStorage.setItem(
      key,
      JSON.stringify({ sortBy, sortDirection, nameWidth })
    )
  } catch {
    /* Storage may be disabled. */
  }
}
