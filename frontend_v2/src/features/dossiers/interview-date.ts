export type InterviewDatePrecision =
  | "unknown"
  | "year"
  | "month"
  | "day"
  | "time"

export function datePrecision(value?: string | null): InterviewDatePrecision {
  if (!value) return "unknown"
  if (value.length === 4) return "year"
  if (value.length === 7) return "month"
  return value.includes("T") ? "time" : "day"
}

export function formatInterviewDate(value?: string | null) {
  const precision = datePrecision(value)
  if (precision === "unknown") return "Date not recorded"
  if (precision === "year") return value!
  if (precision === "month")
    return new Intl.DateTimeFormat(undefined, {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${value}-01T00:00:00Z`))
  if (precision === "day")
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(`${value}T00:00:00Z`))
  const parsed = new Date(value!)
  return Number.isNaN(parsed.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed)
}

export function localInterviewTime(value?: string | null) {
  if (!value || !value.includes("T")) return value ?? ""
  const parsed = new Date(value)
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}
