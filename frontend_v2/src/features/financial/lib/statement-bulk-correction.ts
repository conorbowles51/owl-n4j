import type { StatementDraft } from "./statement-review-draft"

export type ReviewEdit = StatementDraft["rows"][number]
export type CorrectionAction =
  | "exclude"
  | "include"
  | "switch"
  | "date"
  | "date_year"
  | "counterparty"

function completePrintedDate(printed: string, closing: string) {
  const match = /^(\d{1,2})\/(\d{1,2})$/.exec(printed)
  if (!match)
    throw Error(
      "A selected row has no readable day and month. Leave it for individual review."
    )
  const endYear = Number(closing.slice(0, 4))
  const endMonth = Number(closing.slice(5, 7))
  const month = Number(match[1]),
    day = Number(match[2])
  const year = endYear - (endMonth === 1 && month === 12 ? 1 : 0)
  const date = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`
  if (
    year < 1 ||
    ![endMonth, ((endMonth + 10) % 12) + 1].includes(month) ||
    Number.isNaN(Date.parse(date)) ||
    new Date(date).toISOString().slice(0, 10) !== date ||
    date > closing
  )
    throw Error(
      "A printed day and month does not fit this closing date. Check the selected rows against the PDF."
    )
  return date
}

export function previewCorrections(
  rows: ReviewEdit[],
  selected: ReadonlySet<string>,
  action: CorrectionAction,
  value: string,
  reason: string,
  printedDates?: ReadonlyMap<string, string>
) {
  if (!selected.size) throw Error("Select the transactions to correct.")
  if (reason.length > 2000)
    throw Error("Keep the reason under 2,000 characters.")
  if (
    (action === "date" || action === "date_year") &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number(value.slice(0, 4)) < 1 ||
      Number.isNaN(Date.parse(value)) ||
      new Date(value).toISOString().slice(0, 10) !== value)
  )
    throw Error(
      action === "date_year"
        ? "Enter a valid statement closing date."
        : "Enter a valid transaction date."
    )
  if (action === "counterparty" && (!value.trim() || value.length > 4096))
    throw Error("Enter the person or business name (up to 4,096 characters).")
  const changes: {
    before: ReviewEdit
    after: ReviewEdit
    printedDate?: string
  }[] = []
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
      case "date_year":
        if (row.date || row.date_unprinted) continue
        patch = {
          date: completePrintedDate(printedDates?.get(row.id) || "", value),
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
    const dateReason =
      action === "date_year"
        ? `Year completed using statement closing date ${value}; printed day/month ${printedDates?.get(row.id)}.`
        : ""
    const explanation = [row.reason.trim(), reason.trim(), dateReason]
      .filter(Boolean)
      .join("\n")
    if (explanation.length > 4096)
      throw Error(
        "A selected row already has a long correction history. Update its reason individually first."
      )
    changes.push({
      before: row,
      after: { ...row, ...patch, reason: explanation },
      ...(action === "date_year"
        ? { printedDate: printedDates?.get(row.id) }
        : {}),
    })
  }
  if (found !== selected.size)
    throw Error("The selected rows changed. Select them again.")
  if (!changes.length)
    throw Error("The selected rows already have these values.")
  return changes
}

export function correctionValue(
  row: ReviewEdit,
  action: CorrectionAction,
  printedDates?: ReadonlyMap<string, string>
) {
  if (action === "exclude" || action === "include")
    return row.excluded ? "Excluded" : "Included"
  if (action === "switch")
    return row.direction === "credit"
      ? "Credit"
      : row.direction === "debit"
        ? "Debit"
        : "Not set"
  return action === "date" || action === "date_year"
    ? row.date ||
        (row.date_unprinted
          ? "Not printed"
          : action === "date_year" && printedDates?.has(row.id)
            ? `${printedDates.get(row.id)} (year missing)`
            : "Not set")
    : row.counterparty || "Not set"
}
