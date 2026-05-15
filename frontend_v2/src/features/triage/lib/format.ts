import type { TriageStage } from "../triage.types"

export function formatBytes(bytes?: number | null) {
  if (!bytes || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB", "PB"]
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatDateTime(value?: string | null) {
  if (!value) return ""
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed)
}

export function normalizeCategoryRows(
  input?: Record<string, unknown> | Array<Record<string, unknown>>
) {
  if (!input) return []
  if (Array.isArray(input)) {
    return input.map((row) => ({
      category: String(row.category ?? row.label ?? "other"),
      count: Number(row.count ?? row.value ?? 0),
      total_size: Number(row.total_size ?? row.size ?? 0),
      top_extensions: Array.isArray(row.top_extensions)
        ? row.top_extensions.map(String)
        : [],
    }))
  }
  return Object.entries(input).map(([category, count]) => ({
    category,
    count: Number(count ?? 0),
    total_size: 0,
    top_extensions: [],
  }))
}

export function stageProgress(stage?: Pick<TriageStage, "files_total" | "files_processed"> | null) {
  if (!stage?.files_total) return stage?.files_processed ? 100 : 0
  return Math.min(100, Math.round(((stage.files_processed ?? 0) / stage.files_total) * 100))
}

export function isRunningStatus(
  status?: string,
  options: { includeProcessing?: boolean } = {}
) {
  const includeProcessing = options.includeProcessing ?? true
  return (
    status === "running" ||
    status === "scanning" ||
    status === "classifying" ||
    status === "profiling" ||
    (includeProcessing && status === "processing")
  )
}
