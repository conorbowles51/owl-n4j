export function workDateLabel(
  value: string | null | undefined,
  now = new Date()
) {
  if (!value) return "No due date"
  const date = new Date(value.includes("T") ? value : `${value}T00:00:00`)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const formatted = date.toLocaleDateString([], {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
  const time = value.includes("T")
    ? ` · ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    : ""
  const overdue = value.includes("T") ? date < now : day < today
  return `${overdue ? "Overdue · " : day.getTime() === today.getTime() ? "Today · " : ""}${formatted}${time}`
}
