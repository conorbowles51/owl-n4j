export const dateRoles = ["date", "booking_date", "value_date"] as const
export type DateRole = (typeof dateRoles)[number]
export const dateLabels: Record<DateRole, string> = {
  date: "Transaction date",
  booking_date: "Posting date",
  value_date: "Value date",
}

export function sourceDateRoles(fields: Record<string, string>): DateRole[] {
  const roles = dateRoles.filter(
    (role) => fields[role] || `${role}_column` in fields
  )
  return roles.length ? roles : ["date"]
}

export function primaryDateRole(fields: Record<string, string>): DateRole {
  return dateRoles.find((role) => fields[role]) ?? sourceDateRoles(fields)[0]
}

export function additionalDateValues(fields: Record<string, string>) {
  const primary = primaryDateRole(fields)
  return Object.fromEntries(
    sourceDateRoles(fields)
      .filter((role) => role !== primary)
      .map((role) => [role, fields[role] ?? ""])
  ) as Partial<Record<DateRole, string>>
}
