export function workDateLabel(
  value: string | null | undefined,
  now = new Date(),
  completed = false
) {
  if (!value) return "No due date"
  const date = new Date(value.includes("T") ? value : `${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return "Date unavailable"
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
  return `${!completed && overdue ? "Overdue · " : !completed && day.getTime() === today.getTime() ? "Today · " : ""}${formatted}${time}`
}

export function workDateGroup(
  value: string | null | undefined,
  completed: boolean,
  now = new Date()
) {
  if (completed) return "Completed"
  if (!value) return "No due date"
  const date = new Date(value.includes("T") ? value : `${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return "No due date"
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  if (value.includes("T") ? date < now : day < today) return "Overdue"
  return day.getTime() === today.getTime() ? "Today" : "Upcoming"
}
