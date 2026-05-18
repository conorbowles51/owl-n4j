import type { CellebriteRecord, PhoneReport } from "../../types"

export function isRecord(value: unknown): value is CellebriteRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

export function asText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback
  if (typeof value === "string") return value || fallback
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  if (Array.isArray(value)) return value.map((item) => asText(item)).filter(Boolean).join(", ")
  if (isRecord(value)) {
    const label = readText(value, ["display_name", "name", "label", "title", "key", "id"])
    return label || fallback
  }
  return fallback
}

export function readText(row: CellebriteRecord | null | undefined, keys: string[], fallback = ""): string {
  if (!row) return fallback
  for (const key of keys) {
    const text = asText(row[key])
    if (text) return text
  }
  return fallback
}

export function readNumber(row: CellebriteRecord | null | undefined, keys: string[], fallback = 0): number {
  if (!row) return fallback
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return fallback
}

export function readList(row: CellebriteRecord | null | undefined, keys: string[]): string[] {
  if (!row) return []
  for (const key of keys) {
    const value = row[key]
    if (Array.isArray(value)) {
      return value.map((item) => asText(item)).filter(Boolean)
    }
    const text = asText(value)
    if (text) return [text]
  }
  return []
}

export function compactDate(value: unknown): string {
  const text = asText(value)
  if (!text) return "-"
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function compactNumber(value: number | undefined | null): string {
  return new Intl.NumberFormat().format(value ?? 0)
}

export function truncate(value: string, length = 120): string {
  return value.length > length ? `${value.slice(0, length - 1)}...` : value
}

export function reportKey(report: PhoneReport): string {
  return report.report_key
}

export function reportTitle(report: PhoneReport): string {
  return (
    report.device_name_override ||
    report.device_name ||
    report.device_model ||
    report.phone_owner_name ||
    report.owner_name ||
    report.report_key
  )
}

export function itemKey(row: CellebriteRecord, fallback: string): string {
  return readText(row, ["key", "node_key", "id", "message_id", "thread_id", "file_id"], fallback)
}

export function selectedReportParams(keys: string[]): string[] | null {
  return keys.length > 0 ? keys : null
}
