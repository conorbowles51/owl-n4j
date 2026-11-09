export const STRIP_STEPS = 8

/** "14:05", or "Tue 14:05" for an older day. */
export function when(at: string, now = Date.now()): string {
  const d = new Date(at)
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  return now - d.getTime() < 20 * 3600_000 && new Date(now).getDate() === d.getDate()
    ? time
    : `${d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} ${time}`
}

/** Scrolls the strip sideways, and only the strip, so the step is fully visible. */
export function keepInView(ol: HTMLElement, el: HTMLElement) {
  const box = ol.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  if (r.right > box.right) ol.scrollLeft += r.right - box.right
  else if (r.left < box.left) ol.scrollLeft -= box.left - r.left
}
