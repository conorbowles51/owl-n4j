import { useEffect, useRef, useState } from "react"

export interface RectLike {
  top: number
  height: number
}

/**
 * Maps a pinned section's bounding rect to 0..1.
 *
 * A pinned section is taller than the viewport; the sticky child stays fixed while the
 * extra height scrolls past. Progress is how far through that extra height we are.
 */
export function progressFromRect(rect: RectLike, viewportHeight: number): number {
  const scrollable = rect.height - viewportHeight
  if (scrollable <= 0) return 0
  const travelled = -rect.top
  return Math.min(1, Math.max(0, travelled / scrollable))
}

/** Subscribes to scroll and returns the section's 0..1 progress. */
export function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    let frame = 0
    const update = () => {
      frame = 0
      const rect = node.getBoundingClientRect()
      setProgress(progressFromRect(rect, window.innerHeight))
    }
    const onScroll = () => {
      if (frame) return
      frame = requestAnimationFrame(update)
    }

    update()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onScroll, { passive: true })
    return () => {
      if (frame) cancelAnimationFrame(frame)
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onScroll)
    }
  }, [])

  return { ref, progress }
}

/**
 * Maps overall progress onto one segment of a sequence, returning 0..1 within it.
 * Lets a beat say "this happens between 30% and 60%" without arithmetic at each site.
 */
export function segment(progress: number, start: number, end: number): number {
  if (end <= start) return progress >= end ? 1 : 0
  return Math.min(1, Math.max(0, (progress - start) / (end - start)))
}
