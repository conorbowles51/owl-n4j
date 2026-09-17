import type { StatementDraft } from "./statement-review-draft"

export type ReviewEdit = StatementDraft["rows"][number]
export type CorrectionAction =
  | "exclude"
  | "include"
  | "switch"
  | "date"
  | "counterparty"

export function previewCorrections(
  rows: ReviewEdit[],
  selected: ReadonlySet<string>,
  action: CorrectionAction,
  value: string,
  reason: string
) {
  if (!selected.size) throw Error("Select the transactions to correct.")
  if (!reason.trim()) throw Error("Enter the reason for these corrections.")
  if (reason.length > 2000)
    throw Error("Keep the reason under 2,000 characters.")
  if (
    action === "date" &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number(value.slice(0, 4)) < 1 ||
      Number.isNaN(Date.parse(value)) ||
      new Date(value).toISOString().slice(0, 10) !== value)
  )
    throw Error("Enter a valid transaction date.")
  if (action === "counterparty" && (!value.trim() || value.length > 4096))
    throw Error("Enter the person or business name (up to 4,096 characters).")
  const changes: { before: ReviewEdit; after: ReviewEdit }[] = []
  let found = 0
  for (const row of rows) {
    if (!selected.has(row.id)) continue
    found++
    let patch: Partial<ReviewEdit>
    switch (action) {
      case "include":
        patch = { excluded: false }
        break
      case "exclude":
        patch = { excluded: true }
        break
      case "date":
        patch = {
          date: value,
          ...(row.date_unprinted ? { date_unprinted: false } : {}),
        }
        break
      case "counterparty":
        patch = { counterparty: value.trim() }
        break
      case "switch":
        if (!row.direction)
          throw Error(
            "A selected row has no credit or debit to switch. Correct it individually first."
          )
        patch = { direction: row.direction === "credit" ? "debit" : "credit" }
        break
    }
    if (
      Object.entries(patch).every(
        ([key, next]) => row[key as keyof ReviewEdit] === next
      )
    )
      continue
    const explanation = [row.reason.trim(), reason.trim()]
      .filter(Boolean)
      .join("\n")
    if (explanation.length > 4096)
      throw Error(
        "A selected row already has a long correction history. Update its reason individually first."
      )
    changes.push({
      before: row,
      after: { ...row, ...patch, reason: explanation },
    })
  }
  if (found !== selected.size)
    throw Error("The selected rows changed. Select them again.")
  if (!changes.length)
    throw Error("The selected rows already have these values.")
  return changes
}

export function correctionValue(row: ReviewEdit, action: CorrectionAction) {
  if (action === "exclude" || action === "include")
    return row.excluded ? "Excluded" : "Included"
  if (action === "switch")
    return row.direction === "credit"
      ? "Credit"
      : row.direction === "debit"
        ? "Debit"
        : "Not set"
  return action === "date"
    ? row.date || (row.date_unprinted ? "Not printed" : "Not set")
    : row.counterparty || "Not set"
}
