import type { StripDay } from "./TimeStrip"

// One formatter for every call: toLocaleDateString with options builds a new Intl.DateTimeFormat on each call, and the
// time strip names every day of the scope (one title per bar) on each render.
const DAY_WORDS = new Intl.DateTimeFormat("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })

export function dayWords(date: string): string {
  const d = new Date(`${date}T12:00:00Z`)
  // format() throws on an invalid date where toLocaleDateString answered "Invalid Date"; keep that answer.
  return Number.isNaN(d.getTime()) ? "Invalid Date" : DAY_WORDS.format(d)
}

export function stripSummary(days: StripDay[], noun: string): string {
  const withData = days.filter((d) => d.count !== null)
  const total = withData.reduce((s, d) => s + (d.count ?? 0), 0)
  const noData = days.length - withData.length
  const quiet = withData.filter((d) => d.count === 0).length
  return `${total.toLocaleString("en-US")} ${noun} over ${days.length} days; ${quiet} days with none; ${noData} days with no data`
}
