import { useCallback } from "react"
import type { MapLocation } from "./use-map-data"

function escapeCSV(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

const COLUMNS: { label: string; get: (l: MapLocation) => string }[] = [
  { label: "Name",                 get: (l) => l.name },
  { label: "Type",                 get: (l) => l.type },
  { label: "Latitude",             get: (l) => String(l.latitude) },
  { label: "Longitude",            get: (l) => String(l.longitude) },
  { label: "Location (Formatted)", get: (l) => l.location_formatted ?? "" },
  { label: "Location (Raw)",       get: (l) => l.location_raw ?? "" },
  { label: "Geocoding Confidence", get: (l) => l.geocoding_confidence ?? "" },
  { label: "Date",                 get: (l) => l.date ?? "" },
  { label: "Summary",              get: (l) => l.summary ?? "" },
  { label: "Connections",          get: (l) =>
      (l.connections ?? []).map((c) => `${c.name} (${c.relationship})`).join("; ") },
]

export function useMapCsvExport() {
  const exportCSV = useCallback((locations: MapLocation[], caseId: string) => {
    const header = COLUMNS.map((c) => escapeCSV(c.label)).join(",")
    const rows = locations.map((loc) =>
      COLUMNS.map((c) => escapeCSV(c.get(loc))).join(",")
    )
    const csv = [header, ...rows].join("\n")
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `locations-${caseId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  return { exportCSV }
}
