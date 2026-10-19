export function parseFinancialDate(
  dateStr: string | null | undefined
): Date | null {
  if (typeof dateStr !== "string") return null
  const text = dateStr.trim()
  if (
    !/^\d{4}-\d{2}-\d{2}(?:[T ](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,9})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?$/.test(
      text
    )
  )
    return null
  const day = text.slice(0, 10)
  const date = new Date(`${day}T00:00:00Z`)
  // Keep the recorded calendar day, independent of browser timezone. Do not
  // invent a day/year or normalize impossible dates such as 30 February.
  return date.getUTCFullYear() > 0 &&
    Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10) === day
    ? date
    : null
}

export function financialDateDay(
  dateStr: string | null | undefined
): string | null {
  return parseFinancialDate(dateStr)?.toISOString().slice(0, 10) ?? null
}

export function isValidFinancialDate(
  dateStr: string | null | undefined
): boolean {
  return parseFinancialDate(dateStr) !== null
}

export function getFinancialDateTimestamp(
  dateStr: string | null | undefined
): number | null {
  const date = parseFinancialDate(dateStr)
  return date ? date.getTime() : null
}

export function formatFinancialDate(
  dateStr: string | null | undefined,
  fallback = "Not recorded"
): string {
  const date = parseFinancialDate(dateStr)
  return date
    ? date.toISOString().slice(0, 10)
    : dateStr?.trim()
      ? `${dateStr.trim()} (check date)`
      : fallback
}
