import { useCallback } from "react"
import type { MapLocation } from "./use-map-data"

function escapeCSV(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

export function useMapCsvExport() {
  const exportCSV = useCallback((locations: MapLocation[], caseId: string) => {
    const header = [
      "Name",
      "Type",
      "Latitude",
      "Longitude",
      "Location (Formatted)",
      "Location (Raw)",
      "Geocoding Confidence",
      "Date",
      "Summary",
      "Connections",
    ].join(",")

    const rows = locations.map((l) =>
      [
        l.name,
        l.type,
        String(l.latitude),
        String(l.longitude),
        l.location_formatted ?? "",
        l.location_raw ?? "",
        l.geocoding_confidence ?? "",
        l.date ?? "",
        l.summary ?? "",
        (l.connections ?? [])
          .map((c) => `${c.name} (${c.relationship})`)
          .join("; "),
      ]
        .map(escapeCSV)
        .join(",")
    )

    const csv = [header, ...rows].join("\n")
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `locations-${caseId}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }, [])

  return { exportCSV }
}
