import type { StripDay } from "./TimeStrip"

export function dayWords(date: string): string {
  const d = new Date(`${date}T12:00:00Z`)
  return d.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
}

export function stripSummary(days: StripDay[], noun: string): string {
  const withData = days.filter((d) => d.count !== null)
  const total = withData.reduce((s, d) => s + (d.count ?? 0), 0)
  const noData = days.length - withData.length
  const quiet = withData.filter((d) => d.count === 0).length
  return `${total.toLocaleString("en-US")} ${noun} over ${days.length} days; ${quiet} days with none; ${noData} days with no data`
}
