export function parseFinancialDate(
  dateStr: string | null | undefined
): Date | null {
  if (!dateStr) return null
  const date = new Date(dateStr)
  return Number.isNaN(date.getTime()) ? null : date
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
  fallback = "—"
): string {
  const date = parseFinancialDate(dateStr)
  return date ? date.toLocaleDateString() : fallback
}
