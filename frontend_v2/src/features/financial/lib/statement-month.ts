/** Calendar dates, independent of browser timezone. Never infer a month from a filename. */
export function statementMonth(value: string) {
  const match = /^(\d{4})-(\d{2})$/.exec(value)
  if (!match) return null
  const year = Number(match[1]),
    month = Number(match[2])
  if (year < 1 || month < 1 || month > 12) return null
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
    month - 1
  ]
  return { period_start: `${value}-01`, period_end: `${value}-${days}` }
}
