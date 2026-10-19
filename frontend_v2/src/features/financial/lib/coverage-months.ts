/** Calendar-month coverage within the saved statement range, never an assumed case range. */
export function coverageMonths(windows: { start: string; end: string }[]) {
  const ranges = windows
    .map(({ start, end }) => [Date.parse(start), Date.parse(end)] as const)
    .filter(
      ([start, end]) =>
        Number.isFinite(start) && Number.isFinite(end) && start <= end
    )
    .sort((a, b) => a[0] - b[0])
  if (!ranges.length) return null
  const start = ranges[0][0],
    end = Math.max(...ranges.map((range) => range[1]))
  const months: { month: string; status: "covered" | "partial" | "missing" }[] =
    []
  const cursor = new Date(start)
  cursor.setUTCDate(1)
  while (cursor.getTime() <= end) {
    const month = cursor.toISOString().slice(0, 7)
    const first = Math.max(start, cursor.getTime())
    cursor.setUTCMonth(cursor.getUTCMonth() + 1)
    const last = Math.min(end, cursor.getTime() - 86400000)
    let through = first - 86400000,
      any = false,
      gap = false
    for (const [a, b] of ranges) {
      const left = Math.max(a, first),
        right = Math.min(b, last)
      if (left > right) continue
      any = true
      if (left > through + 86400000) gap = true
      through = Math.max(through, right)
    }
    months.push({
      month,
      status: !any ? "missing" : gap || through < last ? "partial" : "covered",
    })
  }
  return {
    start: new Date(start).toISOString().slice(0, 10),
    end: new Date(end).toISOString().slice(0, 10),
    months,
  }
}
