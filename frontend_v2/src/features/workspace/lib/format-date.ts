export function formatWorkspaceDate(date?: string | null) {
  if (!date) return ""

  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(date)
  const parsed = dateOnly ? new Date(`${date}T00:00:00`) : new Date(date)
  if (Number.isNaN(parsed.getTime())) return date

  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function formatWorkspaceDateTime(date?: string | null) {
  if (!date) return ""

  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(date)
  const parsed = dateOnly ? new Date(`${date}T00:00:00`) : new Date(date)
  if (Number.isNaN(parsed.getTime())) return date

  if (dateOnly) {
    return formatWorkspaceDate(date)
  }

  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
