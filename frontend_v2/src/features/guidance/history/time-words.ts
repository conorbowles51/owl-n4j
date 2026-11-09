export const STRIP_STEPS = 8

/** "14:05", or "Tue 14:05" for an older day. */
export function when(at: string, now = Date.now()): string {
  const d = new Date(at)
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  return now - d.getTime() < 20 * 3600_000 && new Date(now).getDate() === d.getDate()
    ? time
    : `${d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} ${time}`
}
